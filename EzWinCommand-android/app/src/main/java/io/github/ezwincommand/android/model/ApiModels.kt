package io.github.ezwincommand.android.model

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
)

data class DeviceInfo(
    val key: String,
    val name: String,
    val createdAt: String?,
    val lastSeen: String?,
)
