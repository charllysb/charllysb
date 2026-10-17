package dev.charllys.zapsaver

import org.junit.Assert.assertEquals
import org.junit.Test

class DailyQuotaTest {

    private class MemoryStore : QuotaStore {
        override var day: String? = null
        override var used: Int = 0
        override fun save(day: String, used: Int) {
            this.day = day
            this.used = used
        }
    }

    private var today = "2026-10-17"
    private val quota = DailyQuota(MemoryStore(), limit = 4, today = { today })

    @Test
    fun startsWithFullAllowance() {
        assertEquals(4, quota.remaining())
    }

    @Test
    fun countsDownAndStopsAtZero() {
        quota.consume(3)
        assertEquals(1, quota.remaining())
        quota.consume(2)
        assertEquals(0, quota.remaining())
    }

    @Test
    fun resetsOnNewDay() {
        quota.consume(4)
        assertEquals(0, quota.remaining())
        today = "2026-10-18"
        assertEquals(4, quota.remaining())
        quota.consume(1)
        assertEquals(3, quota.remaining())
    }
}
