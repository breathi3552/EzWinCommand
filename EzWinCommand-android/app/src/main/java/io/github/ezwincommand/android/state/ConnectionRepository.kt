package io.github.ezwincommand.android.state

import io.github.ezwincommand.android.network.ApiResult
import io.github.ezwincommand.android.network.EzApiClient
import io.github.ezwincommand.android.storage.DeviceKeyStore
import java.net.URI

class ConnectionRepository(
    private val keyStore: DeviceKeyStore,
    private val clientFactory: (String, () -> String?) -> EzApiClient = { baseUrl, provider ->
        EzApiClient(baseUrl, provider, timeoutMillis = 5_000)
    },
) {
    suspend fun testConnection(baseUrl: String): ConnectionCheckResult {
        val normalized = normalizeBaseUrl(baseUrl) ?: return ConnectionCheckResult.Unreachable(lastNormalizeError)
        val client = clientFactory(normalized) { keyStore.getDeviceKey() }
        return when (val ping = client.ping()) {
            is ApiResult.Success -> when (val pairing = client.pairingStatus()) {
                is ApiResult.Success -> ConnectionCheckResult.Reachable(normalized, pairing.value)
                is ApiResult.HttpError -> ConnectionCheckResult.Unreachable(connectionMessage(pairing.status, pairing.message))
                is ApiResult.NetworkError -> ConnectionCheckResult.Unreachable(networkMessage(normalized, pairing.message, pairing.cause))
                is ApiResult.ParseError -> ConnectionCheckResult.Unreachable("服务器返回的数据无法识别，请确认该地址是否是 EzWinCommand 服务。")
            }
            is ApiResult.HttpError -> ConnectionCheckResult.Unreachable(connectionMessage(ping.status, ping.message))
            is ApiResult.NetworkError -> ConnectionCheckResult.Unreachable(networkMessage(normalized, ping.message, ping.cause))
            is ApiResult.ParseError -> ConnectionCheckResult.Unreachable("服务器返回的数据无法识别，请确认该地址是否是 EzWinCommand 服务。")
        }
    }

    suspend fun pair(baseUrl: String, code: String, deviceName: String): PairingResult {
        val normalized = normalizeBaseUrl(baseUrl) ?: return PairingResult.Failed(lastNormalizeError, lockedOrInvalid = false)
        val pairingCode = code.trim().lowercase()
        if (!PAIRING_CODE.matches(pairingCode)) {
            return PairingResult.Failed("请输入 PC 管理面板显示的 4 位配对码。", lockedOrInvalid = false)
        }
        val name = deviceName.trim().ifBlank { "Android" }
        val client = clientFactory(normalized) { null }
        return when (val result = client.authorize(pairingCode, name)) {
            is ApiResult.Success -> {
                val session = result.value.deviceKey?.trim().orEmpty()
                if (result.value.success && session.isNotEmpty()) {
                    keyStore.saveSession(normalized, session, name)
                    PairingResult.Paired(normalized, session)
                } else {
                    PairingResult.Failed(result.value.message?.ifBlank { null } ?: "配对失败。", lockedOrInvalid = false)
                }
            }
            is ApiResult.HttpError -> PairingResult.Failed(pairingMessage(result.status, result.message, normalized), lockedOrInvalid = result.status == 401 || result.status == 403)
            is ApiResult.NetworkError -> PairingResult.Failed(networkMessage(normalized, result.message, result.cause), lockedOrInvalid = false)
            is ApiResult.ParseError -> PairingResult.Failed("服务器返回的数据无法识别，请稍后重试。", lockedOrInvalid = false)
        }
    }

    suspend fun restoreSession(): RestoreResult {
        val baseUrl = keyStore.getBaseUrl()?.trim().orEmpty()
        val session = keyStore.getDeviceKey()?.trim().orEmpty()
        if (baseUrl.isEmpty() || session.isEmpty()) return RestoreResult.NoSavedSession
        val normalized = normalizeBaseUrl(baseUrl) ?: run {
            keyStore.clearSession()
            return RestoreResult.InvalidSavedSession(lastNormalizeError)
        }
        val client = clientFactory(normalized) { session }
        return when (val result = client.listActions()) {
            is ApiResult.Success -> RestoreResult.Restored(normalized)
            is ApiResult.HttpError -> {
                if (result.status == 401 || result.status == 403) keyStore.clearSession()
                RestoreResult.InvalidSavedSession(sessionMessage(result.status, result.message, normalized))
            }
            is ApiResult.NetworkError -> RestoreResult.InvalidSavedSession(networkMessage(normalized, result.message, result.cause))
            is ApiResult.ParseError -> RestoreResult.InvalidSavedSession("服务器返回的数据无法识别，无法恢复会话。")
        }
    }

    fun signOut() {
        keyStore.clearSession()
    }

    fun normalizeInputForAndroid(address: String, port: String?): NormalizeResult {
        val rawAddress = address.trim().trimEnd('/')
        val rawPort = port?.trim().orEmpty()
        if (rawAddress.isEmpty()) return NormalizeResult.Invalid("请输入服务地址。")
        val candidate = when {
            rawAddress.contains("://") -> appendPortIfMissing(rawAddress, rawPort)
            rawPort.isEmpty() -> rawAddress
            rawAddress.substringAfterLast('/').contains(':') -> rawAddress
            else -> "$rawAddress:$rawPort"
        }
        val normalized = normalizeBaseUrl(candidate) ?: return NormalizeResult.Invalid(lastNormalizeError)
        val uri = URI(normalized)
        val portValue = if (uri.port == -1) null else uri.port
        return NormalizeResult.Valid(baseUrl = normalized, host = uri.host.orEmpty(), port = portValue)
    }

    private fun appendPortIfMissing(address: String, port: String): String {
        if (port.isBlank()) return address
        val uri = try {
            URI(address)
        } catch (_: Throwable) {
            return address
        }
        if (uri.port != -1 || uri.host.isNullOrBlank()) return address
        return "${uri.scheme}://${uri.host}:$port"
    }

    fun normalizeForTest(baseUrl: String): String? = normalizeBaseUrl(baseUrl)

    fun normalizeBaseUrlForProduction(baseUrl: String): String? = normalizeBaseUrl(baseUrl)

    fun networkHintForTest(baseUrl: String, message: String, cause: Throwable?): String = networkMessage(baseUrl, message, cause)

    private var lastNormalizeError: String = ""

    private fun normalizeBaseUrl(value: String): String? {
        val raw = value.trim().trimEnd('/')
        if (raw.isEmpty()) return fail("请输入服务地址。")
        val withScheme = if (raw.contains("://")) raw else "http://$raw"
        val uri = try {
            URI(withScheme)
        } catch (_: Throwable) {
            return fail("服务地址格式不正确，请输入类似 192.168.1.10:8080 或 http://192.168.1.10:8080。")
        }
        val scheme = uri.scheme?.lowercase().orEmpty()
        if (scheme != "http" && scheme != "https") return fail("服务地址必须以 http:// 或 https:// 开头。")
        val host = uri.host?.trim().orEmpty()
        if (host.isEmpty()) return fail("服务地址缺少主机名，请确认是否输入了正确的 LAN 地址。")
        if (host == "0.0.0.0") return fail("0.0.0.0 只能用于服务端监听，手机不能直接连接；请改成局域网 IP 或主机名。")
        if (host == "localhost" || host == "127.0.0.1") return fail("localhost/127.0.0.1 在 Android 上指手机自身；请填写 PC 的局域网 IP。")
        val port = if (uri.port == -1) "" else ":${uri.port}"
        return "$scheme://$host$port"
    }

    private fun fail(message: String): String? {
        lastNormalizeError = message
        return null
    }

    private fun connectionMessage(status: Int, remoteMessage: String): String = when (status) {
        401, 403 -> "会话已失效，请重新配对。"
        else -> remoteMessage.ifBlank { "无法连接到服务，请确认手机与 PC 在同一局域网、HOST=0.0.0.0、地址/端口正确，且服务端未被防火墙拦截。" }
    }

    private fun sessionMessage(status: Int, remoteMessage: String, baseUrl: String): String = when (status) {
        401, 403 -> "会话已失效，已清除本地密钥，请重新配对。"
        else -> remoteMessage.ifBlank { "无法恢复会话，请确认 $baseUrl 可访问，且服务端未被防火墙拦截。" }
    }

    private fun pairingMessage(status: Int, remoteMessage: String, baseUrl: String): String = when (status) {
        401, 403 -> remoteMessage.ifBlank { "配对码无效或已锁定，请在 PC 管理面板确认配对码后重试。" }
        else -> remoteMessage.ifBlank { "配对失败，请确认同一局域网内的 $baseUrl 可访问，且服务端未被防火墙拦截。" }
    }

    private fun networkMessage(baseUrl: String, message: String, cause: Throwable?): String {
        val detail = listOfNotNull(
            message.takeIf { it.isNotBlank() },
            cause?.message?.takeIf { it.isNotBlank() },
        ).joinToString("；")
        val hint = when {
            baseUrl.contains("0.0.0.0") -> "0.0.0.0 不能作为客户端目标地址，请改用局域网 IP。"
            else -> "无法连接，请确认手机与 PC 在同一局域网，PC 地址/端口正确，HOST=0.0.0.0，且防火墙已放行。"
        }
        return if (detail.isBlank()) hint else "$hint $detail"
    }

    private companion object {
        val PAIRING_CODE = Regex("^[0-9a-z]{4}$")
    }
}
