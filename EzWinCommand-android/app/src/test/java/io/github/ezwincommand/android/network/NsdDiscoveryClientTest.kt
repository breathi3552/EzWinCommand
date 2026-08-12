package io.github.ezwincommand.android.network

import io.github.ezwincommand.android.model.ServerIdentity
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class NsdDiscoveryClientTest {
    @Test
    fun `http 426 dispatches an incompatible discovery callback`() {
        val events = mutableListOf<DiscoveryEvent.Incompatible>()
        var failures = 0

        NsdDiscoveryClient.dispatchIdentityResult(
            ApiResult.HttpError(426, "protocol mismatch"),
            onSuccess = { throw AssertionError("unexpected success") },
            onIncompatible = events::add,
            onFailure = { _, _ -> failures++ },
        )

        assertEquals(0, failures)
        assertEquals("服务器协议不兼容，请升级应用。", events.single().message)
    }

    @Test
    fun `unsupported identity payload dispatches the same incompatible callback`() {
        val events = mutableListOf<DiscoveryEvent.Incompatible>()
        val mismatch = UnsupportedProtocolException(1)

        NsdDiscoveryClient.dispatchIdentityResult(
            ApiResult.ParseError(mismatch.message.orEmpty(), mismatch),
            onSuccess = { throw AssertionError("unexpected success") },
            onIncompatible = events::add,
            onFailure = { _, _ -> throw AssertionError("unexpected failure") },
        )

        assertEquals("服务器协议不兼容，请升级应用。", events.single().message)
    }

    @Test
    fun `compatible identity remains a discovered server update`() {
        val server = ServerIdentity(2, "00000000-0000-4000-8000-000000000001", "PC")
        var found: ServerIdentity? = null

        NsdDiscoveryClient.dispatchIdentityResult(
            ApiResult.Success(server),
            onSuccess = { found = it },
            onIncompatible = { throw AssertionError("unexpected incompatibility") },
            onFailure = { _, _ -> throw AssertionError("unexpected failure") },
        )

        assertTrue(found === server)
    }
}
