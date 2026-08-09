package io.github.ezwincommand.android.ui.control

import io.github.ezwincommand.android.model.CommandResult
import io.github.ezwincommand.android.network.ApiResult
import io.github.ezwincommand.android.network.EzApiClient
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertTrue
import org.junit.Assert.assertEquals
import org.junit.Test

class MediaCommandRoutingTest {
    @Test
    fun `set volume wire contains only sub action and volume`() = runBlocking {
        var capturedAction = ""
        var capturedParams: Map<String, Any?> = emptyMap()
        val client = object : EzApiClient("http://127.0.0.1:8080", { "key" }) {
            override suspend fun executeCommand(action: String, params: Map<String, Any?>): ApiResult<CommandResult> {
                capturedAction = action
                capturedParams = params
                return ApiResult.Success(CommandResult(true, "ok", emptyMap()))
            }
        }
        val controller = ControlController(client, onAuthInvalid = {})
        controller.sendMediaAction("set_volume", 37)
        assertEquals("media", capturedAction)
        assertEquals(mapOf("sub_action" to "set_volume", "volume" to 37), capturedParams)
        assertEquals(2, capturedParams.size)
    }
    @Test
    fun `playback commands keep feedback and skip post-command refresh`() = runBlocking {
        val playbackActions = listOf("play_pause", "prev", "next")
        val sent = mutableListOf<Pair<String, Any?>>()
        var refreshes = 0

        playbackActions.forEach { subAction ->
            val result = sendMediaActionWithRefreshPolicy(
                subAction = subAction,
                value = null,
                send = { action, value ->
                    sent += (action to value)
                    CommandResult(true, "ok", emptyMap())
                },
                refresh = { refreshes += 1 },
            )
            assertTrue(result.success)
            assertEquals("ok", result.message)
        }

        assertEquals(playbackActions, sent.map { it.first })
        assertTrue(sent.all { it.second == null })
        assertEquals(0, refreshes)

        val failed = sendMediaActionWithRefreshPolicy(
            subAction = "next",
            value = null,
            send = { _, _ -> CommandResult(false, "播放器拒绝了媒体操作", emptyMap()) },
            refresh = { refreshes += 1 },
        )
        assertTrue(!failed.success)
        assertEquals("播放器拒绝了媒体操作", failed.message)
        assertEquals(0, refreshes)

        sendMediaActionWithRefreshPolicy(
            subAction = "set_volume",
            value = 37,
            send = { _, _ -> CommandResult(true, "ok", emptyMap()) },
            refresh = { refreshes += 1 },
        )
        assertEquals(1, refreshes)
    }

    @Test
    fun `device command wires contain only sub action and endpoint id`() = runBlocking {
        val captured = mutableListOf<Pair<String, Map<String, Any?>>>()
        val client = object : EzApiClient("http://127.0.0.1:8080", { "key" }) {
            override suspend fun executeCommand(action: String, params: Map<String, Any?>): ApiResult<CommandResult> {
                captured += action to params
                return ApiResult.Success(CommandResult(true, "ok", emptyMap()))
            }
        }
        val controller = ControlController(client, onAuthInvalid = {})
        controller.sendMediaAction("set_output_device", "output-id")
        controller.sendMediaAction("set_input_device", "input-id")
        assertEquals(
            listOf(
                "media" to mapOf("sub_action" to "set_output_device", "endpoint_id" to "output-id"),
                "media" to mapOf("sub_action" to "set_input_device", "endpoint_id" to "input-id"),
            ),
            captured,
        )
        assertEquals(listOf(2, 2), captured.map { it.second.size })
    }
}
