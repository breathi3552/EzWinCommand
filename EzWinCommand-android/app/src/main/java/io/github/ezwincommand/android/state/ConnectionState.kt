package io.github.ezwincommand.android.state

sealed interface ConnectionState {
    data object Disconnected : ConnectionState

    data class Checking(val baseUrl: String) : ConnectionState

    data class PairingRequired(val baseUrl: String, val expiresIn: Int?) : ConnectionState

    data class Connected(val baseUrl: String, val deviceName: String) : ConnectionState

    data class Error(val baseUrl: String?, val message: String, val recoverable: Boolean) : ConnectionState
}

data class ConnectionConfig(val baseUrl: String)

sealed interface NormalizeResult {
    data class Valid(val baseUrl: String, val host: String, val port: Int?) : NormalizeResult
    data class Invalid(val message: String) : NormalizeResult
}

sealed interface ConnectionCheckResult {
    data class Reachable(val baseUrl: String, val pairing: io.github.ezwincommand.android.model.PairingStatus) : ConnectionCheckResult
    data class Unreachable(val message: String) : ConnectionCheckResult
}

sealed interface PairingResult {
    data class Paired(val baseUrl: String, val deviceKey: String) : PairingResult
    data class Failed(val message: String, val lockedOrInvalid: Boolean) : PairingResult
}

sealed interface RestoreResult {
    data class Restored(val baseUrl: String) : RestoreResult
    data object NoSavedSession : RestoreResult
    data class InvalidSavedSession(val message: String) : RestoreResult
}
