package io.github.ezwincommand.android.network

import io.github.ezwincommand.android.AppConstants
import io.github.ezwincommand.android.model.ActionPlugin
import io.github.ezwincommand.android.model.AuthorizeResult
import io.github.ezwincommand.android.model.CommandResult
import io.github.ezwincommand.android.model.DeviceInfo
import io.github.ezwincommand.android.model.PairingStatus
import io.github.ezwincommand.android.model.PingResponse
import io.github.ezwincommand.android.model.SubAction
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.InputStream
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

open class EzApiClient(
    baseUrl: String,
    private val deviceKeyProvider: () -> String?,
    private val timeoutMillis: Int = 5_000,
) {
    internal val normalizedBaseUrl: String = normalizeBaseUrl(baseUrl)

    open suspend fun ping(): ApiResult<PingResponse> = request(
        method = "GET",
        path = "/ping",
        authenticated = false,
        parser = { body -> PingResponse(status = body.optString("status", "")) },
    )

    open suspend fun pairingStatus(): ApiResult<PairingStatus> = request(
        method = "GET",
        path = "/api/pairing-code",
        authenticated = false,
        parser = { body ->
            PairingStatus(
                hasCode = body.optBoolean("has_code", false),
                hasDevices = body.optBoolean("has_devices", false),
                expiresIn = body.optInt("expires_in", 0),
            )
        },
    )

    open suspend fun authorize(token: String, name: String): ApiResult<AuthorizeResult> = request(
        method = "POST",
        path = "/api/authorize",
        authenticated = false,
        body = JSONObject()
            .put("token", token)
            .put("name", name),
        successCodes = setOf(201),
        parser = { body ->
            AuthorizeResult(
                success = body.optBoolean("success", false),
                deviceKey = body.optStringOrNull("device_key"),
                message = body.optStringOrNull("message"),
            )
        },
    )

    open suspend fun listActions(): ApiResult<List<ActionPlugin>> = request(
        method = "GET",
        path = "/api/actions",
        authenticated = true,
        parser = { body -> parseActionPlugins(body.optJSONArray("actions")) },
    )

    open suspend fun executeCommand(action: String, params: Map<String, Any?> = emptyMap()): ApiResult<CommandResult> = request(
        method = "POST",
        path = "/api/command",
        authenticated = true,
        body = JSONObject()
            .put("action", action)
            .put("params", mapToJsonObject(params)),
        parser = { body ->
            CommandResult(
                success = body.optBoolean("success", false),
                message = body.optString("message", ""),
                data = jsonObjectToMap(body.optJSONObject("data") ?: JSONObject()),
            )
        },
    )

    open suspend fun listDevices(): ApiResult<List<DeviceInfo>> = request(
        method = "GET",
        path = "/api/devices",
        authenticated = true,
        parser = { body -> parseDevices(body.optJSONArray("devices")) },
    )

    open suspend fun revokeDevice(deviceKey: String): ApiResult<Boolean> = request(
        method = "DELETE",
        path = "/api/devices/${encodePathSegment(deviceKey)}",
        authenticated = true,
        parser = { body -> body.optBoolean("success", false) },
    )

    private suspend fun <T> request(
        method: String,
        path: String,
        authenticated: Boolean,
        body: JSONObject? = null,
        successCodes: Set<Int> = setOf(200),
        parser: (JSONObject) -> T,
    ): ApiResult<T> = withContext(Dispatchers.IO) {
        val connection = try {
            openConnection(path).apply {
                requestMethod = method
                connectTimeout = timeoutMillis
                readTimeout = timeoutMillis
                doInput = true
                if (body != null) {
                    doOutput = true
                    setRequestProperty("Content-Type", "application/json; charset=utf-8")
                }
                if (authenticated) {
                    deviceKeyProvider()?.trim()?.takeIf { it.isNotEmpty() }?.let { key ->
                        setRequestProperty("Authorization", "Bearer $key")
                    }
                }
            }
        } catch (t: Throwable) {
            return@withContext ApiResult.NetworkError("无法建立请求", t)
        }

        try {
            body?.let { payload ->
                connection.outputStream.use { output ->
                    output.write(payload.toString().toByteArray(Charsets.UTF_8))
                }
            }

            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            val responseText = stream?.readTextUtf8().orEmpty()
            val responseJson = responseText.toJsonObjectOrNull()

            if (code !in successCodes) {
                val message = responseJson?.optString("message", responseText.ifBlank { connection.responseMessage }.ifBlank { "HTTP $code" })
                    ?: responseText.ifBlank { connection.responseMessage }.ifBlank { "HTTP $code" }
                return@withContext ApiResult.HttpError(code, message)
            }

            val parsed = try {
                parser(responseJson ?: JSONObject())
            } catch (t: Throwable) {
                return@withContext ApiResult.ParseError("解析响应失败", t)
            }
            ApiResult.Success(parsed)
        } catch (t: Throwable) {
            ApiResult.NetworkError("网络请求失败", t)
        } finally {
            connection.disconnect()
        }
    }

    internal fun openConnection(path: String): HttpURLConnection {
        val url = URL(normalizedBaseUrl + ensureLeadingSlash(path))
        return url.openConnection() as HttpURLConnection
    }

    private fun normalizeBaseUrl(value: String): String {
        val candidate = value.trim().ifBlank { throw IllegalArgumentException("baseUrl 不能为空") }
        val withScheme = if (candidate.contains("://")) candidate else "${AppConstants.DEFAULT_SCHEME}://$candidate"
        val parsed = URL(withScheme.trimEnd('/'))
        val host = parsed.host.trim()
        require(host.isNotEmpty()) { "baseUrl 缺少 host" }
        require(parsed.protocol != "http" || isTrustedLanHost(host)) { "HTTP 仅允许可信局域网地址" }
        return buildString {
            append(parsed.protocol)
            append("://")
            append(host)
            if (parsed.port != -1) {
                append(":")
                append(parsed.port)
            }
        }.trimEnd('/')
    }

    private fun isTrustedLanHost(host: String): Boolean {
        val lower = host.lowercase()
        if (lower == "localhost") return true
        val parts = lower.split('.')
        if (parts.size != 4) return false
        val octets = parts.map { it.toIntOrNull() ?: return false }
        return octets[0] == 10 ||
            (octets[0] == 172 && octets[1] in 16..31) ||
            (octets[0] == 192 && octets[1] == 168) ||
            (octets[0] == 127)
    }

    private fun ensureLeadingSlash(path: String): String = if (path.startsWith('/')) path else "/$path"

    private fun encodePathSegment(segment: String): String = URLEncoder.encode(segment, Charsets.UTF_8.name()).replace("+", "%20")

    private fun InputStream.readTextUtf8(): String = bufferedReader(Charsets.UTF_8).use { it.readText() }

    private fun String.toJsonObjectOrNull(): JSONObject? = try {
        if (isBlank()) null else JSONObject(this)
    } catch (_: Throwable) {
        null
    }

    internal fun parseActionPlugins(array: JSONArray?): List<ActionPlugin> {
        if (array == null) return emptyList()
        return buildList {
            for (i in 0 until array.length()) {
                val obj = array.optJSONObject(i) ?: continue
                add(
                    ActionPlugin(
                        name = obj.optString("name", ""),
                        label = obj.optString("label", obj.optString("name", "")),
                        description = obj.optString("description", ""),
                        version = obj.optString("version", ""),
                        subActions = parseSubActions(obj),
                    ),
                )
            }
        }
    }

    private fun parseSubActions(obj: JSONObject): List<SubAction> {
        val primary = obj.optJSONArray("sub_actions") ?: obj.optJSONArray("actions")
        if (primary == null) return emptyList()
        return buildList {
            for (i in 0 until primary.length()) {
                val child = primary.optJSONObject(i) ?: continue
                add(
                    SubAction(
                        id = child.optString("id", child.optString("name", "")),
                        label = child.optString("label", child.optString("name", "")),
                    ),
                )
            }
        }
    }

    private fun parseDevices(array: JSONArray?): List<DeviceInfo> {
        if (array == null) return emptyList()
        return buildList {
            for (i in 0 until array.length()) {
                val obj = array.optJSONObject(i) ?: continue
                add(
                    DeviceInfo(
                        key = obj.optString("key", obj.optString("device_key", "")),
                        name = obj.optString("name", ""),
                        createdAt = obj.optStringOrNull("created_at"),
                        lastSeen = obj.optStringOrNull("last_seen"),
                    ),
                )
            }
        }
    }

    private fun JSONObject.optStringOrNull(name: String): String? = if (has(name) && !isNull(name)) optString(name) else null

    private fun mapToJsonObject(map: Map<String, Any?>): JSONObject {
        val json = JSONObject()
        for ((key, value) in map) {
            json.put(key, toJsonValue(value))
        }
        return json
    }

    private fun toJsonValue(value: Any?): Any? = when (value) {
        null -> JSONObject.NULL
        is JSONObject, is JSONArray, is Boolean, is Int, is Long, is Double, is Float, is String -> value
        is Map<*, *> -> JSONObject().apply {
            for ((k, v) in value) {
                put(k.toString(), toJsonValue(v))
            }
        }
        is Iterable<*> -> JSONArray().apply {
            for (item in value) put(toJsonValue(item))
        }
        else -> value.toString()
    }

    private fun jsonObjectToMap(obj: JSONObject): Map<String, Any?> {
        val result = LinkedHashMap<String, Any?>()
        val keys = obj.keys()
        while (keys.hasNext()) {
            val key = keys.next()
            result[key] = fromJsonValue(obj.opt(key))
        }
        return result
    }

    private fun fromJsonValue(value: Any?): Any? = when (value) {
        JSONObject.NULL -> null
        is JSONObject -> jsonObjectToMap(value)
        is JSONArray -> buildList {
            for (i in 0 until value.length()) {
                add(fromJsonValue(value.opt(i)))
            }
        }
        else -> value
    }
}
