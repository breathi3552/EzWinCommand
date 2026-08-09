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
        controller.sendMediaAction("set_volume", 37)
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
            "play_pause" to null,
            "prev" to null,
            "next" to null,
            "set_volume" to 37,
            "set_output_device" to "output-id",
            "set_input_device" to "input-id",
        )

        commands.forEach { (subAction, value) ->
            val result = sendMediaActionWithRefreshPolicy(
                subAction = subAction,
                value = value,
                send = { action, argument -> controller.sendMediaAction(action, argument) },
                refresh = { refreshes += 1 },
            )
            assertTrue(result.success)
            assertEquals("ok", result.message)
        }

        assertEquals(
            commands.map { "media" to it.first },
            sent,
        )
        assertEquals(0, refreshes)
        failSubAction = "set_volume"
        val failed = sendMediaActionWithRefreshPolicy(
            subAction = "set_volume",
            value = 55,
            send = { action, argument -> controller.sendMediaAction(action, argument) },
            refresh = { refreshes += 1 },
        )
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
