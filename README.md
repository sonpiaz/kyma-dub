# dub-cli

Dub any video into another language with a natural, **time-aligned** AI voiceover — from the terminal.

```bash
dub talk.mp4 --from vi --voice charlie
# -> talk [EN dub].mp4
```

It transcribes the source, translates it to the target language *fitted to the original timing*, speaks it in a natural voice, and muxes the new audio back over the original video. The narration tracks what's on screen — it doesn't drift.

Built the same way as [watch-cli](https://github.com/sonpiaz/watch-cli): use it yourself, ship it open-source, and dogfood [Kyma](https://kymaapi.com) for the AI calls.

## Install

```bash
curl -fsSL https://github.com/sonpiaz/dub-cli/releases/latest/download/install.sh | bash
```

Then set your keys (one Kyma key + one ElevenLabs key):

```bash
# ~/.config/dub-cli/env  (created by the installer)
KYMA_API_KEY=kyma-xxxxxxxx        # transcription + translation
ELEVENLABS_API_KEY=xi-xxxxxxxx    # the voice
```

Get a Kyma key at [kymaapi.com](https://kymaapi.com) — 60 seconds, no card, free credit at signup.

**Dependencies:** `ffmpeg`, `ffprobe`, `curl`, `python3` (`brew install ffmpeg`).

## Usage

```bash
dub <video> [options]

  --from <lang>            source language code (default: auto-detect)
  --to <lang>              target language code (default: en)
  --voice <name|id>        charlie | will | liam | brian | rachel | adam | jessica
                           or a raw ElevenLabs voice id (default: charlie)
  --tts <engine>           elevenlabs (default, best v3) | kyma
  --model <id>             translation model via Kyma (default: best)
  --wps <n>                target words/second for timing (default: 2.4)
  --allow-voice-fallback   permit an independent MiniMax voice if every
                           ElevenLabs path is down (CHANGES the voice)
  --out <path>             output file
  --keep-temp              keep intermediate files
  --version / -h
```

Examples:

```bash
dub talk.mp4                          # auto -> English, voice charlie
dub talk.mp4 --voice will             # a younger, friendlier voice
dub talk.mp4 --to es --voice rachel   # dub to Spanish
dub talk.mp4 --tts kyma               # route TTS through Kyma (one key)
```

## How it works

```
video ─▶ extract audio (ffmpeg)
      ─▶ transcribe + timestamps (Whisper)
      ─▶ group into chunks at natural speech pauses
      ─▶ translate each chunk, fitting word count to its seconds (LLM)
      ─▶ TTS each chunk with a locked voice engine
      ─▶ time-stretch each clip to its slot, reassemble on the original timeline
      ─▶ mux new audio over the original video
```

The trick that keeps it in sync: it never translates-then-reads one long block (that drifts). It translates, voices, and time-stretches **per chunk anchored to the original timestamps**, so the voiceover lands where the speaker was.

## Routing & fallback

Two gates dogfood Kyma; the voice uses ElevenLabs directly for v3 quality.

| Step | Default route | Notes |
|---|---|---|
| Transcribe | Kyma `whisper-v3-turbo` (or Groq direct) | timestamps |
| Translate | Kyma `best` | fitted to timing |
| TTS | ElevenLabs `eleven_v3` | best, expressive |

The TTS engine is **locked once at job start** so the voice never changes mid-video. The fallback chain:

| # | Engine | Voice | Covers |
|---|---|---|---|
| 1 | ElevenLabs v3 (direct) | preserved | default |
| 2 | ElevenLabs multilingual-v2 (direct) | preserved | v3 flakiness / rate limits |
| 3 | Kyma → eleven-multilingual-v2 | preserved | local key/network issue |
| 4 | Kyma → minimax-speech-hd | **changes** | full ElevenLabs outage — opt-in via `--allow-voice-fallback` |

Layers 1–3 share the ElevenLabs upstream, so a full ElevenLabs outage only leaves layer 4 — an independent provider, at the cost of a different speaker. That's why it's opt-in: the tool refuses to silently swap the voice.

## Notes & limits

- Best for narration / presentation / b-roll. It replaces audio only — **no lip-sync**. For talking-head where mouths must match, use a lip-sync product (HeyGen, Sync.so).
- English usually runs ~20% shorter than Vietnamese; each chunk is stretched within a natural range (0.7–1.6×) to fit. Extreme mismatches log a tempo near the clamp.
- Background music is replaced along with speech. Source-separation (keep the music bed) is not in v0.1.

## License

MIT © Son Piaz
