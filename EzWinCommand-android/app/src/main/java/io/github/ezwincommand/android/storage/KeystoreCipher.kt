package io.github.ezwincommand.android.storage

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import java.nio.charset.StandardCharsets
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import android.util.Base64

/** Android Keystore AES/GCM 封装；密文永不作为明文回退。 */
interface SessionCipher {
    fun encrypt(serverId: String, credentialVersion: Long, value: String): KeystoreCipher.EncryptedValue
    fun decrypt(serverId: String, value: KeystoreCipher.EncryptedValue): String
    fun deleteAlias(alias: String)
    fun applicationAliases(): Set<String>
}

class KeystoreCipher(
    private val keyStore: KeyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) },
) : SessionCipher {
    data class EncryptedValue(val alias: String, val iv: String, val ciphertext: String)

    override fun encrypt(serverId: String, credentialVersion: Long, value: String): EncryptedValue {
        val alias = aliasFor(serverId, credentialVersion)
        val key = getOrCreate(alias)
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, key)
        cipher.updateAAD(serverId.toByteArray(StandardCharsets.UTF_8))
        val encrypted = cipher.doFinal(value.toByteArray(StandardCharsets.UTF_8))
        return EncryptedValue(alias, encode(cipher.iv), encode(encrypted))
    }

    override fun decrypt(serverId: String, value: EncryptedValue): String {
        val key = (keyStore.getKey(value.alias, null) as? SecretKey)
            ?: throw IllegalStateException("credential key unavailable")
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.DECRYPT_MODE, key, GCMParameterSpec(128, decode(value.iv)))
        cipher.updateAAD(serverId.toByteArray(StandardCharsets.UTF_8))
        return cipher.doFinal(decode(value.ciphertext)).toString(StandardCharsets.UTF_8)
    }

    override fun deleteAlias(alias: String) {
        if (keyStore.containsAlias(alias)) keyStore.deleteEntry(alias)
    }

    override fun applicationAliases(): Set<String> = keyStore.aliases().toList()
        .filterTo(linkedSetOf()) { it.startsWith(ALIAS_PREFIX) }

    private fun getOrCreate(alias: String): SecretKey {
        (keyStore.getKey(alias, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEYSTORE)
        generator.init(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
            .setKeySize(256)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .build())
        return generator.generateKey()
    }

    private fun aliasFor(serverId: String, version: Long): String =
        "$ALIAS_PREFIX${sha256(serverId)}_$version"

    private fun sha256(value: String): String = java.security.MessageDigest.getInstance("SHA-256")
        .digest(value.toByteArray(StandardCharsets.UTF_8)).joinToString("") { "%02x".format(it) }.take(32)

    private fun encode(bytes: ByteArray) = Base64.encodeToString(bytes, Base64.NO_WRAP)
    private fun decode(value: String) = Base64.decode(value, Base64.NO_WRAP)

    private companion object {
        const val ALIAS_PREFIX = "ezwin_session_"
        const val ANDROID_KEYSTORE = "AndroidKeyStore"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
    }
}
