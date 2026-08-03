// SPDX-License-Identifier: GPL-2.0-or-later

package org.citron.citron_emu.features.multiplayer.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.merge
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.withContext
import org.citron.citron_emu.features.multiplayer.data.MultiplayerRepository
import org.citron.citron_emu.features.multiplayer.model.DirectConnectParams
import org.citron.citron_emu.features.multiplayer.model.HostRoomParams
import org.citron.citron_emu.features.multiplayer.model.MultiplayerSnapshot
import org.citron.citron_emu.features.multiplayer.model.RoomContent
import org.citron.citron_emu.features.multiplayer.model.StartRoomResult

class MultiplayerViewModel : ViewModel() {
    private val refreshRequests = MutableSharedFlow<Unit>(extraBufferCapacity = 1)
    private val repository = MultiplayerRepository

    val snapshot: StateFlow<MultiplayerSnapshot> = merge(
        pollingTicks(SNAPSHOT_POLL_MS),
        refreshRequests
    ).map { repository.getSnapshot() }
        .flowOn(Dispatchers.IO)
        .stateIn(
            viewModelScope,
            SharingStarted.WhileSubscribed(STOP_TIMEOUT_MS),
            repository.getSnapshot()
        )

    val roomContent: StateFlow<RoomContent> = pollingTicks(ROOM_CONTENT_POLL_MS)
        .map {
            if (repository.getSnapshot().isConnected) {
                repository.getRoomContent()
            } else {
                RoomContent()
            }
        }
        .flowOn(Dispatchers.IO)
        .stateIn(
            viewModelScope,
            SharingStarted.WhileSubscribed(STOP_TIMEOUT_MS),
            RoomContent()
        )

    private val _airplaneMode = MutableStateFlow(repository.isAirplaneModeEnabled())
    val airplaneMode: StateFlow<Boolean> = _airplaneMode.asStateFlow()

    fun setAirplaneModeEnabled(enabled: Boolean) {
        repository.setAirplaneModeEnabled(enabled)
        _airplaneMode.value = enabled
    }

    suspend fun connect(params: DirectConnectParams): StartRoomResult = withContext(Dispatchers.IO) {
        repository.connect(params).also {
            _airplaneMode.value = repository.isAirplaneModeEnabled()
            refreshRequests.tryEmit(Unit)
        }
    }

    suspend fun host(params: HostRoomParams): StartRoomResult = withContext(Dispatchers.IO) {
        repository.host(params).also {
            _airplaneMode.value = repository.isAirplaneModeEnabled()
            refreshRequests.tryEmit(Unit)
        }
    }

    suspend fun leaveOrClose(hosting: Boolean) = withContext(Dispatchers.IO) {
        if (hosting) repository.closeRoom() else repository.leaveRoom()
        refreshRequests.tryEmit(Unit)
    }

    suspend fun sendChatMessage(message: String): Boolean = withContext(Dispatchers.IO) {
        repository.sendChatMessage(message)
    }

    private fun pollingTicks(intervalMs: Long) = flow {
        while (true) {
            emit(Unit)
            delay(intervalMs)
        }
    }

    companion object {
        private const val SNAPSHOT_POLL_MS = 250L
        private const val ROOM_CONTENT_POLL_MS = 500L
        private const val STOP_TIMEOUT_MS = 1_000L
    }
}
