package io.github.ezwincommand.android.network

import io.github.ezwincommand.android.model.MediaPlayback
import org.json.JSONObject
import org.junit.Assert.assertEquals
import kotlin.test.assertFailsWith
import org.junit.Test

class MediaApiClientTest {
    private val client = EzApiClient("http://127.0.0.1:8080", { "device-key" })

    @Test
    fun `strict media state parses complete wire`() {
        val state = client.parseMediaState(JSONObject(validState()))
        assertEquals(7L, state.revision)
        assertEquals(37, state.volume)
        assertEquals(MediaPlayback.PLAYING, state.playback)
        assertEquals("render-1", state.renderDevices.single().id)
        assertEquals("/api/media/cover/token", state.cover)
    }

    @Test
    fun `strict media state rejects missing revision`() {
        val json = JSONObject(validState()).apply { remove("revision") }
        assertFailsWith<IllegalArgumentException> { client.parseMediaState(json) }
    }

    @Test
    fun `strict media state rejects unknown playback and out of range volume`() {
        assertFailsWith<IllegalArgumentException> {
            client.parseMediaState(JSONObject(validState()).put("playback", "buffering"))
        }
        assertFailsWith<IllegalArgumentException> {
            client.parseMediaState(JSONObject(validState()).put("volume", 101))
        }
    }

    private fun validState() = """{
        "revision":7,"available":true,"title":"Song","artist":"Artist",
        "playback":"playing","cover":"/api/media/cover/token","volume":37,
        "render_devices":[{"id":"render-1","name":"Speakers"}],
        "capture_devices":[{"id":"capture-1","name":"Mic"}],
        "selected_render_id":"render-1","selected_capture_id":"capture-1","error":null
    }"""
}
