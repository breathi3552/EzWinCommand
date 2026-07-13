package io.github.ezwincommand.android.ui.control

import io.github.ezwincommand.android.model.CommandResult
import io.github.ezwincommand.android.network.ApiResult
import io.github.ezwincommand.android.network.EzApiClient
import kotlinx.coroutines.runBlocking
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
