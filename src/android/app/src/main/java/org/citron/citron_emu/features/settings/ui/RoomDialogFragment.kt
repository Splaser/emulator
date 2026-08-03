// SPDX-License-Identifier: GPL-2.0-or-later

package org.citron.citron_emu.features.settings.ui

import android.app.Dialog
import android.os.Bundle
import androidx.appcompat.app.AlertDialog
import androidx.fragment.app.DialogFragment
import androidx.fragment.app.activityViewModels
import androidx.lifecycle.lifecycleScope
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.citron.citron_emu.NativeLibrary
import org.citron.citron_emu.R
import org.citron.citron_emu.databinding.DialogMultiplayerRoomBinding

class RoomDialogFragment : DialogFragment() {
    private lateinit var binding: DialogMultiplayerRoomBinding
    private var updateJob: Job? = null
    private val chatLines = ArrayDeque<String>()
    private val settingsViewModel: SettingsViewModel by activityViewModels()

    override fun onCreateDialog(savedInstanceState: Bundle?): Dialog {
        binding = DialogMultiplayerRoomBinding.inflate(layoutInflater)
        val hosting = NativeLibrary.isHostingRoom()
        return MaterialAlertDialogBuilder(requireContext())
            .setTitle(R.string.room_title)
            .setView(binding.root)
            .setNegativeButton(
                if (hosting) R.string.room_close_hosted else R.string.room_leave,
                null
            )
            .setPositiveButton(R.string.close, null)
            .create()
            .also { dialog ->
                dialog.setOnShowListener {
                    dialog.getButton(AlertDialog.BUTTON_NEGATIVE).setOnClickListener {
                        disconnect(hosting)
                    }
                    binding.roomSend.setOnClickListener { sendMessage() }
                    binding.roomMessage.setOnEditorActionListener { _, _, _ ->
                        sendMessage()
                        true
                    }
                    startUpdating(dialog, hosting)
                }
            }
    }

    override fun onDestroyView() {
        updateJob?.cancel()
        super.onDestroyView()
    }

    private fun startUpdating(dialog: AlertDialog, hosting: Boolean) {
        updateJob?.cancel()
        updateJob = lifecycleScope.launch {
            var wasConnected = false
            while (currentCoroutineContext().isActive) {
                val state = withContext(Dispatchers.IO) {
                    NativeLibrary.getRoomConnectionState()
                }
                if (MultiplayerRoomState.isConnected(state)) {
                    wasConnected = true
                    updateRoomContent()
                } else if (wasConnected || state == MultiplayerRoomState.IDLE) {
                    val error = awaitMultiplayerError()
                    binding.roomStatus.text = if (error >= 0) {
                        multiplayerErrorText(requireContext(), error)
                    } else {
                        getString(R.string.direct_connect_disconnected)
                    }
                    binding.roomMessage.isEnabled = false
                    binding.roomSend.isEnabled = false
                    dialog.getButton(AlertDialog.BUTTON_NEGATIVE).isEnabled = hosting
                    settingsViewModel.setShouldReloadSettingsList(true)
                    return@launch
                } else {
                    binding.roomStatus.setText(R.string.direct_connect_connecting)
                }
                delay(ROOM_UPDATE_INTERVAL_MS)
            }
        }
    }

    private suspend fun updateRoomContent() {
        val snapshot = withContext(Dispatchers.IO) {
            Triple(
                NativeLibrary.getRoomInfo(),
                NativeLibrary.getRoomMembers(),
                NativeLibrary.drainRoomEvents()
            )
        }
        val info = snapshot.first
        if (info.size >= 6) {
            binding.roomSummary.text = getString(
                R.string.room_summary,
                info[0],
                info[3],
                info[4]
            )
            binding.roomDescription.text = info[1].ifBlank {
                getString(R.string.room_no_description)
            }
            binding.roomStatus.text = if (info[2].isBlank()) {
                getString(R.string.room_connected_port, info[5])
            } else {
                getString(R.string.room_connected_game, info[2], info[5])
            }
        }

        binding.roomMembers.text = snapshot.second.toList().chunked(MEMBER_FIELD_COUNT)
            .filter { it.size == MEMBER_FIELD_COUNT }
            .joinToString("\n") { member ->
                val identity = if (member[1].isBlank() || member[1] == member[0]) {
                    member[0]
                } else {
                    "${member[0]} (${member[1]})"
                }
                if (member[2].isBlank()) {
                    identity
                } else if (member[3].isBlank()) {
                    "$identity — ${member[2]}"
                } else {
                    "$identity — ${member[2]} (${member[3]})"
                }
            }

        snapshot.third.toList().chunked(EVENT_FIELD_COUNT)
            .filter { it.size == EVENT_FIELD_COUNT }
            .forEach(::appendEvent)
    }

    private fun appendEvent(event: List<String>) {
        val displayName = if (event[2].isBlank() || event[2] == event[1]) {
            event[1]
        } else {
            "${event[1]} (${event[2]})"
        }
        val line = if (event[0] == EVENT_CHAT) {
            getString(R.string.room_chat_line, displayName, event[3])
        } else {
            when (event[3].toIntOrNull()) {
                1 -> getString(R.string.room_member_joined, displayName)
                2 -> getString(R.string.room_member_left, displayName)
                3 -> getString(R.string.room_member_kicked, displayName)
                4 -> getString(R.string.room_member_banned, displayName)
                5 -> getString(R.string.room_member_unbanned, displayName)
                else -> return
            }
        }
        appendChatLine(line)
    }

    private fun sendMessage() {
        val message = binding.roomMessage.text?.toString()?.trim().orEmpty()
        if (message.isEmpty()) return
        lifecycleScope.launch {
            val sent = withContext(Dispatchers.IO) {
                NativeLibrary.sendRoomChatMessage(message)
            }
            if (sent) {
                appendChatLine(getString(R.string.room_chat_line_self, message))
                binding.roomMessage.text?.clear()
            }
        }
    }

    private fun appendChatLine(line: String) {
        chatLines.addLast(line)
        while (chatLines.size > MAX_VISIBLE_EVENTS) chatLines.removeFirst()
        binding.roomChatHistory.text = chatLines.joinToString("\n")
        binding.roomChatScroll.post { binding.roomChatScroll.fullScroll(android.view.View.FOCUS_DOWN) }
    }

    private fun disconnect(hosting: Boolean) {
        updateJob?.cancel()
        lifecycleScope.launch {
            withContext(Dispatchers.IO) {
                if (hosting) NativeLibrary.closeRoom() else NativeLibrary.leaveRoom()
            }
            settingsViewModel.setShouldReloadSettingsList(true)
            dismissAllowingStateLoss()
        }
    }

    companion object {
        const val TAG = "RoomDialog"

        private const val MEMBER_FIELD_COUNT = 4
        private const val EVENT_FIELD_COUNT = 4
        private const val EVENT_CHAT = "0"
        private const val ROOM_UPDATE_INTERVAL_MS = 500L
        private const val MAX_VISIBLE_EVENTS = 100
    }
}
