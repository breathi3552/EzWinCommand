package io.github.ezwincommand.android.model

data class AudioEndpoint(
    val id: String,
    val name: String,
)

enum class MediaPlayback(val wireValue: String) {
    PLAYING("playing"),
    PAUSED("paused"),
    STOPPED("stopped"),
    NONE("none");

    companion object {
        fun fromWire(value: String): MediaPlayback = entries.firstOrNull { it.wireValue == value }
            ?: throw IllegalArgumentException("未知 playback: $value")
    }
}

data class MediaState(
    val revision: Long,
    val available: Boolean,
    val title: String?,
    val artist: String?,
    val playback: MediaPlayback,
    val cover: String?,
    val volume: Int,
    val renderDevices: List<AudioEndpoint>,
    val captureDevices: List<AudioEndpoint>,
    val selectedRenderId: String?,
    val selectedCaptureId: String?,
    val error: String?,
) {
    init {
        require(revision >= 0) { "revision 不能为负数" }
        require(volume in 0..100) { "volume 必须在 0..100" }
    }

    companion object {
        val LOADING = MediaState(
            revision = 0,
            available = false,
            title = null,
            artist = null,
            playback = MediaPlayback.NONE,
            cover = null,
            volume = 0,
            renderDevices = emptyList(),
            captureDevices = emptyList(),
            selectedRenderId = null,
            selectedCaptureId = null,
            error = null,
        )
    }
}

data class PingResponse(
    val status: String,
)

data class PairingStatus(
    val hasCode: Boolean,
    val hasDevices: Boolean,
    val expiresIn: Int,
)

data class AuthorizeResult(
    val success: Boolean,
    val deviceKey: String?,
    val message: String?,
)

data class ActionPlugin(
    val name: String,
    val label: String,
    val description: String,
    val version: String,
    val subActions: List<SubAction>,
)

data class SubAction(
    val id: String,
    val label: String,
)

data class CommandResult(
    val success: Boolean,
    val message: String,
    val data: Map<String, Any?>,
    val commandId: String? = null,
    val status: String? = null,
)

data class AsyncCommandAccepted(
    val commandId: String,
    val status: String,
)

data class CommandStatus(
    val commandId: String,
    val status: String,
    val message: String? = null,
    val data: Map<String, Any?>? = null,
    val error: Map<String, Any?>? = null,
)

data class DeviceInfo(
    val key: String,
    val name: String,
    val createdAt: String?,
    val lastSeen: String?,
)
