package dev.charllys.zapsaver

import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Where the quota keeps today's date and count; split out so the logic is testable without Android. */
interface QuotaStore {
    val day: String?
    val used: Int
    fun save(day: String, used: Int)
}

/**
 * Free-tier limit: [limit] saves per calendar day, in the phone's local time zone.
 * The count resets the first time it is read on a new day.
 */
class DailyQuota(
    private val store: QuotaStore,
    private val limit: Int = FREE_DAILY_LIMIT,
    private val today: () -> String = { SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Date()) },
) {
    fun remaining(): Int = (limit - usedToday()).coerceAtLeast(0)

    fun consume(count: Int = 1) {
        store.save(today(), usedToday() + count)
    }

    private fun usedToday(): Int = if (store.day == today()) store.used else 0

    companion object {
        const val FREE_DAILY_LIMIT = 4
    }
}
