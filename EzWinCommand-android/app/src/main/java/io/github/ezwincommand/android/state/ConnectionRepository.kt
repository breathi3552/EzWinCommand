package io.github.ezwincommand.android.state

import io.github.ezwincommand.android.network.ApiResult
import io.github.ezwincommand.android.network.EzApiClient
import io.github.ezwincommand.android.storage.ServerSessionStore
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import java.net.URI
import java.util.concurrent.atomic.AtomicLong

class ConnectionRepository(
    private val sessions: ServerSessionStore,
    private val clientFactory: (String, () -> String?) -> EzApiClient = { baseUrl, provider ->
        EzApiClient(baseUrl, provider, timeoutMillis = 5_000)
    },
    private val now: () -> Long = System::currentTimeMillis,
) {
    private val operation = AtomicLong(0)
    private var pending: PendingPairing? = null
    private var restoreAttempted = false

    data class PendingPairing(val operationId: Long, val serverId: String, val baseUrl: String, val pairingId: String, val deviceName: String)

    fun savedServers() = sessions.list()

    suspend fun testConnection(baseUrl: String): ConnectionCheckResult {
        val normalized = normalizeBaseUrl(baseUrl) ?: return ConnectionCheckResult.Unreachable(lastNormalizeError)
        val op = operation.incrementAndGet()
        pending = null
        val anonymous = clientFactory(normalized) { null }
        val identity = when (val result = anonymous.identity()) {
            is ApiResult.Success -> result.value
            is ApiResult.HttpError -> return ConnectionCheckResult.Unreachable(connectionMessage(result.status, result.message))
            is ApiResult.NetworkError -> return ConnectionCheckResult.Unreachable(networkMessage(normalized, result.message, result.cause))
            is ApiResult.ParseError -> return ConnectionCheckResult.Unreachable("服务器身份无法识别。")
        }
        if (operation.get() != op) return ConnectionCheckResult.Unreachable("操作已取消。")
        val saved = sessions.get(identity.serverId)
        if (saved != null && !saved.needsRepair) {
            val key = sessions.readDeviceKey(identity.serverId)
            if (key != null) {
                val authorized = clientFactory(normalized) { key }.listActions()
                if (operation.get() != op) return ConnectionCheckResult.Unreachable("操作已取消。")
                if (authorized is ApiResult.Success) {
                    val updated = sessions.recordAuthorized(identity.serverId, normalized, identity.name, now())
                    return ConnectionCheckResult.Reachable(identity, normalized, null, null, updated ?: saved)
                }
                if (authorized is ApiResult.HttpError && (authorized.status == 401 || authorized.status == 403)) sessions.markRepair(identity.serverId)
            }
        }
        val created = when (val result = anonymous.createPairing(identity.serverId, "Android")) {
            is ApiResult.Success -> result.value
            is ApiResult.HttpError -> return ConnectionCheckResult.Unreachable(result.message)
            is ApiResult.NetworkError -> return ConnectionCheckResult.Unreachable(networkMessage(normalized, result.message, result.cause))
            is ApiResult.ParseError -> return ConnectionCheckResult.Unreachable("配对响应无法识别。")
        }
        if (operation.get() != op) {
            anonymous.cancelPairing(created.pairingId)
            return ConnectionCheckResult.Unreachable("操作已取消。")
        }
        pending = PendingPairing(op, identity.serverId, normalized, created.pairingId, "Android")
        return ConnectionCheckResult.Reachable(identity, normalized, created.pairingId, created.expiresIn, saved)
    }

    suspend fun pair(baseUrl: String, code: String, deviceName: String): PairingResult {
        val current = pending ?: return PairingResult.Failed("请重新选择服务端。", false)
        if (current.baseUrl != normalizeBaseUrl(baseUrl)) return PairingResult.Failed("配对目标已变化，请重试。", false)
        if (!code.matches(Regex("[0-9]{4}"))) return PairingResult.Failed("请输入 4 位数字验证码。", false)
        val op = current.operationId
        if (operation.get() != op || pending != current) return PairingResult.UiInvalidated
        val resolvedDeviceName = deviceName.ifBlank { current.deviceName }
        val client = clientFactory(current.baseUrl) { null }
        val result = withContext(NonCancellable) {
            withTimeout(PAIRING_COMMIT_TIMEOUT_MILLIS) {
                when (val completed = client.completePairing(current.serverId, current.pairingId, code, resolvedDeviceName)) {
                    is ApiResult.Success -> sessions.saveSession(current.serverId, current.baseUrl, resolvedDeviceName, completed.value.deviceKey, now())
                        ?.let(PairingResult::Paired)
                        ?: PairingResult.Failed("保存会话失败。", false)
                    is ApiResult.HttpError -> PairingResult.Failed(completed.message.ifBlank { "验证码无效或已锁定。" }, completed.status == 401 || completed.status == 403)
                    is ApiResult.NetworkError -> PairingResult.Failed(networkMessage(current.baseUrl, completed.message, completed.cause), false)
                    is ApiResult.ParseError -> PairingResult.Failed("配对响应无法识别。", false)
                }
            }
        }
        if (operation.get() != op || pending != current) return PairingResult.UiInvalidated
        pending = null
        return result
    }

    suspend fun restoreSession(): RestoreResult {
        if (restoreAttempted) return RestoreResult.NoSavedSession
        restoreAttempted = true
        val target = sessions.active() ?: return RestoreResult.NoSavedSession
        val key = sessions.readDeviceKey(target.serverId) ?: return RestoreResult.InvalidSavedSession(target.serverId, "会话需要重新配对。")
        return when (val result = clientFactory(target.baseUrl) { key }.listActions()) {
            is ApiResult.Success -> {
                val updated = sessions.recordAuthorized(target.serverId, target.baseUrl, target.deviceName, now()) ?: target
                RestoreResult.Restored(updated)
            }
            is ApiResult.HttpError -> {
                if (result.status == 401 || result.status == 403) sessions.markRepair(target.serverId)
                RestoreResult.InvalidSavedSession(target.serverId, sessionMessage(result.status, result.message))
            }
            is ApiResult.NetworkError -> RestoreResult.InvalidSavedSession(target.serverId, networkMessage(target.baseUrl, result.message, result.cause))
            is ApiResult.ParseError -> RestoreResult.InvalidSavedSession(target.serverId, "服务器响应无法识别。")
        }
    }
    /** 旧三键只有 identity 可达且 v2 安全提交后才删除；不可达时原值保持。 */
    suspend fun migrateLegacy(): Boolean {
        val legacy = sessions.legacyValues() ?: return false
        val normalized = normalizeBaseUrl(legacy.first) ?: return false
        val identity = when (val result = clientFactory(normalized) { null }.identity()) {
            is ApiResult.Success -> result.value
            else -> return false
        }
        return sessions.migrateLegacy(identity.serverId, normalized, legacy.third, legacy.second) != null
    }

    fun invalidate(serverId: String) { sessions.markRepair(serverId) }
    fun removeSession(serverId: String): Boolean = sessions.remove(serverId)
    fun cancelCurrent() { operation.incrementAndGet(); pending = null }
    fun session(serverId: String) = sessions.get(serverId)
    fun deviceKey(serverId: String) = sessions.readDeviceKey(serverId)

    fun normalizeInputForAndroid(address: String, port: String?): NormalizeResult {
        val rawAddress = address.trim().trimEnd('/'); val rawPort = port?.trim().orEmpty()
        if (rawAddress.isEmpty()) return NormalizeResult.Invalid("请输入服务地址。")
        val candidate = if (rawAddress.contains("://")) appendPortIfMissing(rawAddress, rawPort) else if (rawPort.isEmpty() || rawAddress.substringAfterLast('/').contains(':')) rawAddress else "$rawAddress:$rawPort"
        val normalized = normalizeBaseUrl(candidate) ?: return NormalizeResult.Invalid(lastNormalizeError)
        val uri = URI(normalized)
        return NormalizeResult.Valid(normalized, uri.host.orEmpty(), uri.port.takeIf { it != -1 })
    }
    private fun appendPortIfMissing(address: String, port: String): String { if (port.isBlank()) return address; val uri = runCatching { URI(address) }.getOrNull() ?: return address; return if (uri.port != -1 || uri.host.isNullOrBlank()) address else "${uri.scheme}://${uri.host}:$port" }
    fun normalizeForTest(baseUrl: String) = normalizeBaseUrl(baseUrl)
    fun normalizeBaseUrlForProduction(baseUrl: String) = normalizeBaseUrl(baseUrl)
    fun networkHintForTest(baseUrl: String, message: String, cause: Throwable?) = networkMessage(baseUrl, message, cause)
    private var lastNormalizeError = ""
    private fun normalizeBaseUrl(value: String): String? { val raw=value.trim().trimEnd('/'); if(raw.isEmpty()) return fail("请输入服务地址。"); val uri=runCatching { URI(if(raw.contains("://")) raw else "http://$raw") }.getOrNull() ?: return fail("服务地址格式不正确。"); val scheme=uri.scheme?.lowercase(); val host=uri.host?.trim().orEmpty(); if(scheme !in setOf("http","https") || host.isEmpty()) return fail("服务地址格式不正确。"); if(host in setOf("0.0.0.0","localhost","127.0.0.1")) return fail("请输入电脑的局域网地址。"); return "$scheme://$host${if(uri.port == -1) "" else ":${uri.port}"}" }
    private fun fail(message:String):String? { lastNormalizeError=message; return null }
    private fun connectionMessage(status:Int,message:String)=if(status==401||status==403) "会话已失效，请重新配对。" else message.ifBlank { "无法连接到服务。" }
    private fun sessionMessage(status:Int,message:String)=if(status==401||status==403) "会话已失效，请重新配对。" else message.ifBlank { "无法恢复会话。" }
    private fun networkMessage(baseUrl:String,message:String,cause:Throwable?):String { val unused=baseUrl; val detail=message.ifBlank { cause?.message.orEmpty() }; return if(detail.isBlank()) "无法连接，请确认手机与电脑在同一局域网。" else "无法连接：$detail" }
    private companion object {
        const val PAIRING_COMMIT_TIMEOUT_MILLIS = 5_000L
    }
}
