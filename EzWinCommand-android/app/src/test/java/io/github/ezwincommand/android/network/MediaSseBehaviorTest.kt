package io.github.ezwincommand.android.network

import java.io.ByteArrayInputStream
import java.io.Closeable
import java.io.InputStream
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class MediaSseBehaviorTest {
    @Test
    fun `parses id event and multiline data then reports eof once`() {
        val body = """id: 7
event: media
data: {"revision":7,"available":true,"title":"Song","artist":"Artist","playback":"playing",
data: "cover":null,"volume":37,"render_devices":[],"capture_devices":[],"selected_render_id":null,"selected_capture_id":null,"error":null}

"""
        val client = StubClient(200, body)
        val revisions = mutableListOf<Long>()
        val reasons = mutableListOf<MediaEventTermination>()
        val done = CountDownLatch(1)
        client.openMediaEvents(0, { revisions += it.revision }, { reasons += it; done.countDown() })
        assertTrue(done.await(2, TimeUnit.SECONDS))
        assertEquals(listOf(7L), revisions)
        assertEquals(listOf(MediaEventTermination.Eof), reasons)
    }

    @Test
    fun `http error remains http termination and closes once`() {
        val client = StubClient(401, "{\"message\":\"授权失效\"}")
        val count = AtomicInteger()
        var reason: MediaEventTermination? = null
        val done = CountDownLatch(1)
        client.openMediaEvents(0, {}, { reason = it; count.incrementAndGet(); done.countDown() })
        assertTrue(done.await(2, TimeUnit.SECONDS))
        assertEquals(MediaEventTermination.HttpError(401, "授权失效"), reason)
        assertEquals(1, count.get())
    }

    @Test
    fun `read failure reports network error once`() {
        val count = AtomicInteger()
        var reason: MediaEventTermination? = null
        val done = CountDownLatch(1)
        ThrowingClient().openMediaEvents(0, {}, { reason = it; count.incrementAndGet(); done.countDown() })
        assertTrue(done.await(2, TimeUnit.SECONDS))
        assertTrue(reason is MediaEventTermination.NetworkError)
        assertEquals(1, count.get())
    }

    @Test
    fun `caller close reports closed by caller exactly once`() {
        val client = StubClient(200, "", blocking = true)
        val count = AtomicInteger()
        var reason: MediaEventTermination? = null
        val done = CountDownLatch(1)
        val handle: Closeable = client.openMediaEvents(0, {}, { reason = it; count.incrementAndGet(); done.countDown() })
        handle.close()
        assertTrue(done.await(2, TimeUnit.SECONDS))
        assertEquals(MediaEventTermination.ClosedByCaller, reason)
        assertEquals(1, count.get())
    }

    private class ThrowingClient : EzApiClient("http://127.0.0.1:8080", { "key" }) {
        override fun openConnection(path: String): HttpURLConnection = object : HttpURLConnection(URL("http://127.0.0.1$path")) {
            override fun getResponseCode() = 200
            override fun getInputStream(): InputStream = throw java.io.IOException("read failed")
            override fun disconnect() = Unit
            override fun usingProxy() = false
            override fun connect() = Unit
        }
    }

    private class StubClient(private val status: Int, private val responseBody: String, private val blocking: Boolean = false) : EzApiClient("http://127.0.0.1:8080", { "key" }) {
        override fun openConnection(path: String): HttpURLConnection = object : HttpURLConnection(URL("http://127.0.0.1$path")) {
            override fun getResponseCode() = status
            override fun getInputStream(): InputStream = if (blocking) object : InputStream() {
                @Volatile private var closed = false
                override fun read(): Int { while (!closed) Thread.sleep(10); return -1 }
                override fun close() { closed = true }
            } else ByteArrayInputStream(responseBody.toByteArray())
            override fun getErrorStream(): InputStream? = if (status >= 400) ByteArrayInputStream(responseBody.toByteArray()) else null
            override fun disconnect() = Unit
            override fun usingProxy() = false
            override fun connect() = Unit
        }
    }
}
