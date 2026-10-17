package dev.charllys.zapsaver

import android.content.Context

/**
 * Local record of what the user may do: the Pro flag and the free daily quota.
 *
 * The Pro flag is a cache of the Play purchase so the share flow works offline
 * and instantly; [Billing] refreshes it whenever the main screen opens.
 */
class Entitlements(context: Context) {

    private val prefs = context.applicationContext.getSharedPreferences("zapsaver", Context.MODE_PRIVATE)

    var isPro: Boolean
        get() = prefs.getBoolean(KEY_PRO, false)
        set(value) = prefs.edit().putBoolean(KEY_PRO, value).apply()

    val quota = DailyQuota(object : QuotaStore {
        override val day: String? get() = prefs.getString(KEY_DAY, null)
        override val used: Int get() = prefs.getInt(KEY_USED, 0)
        override fun save(day: String, used: Int) {
            prefs.edit().putString(KEY_DAY, day).putInt(KEY_USED, used).apply()
        }
    })

    /** How many more items may be saved right now; [Int.MAX_VALUE] for Pro. */
    fun allowance(): Int = if (isPro) Int.MAX_VALUE else quota.remaining()

    fun recordSaves(count: Int) {
        if (!isPro && count > 0) quota.consume(count)
    }

    private companion object {
        const val KEY_PRO = "pro"
        const val KEY_DAY = "quota_day"
        const val KEY_USED = "quota_used"
    }
}
