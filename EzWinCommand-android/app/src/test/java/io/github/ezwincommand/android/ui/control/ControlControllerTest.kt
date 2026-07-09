package io.github.ezwincommand.android.ui.control

import io.github.ezwincommand.android.model.ActionPlugin
import io.github.ezwincommand.android.model.CommandResult
import io.github.ezwincommand.android.model.DeviceInfo
import io.github.ezwincommand.android.model.SubAction
import io.github.ezwincommand.android.network.ApiResult
import io.github.ezwincommand.android.network.EzApiClient
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ControlControllerTest {
    @Test
    fun `loads empty actions and devices`() = runBlocking {
        val controller = ControlController(fakeClient(actions = emptyList(), devices = emptyList()), onAuthInvalid = {})
        val state = controller.load()
        assertTrue(state is ControlUiState.Ready)
        state as ControlUiState.Ready
        assertTrue(state.actions.isEmpty())
        assertTrue(state.devices.isEmpty())
    }

    @Test
    fun `load marks current device key`() = runBlocking {
        val controller = ControlController(fakeClient(devices = listOf(DeviceInfo("k", "手机", null, null))), currentDeviceKeyProvider = { "k" }, onAuthInvalid = {})
        val state = controller.load() as ControlUiState.Ready
        assertEquals("k", state.currentDeviceKey)
    }

    @Test
    fun `renders single action without sub actions`() = runBlocking {
        val controller = ControlController(fakeClient(actions = listOf(ActionPlugin("sleep", "睡眠", "desc", "1", emptyList()))), onAuthInvalid = {})
        val state = controller.load() as ControlUiState.Ready
        val result = controller.sendAction(ActionCommand(state.actions[0].name))
        assertEquals("ok", result.message)
    }

    @Test
    fun `sends sub action params with fixed key`() = runBlocking {
        val controller = ControlController(fakeClient(actions = listOf(ActionPlugin("power", "电源", "desc", "1", listOf(SubAction("restart", "重启")))), commandResult = CommandResult(true, "done", emptyMap())), onAuthInvalid = {})
        val result = controller.sendAction(ActionCommand("power", mapOf("sub_action" to "restart")))
        assertEquals("done", result.message)
    }

    @Test
    fun `keeps success false message visible`() = runBlocking {
        val controller = ControlController(fakeClient(commandResult = CommandResult(false, "失败信息", emptyMap())), onAuthInvalid = {})
        val result = controller.sendAction(ActionCommand("power"))
        assertFalse(result.success)
        assertEquals("失败信息", result.message)
    }

    @Test
    fun `invokes auth invalid callback on 401 and 403`() = runBlocking {
        var authInvalidCount = 0
        val controller = ControlController(fakeClient(httpStatus = 403), onAuthInvalid = { authInvalidCount++ })
        val state = controller.load()
        assertTrue(state is ControlUiState.Error)
        assertEquals(1, authInvalidCount)
    }

    @Test
    fun `revoke device returns true on success`() = runBlocking {
        val controller = ControlController(fakeClient(), onAuthInvalid = {})
        assertTrue(controller.revokeDevice("k"))
    }

    @Test
    fun `revoke device invokes auth invalid on 403`() = runBlocking {
        var authInvalidCount = 0
        val controller = ControlController(fakeClient(httpStatus = 403), onAuthInvalid = { authInvalidCount++ })
        assertFalse(controller.revokeDevice("k"))
        assertEquals(1, authInvalidCount)
    }

    @Test
    fun `rename device returns true on success`() = runBlocking {
        val controller = ControlController(fakeClient(), onAuthInvalid = {})
        assertTrue(controller.renameDevice("k", "新手机"))
    }

    @Test
    fun `rename device rejects blank names`() = runBlocking {
        val controller = ControlController(fakeClient(), onAuthInvalid = {})
        assertFalse(controller.renameDevice("k", "   "))
    }

    private fun fakeClient(
        actions: List<ActionPlugin> = listOf(ActionPlugin("power", "电源", "desc", "1", listOf(SubAction("sleep", "睡眠")))),
        devices: List<DeviceInfo> = listOf(DeviceInfo("k", "手机", null, null)),
        commandResult: CommandResult = CommandResult(true, "ok", emptyMap()),
        httpStatus: Int? = null,
    ): EzApiClient {
        return object : EzApiClient("http://192.168.1.10:8080", deviceKeyProvider = { "k" }) {
            override suspend fun listActions(): ApiResult<List<ActionPlugin>> = if (httpStatus != null) ApiResult.HttpError(httpStatus, "auth invalid") else ApiResult.Success(actions)
            override suspend fun listDevices(): ApiResult<List<DeviceInfo>> = if (httpStatus != null) ApiResult.HttpError(httpStatus, "auth invalid") else ApiResult.Success(devices)
            override suspend fun executeCommand(action: String, params: Map<String, Any?>): ApiResult<CommandResult> = if (httpStatus != null) ApiResult.HttpError(httpStatus, "auth invalid") else ApiResult.Success(commandResult)
            override suspend fun revokeDevice(deviceKey: String): ApiResult<Boolean> = if (httpStatus != null) ApiResult.HttpError(httpStatus, "auth invalid") else ApiResult.Success(true)
            override suspend fun renameDevice(deviceKey: String, name: String): ApiResult<Boolean> = if (httpStatus != null) ApiResult.HttpError(httpStatus, "auth invalid") else ApiResult.Success(true)
        }
    }
}
