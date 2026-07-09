package io.github.ezwincommand.android.storage

interface DeviceKeyStore {
    fun getBaseUrl(): String?
    fun getDeviceKey(): String?
    fun saveSession(baseUrl: String, deviceKey: String)
    fun clearSession()
}
