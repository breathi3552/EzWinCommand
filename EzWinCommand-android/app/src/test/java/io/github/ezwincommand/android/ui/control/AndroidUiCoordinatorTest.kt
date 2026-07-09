package io.github.ezwincommand.android.ui.control

import io.github.ezwincommand.android.model.ActionPlugin
import io.github.ezwincommand.android.model.AuthorizeResult
import io.github.ezwincommand.android.model.PairingStatus
import io.github.ezwincommand.android.model.PingResponse
import io.github.ezwincommand.android.network.ApiResult
import io.github.ezwincommand.android.network.EzApiClient
import io.github.ezwincommand.android.state.ConnectionRepository
import io.github.ezwincommand.android.state.RestoreResult
import io.github.ezwincommand.android.storage.DeviceKeyStore
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class AndroidUiCoordinatorTest {
    @Test
    fun `restore invalid does not overwrite draft and returns to main`() = runBlocking {
        val store = InMemoryDeviceKeyStore().apply { saveSession("http://192.168.1.10:8080", "key-1") }
        val repo = ConnectionRepository(store) { _, _ -> FakeClient(FakeClient.Mode.Unauthorized) }
        val coordinator = AndroidUiCoordinator(repo) { error("unused") }

        val effect = coordinator.restoreSession()

        assertTrue(effect is AndroidUiEffect.ShowMessage)
        assertTrue(coordinator.state is AndroidUiState.Main)
        assertNull(store.getDeviceKey())
    }

    @Test
    fun `restore success opens control`() = runBlocking {
        val store = InMemoryDeviceKeyStore().apply { saveSession("http://192.168.1.10:8080", "key-1") }
        val repo = ConnectionRepository(store) { _, _ -> FakeClient(FakeClient.Mode.Success) }
        val coordinator = AndroidUiCoordinator(repo) { error("unused") }

        val effect = coordinator.restoreSession()

        assertTrue(effect is AndroidUiEffect.OpenControl)
        assertTrue(coordinator.state is AndroidUiState.Control)
        assertEquals("http://192.168.1.10:8080", (coordinator.state as AndroidUiState.Control).baseUrl)
    }

    @Test
    fun `auth invalid returns main and clears session`() {
        val store = InMemoryDeviceKeyStore().apply { saveSession("http://192.168.1.10:8080", "key-1") }
        val repo = ConnectionRepository(store) { _, _ -> FakeClient(FakeClient.Mode.Success) }
        val coordinator = AndroidUiCoordinator(repo) { error("unused") }

        val effect = coordinator.onAuthInvalid()

        assertTrue(effect is AndroidUiEffect.ReturnToMain)
        assertTrue(coordinator.state is AndroidUiState.Main)
        assertNull(store.getDeviceKey())
        assertNull(store.getBaseUrl())
    }

    private class FakeClient(private val mode: Mode) : EzApiClient("http://192.168.1.10:8080", { null }, 5_000) {
        enum class Mode { Success, Unauthorized }

        override suspend fun ping(): ApiResult<PingResponse> = when (mode) {
            Mode.Success -> ApiResult.Success(PingResponse("ok"))
            Mode.Unauthorized -> ApiResult.HttpError(403, "forbidden")
        }

        override suspend fun pairingStatus(): ApiResult<PairingStatus> = when (mode) {
            Mode.Success -> ApiResult.Success(PairingStatus(hasCode = true, hasDevices = false, expiresIn = 300))
            Mode.Unauthorized -> ApiResult.HttpError(403, "forbidden")
        }

        override suspend fun authorize(token: String, name: String): ApiResult<AuthorizeResult> = when (mode) {
            Mode.Success -> ApiResult.Success(AuthorizeResult(true, "key-1", null))
            Mode.Unauthorized -> ApiResult.HttpError(403, "forbidden")
        }

        override suspend fun listActions(): ApiResult<List<ActionPlugin>> = when (mode) {
            Mode.Success -> ApiResult.Success(emptyList())
            Mode.Unauthorized -> ApiResult.HttpError(401, "unauthorized")
        }
    }

    private class InMemoryDeviceKeyStore : DeviceKeyStore {
        private var baseUrl: String? = null
        private var deviceKey: String? = null

        override fun getBaseUrl(): String? = baseUrl
        override fun getDeviceKey(): String? = deviceKey

        override fun saveSession(baseUrl: String, deviceKey: String) {
            this.baseUrl = baseUrl.trim()
            this.deviceKey = deviceKey.trim()
        }

        override fun clearSession() {
            baseUrl = null
            deviceKey = null
        }
    }
}
