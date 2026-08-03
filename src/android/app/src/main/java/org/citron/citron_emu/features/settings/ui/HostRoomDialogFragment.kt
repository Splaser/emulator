// SPDX-License-Identifier: GPL-2.0-or-later

package org.citron.citron_emu.features.settings.ui

import android.app.Dialog
import android.os.Bundle
import androidx.appcompat.app.AlertDialog
import androidx.core.view.isVisible
import androidx.fragment.app.DialogFragment
import androidx.fragment.app.activityViewModels
import androidx.lifecycle.lifecycleScope
import androidx.preference.PreferenceManager
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.citron.citron_emu.CitronApplication
import org.citron.citron_emu.NativeLibrary
import org.citron.citron_emu.R
import org.citron.citron_emu.databinding.DialogHostRoomBinding

class HostRoomDialogFragment : DialogFragment() {
    private lateinit var binding: DialogHostRoomBinding
    private var hostJob: Job? = null
    private val settingsViewModel: SettingsViewModel by activityViewModels()

    override fun onCreateDialog(savedInstanceState: Bundle?): Dialog {
        binding = DialogHostRoomBinding.inflate(layoutInflater)
        val preferences = PreferenceManager.getDefaultSharedPreferences(CitronApplication.appContext)
        binding.hostRoomName.setText(preferences.getString(PREF_ROOM_NAME, ""))
        binding.hostRoomNickname.setText(preferences.getString(PREF_NICKNAME, ""))
        binding.hostRoomDescription.setText(preferences.getString(PREF_DESCRIPTION, ""))
        binding.hostRoomPort.setText(preferences.getInt(PREF_PORT, DEFAULT_PORT).toString())
        binding.hostRoomMaxPlayers.setText(preferences.getInt(PREF_MAX_PLAYERS, 8).toString())

        return MaterialAlertDialogBuilder(requireContext())
            .setTitle(R.string.host_room_unlisted)
            .setView(binding.root)
            .setNegativeButton(R.string.close, null)
            .setPositiveButton(R.string.host_room_create, null)
            .create()
            .also { dialog ->
                dialog.setOnShowListener {
                    dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                        host(dialog)
                    }
                }
            }
    }

    override fun onDestroyView() {
        hostJob?.cancel()
        super.onDestroyView()
    }

    private fun host(dialog: AlertDialog) {
        val roomName = binding.hostRoomName.text?.toString()?.trim().orEmpty()
        val nickname = binding.hostRoomNickname.text?.toString()?.trim().orEmpty()
        val description = binding.hostRoomDescription.text?.toString()?.trim().orEmpty()
        val password = binding.hostRoomPassword.text?.toString().orEmpty()
        val port = binding.hostRoomPort.text?.toString()?.toIntOrNull()
        val maxPlayers = binding.hostRoomMaxPlayers.text?.toString()?.toIntOrNull()
        if (roomName.length !in MIN_ROOM_NAME_LENGTH..MAX_ROOM_NAME_LENGTH ||
            nickname.length !in MIN_NICKNAME_LENGTH..MAX_NICKNAME_LENGTH ||
            !nickname.matches(NICKNAME_PATTERN) || port !in 1..MAX_PORT ||
            maxPlayers !in 2..16
        ) {
            showStatus(getString(R.string.host_room_invalid_input))
            return
        }
        val portValue = port ?: return
        val maxPlayersValue = maxPlayers ?: return

        PreferenceManager.getDefaultSharedPreferences(CitronApplication.appContext).edit()
            .putString(PREF_ROOM_NAME, roomName)
            .putString(PREF_NICKNAME, nickname)
            .putString(PREF_DESCRIPTION, description)
            .putInt(PREF_PORT, portValue)
            .putInt(PREF_MAX_PLAYERS, maxPlayersValue)
            .apply()

        dialog.getButton(AlertDialog.BUTTON_POSITIVE).isEnabled = false
        showStatus(getString(R.string.host_room_creating))
        hostJob?.cancel()
        hostJob = lifecycleScope.launch {
            val started = withContext(Dispatchers.IO) {
                NativeLibrary.hostRoom(
                    nickname,
                    roomName,
                    description,
                    portValue,
                    password,
                    maxPlayersValue
                )
            }
            if (!started) {
                val error = awaitMultiplayerError()
                showStatus(
                    if (error >= 0) {
                        multiplayerErrorText(requireContext(), error)
                    } else {
                        getString(R.string.host_room_create_failed)
                    }
                )
                dialog.getButton(AlertDialog.BUTTON_POSITIVE).isEnabled = true
                return@launch
            }
            monitorHostConnection(dialog)
        }
    }

    private suspend fun monitorHostConnection(dialog: AlertDialog) {
        while (currentCoroutineContext().isActive) {
            val state = withContext(Dispatchers.IO) { NativeLibrary.getRoomConnectionState() }
            if (MultiplayerRoomState.isConnected(state)) {
                settingsViewModel.setShouldReloadSettingsList(true)
                dismissAllowingStateLoss()
                RoomDialogFragment().show(parentFragmentManager, RoomDialogFragment.TAG)
                return
            }
            if (state != MultiplayerRoomState.JOINING) {
                val error = awaitMultiplayerError()
                withContext(Dispatchers.IO) { NativeLibrary.closeRoom() }
                showStatus(
                    multiplayerErrorText(requireContext(), error)
                )
                dialog.getButton(AlertDialog.BUTTON_POSITIVE).isEnabled = true
                return
            }
            delay(CONNECTION_STATE_POLL_MS)
        }
    }

    private fun showStatus(message: String) {
        binding.hostRoomStatus.text = message
        binding.hostRoomStatus.isVisible = true
    }

    companion object {
        const val TAG = "HostRoomDialog"

        private const val PREF_ROOM_NAME = "HostRoomName"
        private const val PREF_NICKNAME = "HostRoomNickname"
        private const val PREF_DESCRIPTION = "HostRoomDescription"
        private const val PREF_PORT = "HostRoomPort"
        private const val PREF_MAX_PLAYERS = "HostRoomMaxPlayers"
        private const val DEFAULT_PORT = 24872
        private const val MIN_ROOM_NAME_LENGTH = 4
        private const val MAX_ROOM_NAME_LENGTH = 50
        private const val MIN_NICKNAME_LENGTH = 4
        private const val MAX_NICKNAME_LENGTH = 20
        private const val MAX_PORT = 65535
        private const val CONNECTION_STATE_POLL_MS = 250L
        private val NICKNAME_PATTERN = Regex("[a-zA-Z0-9._ -]+")
    }
}
