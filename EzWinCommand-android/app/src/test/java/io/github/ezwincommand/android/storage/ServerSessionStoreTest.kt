package io.github.ezwincommand.android.storage

import android.content.SharedPreferences
import java.lang.reflect.Proxy
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment

@RunWith(RobolectricTestRunner::class)
class ServerSessionStoreTest {
    private class FakeCipher : SessionCipher {
        val values = linkedMapOf<String, String>()
        val deleted = mutableListOf<String>()
        override fun encrypt(serverId: String, credentialVersion: Long, value: String): KeystoreCipher.EncryptedValue {
            val alias = "ezwin_session_${serverId}_$credentialVersion"
            values[alias] = value
            return KeystoreCipher.EncryptedValue(alias, "iv", "cipher")
        }
        override fun decrypt(serverId: String, value: KeystoreCipher.EncryptedValue): String =
            values[value.alias] ?: error("missing alias")
        override fun deleteAlias(alias: String) { deleted += alias; values.remove(alias) }
        override fun applicationAliases(): Set<String> = values.keys
    }

    private fun preferences(name: String): SharedPreferences =
        RuntimeEnvironment.getApplication().getSharedPreferences(name, 0).also { it.edit().clear().commit() }

    @Test
    fun `legacy migration keeps null success time and deletes old keys only after verified v2 write`() {
        val prefs = preferences("legacy")
        prefs.edit().putString("base_url", "http://192.168.1.2:8080").putString("device_key", "secret").putString("device_name", "Phone").commit()
        val store = ServerSessionStore(prefs, FakeCipher())

        val migrated = store.migrateLegacy("server-a", "http://192.168.1.2:8080", "Phone", "secret")

        assertEquals(null, migrated?.lastSuccessfulAt)
        assertEquals("secret", store.readDeviceKey("server-a"))
        assertFalse(prefs.contains("base_url")); assertFalse(prefs.contains("device_key")); assertFalse(prefs.contains("device_name"))
    }

    @Test
    fun `authorized readback updates address without rotating credential generation`() {
        val store = ServerSessionStore(preferences("authorized"), FakeCipher())
        val initial = store.saveSession("server-a", "http://192.168.1.2:8080", "Phone", "secret", 100)!!
        val updated = store.recordAuthorized("server-a", "http://192.168.1.3:8080", "PC", 200)!!

        assertEquals(initial.credentialVersion, updated.credentialVersion)
        assertEquals("http://192.168.1.3:8080", updated.baseUrl)
        assertEquals("secret", store.readDeviceKey("server-a"))
    }

    @Test
    fun `unknown newer schema is rejected and valid backup remains readable`() {
        val prefs = preferences("schema")
        val cipher = FakeCipher()
        val store = ServerSessionStore(prefs, cipher)
        store.saveSession("server-a", "http://192.168.1.2:8080", "Phone", "secret", 100)
        val active = prefs.getString("active_v2", null)!!
        prefs.edit().putString("backup_v2", active).commit()
        val wrapper = JSONObject(active)
        val payload = JSONObject(wrapper.getString("payload")).put("schema", 99).toString()
        val checksum = java.security.MessageDigest.getInstance("SHA-256").digest(payload.toByteArray()).joinToString("") { "%02x".format(it) }
        prefs.edit().putString("active_v2", JSONObject().put("epoch", wrapper.getLong("epoch") + 1).put("payload", payload).put("checksum", checksum).toString()).commit()

        assertEquals("server-a", store.get("server-a")?.serverId)
        assertEquals("secret", store.readDeviceKey("server-a"))
    }

    @Test
    fun `one damaged record is isolated while another remains readable`() {
        val prefs = preferences("isolate")
        val cipher = FakeCipher()
        val store = ServerSessionStore(prefs, cipher)
        store.saveSession("server-a", "http://192.168.1.2:8080", "A", "key-a", 100)
        store.saveSession("server-b", "http://192.168.1.3:8080", "B", "key-b", 200)
        cipher.values.remove("ezwin_session_server-a_1")

        assertNull(store.readDeviceKey("server-a"))
        assertTrue(store.get("server-a")!!.needsRepair)
        assertEquals("key-b", store.readDeviceKey("server-b"))
    }

    @Test
    fun `active commit failure keeps alias referenced by backup and does not report success`() {
        val delegate = preferences("fault")
        val failing = failCommit(delegate, 2)
        val cipher = FakeCipher()
        val store = ServerSessionStore(failing, cipher)

        assertNull(store.saveSession("server-a", "http://192.168.1.2:8080", "A", "key-a", 100))
        assertTrue(cipher.deleted.isEmpty())
        assertTrue(delegate.contains("backup_v2"))
    }

    private fun failCommit(delegate: SharedPreferences, failedCommit: Int): SharedPreferences {
        var commits = 0
        return Proxy.newProxyInstance(javaClass.classLoader, arrayOf(SharedPreferences::class.java)) { _, method, args ->
            if (method.name != "edit") return@newProxyInstance method.invoke(delegate, *(args ?: emptyArray()))
            val editor = delegate.edit()
            lateinit var proxy: SharedPreferences.Editor
            proxy = Proxy.newProxyInstance(javaClass.classLoader, arrayOf(SharedPreferences.Editor::class.java)) { _, editorMethod, editorArgs ->
                if (editorMethod.name == "commit") {
                    commits += 1
                    if (commits == failedCommit) return@newProxyInstance false
                }
                val result = editorMethod.invoke(editor, *(editorArgs ?: emptyArray()))
                if (result is SharedPreferences.Editor) proxy else result
            } as SharedPreferences.Editor
            proxy
        } as SharedPreferences
    }
}
