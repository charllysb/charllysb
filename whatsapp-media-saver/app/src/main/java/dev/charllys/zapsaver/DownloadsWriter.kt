package dev.charllys.zapsaver

import android.content.ContentValues
import android.content.Context
import android.media.MediaScannerConnection
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import androidx.annotation.RequiresApi
import java.io.File
import java.io.IOException
import java.io.OutputStream

/** Writes a file into the public Download folder, on every supported Android version. */
class DownloadsWriter(private val context: Context) {

    /**
     * Creates [displayName] in Downloads and hands its stream to [write].
     * If [write] throws, the half-written file is removed so Downloads never
     * shows a broken entry. Returns the name the file was actually saved as.
     */
    fun save(displayName: String, mimeType: String, write: (OutputStream) -> Unit): String =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            saveWithMediaStore(displayName, mimeType, write)
        } else {
            saveLegacy(displayName, mimeType, write)
        }

    @RequiresApi(Build.VERSION_CODES.Q)
    private fun saveWithMediaStore(displayName: String, mimeType: String, write: (OutputStream) -> Unit): String {
        val resolver = context.contentResolver
        val values = ContentValues().apply {
            put(MediaStore.Downloads.DISPLAY_NAME, displayName)
            put(MediaStore.Downloads.MIME_TYPE, mimeType)
            put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS)
            put(MediaStore.Downloads.IS_PENDING, 1)
        }
        val uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
            ?: throw IOException("MediaStore refused to create $displayName")

        try {
            resolver.openOutputStream(uri)?.use(write) ?: throw IOException("Could not open $uri")
            resolver.update(uri, ContentValues().apply { put(MediaStore.Downloads.IS_PENDING, 0) }, null, null)
        } catch (e: Exception) {
            resolver.delete(uri, null, null)
            throw e
        }

        // MediaStore appends " (1)" etc. on name clashes; report what it chose.
        resolver.query(uri, arrayOf(MediaStore.Downloads.DISPLAY_NAME), null, null, null)?.use { c ->
            if (c.moveToFirst()) return c.getString(0)
        }
        return displayName
    }

    @Suppress("DEPRECATION")
    private fun saveLegacy(displayName: String, mimeType: String, write: (OutputStream) -> Unit): String {
        val dir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
        if (!dir.exists() && !dir.mkdirs()) throw IOException("Could not create $dir")

        val file = uniqueFile(dir, displayName)
        try {
            file.outputStream().use(write)
        } catch (e: Exception) {
            file.delete()
            throw e
        }
        MediaScannerConnection.scanFile(context, arrayOf(file.absolutePath), arrayOf(mimeType), null)
        return file.name
    }

    private fun uniqueFile(dir: File, name: String): File {
        val base = name.substringBeforeLast('.')
        val ext = name.substringAfterLast('.', "").let { if (it.isEmpty()) "" else ".$it" }
        var candidate = File(dir, name)
        var n = 1
        while (candidate.exists()) candidate = File(dir, "$base (${n++})$ext")
        return candidate
    }
}
