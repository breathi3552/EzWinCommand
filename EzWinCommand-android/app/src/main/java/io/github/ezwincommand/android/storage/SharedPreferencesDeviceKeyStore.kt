package io.github.ezwincommand.android.storage

import android.content.SharedPreferences

class SharedPreferencesDeviceKeyStore(
    private val preferences: SharedPreferences,
) : DeviceKeyStore {
    override fun getBaseUrl(): String? = preferences.getString(KEY_BASE_URL, null)

    override fun getDeviceKey(): String? = preferences.getString(KEY_DEVICE_KEY, null)

    override fun saveSession(baseUrl: String, deviceKey: String) {
        preferences.edit()
            .putString(KEY_BASE_URL, baseUrl.trim())
            .putString(KEY_DEVICE_KEY, deviceKey.trim())
            .apply()
    }

    override fun clearSession() {
        preferences.edit()
            .remove(KEY_BASE_URL)
            .remove(KEY_DEVICE_KEY)
            .apply()
    }

    private companion object {
        const val KEY_BASE_URL = "base_url"
        const val KEY_DEVICE_KEY = "device_key"
    }
}
