// SPDX-License-Identifier: GPL-2.0-or-later

package org.citron.citron_emu.features.settings.ui

import android.app.Dialog
import android.content.DialogInterface
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
import org.citron.citron_emu.databinding.DialogDirectConnectBinding

class DirectConnectDialogFragment : DialogFragment() {
    private lateinit var binding: DialogDirectConnectBinding
    private var connectionJob: Job? = null
    private var connectionState = MultiplayerRoomState.IDLE

    private val settingsViewModel: SettingsViewModel by activityViewModels()

    override fun onCreateDialog(savedInstanceState: Bundle?): Dialog {
        binding = DialogDirectConnectBinding.inflate(layoutInflater)
        val preferences = PreferenceManager.getDefaultSharedPreferences(CitronApplication.appContext)
        binding.directConnectHost.setText(preferences.getString(PREF_HOST, ""))
        binding.directConnectPort.setText(preferences.getInt(PREF_PORT, DEFAULT_PORT).toString())
        binding.directConnectNickname.setText(preferences.getString(PREF_NICKNAME, ""))

        return MaterialAlertDialogBuilder(requireContext())
            .setTitle(R.string.direct_connect)
            .setView(binding.root)
            .setNegativeButton(R.string.close, null)
            .setNeutralButton(R.string.direct_connect_disconnect, null)
            .setPositiveButton(R.string.direct_connect_connect, null)
            .create()
            .also { dialog ->
                dialog.setOnShowListener {
                    dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                        connect(dialog)
                    }
                    dialog.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener {
                        disconnect(dialog)
                    }
                    val state = NativeLibrary.getRoomConnectionState()
                    renderState(dialog, state)
                    if (state == MultiplayerRoomState.JOINING) {
                        startObservingConnection(dialog)
                    }
                }
            }
    }

    override fun onDestroyView() {
        connectionJob?.cancel()
        super.onDestroyView()
    }

    override fun onDismiss(dialog: DialogInterface) {
        saveForm()
        super.onDismiss(dialog)
    }

    private fun connect(dialog: AlertDialog) {
        val host = binding.directConnectHost.text?.toString()?.trim().orEmpty()
        val nickname = binding.directConnectNickname.text?.toString()?.trim().orEmpty()
        val password = binding.directConnectPassword.text?.toString().orEmpty()
        val port = binding.directConnectPort.text?.toString()?.toIntOrNull()
        saveForm()
        if (host.isEmpty() || host.length > MAX_HOST_LENGTH ||
            nickname.length !in MIN_NICKNAME_LENGTH..MAX_NICKNAME_LENGTH ||
            !nickname.matches(NICKNAME_PATTERN) || port !in 1..MAX_PORT
        ) {
            showStatus(R.string.direct_connect_invalid_input)
            return
        }
        val portValue = port ?: return

        dialog.getButton(AlertDialog.BUTTON_POSITIVE).isEnabled = false
        showStatus(R.string.direct_connect_connecting)
        connectionJob?.cancel()
        connectionJob = lifecycleScope.launch {
            val started = withContext(Dispatchers.IO) {
                NativeLibrary.connectToRoom(nickname, host, portValue, password)
            }
            if (!started) {
                showConnectionError()
                renderState(dialog, MultiplayerRoomState.IDLE)
                return@launch
            }
            monitorConnection(dialog)
        }
    }

    private fun startObservingConnection(dialog: AlertDialog) {
        connectionJob?.cancel()
        connectionJob = lifecycleScope.launch {
            monitorConnection(dialog)
        }
    }

    private suspend fun monitorConnection(dialog: AlertDialog) {
        while (currentCoroutineContext().isActive) {
            val state = withContext(Dispatchers.IO) {
                NativeLibrary.getRoomConnectionState()
            }
            renderState(dialog, state)
            if (state != MultiplayerRoomState.JOINING) {
                if (MultiplayerRoomState.isConnected(state)) {
                    dismissAllowingStateLoss()
                    RoomDialogFragment().show(parentFragmentManager, RoomDialogFragment.TAG)
                } else {
                    showConnectionError()
                }
                return
            }
            delay(CONNECTION_STATE_POLL_MS)
        }
    }

    private fun disconnect(dialog: AlertDialog) {
        connectionJob?.cancel()
        lifecycleScope.launch {
            withContext(Dispatchers.IO) { NativeLibrary.leaveRoom() }
            showStatus(R.string.direct_connect_disconnected)
            renderState(dialog, MultiplayerRoomState.IDLE)
        }
    }

    private fun renderState(dialog: AlertDialog, state: Int) {
        if (connectionState != state) {
            connectionState = state
            settingsViewModel.setShouldReloadSettingsList(true)
        }

        val connecting = state == MultiplayerRoomState.JOINING
        val connected = MultiplayerRoomState.isConnected(state)
        binding.directConnectHost.isEnabled = !connecting && !connected
        binding.directConnectPort.isEnabled = !connecting && !connected
        binding.directConnectNickname.isEnabled = !connecting && !connected
        binding.directConnectPassword.isEnabled = !connecting && !connected
        dialog.getButton(AlertDialog.BUTTON_POSITIVE).isEnabled = !connecting && !connected
        dialog.getButton(AlertDialog.BUTTON_NEUTRAL).isEnabled = connecting || connected

        when {
            connecting -> showStatus(R.string.direct_connect_connecting)
            connected -> showStatus(R.string.direct_connect_connected)
        }
    }

    private fun showStatus(stringId: Int) {
        binding.directConnectStatus.setText(stringId)
        binding.directConnectStatus.isVisible = true
    }

    private suspend fun showConnectionError() {
        binding.directConnectStatus.text = multiplayerErrorText(
            requireContext(),
            awaitMultiplayerError()
        )
        binding.directConnectStatus.isVisible = true
    }

    private fun saveForm() {
        val editor = PreferenceManager
            .getDefaultSharedPreferences(CitronApplication.appContext)
            .edit()
            .putString(PREF_HOST, binding.directConnectHost.text?.toString()?.trim().orEmpty())
            .putString(
                PREF_NICKNAME,
                binding.directConnectNickname.text?.toString()?.trim().orEmpty()
            )
        binding.directConnectPort.text?.toString()?.toIntOrNull()?.let {
            if (it in 1..MAX_PORT) editor.putInt(PREF_PORT, it)
        }
        editor.apply()
    }

    companion object {
        const val TAG = "DirectConnectDialog"

        private const val PREF_HOST = "DirectConnectHost"
        private const val PREF_PORT = "DirectConnectPort"
        private const val PREF_NICKNAME = "DirectConnectNickname"
        private const val DEFAULT_PORT = 24872
        private const val MIN_NICKNAME_LENGTH = 4
        private const val MAX_NICKNAME_LENGTH = 20
        private const val MAX_HOST_LENGTH = 253
        private const val MAX_PORT = 65535
        private const val CONNECTION_STATE_POLL_MS = 250L
        private val NICKNAME_PATTERN = Regex("[a-zA-Z0-9._ -]+")
    }
}
