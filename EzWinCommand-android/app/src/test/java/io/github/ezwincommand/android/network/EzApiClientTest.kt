package io.github.ezwincommand.android.network

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class EzApiClientTest {
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
    fun `maps http error status and body message`() {
        val result = ApiResult.HttpError(403, "配对码无效或已锁定")
        assertEquals(403, result.status)
        assertEquals("配对码无效或已锁定", result.message)
    }
}
