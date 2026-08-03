// SPDX-License-Identifier: GPL-2.0-or-later

package org.citron.citron_emu.features.settings.ui

import android.content.Context
import kotlinx.coroutines.delay
import org.citron.citron_emu.NativeLibrary
import org.citron.citron_emu.R

object MultiplayerRoomState {
    const val IDLE = 1
    const val JOINING = 2
    const val JOINED = 3
    const val MODERATOR = 4

    fun isConnected(state: Int) = state == JOINED || state == MODERATOR
}

internal fun multiplayerErrorText(context: Context, error: Int): String =
    context.getString(
        when (error) {
            0 -> R.string.multiplayer_error_lost_connection
            1 -> R.string.multiplayer_error_kicked
            3 -> R.string.multiplayer_error_name_collision
            4 -> R.string.multiplayer_error_ip_collision
            5 -> R.string.multiplayer_error_wrong_version
            6 -> R.string.multiplayer_error_wrong_password
            7 -> R.string.multiplayer_error_could_not_connect
            8 -> R.string.multiplayer_error_room_full
            9 -> R.string.multiplayer_error_banned
            10 -> R.string.multiplayer_error_permission_denied
            11 -> R.string.multiplayer_error_no_such_user
            100 -> R.string.multiplayer_error_network_not_initialized
            101 -> R.string.multiplayer_error_invalid_arguments
            102 -> R.string.multiplayer_error_no_network_interface
            103 -> R.string.multiplayer_error_room_unavailable
            104 -> R.string.multiplayer_error_room_already_open
            105 -> R.string.multiplayer_error_member_busy
            106 -> R.string.multiplayer_error_could_not_create_room
            107 -> R.string.multiplayer_error_local_join_failed
            else -> R.string.multiplayer_error_unknown
        }
    )

internal suspend fun awaitMultiplayerError(): Int {
    repeat(ERROR_POLL_ATTEMPTS) {
        val error = NativeLibrary.getRoomLastError()
        if (error >= 0) return error
        delay(ERROR_POLL_DELAY_MS)
    }
    return -1
}

private const val ERROR_POLL_ATTEMPTS = 5
private const val ERROR_POLL_DELAY_MS = 20L
