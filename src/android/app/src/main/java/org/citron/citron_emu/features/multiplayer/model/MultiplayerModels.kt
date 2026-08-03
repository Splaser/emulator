// SPDX-License-Identifier: GPL-2.0-or-later

package org.citron.citron_emu.features.multiplayer.model

enum class RoomConnectionState(val nativeValue: Int) {
    UNINITIALIZED(0),
    IDLE(1),
    JOINING(2),
    JOINED(3),
    MODERATOR(4),
    UNKNOWN(-1);

    val isConnected: Boolean
        get() = this == JOINED || this == MODERATOR

    companion object {
        fun fromNative(value: Int): RoomConnectionState =
            entries.firstOrNull { it.nativeValue == value } ?: UNKNOWN
    }
}

enum class MultiplayerError(val nativeValue: Int) {
    LOST_CONNECTION(0),
    KICKED(1),
    NAME_COLLISION(3),
    IP_COLLISION(4),
    WRONG_VERSION(5),
    WRONG_PASSWORD(6),
    COULD_NOT_CONNECT(7),
    ROOM_FULL(8),
    BANNED(9),
    PERMISSION_DENIED(10),
    NO_SUCH_USER(11),
    NETWORK_NOT_INITIALIZED(100),
    INVALID_ARGUMENTS(101),
    NO_NETWORK_INTERFACE(102),
    ROOM_UNAVAILABLE(103),
    ROOM_ALREADY_OPEN(104),
    MEMBER_BUSY(105),
    COULD_NOT_CREATE_ROOM(106),
    LOCAL_JOIN_FAILED(107),
    UNKNOWN(Int.MIN_VALUE);

    companion object {
        fun fromNative(value: Int): MultiplayerError? {
            if (value < 0) return null
            return entries.firstOrNull { it.nativeValue == value } ?: UNKNOWN
        }
    }
}

data class MultiplayerSnapshot(
    val connectionState: RoomConnectionState = RoomConnectionState.UNINITIALIZED,
    val isHosting: Boolean = false,
    val isEmulationRunning: Boolean = false,
    val lastError: MultiplayerError? = null
) {
    val isConnected: Boolean
        get() = connectionState.isConnected

    val canStartConnection: Boolean
        get() = connectionState != RoomConnectionState.JOINING && !isConnected && !isHosting &&
            !isEmulationRunning
}

data class DirectConnectParams(
    val host: String,
    val port: Int,
    val nickname: String,
    val password: String
)

data class HostRoomParams(
    val roomName: String,
    val nickname: String,
    val description: String,
    val port: Int,
    val password: String,
    val maxPlayers: Int
)

data class StartRoomResult(
    val started: Boolean,
    val error: MultiplayerError? = null,
    val airplaneModeDisabled: Boolean = false,
    val snapshot: MultiplayerSnapshot? = null
)

data class RoomInfo(
    val name: String,
    val description: String,
    val gameName: String,
    val memberCount: String,
    val memberLimit: String,
    val port: String
)

data class RoomMember(
    val nickname: String,
    val username: String,
    val gameName: String,
    val gameId: String
)

sealed interface RoomEvent {
    val nickname: String
    val username: String

    data class Chat(
        override val nickname: String,
        override val username: String,
        val message: String
    ) : RoomEvent

    data class Status(
        override val nickname: String,
        override val username: String,
        val type: Type
    ) : RoomEvent {
        enum class Type { JOINED, LEFT, KICKED, BANNED, UNBANNED }
    }
}

data class RoomContent(
    val info: RoomInfo? = null,
    val members: List<RoomMember> = emptyList(),
    val events: List<RoomEvent> = emptyList()
)

object MultiplayerValidation {
    const val DEFAULT_PORT = 24872
    const val MIN_IDENTIFIER_LENGTH = 4
    const val MAX_IDENTIFIER_LENGTH = 20
    const val MAX_HOST_LENGTH = 253
    const val MAX_PORT = 65535
    const val MIN_PLAYERS = 2
    const val MAX_PLAYERS = 16
    const val MAX_CHAT_MESSAGE_BYTES = 500

    val identifierPattern = Regex("[a-zA-Z0-9._ -]+")

    fun isValidIdentifier(value: String): Boolean =
        value.length in MIN_IDENTIFIER_LENGTH..MAX_IDENTIFIER_LENGTH &&
            value.matches(identifierPattern)

    fun isValidHost(value: String): Boolean = value.isNotEmpty() && value.length <= MAX_HOST_LENGTH
    fun isValidPort(value: Int?): Boolean = value != null && value in 1..MAX_PORT
    fun isValidPlayerCount(value: Int?): Boolean = value != null && value in MIN_PLAYERS..MAX_PLAYERS
    fun isValidChatMessage(value: String): Boolean =
        value.isNotEmpty() && value.toByteArray(Charsets.UTF_8).size <= MAX_CHAT_MESSAGE_BYTES
}
