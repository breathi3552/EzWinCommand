package io.github.ezwincommand.android.state

import io.github.ezwincommand.android.model.ActionPlugin
import io.github.ezwincommand.android.model.AuthorizeResult
import io.github.ezwincommand.android.model.PairingStatus
import io.github.ezwincommand.android.model.PingResponse
import io.github.ezwincommand.android.network.ApiResult
import io.github.ezwincommand.android.network.EzApiClient
import io.github.ezwincommand.android.storage.DeviceKeyStore
import kotlinx.coroutines.runBlocking
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue
import org.junit.Test

class ConnectionRepositoryTest {
    @Test
    fun `normalizeInputForAndroid keeps lan ip and trims scheme slash`() {
        val repo = ConnectionRepository(MemoryDeviceKeyStore())
        assertEquals("http://192.168.1.10:8090", repo.normalizeForTest("192.168.1.10:8090"))
        assertEquals("http://192.168.1.10:8090", repo.normalizeForTest("http://192.168.1.10:8090/"))
    }

    @Test
    fun `normalizeInputForAndroid rejects empty and android-local addresses`() {
        val repo = ConnectionRepository(MemoryDeviceKeyStore())
        assertNull(repo.normalizeBaseUrlForProduction(""))
        assertNull(repo.normalizeBaseUrlForProduction("localhost:8090"))
        assertNull(repo.normalizeBaseUrlForProduction("127.0.0.1:8090"))
        assertNull(repo.normalizeBaseUrlForProduction("0.0.0.0:8090"))
    }

    @Test
    fun `normalizeInputForAndroid accepts host without duplicating port`() {
        val repo = ConnectionRepository(MemoryDeviceKeyStore())
        assertEquals("http://192.168.1.10:8090", repo.normalizeBaseUrlForProduction("192.168.1.10:8090"))
        assertEquals("http://192.168.1.10:9090", repo.normalizeBaseUrlForProduction("http://192.168.1.10:9090"))
    }

    @Test
    fun `normalizeInputForAndroid keeps host when port missing`() {
        val repo = ConnectionRepository(MemoryDeviceKeyStore())
        assertEquals("http://192.168.1.10", repo.normalizeBaseUrlForProduction("192.168.1.10"))
    }


    @Test
    fun `normalizeInputForAndroid appends port to full url when missing`() {
        val repo = ConnectionRepository(MemoryDeviceKeyStore())
        val result = repo.normalizeInputForAndroid("http://192.168.1.10", "8080")
        assertTrue(result is NormalizeResult.Valid)
        assertEquals("http://192.168.1.10:8080", result.baseUrl)
    }

    @Test
    fun `normalizeInputForAndroid preserves explicit url port`() {
        val repo = ConnectionRepository(MemoryDeviceKeyStore())
        val result = repo.normalizeInputForAndroid("http://192.168.1.10:9090/", "8080")
        assertTrue(result is NormalizeResult.Valid)
        assertEquals("http://192.168.1.10:9090", result.baseUrl)
    }

    @Test
    fun `testConnection reads pairing status after ping`() = runBlocking {
        val repo = ConnectionRepository(MemoryDeviceKeyStore()) { _, _ -> FakeClient(FakeClient.Mode.Success) }
        val result = repo.testConnection("http://192.168.1.10:8080")
        assertTrue(result is ConnectionCheckResult.Reachable)
        assertEquals(true, result.pairing.hasCode)
    }

    @Test
    fun `pair saves session only when key is present`() = runBlocking {
        val store = MemoryDeviceKeyStore()
        val repo = ConnectionRepository(store) { _, _ -> FakeClient(FakeClient.Mode.PairSuccess) }
        val result = repo.pair("http://192.168.1.10:8080", "A1b2", "phone")
        assertTrue(result is PairingResult.Paired)
        assertEquals("http://192.168.1.10:8080", store.getBaseUrl())
        assertEquals("key-1", store.getDeviceKey())
    }

    @Test
    fun `pair rejects short code`() = runBlocking {
        val repo = ConnectionRepository(MemoryDeviceKeyStore())
        val result = repo.pair("http://192.168.1.10:8080", "12", "phone")
        assertTrue(result is PairingResult.Failed)
    }

    @Test
    fun `restoreSession clears key on unauthorized`() = runBlocking {
        val store = MemoryDeviceKeyStore().apply { saveSession("http://192.168.1.10:8080", "key-1") }
        val repo = ConnectionRepository(store) { _, _ -> FakeClient(FakeClient.Mode.Unauthorized) }
        val result = repo.restoreSession()
        assertTrue(result is RestoreResult.InvalidSavedSession)
        assertNull(store.getDeviceKey())
    }

    @Test
    fun `restoreSession succeeds when actions are authorized`() = runBlocking {
        val store = MemoryDeviceKeyStore().apply { saveSession("http://192.168.1.10:8080", "key-1") }
        val repo = ConnectionRepository(store) { _, _ -> FakeClient(FakeClient.Mode.Success) }
        val result = repo.restoreSession()
        assertTrue(result is RestoreResult.Restored)
    }

    @Test
    fun `signOut clears local key`() {
        val store = MemoryDeviceKeyStore().apply { saveSession("http://192.168.1.10:8080", "key-1") }
        val repo = ConnectionRepository(store)
        repo.signOut()
        assertNull(store.getDeviceKey())
    }

    @Test
    fun `network hint mentions lan host and firewall`() {
        val repo = ConnectionRepository(MemoryDeviceKeyStore())
        val message = repo.networkHintForTest("http://192.168.1.10:8080", "timeout", null)
        assertTrue(message.contains("同一局域网"))
        assertTrue(message.contains("HOST=0.0.0.0"))
        assertTrue(message.contains("防火墙"))
    }

    private class FakeClient(private val mode: Mode) : EzApiClient("http://192.168.1.10:8080", { null }, 5_000) {
        enum class Mode { Success, PairSuccess, Unauthorized }
        override suspend fun ping(): ApiResult<PingResponse> = when (mode) {
            Mode.Success, Mode.PairSuccess -> ApiResult.Success(PingResponse("ok"))
            Mode.Unauthorized -> ApiResult.HttpError(403, "forbidden")
        }
        override suspend fun pairingStatus(): ApiResult<PairingStatus> = when (mode) {
            Mode.Success, Mode.PairSuccess -> ApiResult.Success(PairingStatus(hasCode = true, hasDevices = false, expiresIn = 300))
            Mode.Unauthorized -> ApiResult.HttpError(403, "forbidden")
        }
        override suspend fun authorize(token: String, name: String): ApiResult<AuthorizeResult> = when (mode) {
            Mode.PairSuccess -> ApiResult.Success(AuthorizeResult(true, "key-1", null))
            else -> ApiResult.HttpError(403, "forbidden")
        }
        override suspend fun listActions(): ApiResult<List<ActionPlugin>> = when (mode) {
            Mode.Unauthorized -> ApiResult.HttpError(401, "unauthorized")
            else -> ApiResult.Success(emptyList())
        }
    }

    private class MemoryDeviceKeyStore : DeviceKeyStore {
        private var baseUrl: String? = null
        private var deviceKey: String? = null
        override fun getBaseUrl(): String? = baseUrl
        override fun getDeviceKey(): String? = deviceKey
        override fun saveSession(baseUrl: String, deviceKey: String) { this.baseUrl = baseUrl.trim(); this.deviceKey = deviceKey.trim() }
        override fun clearSession() { baseUrl = null; deviceKey = null }
    }
}
