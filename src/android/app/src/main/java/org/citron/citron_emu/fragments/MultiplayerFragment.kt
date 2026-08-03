// SPDX-License-Identifier: GPL-2.0-or-later

package org.citron.citron_emu.fragments

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Toast
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.updatePadding
import androidx.fragment.app.Fragment
import androidx.fragment.app.activityViewModels
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.citron.citron_emu.NativeLibrary
import org.citron.citron_emu.R
import org.citron.citron_emu.databinding.FragmentMultiplayerBinding
import org.citron.citron_emu.features.settings.ui.DirectConnectDialogFragment
import org.citron.citron_emu.features.settings.ui.HostRoomDialogFragment
import org.citron.citron_emu.features.settings.ui.MultiplayerRoomState
import org.citron.citron_emu.features.settings.ui.RoomDialogFragment
import org.citron.citron_emu.model.HomeViewModel
import org.citron.citron_emu.utils.ViewUtils.updateMargins

class MultiplayerFragment : Fragment() {
    private var _binding: FragmentMultiplayerBinding? = null
    private val binding get() = _binding!!
    private val homeViewModel: HomeViewModel by activityViewModels()

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        _binding = FragmentMultiplayerBinding.inflate(inflater, container, false)
        return binding.root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        homeViewModel.setNavigationVisibility(visible = true, animated = true)
        homeViewModel.setStatusBarShadeVisibility(visible = true)

        binding.multiplayerDirectConnect.setOnClickListener {
            DirectConnectDialogFragment().show(
                parentFragmentManager,
                DirectConnectDialogFragment.TAG
            )
        }
        binding.multiplayerCreateRoom.setOnClickListener {
            HostRoomDialogFragment().show(parentFragmentManager, HostRoomDialogFragment.TAG)
        }
        binding.multiplayerOpenRoom.setOnClickListener {
            RoomDialogFragment().show(parentFragmentManager, RoomDialogFragment.TAG)
        }
        binding.multiplayerLeaveRoom.setOnClickListener { leaveOrCloseRoom() }

        setInsets()
        observeRoomState()
    }

    override fun onDestroyView() {
        super.onDestroyView()
        _binding = null
    }

    private fun observeRoomState() {
        viewLifecycleOwner.lifecycleScope.launch {
            viewLifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) {
                while (currentCoroutineContext().isActive) {
                    updateRoomState()
                    delay(ROOM_STATE_POLL_MS)
                }
            }
        }
    }

    private fun updateRoomState() {
        val state = NativeLibrary.getRoomConnectionState()
        val hosting = NativeLibrary.isHostingRoom()
        val connected = MultiplayerRoomState.isConnected(state)
        binding.multiplayerStatusText.setText(
            when {
                hosting && connected -> R.string.multiplayer_status_hosting
                hosting -> R.string.multiplayer_status_host_disconnected
                state == MultiplayerRoomState.JOINING -> R.string.multiplayer_status_connecting
                connected -> R.string.multiplayer_status_connected
                else -> R.string.multiplayer_status_disconnected
            }
        )

        val canStartConnection = state != MultiplayerRoomState.JOINING && !connected && !hosting &&
            !NativeLibrary.isRunning()
        binding.multiplayerDirectConnect.isEnabled = canStartConnection
        binding.multiplayerCreateRoom.isEnabled = canStartConnection
        binding.multiplayerOpenRoom.isEnabled = connected || hosting
        binding.multiplayerLeaveRoom.isEnabled = connected || hosting
        binding.multiplayerLeaveRoom.setText(
            if (hosting) R.string.room_close_hosted else R.string.room_leave
        )
    }

    private fun leaveOrCloseRoom() {
        val hosting = NativeLibrary.isHostingRoom()
        viewLifecycleOwner.lifecycleScope.launch {
            withContext(Dispatchers.IO) {
                if (hosting) NativeLibrary.closeRoom() else NativeLibrary.leaveRoom()
            }
            Toast.makeText(
                requireContext(),
                if (hosting) {
                    R.string.multiplayer_close_complete
                } else {
                    R.string.multiplayer_leave_complete
                },
                Toast.LENGTH_SHORT
            ).show()
            updateRoomState()
        }
    }

    private fun setInsets() = ViewCompat.setOnApplyWindowInsetsListener(binding.root) {
            view: View,
            windowInsets: WindowInsetsCompat ->
        val barInsets = windowInsets.getInsets(WindowInsetsCompat.Type.systemBars())
        val cutoutInsets = windowInsets.getInsets(WindowInsetsCompat.Type.displayCutout())
        val spacingNavigation = resources.getDimensionPixelSize(R.dimen.spacing_navigation)
        val spacingNavigationRail =
            resources.getDimensionPixelSize(R.dimen.spacing_navigation_rail)
        val contentPadding = resources.getDimensionPixelSize(R.dimen.spacing_fab)

        binding.multiplayerScroll.updateMargins(
            left = barInsets.left + cutoutInsets.left,
            right = barInsets.right + cutoutInsets.right
        )
        binding.multiplayerScroll.updatePadding(top = barInsets.top, bottom = barInsets.bottom)
        binding.multiplayerContent.updatePadding(bottom = spacingNavigation + contentPadding)
        if (view.layoutDirection == View.LAYOUT_DIRECTION_LTR) {
            binding.multiplayerContent.updatePadding(left = spacingNavigationRail + contentPadding)
        } else {
            binding.multiplayerContent.updatePadding(right = spacingNavigationRail + contentPadding)
        }
        windowInsets
    }

    companion object {
        private const val ROOM_STATE_POLL_MS = 500L
    }
}
