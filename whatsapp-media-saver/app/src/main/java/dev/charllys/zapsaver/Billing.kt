package dev.charllys.zapsaver

import android.app.Activity
import android.util.Log
import com.android.billingclient.api.AcknowledgePurchaseParams
import com.android.billingclient.api.BillingClient
import com.android.billingclient.api.BillingClientStateListener
import com.android.billingclient.api.BillingFlowParams
import com.android.billingclient.api.BillingResult
import com.android.billingclient.api.PendingPurchasesParams
import com.android.billingclient.api.ProductDetails
import com.android.billingclient.api.Purchase
import com.android.billingclient.api.PurchasesUpdatedListener
import com.android.billingclient.api.QueryProductDetailsParams
import com.android.billingclient.api.QueryPurchasesParams

/**
 * Google Play Billing for the one-time "Pro" unlock.
 *
 * Only works in builds installed from Google Play (any test track). A sideloaded
 * APK can't reach Play Billing, and [Listener.onBillingUnavailable] says why.
 * [Listener] callbacks are always delivered on the main thread.
 */
class Billing(
    private val activity: Activity,
    private val entitlements: Entitlements,
    private val listener: Listener,
) : PurchasesUpdatedListener {

    interface Listener {
        fun onProChanged(isPro: Boolean, justPurchased: Boolean)
        fun onPriceLoaded(formattedPrice: String)
        fun onPurchasePending()
        fun onBillingUnavailable(problem: Problem)
    }

    /** Why a purchase couldn't start; the codes help diagnose test-track setups. */
    sealed interface Problem {
        /** Couldn't talk to Play Billing at all (sideloaded build, Play Store outdated, offline). */
        data class NotConnected(val code: Int) : Problem
        /** Connected, but Play has no active product with [PRO_PRODUCT_ID] for this app yet. */
        data object ProductNotFound : Problem
        data class PurchaseFailed(val code: Int) : Problem
    }

    private val client = BillingClient.newBuilder(activity)
        .setListener(this)
        .enablePendingPurchases(PendingPurchasesParams.newBuilder().enableOneTimeProducts().build())
        .build()

    private var product: ProductDetails? = null

    fun connect(onReady: (() -> Unit)? = null) {
        client.startConnection(object : BillingClientStateListener {
            override fun onBillingSetupFinished(result: BillingResult) {
                if (result.responseCode == BillingClient.BillingResponseCode.OK) {
                    refreshPurchases()
                    loadProduct { onReady?.invoke() }
                } else {
                    Log.w(TAG, "Billing setup failed: ${result.responseCode} ${result.debugMessage}")
                    if (onReady != null) ui { listener.onBillingUnavailable(Problem.NotConnected(result.responseCode)) }
                }
            }

            override fun onBillingServiceDisconnected() = Unit
        })
    }

    fun end() = client.endConnection()

    /** Re-reads what the Play account owns. Also restores Pro on a new phone or after reinstalling. */
    fun refreshPurchases() {
        if (!client.isReady) return
        val params = QueryPurchasesParams.newBuilder().setProductType(BillingClient.ProductType.INAPP).build()
        client.queryPurchasesAsync(params) { result, purchases ->
            if (result.responseCode == BillingClient.BillingResponseCode.OK) {
                handlePurchases(purchases, fromRefresh = true)
            }
        }
    }

    /**
     * Starts the purchase. Reconnects and re-queries the product first when needed,
     * so a product activated in Play Console after the app opened still works.
     */
    fun buyPro() {
        when {
            !client.isReady -> connect { launchPurchase() }
            product == null -> loadProduct { launchPurchase() }
            else -> launchPurchase()
        }
    }

    private fun launchPurchase() {
        val details = product ?: return ui { listener.onBillingUnavailable(Problem.ProductNotFound) }
        val params = BillingFlowParams.newBuilder()
            .setProductDetailsParamsList(
                listOf(BillingFlowParams.ProductDetailsParams.newBuilder().setProductDetails(details).build())
            )
            .build()
        client.launchBillingFlow(activity, params)
    }

    override fun onPurchasesUpdated(result: BillingResult, purchases: MutableList<Purchase>?) {
        when (result.responseCode) {
            BillingClient.BillingResponseCode.OK -> handlePurchases(purchases.orEmpty(), fromRefresh = false)
            BillingClient.BillingResponseCode.ITEM_ALREADY_OWNED -> refreshPurchases()
            BillingClient.BillingResponseCode.USER_CANCELED -> Unit
            else -> {
                Log.w(TAG, "Purchase failed: ${result.responseCode} ${result.debugMessage}")
                ui { listener.onBillingUnavailable(Problem.PurchaseFailed(result.responseCode)) }
            }
        }
    }

    private fun loadProduct(onDone: () -> Unit = {}) {
        val params = QueryProductDetailsParams.newBuilder()
            .setProductList(
                listOf(
                    QueryProductDetailsParams.Product.newBuilder()
                        .setProductId(PRO_PRODUCT_ID)
                        .setProductType(BillingClient.ProductType.INAPP)
                        .build()
                )
            )
            .build()
        client.queryProductDetailsAsync(params) { result, details ->
            if (result.responseCode == BillingClient.BillingResponseCode.OK) {
                product = details.productDetailsList.firstOrNull()
                product?.oneTimePurchaseOfferDetails?.formattedPrice?.let { ui { listener.onPriceLoaded(it) } }
            } else {
                Log.w(TAG, "Product query failed: ${result.responseCode} ${result.debugMessage}")
            }
            if (product == null) Log.w(TAG, "No active product '$PRO_PRODUCT_ID' returned by Play")
            // Play delivers this on a background thread; hop back for UI callers.
            ui(onDone)
        }
    }

    private fun handlePurchases(purchases: List<Purchase>, fromRefresh: Boolean) {
        val pro = purchases.filter { PRO_PRODUCT_ID in it.products }
        val purchased = pro.firstOrNull { it.purchaseState == Purchase.PurchaseState.PURCHASED }

        if (purchased != null) {
            // Play refunds purchases that aren't acknowledged within 3 days.
            if (!purchased.isAcknowledged) {
                val ack = AcknowledgePurchaseParams.newBuilder().setPurchaseToken(purchased.purchaseToken).build()
                client.acknowledgePurchase(ack) { r ->
                    if (r.responseCode != BillingClient.BillingResponseCode.OK) {
                        Log.w(TAG, "Acknowledge failed, will retry on next refresh: ${r.debugMessage}")
                    }
                }
            }
            val wasPro = entitlements.isPro
            entitlements.isPro = true
            ui { listener.onProChanged(isPro = true, justPurchased = !wasPro) }
            return
        }

        if (pro.any { it.purchaseState == Purchase.PurchaseState.PENDING }) {
            // Pix/boleto can take a while; Pro unlocks on the refresh after it clears.
            ui { listener.onPurchasePending() }
        }
        if (fromRefresh && entitlements.isPro) {
            // A full refresh that finds no purchase means it was refunded or revoked.
            entitlements.isPro = false
            ui { listener.onProChanged(isPro = false, justPurchased = false) }
        }
    }

    // Play Billing may answer on a background thread; the UI must only be touched on the main one.
    private fun ui(block: () -> Unit) = activity.runOnUiThread(block)

    companion object {
        /** Must match the in-app product created in Play Console (Monetize → Products → In-app products). */
        const val PRO_PRODUCT_ID = "zapsaver_pro"
        private const val TAG = "ZapSaverBilling"
    }
}
