package dev.charllys.zapsaver;

import de.sciss.jump3r.mp3.BitStream;
import de.sciss.jump3r.mp3.GainAnalysis;
import de.sciss.jump3r.mp3.GetAudio;
import de.sciss.jump3r.mp3.ID3Tag;
import de.sciss.jump3r.mp3.Lame;
import de.sciss.jump3r.mp3.LameGlobalFlags;
import de.sciss.jump3r.mp3.MPEGMode;
import de.sciss.jump3r.mp3.Parse;
import de.sciss.jump3r.mp3.Presets;
import de.sciss.jump3r.mp3.Quantize;
import de.sciss.jump3r.mp3.QuantizePVT;
import de.sciss.jump3r.mp3.Reservoir;
import de.sciss.jump3r.mp3.Takehiro;
import de.sciss.jump3r.mp3.VBRTag;
import de.sciss.jump3r.mp3.VbrMode;
import de.sciss.jump3r.mp3.Version;
import de.sciss.jump3r.mpg.Common;
import de.sciss.jump3r.mpg.Interface;
import de.sciss.jump3r.mpg.MPGLib;

import java.io.IOException;
import java.io.OutputStream;

/**
 * Streams 16-bit PCM into MP3 using jump3r (a pure-Java port of LAME).
 *
 * jump3r's own high-level LameEncoder depends on javax.sound, which Android
 * does not ship, so this wires up the same LAME modules directly. Kept in
 * Java so it can be unit-tested on a plain JVM.
 */
public final class Mp3Encoder {

    private final Lame lame;
    private final LameGlobalFlags gfp;
    private final int channels;
    private byte[] mp3Buf = new byte[0];
    private int[] left = new int[0];
    private int[] right = new int[0];

    /**
     * Output is CBR without a Xing/LAME tag, because the tag has to be patched
     * into the start of the file and we write to a non-seekable stream.
     */
    public Mp3Encoder(int sampleRate, int channels, int bitrateKbps) {
        if (channels != 1 && channels != 2) {
            throw new IllegalArgumentException("Only mono or stereo PCM is supported, got " + channels + " channels");
        }
        this.channels = channels;

        lame = new Lame();
        GetAudio gaud = new GetAudio();
        GainAnalysis ga = new GainAnalysis();
        BitStream bs = new BitStream();
        Presets p = new Presets();
        QuantizePVT qupvt = new QuantizePVT();
        Quantize qu = new Quantize();
        VBRTag vbr = new VBRTag();
        Version ver = new Version();
        ID3Tag id3 = new ID3Tag();
        Reservoir rv = new Reservoir();
        Takehiro tak = new Takehiro();
        Parse parse = new Parse();
        MPGLib mpg = new MPGLib();
        Interface intf = new Interface();
        Common common = new Common();

        lame.setModules(ga, bs, p, qupvt, qu, vbr, ver, id3, mpg);
        bs.setModules(ga, mpg, ver, vbr);
        id3.setModules(bs, ver);
        p.setModules(lame);
        qu.setModules(bs, rv, qupvt, tak);
        qupvt.setModules(tak, rv, lame.enc.psy);
        rv.setModules(bs);
        tak.setModules(qupvt);
        vbr.setModules(lame, bs, ver);
        gaud.setModules(parse, mpg);
        parse.setModules(ver, id3, p);
        mpg.setModules(intf, common);
        intf.setModules(vbr, common);

        gfp = lame.lame_init();
        gfp.num_channels = channels;
        gfp.in_samplerate = sampleRate;
        gfp.mode = channels == 1 ? MPEGMode.MONO : MPEGMode.JOINT_STEREO;
        gfp.VBR = VbrMode.vbr_off;
        gfp.brate = bitrateKbps;
        gfp.quality = 5;
        gfp.bWriteVbrTag = false;
        id3.id3tag_init(gfp);
        gfp.write_id3tag_automatic = false;
        gfp.findReplayGain = false;

        if (lame.lame_init_params(gfp) < 0) {
            throw new IllegalArgumentException(
                    "LAME rejected parameters: " + sampleRate + " Hz, " + channels + " ch, " + bitrateKbps + " kbps");
        }
    }

    /** Encodes {@code length} interleaved samples from {@code pcm} and writes any finished frames to {@code out}. */
    public void encode(short[] pcm, int length, OutputStream out) throws IOException {
        int frames = length / channels;
        if (frames == 0) return;
        ensureCapacity(frames);

        if (channels == 2) {
            for (int i = 0; i < frames; i++) {
                left[i] = pcm[2 * i] << 16;
                right[i] = pcm[2 * i + 1] << 16;
            }
        } else {
            for (int i = 0; i < frames; i++) {
                left[i] = pcm[i] << 16;
                right[i] = left[i];
            }
        }

        int written = lame.lame_encode_buffer_int(gfp, left, right, frames, mp3Buf, 0, mp3Buf.length);
        if (written < 0) throw new IOException("LAME encode failed with code " + written);
        out.write(mp3Buf, 0, written);
    }

    /** Flushes the last partial frame and releases the encoder. */
    public void finish(OutputStream out) throws IOException {
        ensureCapacity(0);
        int written = lame.lame_encode_flush(gfp, mp3Buf, 0, mp3Buf.length);
        lame.lame_close(gfp);
        if (written < 0) throw new IOException("LAME flush failed with code " + written);
        out.write(mp3Buf, 0, written);
    }

    private void ensureCapacity(int frames) {
        if (left.length < frames) {
            left = new int[frames];
            right = new int[frames];
        }
        // Worst case from lame.h: 1.25 * samples + 7200.
        int needed = frames + frames / 4 + 7200;
        if (mp3Buf.length < needed) mp3Buf = new byte[needed];
    }
}
