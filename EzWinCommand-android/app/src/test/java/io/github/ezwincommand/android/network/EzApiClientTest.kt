package io.github.ezwincommand.android.network
import io.github.ezwincommand.android.AppConstants

import kotlinx.coroutines.runBlocking
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.InputStream
import java.net.HttpURLConnection
import java.net.URL

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlinx.coroutines.Job
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.withTimeout

class EzApiClientTest {
    private class JsonConnection(private val body: String) : HttpURLConnection(URL("http://192.168.1.10:8080/test")) {
        private val requestProperties = mutableMapOf<String, String>()

        override fun setRequestProperty(key: String, value: String) {
            requestProperties[key] = value
        }

        override fun getRequestProperty(key: String): String? = requestProperties[key]
        override fun getResponseCode(): Int = 200
        override fun getInputStream(): InputStream = ByteArrayInputStream(body.toByteArray())
        override fun getOutputStream() = ByteArrayOutputStream()
        override fun disconnect() = Unit
        override fun usingProxy() = false
        override fun connect() = Unit
    }
    private class SseConnection(private val body: String) : HttpURLConnection(URL("http://127.0.0.1:8080/events")) {
        override fun getResponseCode(): Int = 200
        override fun getInputStream(): InputStream = ByteArrayInputStream(body.toByteArray())
        override fun getOutputStream() = ByteArrayOutputStream()
        override fun disconnect() = Unit
        override fun usingProxy() = false
        override fun connect() = Unit
    }
    @Test
    fun `normalizes baseUrl and preserves port`() {
        val client = EzApiClient(" 192.168.1.10:8080/ ", deviceKeyProvider = { null })
        assertEquals("http://192.168.1.10:8080", client.normalizedBaseUrl)
    }

    @Test
    fun `rejects empty baseUrl`() {
        try {
            EzApiClient("   ", deviceKeyProvider = { null })
            throw AssertionError("expected failure")
        } catch (expected: IllegalArgumentException) {
            assertTrue(expected.message!!.contains("baseUrl"))
        }
    }

    @Test
    fun `rejects public cleartext host`() {
        try {
            EzApiClient("http://example.com:8080", deviceKeyProvider = { null })
            throw AssertionError("expected failure")
        } catch (expected: IllegalArgumentException) {
            assertTrue(expected.message!!.contains("HTTP"))
        }
    }

    @Test
    fun `openConnection builds normalized url`() {
        val client = EzApiClient("http://127.0.0.1:8080", deviceKeyProvider = { null })
        val connection = client.openConnection("/ping")
        assertEquals("http://127.0.0.1:8080/ping", connection.url.toString())
        connection.disconnect()
    }

    @Test
    fun `command timeout constant is five seconds while default remains five`() {
        assertEquals(5_000, EzApiClient.COMMAND_READ_TIMEOUT_MILLIS)
        val field = EzApiClient::class.java.getDeclaredField("timeoutMillis").apply { isAccessible = true }
        assertEquals(5_000, field.getInt(EzApiClient("http://127.0.0.1:8080", deviceKeyProvider = { null })))
    }
    @Test
    fun `maps http error status and body message`() {
        val result = ApiResult.HttpError(403, "配对码无效或已锁定")
        assertEquals(403, result.status)
        assertEquals("配对码无效或已锁定", result.message)
    }

    @Test
    fun `identity reports v2 and carries the protocol marker`() = runBlocking {
        val connection = JsonConnection(
            """{"protocol_version":2,"server_id":"00000000-0000-4000-8000-000000000001","display_name":"PC"}""",
        )
        val client = object : EzApiClient("http://192.168.1.10:8080", { null }) {
            override fun openConnection(path: String): HttpURLConnection = connection
        }

        val result = client.identity()

        assertTrue(result is ApiResult.Success)
        assertEquals("2", connection.getRequestProperty(AppConstants.PROTOCOL_HEADER))
        client.close()
    }

    @Test
    fun `identity rejects an incompatible protocol before protected work`() = runBlocking {
        val connection = JsonConnection(
            """{"protocol_version":1,"server_id":"00000000-0000-4000-8000-000000000001","display_name":"PC"}""",
        )
        val client = object : EzApiClient("http://192.168.1.10:8080", { null }) {
            override fun openConnection(path: String): HttpURLConnection = connection
        }

        val result = client.identity()

        assertTrue(result is ApiResult.ParseError)
        assertTrue((result as ApiResult.ParseError).cause is UnsupportedProtocolException)
        client.close()
    }

    @Test
    fun `protected requests carry the v2 marker`() = runBlocking {
        val connection = JsonConnection("""{"actions":[]}""")
        val client = object : EzApiClient("http://192.168.1.10:8080", { "credential-for-test-only" }) {
            override fun openConnection(path: String): HttpURLConnection = connection
        }

        val result = client.listActions()

        assertTrue(result is ApiResult.Success)
        assertEquals("2", connection.getRequestProperty(AppConstants.PROTOCOL_HEADER))
        client.close()
    }
    @Test
    fun `complete pairing extracts FastAPI detail as short message`() = runBlocking {
        val client = object : EzApiClient("http://192.168.1.10:8080", deviceKeyProvider = { null }) {
            override fun openConnection(path: String): HttpURLConnection = object : HttpURLConnection(URL("http://192.168.1.10:8080$path")) {
                override fun getResponseCode() = 401
                override fun getErrorStream(): InputStream = ByteArrayInputStream("{\"detail\":\"未授权\"}".toByteArray())
                override fun getOutputStream() = ByteArrayOutputStream()
                override fun disconnect() = Unit
                override fun usingProxy() = false
                override fun connect() = Unit
            }
        }

        val result = client.completePairing("server-1", "pair-1", "1234")

        assertEquals(ApiResult.HttpError(401, "未授权"), result)
        client.close()
    }

    @Test
    fun `media SSE authorization revocation is surfaced as terminal termination`() = runBlocking {
        val termination = CompletableDeferred<MediaEventTermination>()
        val connection = SseConnection("event: authorization_revoked\ndata: {}\n\n")
        val client = object : EzApiClient("http://127.0.0.1:8080", { "credential-for-test-only" }) {
            override fun openConnection(path: String): HttpURLConnection = connection
        }

        val handle = client.openMediaEvents(0, {}, { termination.complete(it) })

        assertEquals(
            MediaEventTermination.AuthorizationRevoked,
            withTimeout(1_000) { termination.await() },
        )
        handle.close()
        client.close()
    }

    @Test
    fun `close cancels media scope and is idempotent`() {
        val client = EzApiClient("http://127.0.0.1:8080", deviceKeyProvider = { null })
        val field = EzApiClient::class.java.getDeclaredField("mediaIoJob").apply { isAccessible = true }
        val job = field.get(client) as Job
        assertTrue(job.isActive)
        client.close()
        client.close()
        assertFalse(job.isActive)
        try {
            client.openMediaEvents(0, {}, {})
            throw AssertionError("expected closed client failure")
        } catch (expected: IllegalArgumentException) {
            assertTrue(expected.message!!.contains("关闭"))
        }
    }

}
