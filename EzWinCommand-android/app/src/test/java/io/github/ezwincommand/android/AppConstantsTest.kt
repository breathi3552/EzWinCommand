package io.github.ezwincommand.android

import kotlin.test.Test
import kotlin.test.assertEquals

class AppConstantsTest {

    @Test
    fun exposesExpectedDefaults() {
        assertEquals(8080, AppConstants.DEFAULT_PORT)
        assertEquals("http", AppConstants.DEFAULT_SCHEME)
    }
}
