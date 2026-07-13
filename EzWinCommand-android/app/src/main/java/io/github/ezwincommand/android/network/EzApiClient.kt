package io.github.ezwincommand.android.network

import io.github.ezwincommand.android.AppConstants
import io.github.ezwincommand.android.model.ActionPlugin
import io.github.ezwincommand.android.model.AuthorizeResult
import io.github.ezwincommand.android.model.CommandResult
import io.github.ezwincommand.android.model.CommandStatus
import io.github.ezwincommand.android.model.DeviceInfo
import io.github.ezwincommand.android.model.AudioEndpoint
import io.github.ezwincommand.android.model.MediaPlayback
import io.github.ezwincommand.android.model.MediaState
import io.github.ezwincommand.android.model.PairingStatus
import io.github.ezwincommand.android.model.PingResponse
import io.github.ezwincommand.android.model.SubAction
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.withContext
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.io.Closeable
import java.io.InputStream
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference

sealed interface MediaEventTermination {
    data object Eof : MediaEventTermination
    data class NetworkError(val message: String) : MediaEventTermination
    data class HttpError(val status: Int, val message: String) : MediaEventTermination
    data object ClosedByCaller : MediaEventTermination
}

private class MediaEventConnection(
    private val callerClosed: AtomicBoolean,
    private val connection: AtomicReference<HttpURLConnection?>,
    private val job: AtomicReference<Job?>,
    private val onCallerClosed: () -> Unit,
) : Closeable {
    override fun close() {
        if (callerClosed.compareAndSet(false, true)) {
            onCallerClosed()
            connection.get()?.disconnect()
            job.get()?.cancel()
        }
    }
}

open class EzApiClient(
    baseUrl: String,
    private val deviceKeyProvider: () -> String?,
    private val timeoutMillis: Int = 5_000,
) {
    companion object {
        const val COMMAND_READ_TIMEOUT_MILLIS: Int = 5_000
        private val COMMAND_STATUSES = setOf("queued", "running", "succeeded", "failed")
    }
    internal val normalizedBaseUrl: String = normalizeBaseUrl(baseUrl)
    private val mediaIoScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

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
        body = JSONObject().put("action", action).put("params", mapToJsonObject(params)),
        successCodes = setOf(200, 202),
        parser = { body ->
            val id = body.optStringOrNull("command_id")
            CommandResult(
                success = body.optBoolean("success", id == null),
                message = body.optString("message", ""),
                data = jsonObjectToMap(body.optJSONObject("data") ?: JSONObject()),
                commandId = id,
                status = body.optStringOrNull("status"),
            )
        },
    )

    open suspend fun getCommandStatus(commandId: String): ApiResult<CommandStatus> = request(
        method = "GET",
        path = "/api/commands/${encodePathSegment(commandId)}",
        authenticated = true,
        parser = { body ->
            val rawStatus = body.optStringOrNull("status") ?: throw IllegalArgumentException("缺少 status")
            if (rawStatus !in COMMAND_STATUSES) throw IllegalArgumentException("未知 status: $rawStatus")
            CommandStatus(
                commandId = body.optString("command_id", commandId),
                status = rawStatus,
                message = body.optStringOrNull("message"),
                data = body.optJSONObject("data")?.let { jsonObjectToMap(it) },
                error = body.optJSONObject("error")?.let { jsonObjectToMap(it) },
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

    open suspend fun renameDevice(deviceKey: String, name: String): ApiResult<Boolean> = request(
        method = "PATCH",
        path = "/api/devices/${encodePathSegment(deviceKey)}",
        authenticated = true,
        body = JSONObject().put("name", name),
        parser = { body -> body.optBoolean("success", false) },
    )

    open suspend fun getMediaState(): ApiResult<MediaState> = request(
        method = "GET",
        path = "/api/media/state",
        authenticated = true,
        parser = ::parseMediaState,
    )

    open suspend fun getMediaCover(path: String): ApiResult<ByteArray> = withContext(Dispatchers.IO) {
        val connection = try {
            openConnection(path).apply {
                requestMethod = "GET"
                connectTimeout = timeoutMillis
                readTimeout = timeoutMillis
                setBearer()
            }
        } catch (t: Throwable) {
            return@withContext ApiResult.NetworkError("无法建立封面请求", t)
        }
        try {
            val status = connection.responseCode
            if (status !in 200..299) {
                val message = connection.errorStream?.readTextUtf8().orEmpty().ifBlank { "HTTP $status" }
                ApiResult.HttpError(status, message)
            } else {
                ApiResult.Success(connection.inputStream.use { it.readBytes() })
            }
        } catch (t: Throwable) {
            ApiResult.NetworkError("封面下载失败", t)
        } finally {
            connection.disconnect()
        }
    }

    open fun openMediaEvents(
        since: Long,
        onEvent: (MediaState) -> Unit,
        onClosed: (MediaEventTermination) -> Unit,
    ): Closeable {
        require(since >= 0) { "since 不能为负数" }
        val callerClosed = AtomicBoolean(false)
        val terminated = AtomicBoolean(false)
        val connectionRef = AtomicReference<HttpURLConnection?>()
        val jobRef = AtomicReference<Job?>()
        fun terminate(reason: MediaEventTermination) {
            if (terminated.compareAndSet(false, true)) onClosed(reason)
        }
        val handle = MediaEventConnection(callerClosed, connectionRef, jobRef) { terminate(MediaEventTermination.ClosedByCaller) }
        val job = mediaIoScope.launch {
            var connection: HttpURLConnection? = null
            try {
                connection = openConnection("/api/media/events?since=$since").apply {
                    requestMethod = "GET"
                    connectTimeout = timeoutMillis
                    readTimeout = 0
                    setRequestProperty("Accept", "text/event-stream")
                    setBearer()
                }
                connectionRef.set(connection)
                if (callerClosed.get()) return@launch
                val status = connection.responseCode
                if (status !in 200..299) {
                    val raw = connection.errorStream?.readTextUtf8().orEmpty()
                    val message = raw.toJsonObjectOrNull()?.optString("message")?.takeIf { it.isNotBlank() }
                        ?: raw.ifBlank { "HTTP $status" }
                    terminate(MediaEventTermination.HttpError(status, message))
                    return@launch
                }
                connection.inputStream.bufferedReader(Charsets.UTF_8).use { reader ->
                    var event: String? = null
                    var eventId: Long? = null
                    val data = ArrayList<String>()
                    while (true) {
                        val line = reader.readLine() ?: break
                        if (line.isEmpty()) {
                            if (event == "media" && data.isNotEmpty()) {
                                val id = eventId?.takeIf { it >= 0 } ?: throw IllegalArgumentException("media 事件缺少或 id 非法")
                                val state = parseMediaState(JSONObject(data.joinToString("\n")))
                                require(id == state.revision) { "media 事件 id 与 revision 不一致" }
                                onEvent(state)
                            }
                            event = null
                            eventId = null
                            data.clear()
                        } else if (!line.startsWith(":")) {
                            val separator = line.indexOf(':')
                            val field = if (separator < 0) line else line.substring(0, separator)
                            val value = if (separator < 0) "" else line.substring(separator + 1).removePrefix(" ")
                            when (field) {
                                "id" -> eventId = value.toLongOrNull() ?: throw IllegalArgumentException("非法 SSE id")
                                "event" -> event = value
                                "data" -> data.add(value)
                            }
                        }
                    }
                }
                terminate(MediaEventTermination.Eof)
            } catch (t: Throwable) {
                if (!callerClosed.get()) terminate(MediaEventTermination.NetworkError("媒体事件连接失败"))
            } finally {
                connectionRef.compareAndSet(connection, null)
                connection?.disconnect()
                if (callerClosed.get()) terminate(MediaEventTermination.ClosedByCaller)
            }
        }
        jobRef.set(job)
        if (callerClosed.get()) job.cancel()
        return handle
    }

    private suspend fun <T> request(
        method: String,
        path: String,
        authenticated: Boolean,
        readTimeoutMillis: Int = timeoutMillis,
        body: JSONObject? = null,
        successCodes: Set<Int> = setOf(200),
        parser: (JSONObject) -> T,
    ): ApiResult<T> = withContext(Dispatchers.IO) {
        val connection = try {
            openConnection(path).apply {
                requestMethod = method
                readTimeout = readTimeoutMillis
                connectTimeout = timeoutMillis
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

    internal open fun openConnection(path: String): HttpURLConnection {
        val url = URL(normalizedBaseUrl + ensureLeadingSlash(path))
        return url.openConnection() as HttpURLConnection
    }

    private fun HttpURLConnection.setBearer() {
        deviceKeyProvider()?.trim()?.takeIf { it.isNotEmpty() }?.let {
            setRequestProperty("Authorization", "Bearer $it")
        }
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

    internal fun parseMediaState(body: JSONObject): MediaState {
        fun required(name: String): Any = body.opt(name).takeUnless { it == null || it === JSONObject.NULL }
            ?: throw IllegalArgumentException("缺少 $name")
        val revisionValue = required("revision")
        require(revisionValue is Number) { "revision 必须是整数" }
        val revision = revisionValue.toLong()
        require(revisionValue.toDouble() == revision.toDouble()) { "revision 必须是整数" }
        val available = required("available") as? Boolean ?: throw IllegalArgumentException("available 必须是布尔值")
        val volumeValue = required("volume")
        require(volumeValue is Number) { "volume 必须是整数" }
        val volume = volumeValue.toInt()
        require(volumeValue.toDouble() == volume.toDouble() && volume in 0..100) { "volume 必须是 0..100 整数" }
        fun nullableString(name: String): String? = when (val value = body.opt(name)) {
            null, JSONObject.NULL -> null
            is String -> value
            else -> throw IllegalArgumentException("$name 必须是字符串或 null")
        }
        fun endpoints(name: String): List<AudioEndpoint> {
            val array = required(name) as? JSONArray ?: throw IllegalArgumentException("$name 必须是数组")
            return buildList {
                for (index in 0 until array.length()) {
                    val endpoint = array.optJSONObject(index) ?: throw IllegalArgumentException("$name 元素必须是对象")
                    val id = endpoint.opt("id") as? String ?: throw IllegalArgumentException("endpoint 缺少 id")
                    val endpointName = endpoint.opt("name") as? String ?: throw IllegalArgumentException("endpoint 缺少 name")
                    require(id.isNotEmpty()) { "endpoint id 不能为空" }
                    add(AudioEndpoint(id, endpointName))
                }
            }
        }
        val playback = required("playback") as? String ?: throw IllegalArgumentException("playback 必须是字符串")
        return MediaState(
            revision = revision,
            available = available,
            title = nullableString("title"),
            artist = nullableString("artist"),
            playback = MediaPlayback.fromWire(playback),
            cover = nullableString("cover"),
            volume = volume,
            renderDevices = endpoints("render_devices"),
            captureDevices = endpoints("capture_devices"),
            selectedRenderId = nullableString("selected_render_id"),
            selectedCaptureId = nullableString("selected_capture_id"),
            error = nullableString("error"),
        )
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
