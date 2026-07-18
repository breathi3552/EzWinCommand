package io.github.ezwincommand.android.state

import io.github.ezwincommand.android.model.ServerIdentity
import io.github.ezwincommand.android.storage.ServerSession

sealed interface ConnectionState {
    data object Disconnected : ConnectionState
    data class Checking(val serverId: String?, val baseUrl: String) : ConnectionState
    data class PairingRequired(val serverId: String, val baseUrl: String, val pairingId: String, val expiresIn: Int) : ConnectionState
    data class Connected(val serverId: String, val baseUrl: String, val deviceName: String, val credentialVersion: Long) : ConnectionState
    data class Error(val serverId: String?, val baseUrl: String?, val message: String, val recoverable: Boolean) : ConnectionState
}

data class ConnectionConfig(val serverId: String, val baseUrl: String)

sealed interface NormalizeResult {
    data class Valid(val baseUrl: String, val host: String, val port: Int?) : NormalizeResult
    data class Invalid(val message: String) : NormalizeResult
}

sealed interface ConnectionCheckResult {
    data class Reachable(
        val identity: ServerIdentity,
        val baseUrl: String,
        val pairingId: String?,
        val expiresIn: Int?,
        val savedSession: ServerSession?,
    ) : ConnectionCheckResult
    data class Unreachable(val message: String) : ConnectionCheckResult
}

sealed interface PairingResult {
    data class Paired(val session: ServerSession) : PairingResult
    data object UiInvalidated : PairingResult
    data class Failed(val message: String, val lockedOrInvalid: Boolean) : PairingResult
}

sealed interface RestoreResult {
    data class Restored(val session: ServerSession) : RestoreResult
    data object NoSavedSession : RestoreResult
    data class InvalidSavedSession(val serverId: String?, val message: String) : RestoreResult
}
