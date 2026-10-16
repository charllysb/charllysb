package dev.charllys.zapsaver

import android.content.Context
import android.media.AudioFormat
import android.media.MediaCodec
import android.media.MediaExtractor
import android.media.MediaFormat
import android.net.Uri
import java.io.IOException
import java.io.OutputStream
import java.nio.ByteOrder

/**
 * Decodes the first audio track of [source] (WhatsApp voice notes are Ogg/Opus,
 * but anything MediaExtractor understands works, including the audio of a video)
 * and re-encodes it to MP3.
 */
class AudioToMp3(private val context: Context) {

    fun convert(source: Uri, out: OutputStream) {
        val extractor = MediaExtractor()
        var decoder: MediaCodec? = null
        try {
            extractor.setDataSource(context, source, null)
            val track = (0 until extractor.trackCount).firstOrNull {
                extractor.getTrackFormat(it).getString(MediaFormat.KEY_MIME)?.startsWith("audio/") == true
            } ?: throw IOException("No audio track found")
            extractor.selectTrack(track)

            val inputFormat = extractor.getTrackFormat(track)
            decoder = MediaCodec.createDecoderByType(inputFormat.getString(MediaFormat.KEY_MIME)!!)
            decoder.configure(inputFormat, null, null, 0)
            decoder.start()
            pump(extractor, decoder, out)
        } finally {
            decoder?.runCatching { stop() }
            decoder?.release()
            extractor.release()
        }
    }

    private fun pump(extractor: MediaExtractor, decoder: MediaCodec, out: OutputStream) {
        val info = MediaCodec.BufferInfo()
        var encoder: Mp3Encoder? = null
        var floatPcm = false
        var pcm = ShortArray(0)
        var inputDone = false

        while (true) {
            if (!inputDone) {
                val inIndex = decoder.dequeueInputBuffer(TIMEOUT_US)
                if (inIndex >= 0) {
                    val buf = decoder.getInputBuffer(inIndex)!!
                    val size = extractor.readSampleData(buf, 0)
                    if (size < 0) {
                        decoder.queueInputBuffer(inIndex, 0, 0, 0, MediaCodec.BUFFER_FLAG_END_OF_STREAM)
                        inputDone = true
                    } else {
                        decoder.queueInputBuffer(inIndex, 0, size, extractor.sampleTime, 0)
                        extractor.advance()
                    }
                }
            }

            val outIndex = decoder.dequeueOutputBuffer(info, TIMEOUT_US)
            if (outIndex == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                // The real PCM layout is only known here, so the encoder starts here too.
                encoder = startEncoder(decoder.outputFormat)
                floatPcm = isFloatPcm(decoder.outputFormat)
            } else if (outIndex >= 0) {
                if (info.size > 0) {
                    val enc = encoder ?: startEncoder(decoder.outputFormat).also {
                        encoder = it
                        floatPcm = isFloatPcm(decoder.outputFormat)
                    }
                    val buf = decoder.getOutputBuffer(outIndex)!!.apply {
                        position(info.offset)
                        limit(info.offset + info.size)
                        order(ByteOrder.nativeOrder())
                    }
                    val count = if (floatPcm) info.size / 4 else info.size / 2
                    if (pcm.size < count) pcm = ShortArray(count)
                    if (floatPcm) {
                        val floats = buf.asFloatBuffer()
                        for (i in 0 until count) {
                            pcm[i] = (floats.get(i).coerceIn(-1f, 1f) * Short.MAX_VALUE).toInt().toShort()
                        }
                    } else {
                        buf.asShortBuffer().get(pcm, 0, count)
                    }
                    enc.encode(pcm, count, out)
                }
                decoder.releaseOutputBuffer(outIndex, false)
                if (info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0) break
            }
        }

        (encoder ?: throw IOException("No audio was decoded")).finish(out)
    }

    private fun startEncoder(format: MediaFormat): Mp3Encoder {
        val sampleRate = format.getInteger(MediaFormat.KEY_SAMPLE_RATE)
        val channels = format.getInteger(MediaFormat.KEY_CHANNEL_COUNT)
        if (channels > 2) throw IOException("Unsupported channel count: $channels")
        return Mp3Encoder(sampleRate, channels, if (channels == 1) MONO_KBPS else STEREO_KBPS)
    }

    private fun isFloatPcm(format: MediaFormat) =
        format.containsKey(MediaFormat.KEY_PCM_ENCODING) &&
            format.getInteger(MediaFormat.KEY_PCM_ENCODING) == AudioFormat.ENCODING_PCM_FLOAT

    private companion object {
        const val TIMEOUT_US = 10_000L
        const val MONO_KBPS = 96
        const val STEREO_KBPS = 128
    }
}
