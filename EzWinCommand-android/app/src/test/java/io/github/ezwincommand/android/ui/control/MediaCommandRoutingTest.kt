package io.github.ezwincommand.android.ui.control

import io.github.ezwincommand.android.model.CommandResult
import io.github.ezwincommand.android.network.ApiResult
import io.github.ezwincommand.android.network.EzApiClient
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
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
        controller.sendMediaAction(MediaAction.SetVolume(37))
        assertEquals("media", capturedAction)
        assertEquals(mapOf("sub_action" to "set_volume", "volume" to 37), capturedParams)
        assertEquals(2, capturedParams.size)
    }
    @Test
    fun `media commands keep wire feedback and do not request post-command refresh`() = runBlocking {
        val sent = mutableListOf<Pair<String, String>>()
        var refreshes = 0
        var failSubAction: String? = null
        val client = object : EzApiClient("http://127.0.0.1:8080", { "key" }) {
            override suspend fun executeCommand(action: String, params: Map<String, Any?>): ApiResult<CommandResult> {
                val subAction = params["sub_action"] as String
                sent += action to subAction
                val failed = subAction == failSubAction
                return ApiResult.Success(CommandResult(!failed, if (failed) "媒体操作失败" else "ok", emptyMap()))
            }

            override suspend fun refreshMediaState(): ApiResult<io.github.ezwincommand.android.model.MediaState> {
                refreshes += 1
                return ApiResult.Success(io.github.ezwincommand.android.model.MediaState.LOADING)
            }
        }
        val controller = ControlController(client, onAuthInvalid = {})
        val commands = listOf(
            MediaAction.PlayPause to "play_pause",
            MediaAction.Previous to "prev",
            MediaAction.Next to "next",
            MediaAction.SetVolume(37) to "set_volume",
            MediaAction.SetOutputDevice("output-id") to "set_output_device",
            MediaAction.SetInputDevice("input-id") to "set_input_device",
        )

        commands.forEach { (action, _) ->
            val result = controller.sendMediaAction(action)
            assertTrue(result.success)
            assertEquals("ok", result.message)
        }

        assertEquals(
            commands.map { "media" to it.second },
            sent,
        )
        assertEquals(0, refreshes)
        failSubAction = "set_volume"
        val failed = controller.sendMediaAction(MediaAction.SetVolume(55))
        assertFalse(failed.success)
        assertEquals("媒体操作失败", failed.message)
        assertEquals(0, refreshes)
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
        controller.sendMediaAction(MediaAction.SetOutputDevice("output-id"))
        controller.sendMediaAction(MediaAction.SetInputDevice("input-id"))
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
