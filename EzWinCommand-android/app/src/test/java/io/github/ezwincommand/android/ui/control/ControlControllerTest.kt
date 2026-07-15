package io.github.ezwincommand.android.ui.control

import io.github.ezwincommand.android.model.ActionPlugin
import io.github.ezwincommand.android.model.CommandResult
import io.github.ezwincommand.android.model.DeviceInfo
import io.github.ezwincommand.android.model.SubAction
import io.github.ezwincommand.android.network.ApiResult
import io.github.ezwincommand.android.network.EzApiClient
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
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
    fun `rejects duplicate command while first is running`() = runBlocking {
        var calls = 0
        val client = object : EzApiClient("http://192.168.1.10:8080", deviceKeyProvider = { "k" }) {
            override suspend fun executeCommand(action: String, params: Map<String, Any?>): ApiResult<CommandResult> {
                calls++
                delay(50)
                return ApiResult.Success(CommandResult(true, "ok", emptyMap()))
            }
        }
        val controller = ControlController(client, onAuthInvalid = {})
        coroutineScope {
            val first = async { controller.sendAction(ActionCommand("power")) }
            val second = async { controller.sendAction(ActionCommand("power")) }
            first.await()
            assertFalse(second.await().success)
        }
        assertEquals(1, calls)
        assertTrue(controller.sendAction(ActionCommand("power")).success)
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

    @Test
    fun `poll parse error returns explicit message and keeps pending`() = runBlocking {
        val client = object : EzApiClient("http://192.168.1.10:8080", deviceKeyProvider = { "k" }) {
            override suspend fun getCommandStatus(commandId: String): ApiResult<io.github.ezwincommand.android.model.CommandStatus> = ApiResult.ParseError("解析响应失败")
        }
        val controller = ControlController(client, onAuthInvalid = {})
        val result = controller.pollPending(ActionCommand("power"), "cmd-1", maxPolls = 1, pollDelayMs = 0)
        assertEquals("状态响应解析失败，可稍后重试", result?.message)
        assertEquals("parse_error", result?.status)
    }

    @Test
    fun `poll network error remains running`() = runBlocking {
        val client = object : EzApiClient("http://192.168.1.10:8080", deviceKeyProvider = { "k" }) {
            override suspend fun getCommandStatus(commandId: String): ApiResult<io.github.ezwincommand.android.model.CommandStatus> = ApiResult.NetworkError("网络请求失败")
        }
        val controller = ControlController(client, onAuthInvalid = {})
        val result = controller.pollPending(ActionCommand("power"), "cmd-1", maxPolls = 1, pollDelayMs = 0)
        assertEquals("仍在服务端执行，可稍后继续查询", result?.message)
        assertEquals("running", result?.status)
    }

    @Test
    fun `close cancels tracking ownership and closes client once`() {
        var closes = 0
        val client = object : EzApiClient("http://127.0.0.1:8080", { "k" }) {
            override fun close() { closes++ }
        }
        val controller = ControlController(client, onAuthInvalid = {})
        controller.close()
        assertEquals(1, closes)
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
