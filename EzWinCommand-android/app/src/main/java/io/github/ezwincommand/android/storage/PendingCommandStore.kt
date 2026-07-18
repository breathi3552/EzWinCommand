package io.github.ezwincommand.android.storage

import android.content.SharedPreferences
import org.json.JSONObject

data class PendingCommand(val action: String, val params: Map<String, Any?>, val commandId: String)

class PendingCommandStore(
    private val preferences: SharedPreferences,
    serverId: String,
    credentialVersion: Long,
) {
    private val namespace = "pending:${serverId.trim()}:$credentialVersion:"

    fun key(action: String, params: Map<String, Any?>): String {
        val subAction = params["sub_action"]
        val suffix = if (action == "esports_mode" && subAction != null) "$action:sub_action=$subAction" else "$action:${params.entries.sortedBy { it.key }.joinToString { "${it.key}=${it.value}" }}"
        return namespace + suffix
    }
    fun get(action: String, params: Map<String, Any?>): String? = preferences.getString(key(action, params), null)
    fun put(action: String, params: Map<String, Any?>, commandId: String) {
        preferences.edit().putString(key(action, params), commandId)
            .putString(metaKey(commandId), JSONObject().put("action", action).put("params", JSONObject(params)).toString()).apply()
    }
    fun remove(action: String, params: Map<String, Any?>) {
        val id = get(action, params)
        preferences.edit().remove(key(action, params)).apply()
        if (id != null) preferences.edit().remove(metaKey(id)).apply()
    }
    fun removeById(commandId: String) {
        val meta = preferences.getString(metaKey(commandId), null)
        val editor = preferences.edit().remove(metaKey(commandId))
        if (meta != null) {
            try {
                val o = JSONObject(meta)
                val p = o.optJSONObject("params")
                val params = p?.keys()?.asSequence()?.associateWith { p.get(it) } ?: emptyMap()
                editor.remove(key(o.getString("action"), params))
            } catch (_: Throwable) { }
        }
        editor.apply()
    }
    fun all(): Map<String, String> = preferences.all.mapNotNull { (k,v) -> if (k.startsWith(namespace) && v is String) k to v else null }.toMap()
    fun allPending(): List<PendingCommand> = preferences.all.entries.mapNotNull { (k,v) ->
        if (!k.startsWith(namespace + "pending_meta_") || v !is String) return@mapNotNull null
        try { val o=JSONObject(v); val p=o.optJSONObject("params"); PendingCommand(o.getString("action"), p?.keys()?.asSequence()?.associateWith { p.get(it) } ?: emptyMap(), k.removePrefix(namespace + "pending_meta_")) } catch (_: Throwable) { null }
    }

    private fun metaKey(commandId: String) = namespace + "pending_meta_" + commandId
    fun clearServerGenerations(serverId: String, keepCredentialVersion: Long) {
        val prefix = "pending:${serverId.trim()}:"
        val editor = preferences.edit()
        preferences.all.keys.filter { it.startsWith(prefix) && !it.startsWith("pending:${serverId.trim()}:$keepCredentialVersion:") }.forEach(editor::remove)
        editor.commit()
    }

}
