package dev.charllys.zapsaver

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.OpenableColumns
import android.util.Log
import android.webkit.MimeTypeMap
import android.widget.TextView
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import androidx.core.content.IntentCompat
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Share target. Shows a small "saving…" dialog while it copies (or converts)
 * every shared item into Downloads, then closes itself.
 */
class ShareActivity : ComponentActivity() {

    private val requestLegacyPermission =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            if (granted) process() else {
                Toast.makeText(this, R.string.permission_denied, Toast.LENGTH_LONG).show()
                finish()
            }
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_share)
        setFinishOnTouchOutside(false)

        val needsPermission = Build.VERSION.SDK_INT < Build.VERSION_CODES.Q &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.WRITE_EXTERNAL_STORAGE) !=
            PackageManager.PERMISSION_GRANTED
        if (needsPermission) {
            requestLegacyPermission.launch(Manifest.permission.WRITE_EXTERNAL_STORAGE)
        } else {
            process()
        }
    }

    private fun process() {
        val uris = sharedUris(intent)
        if (uris.isEmpty()) {
            Toast.makeText(this, R.string.nothing_shared, Toast.LENGTH_LONG).show()
            finish()
            return
        }
        val entitlements = Entitlements(this)
        val allowance = entitlements.allowance()
        if (allowance == 0) {
            startActivity(MainActivity.paywallIntent(this))
            finish()
            return
        }
        val batch = uris.take(allowance)
        val skipped = uris.size - batch.size

        val toMp3 = intent.component?.className?.endsWith(".SaveAsMp3") == true
        val status = findViewById<TextView>(R.id.status)
        status.setText(if (toMp3) R.string.converting else R.string.saving)

        lifecycleScope.launch {
            val saved = mutableListOf<String>()
            var failed = 0
            batch.forEachIndexed { i, uri ->
                if (batch.size > 1) status.text = getString(R.string.progress, i + 1, batch.size)
                try {
                    saved += withContext(Dispatchers.IO) { saveOne(uri, toMp3) }
                } catch (e: Exception) {
                    Log.e(TAG, "Failed to save $uri", e)
                    failed++
                }
            }
            entitlements.recordSaves(saved.size)

            var message = when {
                failed == 0 && saved.size == 1 -> getString(R.string.saved_one, saved.single())
                failed == 0 -> getString(R.string.saved_many, saved.size)
                saved.isEmpty() -> getString(R.string.failed_all)
                else -> getString(R.string.saved_partial, saved.size, failed)
            }
            if (skipped > 0) {
                message += "\n" + getString(R.string.skipped_limit, skipped)
                startActivity(MainActivity.paywallIntent(this@ShareActivity))
            }
            Toast.makeText(this@ShareActivity, message, Toast.LENGTH_LONG).show()
            finish()
        }
    }

    private fun saveOne(uri: Uri, toMp3: Boolean): String {
        val mime = contentResolver.getType(uri)?.substringBefore(';')?.trim() ?: "application/octet-stream"
        val name = displayName(uri, mime)
        val writer = DownloadsWriter(this)

        val alreadyMp3 = mime == "audio/mpeg" || name.endsWith(".mp3", ignoreCase = true)
        if (toMp3 && !alreadyMp3) {
            val mp3Name = name.substringBeforeLast('.') + ".mp3"
            return writer.save(mp3Name, "audio/mpeg") { out -> AudioToMp3(this).convert(uri, out) }
        }
        return writer.save(name, mime) { out ->
            val input = contentResolver.openInputStream(uri) ?: error("Could not open $uri")
            input.use { it.copyTo(out) }
        }
    }

    /** WhatsApp usually provides a real name ("WhatsApp Ptt 2026-10-16 at 22.30.01.opus"); otherwise make one up. */
    private fun displayName(uri: Uri, mime: String): String {
        val fromProvider = runCatching {
            contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { c ->
                if (c.moveToFirst()) c.getString(0) else null
            }
        }.getOrNull() ?: uri.lastPathSegment?.takeIf { '.' in it }

        val cleaned = fromProvider?.replace(Regex("[\\\\/:*?\"<>|]"), "_")?.trim()
        if (!cleaned.isNullOrEmpty()) {
            return if ('.' in cleaned) cleaned else cleaned + extensionFor(mime)
        }
        val stamp = SimpleDateFormat("yyyyMMdd_HHmmss_SSS", Locale.US).format(Date())
        return "WhatsApp_$stamp${extensionFor(mime)}"
    }

    private fun extensionFor(mime: String): String {
        if (mime == "audio/ogg" || mime == "audio/opus") return ".opus"
        return MimeTypeMap.getSingleton().getExtensionFromMimeType(mime)?.let { ".$it" } ?: ""
    }

    private fun sharedUris(intent: Intent): List<Uri> {
        val uris = linkedSetOf<Uri>()
        when (intent.action) {
            Intent.ACTION_SEND ->
                IntentCompat.getParcelableExtra(intent, Intent.EXTRA_STREAM, Uri::class.java)?.let(uris::add)
            Intent.ACTION_SEND_MULTIPLE ->
                IntentCompat.getParcelableArrayListExtra(intent, Intent.EXTRA_STREAM, Uri::class.java)
                    ?.let(uris::addAll)
        }
        intent.clipData?.let { clip ->
            for (i in 0 until clip.itemCount) clip.getItemAt(i).uri?.let(uris::add)
        }
        return uris.toList()
    }

    private companion object {
        const val TAG = "ZapSaver"
    }
}
