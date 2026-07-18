package io.github.ezwincommand.android.storage

import android.content.SharedPreferences
import android.util.Log
import org.json.JSONArray
import org.json.JSONObject

/** 按 serverId 隔离的持久会话；密钥仅在 KeystoreCipher 内解密。 */
data class ServerSession(
    val serverId: String,
    val baseUrl: String,
    val deviceName: String,
    val credentialVersion: Long,
    val lastSuccessfulAt: Long?,
    val needsRepair: Boolean = false,
)


class ServerSessionStore(
    private val preferences: SharedPreferences,
    private val cipher: SessionCipher,
) {
    private data class Slot(val key: String, val epoch: Long, val root: JSONObject)

    fun get(serverId: String): ServerSession? = load().firstOrNull { it.serverId == serverId }
    fun list(): List<ServerSession> = load().sortedWith(compareByDescending<ServerSession> { it.lastSuccessfulAt ?: Long.MIN_VALUE }.thenBy { it.serverId })
    fun active(): ServerSession? = list().firstOrNull { !it.needsRepair && it.lastSuccessfulAt != null }


    /** 新凭据写入：仅配对或旧三键迁移调用，并递增授权世代。 */
    fun saveSession(serverId: String, baseUrl: String, deviceName: String, deviceKey: String, now: Long): ServerSession? =
        saveNewCredential(serverId, baseUrl, deviceName, deviceKey, now.takeIf { it > 0 })

    /** 已有凭据授权成功：更新地址/名称/成功时间，不递增授权世代。 */
    fun recordAuthorized(serverId: String, baseUrl: String, deviceName: String, now: Long): ServerSession? {
        val old = get(serverId) ?: return null
        val raw = rawRecord(serverId) ?: return null
        val updated = old.copy(baseUrl = baseUrl.trim(), deviceName = deviceName.trim(), lastSuccessfulAt = now, needsRepair = false)
        return if (commitRecords(load().filterNot { it.serverId == serverId } + updated, validRawRecords() + (serverId to raw))) updated else null
    }

    private fun saveNewCredential(serverId: String, baseUrl: String, deviceName: String, deviceKey: String, successfulAt: Long?): ServerSession? {
        val version = (get(serverId)?.credentialVersion ?: 0L) + 1L
        val encrypted = try {
            cipher.encrypt(serverId, version, deviceKey)
        } catch (error: Throwable) {
            Log.e(TAG, "event=session_save_failed phase=encrypt", error)
            return null
        }
        val updated = ServerSession(serverId, baseUrl.trim(), deviceName.trim(), version, successfulAt, false)
        val raws = validRawRecords().toMutableMap().apply {
            put(serverId, JSONObject().put("alias", encrypted.alias).put("iv", encrypted.iv).put("ciphertext", encrypted.ciphertext))
        }
        val committed = commitRecords(load().filterNot { it.serverId == serverId } + updated, raws)
        val verified = committed && get(serverId) == updated && readDeviceKey(serverId) == deviceKey
        if (!verified) deleteIfUnreferenced(encrypted.alias)
        return updated.takeIf { verified }
    }

    fun readDeviceKey(serverId: String): String? {
        val record = rawRecord(serverId) ?: return null
        return try {
            cipher.decrypt(serverId, KeystoreCipher.EncryptedValue(record.getString("alias"), record.getString("iv"), record.getString("ciphertext")))
        } catch (_: Throwable) {
            markRepair(serverId)
            null
        }
    }

    fun markRepair(serverId: String): Boolean {
        val records = load().map { if (it.serverId == serverId) it.copy(needsRepair = true) else it }
        return commitRecords(records, validRawRecords())
    }

    fun remove(serverId: String): Boolean {
        val records = load().filterNot { it.serverId == serverId }
        val committed = commitRecords(records, validRawRecords() - serverId)
        if (committed) reclaimOrphanAliases()
        return committed
    }

    fun legacyValues(): Triple<String, String, String>? {
        val baseUrl = preferences.getString(LEGACY_BASE_URL, null)?.takeIf { it.isNotBlank() } ?: return null
        val deviceKey = preferences.getString(LEGACY_DEVICE_KEY, null)?.takeIf { it.isNotBlank() } ?: return null
        return Triple(baseUrl, deviceKey, preferences.getString(LEGACY_DEVICE_NAME, null).orEmpty().ifBlank { "Android" })
    }

    /** identity 成功后迁移；v2 安全回读成功才在同一同步提交中删除旧三键。 */
    fun migrateLegacy(serverId: String, baseUrl: String, deviceName: String, deviceKey: String): ServerSession? {
        val migrated = saveNewCredential(serverId, baseUrl, deviceName, deviceKey, null) ?: return null
        if (!preferences.edit().remove(LEGACY_BASE_URL).remove(LEGACY_DEVICE_KEY).remove(LEGACY_DEVICE_NAME).commit()) return null
        return migrated
    }

    private fun load(): List<ServerSession> {
        val array = currentSlot()?.root?.optJSONArray("records") ?: return emptyList()
        return array.asSequence().mapNotNull { item ->
            runCatching {
                val serverId = item.getString("serverId").takeIf { it.isNotBlank() } ?: return@runCatching null
                item.getString("alias"); item.getString("iv"); item.getString("ciphertext")
                ServerSession(serverId, item.getString("baseUrl"), item.optString("deviceName"), item.getLong("credentialVersion").takeIf { it > 0 } ?: return@runCatching null, item.optLong("lastSuccessfulAt").takeIf { item.has("lastSuccessfulAt") && it > 0 }, item.optBoolean("needsRepair"))
            }.getOrNull()
        }.toList()
    }

    private fun currentSlot(): Slot? = listOfNotNull(readSlot(ACTIVE), readSlot(BACKUP)).maxByOrNull { it.epoch }

    private fun readSlot(key: String): Slot? = preferences.getString(key, null)?.let { raw -> decode(raw)?.let { (epoch, root) -> Slot(key, epoch, root) } }

    private fun decode(raw: String): Pair<Long, JSONObject>? = runCatching {
        val wrapper = JSONObject(raw)
        val epoch = wrapper.getLong("epoch").takeIf { it > 0 } ?: return@runCatching null
        val payload = wrapper.getString("payload")
        if (wrapper.getString("checksum") != checksum(payload)) return@runCatching null
        val root = JSONObject(payload)
        if (root.getInt("schema") != SCHEMA) return@runCatching null
        root.getJSONArray("records")
        epoch to root
    }.getOrNull()

    /** B5E2：backup commit → active commit → active readback，任一步失败均保留旧 active/alias 引用。 */
    private fun commitRecords(records: List<ServerSession>, raws: Map<String, JSONObject>): Boolean {
        val epoch = maxOf(readSlot(ACTIVE)?.epoch ?: 0L, readSlot(BACKUP)?.epoch ?: 0L) + 1L
        val wrapper = wrap(epoch, encode(records, raws))
        val oldActive = preferences.getString(ACTIVE, null)
        val backupValue = oldActive ?: wrapper
        if (!preferences.edit().putString(BACKUP, backupValue).commit()) return false
        if (!preferences.edit().putString(ACTIVE, wrapper).commit()) return false
        val readBack = readSlot(ACTIVE) ?: return false
        if (readBack.epoch != epoch || readBack.root.toString() != encode(records, raws).toString()) return false
        reclaimOrphanAliases()
        return true
    }

    private fun wrap(epoch: Long, payload: JSONObject): String {
        val text = payload.toString()
        return JSONObject().put("epoch", epoch).put("payload", text).put("checksum", checksum(text)).toString()
    }

    private fun encode(records: List<ServerSession>, raws: Map<String, JSONObject>): JSONObject {
        val array = JSONArray()
        records.forEach { session ->
            val raw = raws[session.serverId] ?: return@forEach
            val item = JSONObject().put("serverId", session.serverId).put("baseUrl", session.baseUrl).put("deviceName", session.deviceName).put("credentialVersion", session.credentialVersion).put("needsRepair", session.needsRepair)
                .put("alias", raw.getString("alias")).put("iv", raw.getString("iv")).put("ciphertext", raw.getString("ciphertext"))
            if (session.lastSuccessfulAt != null) item.put("lastSuccessfulAt", session.lastSuccessfulAt)
            array.put(item)
        }
        return JSONObject().put("schema", SCHEMA).put("records", array)
    }

    private fun validRawRecords(): Map<String, JSONObject> = currentSlot()?.root?.optJSONArray("records")?.asSequence()?.mapNotNull { item ->
        runCatching {
            item.getString("serverId") to JSONObject().put("alias", item.getString("alias")).put("iv", item.getString("iv")).put("ciphertext", item.getString("ciphertext"))
        }.getOrNull()
    }?.toMap().orEmpty()

    private fun rawRecord(serverId: String): JSONObject? = validRawRecords()[serverId]
    private fun referencedAliases(): Set<String> = listOfNotNull(readSlot(ACTIVE), readSlot(BACKUP)).flatMap { slot ->
        slot.root.getJSONArray("records").asSequence().mapNotNull { runCatching { it.getString("alias") }.getOrNull() }.toList()
    }.toSet()
    private fun deleteIfUnreferenced(alias: String) { if (alias !in referencedAliases()) runCatching { cipher.deleteAlias(alias) } }
    private fun reclaimOrphanAliases() { val referenced = referencedAliases(); cipher.applicationAliases().filterNot { it in referenced }.forEach { runCatching { cipher.deleteAlias(it) } } }
    private fun checksum(value: String) = java.security.MessageDigest.getInstance("SHA-256").digest(value.toByteArray()).joinToString("") { "%02x".format(it) }

    private companion object {
        const val SCHEMA = 2
        const val TAG = "ServerSessionStore"
        const val ACTIVE = "active_v2"
        const val BACKUP = "backup_v2"
        const val LEGACY_BASE_URL = "base_url"
        const val LEGACY_DEVICE_KEY = "device_key"
        const val LEGACY_DEVICE_NAME = "device_name"
    }
}

private fun JSONArray.asSequence(): Sequence<JSONObject> = sequence {
    for (i in 0 until length()) optJSONObject(i)?.let { yield(it) }
}
