package io.github.ezwincommand.android.ui.control

import io.github.ezwincommand.android.model.MediaState
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
import org.junit.Assert.assertNull
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
    fun `keeps loading while server returns provisional revision zero snapshot`() = runBlocking {
        val provisional = MediaState.LOADING.copy(error = "媒体服务正在初始化")
        val state = ControlController(
            fakeClient(mediaResult = ApiResult.Success(provisional)),
            onAuthInvalid = {},
        ).load() as ControlUiState.Ready

        assertTrue(state.mediaLoading)
        assertEquals(MediaState.LOADING, state.media)
    }

    @Test
    fun `load uses server isCurrent flag instead of device credential`() = runBlocking {
        val controller = ControlController(
            fakeClient(devices = listOf(
                DeviceInfo("device-id", "手机", null, null, isCurrent = true),
                DeviceInfo("other-id", "平板", null, null, isCurrent = false),
            )),
            onAuthInvalid = {},
        )
        val state = controller.load() as ControlUiState.Ready
        assertTrue(state.devices.single { it.deviceId == "device-id" }.isCurrent)
        assertFalse(state.devices.single { it.deviceId == "other-id" }.isCurrent)
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
    fun `authorization invalidation suppresses an in-flight command result`() = runBlocking {
        val started = kotlinx.coroutines.CompletableDeferred<Unit>()
        val release = kotlinx.coroutines.CompletableDeferred<ApiResult<CommandResult>>()
        val client = object : EzApiClient("http://192.168.1.10:8080", deviceKeyProvider = { "k" }) {
            override suspend fun executeCommand(
                action: String,
                params: Map<String, Any?>,
            ): ApiResult<CommandResult> {
                started.complete(Unit)
                return kotlinx.coroutines.withContext(kotlinx.coroutines.NonCancellable) { release.await() }
            }
        }
        val controller = ControlController(client, onAuthInvalid = {})
        val request = async { controller.sendAction(ActionCommand("power")) }

        started.await()
        controller.invalidateAuthorization()
        release.complete(ApiResult.Success(CommandResult(true, "已受理", emptyMap())))

        val result = request.await()
        assertFalse(result.success)
        assertEquals("授权已失效，请重新配对。", result.message)
    }
    @Test
    fun `authorization invalidation drops an in-flight task poll`() = runBlocking {
        val started = kotlinx.coroutines.CompletableDeferred<Unit>()
        val release = kotlinx.coroutines.CompletableDeferred<ApiResult<io.github.ezwincommand.android.model.CommandStatus>>()
        val client = object : EzApiClient("http://192.168.1.10:8080", deviceKeyProvider = { "k" }) {
            override suspend fun getCommandStatus(commandId: String): ApiResult<io.github.ezwincommand.android.model.CommandStatus> {
                started.complete(Unit)
                return kotlinx.coroutines.withContext(kotlinx.coroutines.NonCancellable) { release.await() }
            }
        }
        val controller = ControlController(client, onAuthInvalid = {})
        val poll = async {
            controller.pollPending(ActionCommand("power"), "command-id", maxPolls = 1, pollDelayMs = 0)
        }

        started.await()
        controller.invalidateAuthorization()
        release.complete(
            ApiResult.Success(
                io.github.ezwincommand.android.model.CommandStatus("command-id", "succeeded", "done"),
            ),
        )

        assertNull(poll.await())
    }
    @Test
    fun `revoke device uses stable device id`() = runBlocking {
        val controller = ControlController(fakeClient(), onAuthInvalid = {})
        assertTrue(controller.revokeDevice("device-id"))
    }

    @Test
    fun `revoke device invokes auth invalid on 403`() = runBlocking {
        var authInvalidCount = 0
        val controller = ControlController(fakeClient(httpStatus = 403), onAuthInvalid = { authInvalidCount++ })
        assertFalse(controller.revokeDevice("device-id"))
        assertEquals(1, authInvalidCount)
    }

    @Test
    fun `rename device returns true on success`() = runBlocking {
        val controller = ControlController(fakeClient(), onAuthInvalid = {})
        assertTrue(controller.renameDevice("device-id", "新手机"))
    }

    @Test
    fun `rename device rejects blank names`() = runBlocking {
        val controller = ControlController(fakeClient(), onAuthInvalid = {})
        assertFalse(controller.renameDevice("device-id", "   "))
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
    fun `self revoke removes session and returns to pairing without refreshing`() = runBlocking {
        var revokedId: String? = null
        var removedSession = false
        var refreshCalls = 0
        val transition = applyDeviceRevoke(
            deviceId = "current-id",
            devices = listOf(
                DeviceInfo("current-id", "手机", null, null, isCurrent = true),
                DeviceInfo("other-id", "平板", null, null, isCurrent = false),
            ),
            revoke = { revokedId = it; true },
            onSelfRevoked = { removedSession = true; true },
            refresh = { refreshCalls++; ControlUiState.Error("unexpected", false) },
        )

        assertTrue(transition === DeviceRevokeTransition.ReturnedToPairing)
        assertEquals("current-id", revokedId)
        assertTrue(removedSession)
        assertEquals(0, refreshCalls)
    }

    @Test
    fun `self revoke cleanup failure does not report success`() = runBlocking {
        val transition = applyDeviceRevoke(
            deviceId = "current-id",
            devices = listOf(DeviceInfo("current-id", "手机", null, null, isCurrent = true)),
            revoke = { true },
            onSelfRevoked = { false },
            refresh = { ControlUiState.Error("unexpected", false) },
        )

        assertTrue(transition === DeviceRevokeTransition.CleanupFailed)
    }

    @Test
    fun `remote revoke keeps control and refreshes authoritative devices`() = runBlocking {
        var removedSession = false
        var refreshCalls = 0
        val expected = ControlUiState.Ready(
            actions = emptyList(),
            devices = listOf(DeviceInfo("current-id", "手机", null, null, isCurrent = true)),
        )
        val transition = applyDeviceRevoke(
            deviceId = "other-id",
            devices = listOf(
                DeviceInfo("current-id", "手机", null, null, isCurrent = true),
                DeviceInfo("other-id", "平板", null, null, isCurrent = false),
            ),
            revoke = { true },
            onSelfRevoked = { removedSession = true; true },
            refresh = { refreshCalls++; expected },
        )

        assertTrue(transition is DeviceRevokeTransition.Refreshed)
        assertEquals(expected, (transition as DeviceRevokeTransition.Refreshed).state)
        assertFalse(removedSession)
        assertEquals(1, refreshCalls)
    }

    @Test
    fun `failed revoke leaves session and control state untouched`() = runBlocking {
        var removedSession = false
        var refreshCalls = 0
        val transition = applyDeviceRevoke(
            deviceId = "missing-id",
            devices = listOf(DeviceInfo("current-id", "手机", null, null, isCurrent = true)),
            revoke = { false },
            onSelfRevoked = { removedSession = true; true },
            refresh = { refreshCalls++; ControlUiState.Error("unexpected", false) },
        )

        assertTrue(transition === DeviceRevokeTransition.Failed)
        assertFalse(removedSession)
        assertEquals(0, refreshCalls)
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
        devices: List<DeviceInfo> = listOf(DeviceInfo("device-id", "手机", null, null)),
        commandResult: CommandResult = CommandResult(true, "ok", emptyMap()),
        httpStatus: Int? = null,
        mediaResult: ApiResult<MediaState> = ApiResult.NetworkError("media unavailable"),
    ): EzApiClient {
        return object : EzApiClient("http://192.168.1.10:8080", deviceKeyProvider = { "k" }) {
            override suspend fun getMediaState(): ApiResult<MediaState> = mediaResult
            override suspend fun listActions(): ApiResult<List<ActionPlugin>> = if (httpStatus != null) ApiResult.HttpError(httpStatus, "auth invalid") else ApiResult.Success(actions)
            override suspend fun listDevices(): ApiResult<List<DeviceInfo>> = if (httpStatus != null) ApiResult.HttpError(httpStatus, "auth invalid") else ApiResult.Success(devices)
            override suspend fun executeCommand(action: String, params: Map<String, Any?>): ApiResult<CommandResult> = if (httpStatus != null) ApiResult.HttpError(httpStatus, "auth invalid") else ApiResult.Success(commandResult)
            override suspend fun revokeDevice(deviceId: String): ApiResult<Boolean> = if (httpStatus != null) ApiResult.HttpError(httpStatus, "auth invalid") else ApiResult.Success(true)
            override suspend fun renameDevice(deviceId: String, name: String): ApiResult<Boolean> = if (httpStatus != null) ApiResult.HttpError(httpStatus, "auth invalid") else ApiResult.Success(true)
        }
    }
}
