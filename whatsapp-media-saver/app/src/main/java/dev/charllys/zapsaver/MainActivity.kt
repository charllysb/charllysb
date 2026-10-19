package dev.charllys.zapsaver

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.TextView
import android.widget.Toast
import androidx.activity.ComponentActivity

/**
 * Launcher screen: how to use the app, the free-tier counter and the Pro purchase.
 * ShareActivity also opens it as the paywall when the daily limit runs out.
 */
class MainActivity : ComponentActivity(), Billing.Listener {

    private lateinit var entitlements: Entitlements
    private lateinit var billing: Billing
    private var price: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        entitlements = Entitlements(this)
        billing = Billing(this, entitlements, this)

        findViewById<Button>(R.id.buy_pro).setOnClickListener { billing.buyPro() }
        findViewById<Button>(R.id.restore).setOnClickListener {
            billing.refreshPurchases()
            Toast.makeText(this, R.string.restore_checking, Toast.LENGTH_SHORT).show()
        }
        showLimitBanner(intent)

        billing.connect()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        showLimitBanner(intent)
    }

    private fun showLimitBanner(intent: Intent) {
        val limited = intent.getBooleanExtra(EXTRA_LIMIT_REACHED, false) && !entitlements.isPro
        findViewById<View>(R.id.limit_banner).visibility = if (limited) View.VISIBLE else View.GONE
    }

    override fun onResume() {
        super.onResume()
        render()
    }

    override fun onDestroy() {
        billing.end()
        super.onDestroy()
    }

    private fun render() {
        val pro = entitlements.isPro
        val status = findViewById<TextView>(R.id.plan_status)
        status.text = if (pro) {
            getString(R.string.plan_pro)
        } else {
            getString(R.string.plan_free, entitlements.quota.remaining(), DailyQuota.FREE_DAILY_LIMIT)
        }
        findViewById<Button>(R.id.buy_pro).apply {
            visibility = if (pro) View.GONE else View.VISIBLE
            text = getString(R.string.buy_pro, price ?: getString(R.string.pro_default_price))
        }
        findViewById<View>(R.id.pro_pitch).visibility = if (pro) View.GONE else View.VISIBLE
        findViewById<View>(R.id.restore).visibility = if (pro) View.GONE else View.VISIBLE
        if (pro) findViewById<View>(R.id.limit_banner).visibility = View.GONE
    }

    override fun onProChanged(isPro: Boolean, justPurchased: Boolean) {
        render()
        if (justPurchased) Toast.makeText(this, R.string.pro_thanks, Toast.LENGTH_LONG).show()
    }

    override fun onPriceLoaded(formattedPrice: String) {
        price = formattedPrice
        render()
    }

    override fun onPurchasePending() {
        Toast.makeText(this, R.string.purchase_pending, Toast.LENGTH_LONG).show()
    }

    override fun onBillingUnavailable(problem: Billing.Problem) {
        val message = when (problem) {
            is Billing.Problem.NotConnected -> getString(R.string.billing_not_connected, problem.code)
            Billing.Problem.ProductNotFound -> getString(R.string.billing_product_missing)
            is Billing.Problem.PurchaseFailed -> getString(R.string.billing_failed, problem.code)
        }
        Toast.makeText(this, message, Toast.LENGTH_LONG).show()
    }

    companion object {
        private const val EXTRA_LIMIT_REACHED = "limit_reached"

        fun paywallIntent(context: Context): Intent =
            Intent(context, MainActivity::class.java)
                .putExtra(EXTRA_LIMIT_REACHED, true)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
    }
}
