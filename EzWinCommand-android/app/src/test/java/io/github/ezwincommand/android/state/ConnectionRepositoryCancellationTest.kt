package io.github.ezwincommand.android.state

import android.content.SharedPreferences
import io.github.ezwincommand.android.model.PairingCompleted
import io.github.ezwincommand.android.model.PairingCreated
import io.github.ezwincommand.android.model.ServerIdentity
import io.github.ezwincommand.android.network.ApiResult
import io.github.ezwincommand.android.network.EzApiClient
import io.github.ezwincommand.android.storage.KeystoreCipher
import io.github.ezwincommand.android.storage.ServerSessionStore
import io.github.ezwincommand.android.storage.SessionCipher
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.async
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment

@RunWith(RobolectricTestRunner::class)
class ConnectionRepositoryCancellationTest {
    private class FakeCipher : SessionCipher {
        private val values = mutableMapOf<String, String>()
        override fun encrypt(serverId: String, credentialVersion: Long, value: String): KeystoreCipher.EncryptedValue {
            val alias = "ezwin_session_${serverId}_$credentialVersion"
            values[alias] = value
            return KeystoreCipher.EncryptedValue(alias, "iv", "cipher")
        }
        override fun decrypt(serverId: String, value: KeystoreCipher.EncryptedValue) = values.getValue(value.alias)
        override fun deleteAlias(alias: String) { values.remove(alias) }
        override fun applicationAliases() = values.keys
    }

    private fun store(name: String): ServerSessionStore {
        val prefs: SharedPreferences = RuntimeEnvironment.getApplication().getSharedPreferences(name, 0)
        prefs.edit().clear().commit()
        return ServerSessionStore(prefs, FakeCipher())
    }

    private fun client(
        completeStarted: CompletableDeferred<Unit>? = null,
        completeRelease: CompletableDeferred<Unit>? = null,
        completed: ApiResult<PairingCompleted> = ApiResult.Success(PairingCompleted("new-key-a")),
        completeCalls: (() -> Unit)? = null,
    ) = object : EzApiClient("http://192.168.1.2:8080", { null }) {
        override suspend fun identity() = ApiResult.Success(ServerIdentity(1, SERVER_A, "PC A"))
        override suspend fun createPairing(serverId: String, deviceName: String) = ApiResult.Success(PairingCreated("pair", 300))
        override suspend fun completePairing(serverId: String, pairingId: String, code: String, deviceName: String): ApiResult<PairingCompleted> {
            completeCalls?.invoke()
            completeStarted?.complete(Unit)
            completeRelease?.await()
            return completed
        }
    }

    @Test
    fun `cancel before valid submission makes no complete request or disk write`() = runTest {
        val store = store("cancel-before-submit")
        var completeCalls = 0
        val api = client(completeCalls = { completeCalls += 1 })
        val repository = ConnectionRepository(store, clientFactory = { _, _ -> api })
        assertTrue(repository.testConnection(BASE_URL_A) is ConnectionCheckResult.Reachable)

        repository.cancelCurrent()
        val result = repository.pair(BASE_URL_A, "1234", "Phone")

        assertTrue(result is PairingResult.Failed)
        assertEquals(0, completeCalls)
        assertTrue(store.list().isEmpty())
    }

    @Test
    fun `cancel after submission keeps replacement session and other history but suppresses UI result`() = runTest {
        val store = store("cancel-after-submit")
        store.saveSession(SERVER_A, BASE_URL_A, "Old A", "old-key-a", 100)
        store.saveSession(SERVER_B, BASE_URL_B, "B", "key-b", 200)
        val completeStarted = CompletableDeferred<Unit>()
        val completeRelease = CompletableDeferred<Unit>()
        val api = client(completeStarted, completeRelease)
        val repository = ConnectionRepository(store, clientFactory = { _, _ -> api }, now = { 300 })
        assertTrue(repository.testConnection(BASE_URL_A) is ConnectionCheckResult.Reachable)

        val result = async { repository.pair(BASE_URL_A, "1234", "Phone") }
        completeStarted.await()
        repository.cancelCurrent()
        completeRelease.complete(Unit)

        assertTrue(result.await() is PairingResult.UiInvalidated)
        assertEquals("new-key-a", store.readDeviceKey(SERVER_A))
        assertEquals(2L, store.get(SERVER_A)!!.credentialVersion)
        assertEquals("key-b", store.readDeviceKey(SERVER_B))
        assertEquals(1L, store.get(SERVER_B)!!.credentialVersion)
    }

    @Test
    fun `complete failure writes nothing and does not rotate credential version`() = runTest {
        val store = store("complete-failure")
        store.saveSession(SERVER_A, BASE_URL_A, "Old A", "old-key-a", 100)
        val api = client(completed = ApiResult.HttpError(401, "验证码无效"))
        val repository = ConnectionRepository(store, clientFactory = { _, _ -> api })
        assertTrue(repository.testConnection(BASE_URL_A) is ConnectionCheckResult.Reachable)

        val result = repository.pair(BASE_URL_A, "1234", "Phone")

        assertTrue(result is PairingResult.Failed)
        assertEquals("old-key-a", store.readDeviceKey(SERVER_A))
        assertEquals(1L, store.get(SERVER_A)!!.credentialVersion)
        assertNull(store.get(SERVER_B))
    }

    @Test
    fun `invalid code makes no complete request or disk write`() = runTest {
        val store = store("invalid-code")
        var completeCalls = 0
        val api = client(completeCalls = { completeCalls += 1 })
        val repository = ConnectionRepository(store, clientFactory = { _, _ -> api })
        assertTrue(repository.testConnection(BASE_URL_A) is ConnectionCheckResult.Reachable)

        val result = repository.pair(BASE_URL_A, "12x4", "Phone")

        assertTrue(result is PairingResult.Failed)
        assertEquals(0, completeCalls)
        assertFalse(store.list().isNotEmpty())
    }

    private companion object {
        const val SERVER_A = "00000000-0000-4000-8000-000000000001"
        const val SERVER_B = "00000000-0000-4000-8000-000000000002"
        const val BASE_URL_A = "http://192.168.1.2:8080"
        const val BASE_URL_B = "http://192.168.1.3:8080"
    }
}
