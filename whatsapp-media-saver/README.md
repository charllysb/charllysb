# Zap Saver

Android app that adds two entries to the share sheet:

- **Salvar em Downloads**: saves whatever you share (photo, video, voice note, document) straight into the phone's `Download` folder, keeping the original file.
- **Salvar como MP3**: converts audio to MP3 before saving. Works on WhatsApp voice notes (Ogg/Opus) and on the audio track of videos.

Made for WhatsApp, where getting a voice note out as a normal file takes too many taps, but it accepts shares from any app.

## How it works

| Piece | What it does |
|---|---|
| `ShareActivity` | Share target, exposed twice via `activity-alias`. Shows a small progress dialog, processes every shared item (single or multiple), then closes with a toast. |
| `DownloadsWriter` | Android 10+: `MediaStore.Downloads` with `IS_PENDING`, so no storage permission is needed and a failed write never leaves a broken file. Android 7–9: writes to the public Download folder with the legacy permission. |
| `AudioToMp3` | `MediaExtractor` + `MediaCodec` decode the first audio track to PCM. |
| `Mp3Encoder` | Encodes PCM to CBR MP3 with [jump3r](https://github.com/Sciss/jump3r), a pure-Java port of LAME. Android has no built-in MP3 encoder, and jump3r's own wrapper depends on `javax.sound` (absent on Android), so this class wires up the LAME modules directly. |

Voice notes come out as 48 kHz mono at 96 kbps; stereo sources at 128 kbps.

## Build

Needs the Android SDK (or just Android Studio):

```bash
./gradlew testDebugUnitTest assembleDebug
# APK: app/build/outputs/apk/debug/app-debug.apk
```

Every push that touches this folder also builds the APK on GitHub Actions. Download it from the run's **Artifacts** (`zap-saver-debug-apk`) and install it on the phone (you'll need to allow installs from unknown sources).

Requires Android 7.0+.

## License note

jump3r is LGPL-2.1+. It is linked as an unmodified library dependency.
