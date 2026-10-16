package dev.charllys.zapsaver

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayOutputStream
import kotlin.math.PI
import kotlin.math.sin

class Mp3EncoderTest {

    private fun sine(seconds: Int, sampleRate: Int, channels: Int): ShortArray {
        val frames = seconds * sampleRate
        return ShortArray(frames * channels) { i ->
            val t = (i / channels).toDouble() / sampleRate
            (sin(2 * PI * 440 * t) * 8000).toInt().toShort()
        }
    }

    private fun encode(pcm: ShortArray, sampleRate: Int, channels: Int, kbps: Int): ByteArray {
        val out = ByteArrayOutputStream()
        val encoder = Mp3Encoder(sampleRate, channels, kbps)
        // Feed in decoder-sized chunks, like AudioToMp3 does.
        val chunk = 4096 * channels
        var offset = 0
        while (offset < pcm.size) {
            val n = minOf(chunk, pcm.size - offset)
            encoder.encode(pcm.copyOfRange(offset, offset + n), n, out)
            offset += n
        }
        encoder.finish(out)
        return out.toByteArray()
    }

    private fun assertMp3(bytes: ByteArray, seconds: Int, kbps: Int) {
        // MPEG audio frame sync: 11 set bits.
        assertEquals(0xFF, bytes[0].toInt() and 0xFF)
        assertEquals(0xE0, bytes[1].toInt() and 0xE0)
        val expected = seconds * kbps * 1000 / 8
        assertTrue("size ${bytes.size} far from $expected", bytes.size in expected * 9 / 10..expected * 11 / 10)
    }

    @Test
    fun encodesMono48kVoiceNote() {
        // Opus voice notes decode to 48 kHz mono.
        assertMp3(encode(sine(5, 48_000, 1), 48_000, 1, 96), 5, 96)
    }

    @Test
    fun encodesStereo44k() {
        assertMp3(encode(sine(5, 44_100, 2), 44_100, 2, 128), 5, 128)
    }
}
