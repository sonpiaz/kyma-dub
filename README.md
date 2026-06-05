# kyma-dub

[![npm: @sonpiaz/kyma-dub-mcp](https://img.shields.io/npm/v/@sonpiaz/kyma-dub-mcp?label=mcp%20server&color=cb3837&logo=npm)](https://www.npmjs.com/package/@sonpiaz/kyma-dub-mcp) [![license: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

Dub any video into another language with a natural, **time-aligned** AI voiceover — from the terminal, all on one [Kyma](https://kymaapi.com) key.

```bash
kyma-dub talk.mp4 --from vi --voice charlie
# -> talk [EN dub].mp4
```

It transcribes the source, translates it to the target language *fitted to the original timing*, speaks it in a natural voice, and muxes the new audio back over the original video. The narration tracks what's on screen — it doesn't drift.

Built the same way as [watch-cli](https://github.com/sonpiaz/watch-cli): use it yourself, ship it open-source, and run every AI call through Kyma — transcribe, translate, and voice on a single key.

## Install

```bash
curl -fsSL https://github.com/sonpiaz/kyma-dub/releases/latest/download/install.sh | bash
```

Then set one key:

```bash
# ~/.config/kyma-dub/env  (created by the installer)
KYMA_API_KEY=kyma-xxxxxxxx        # transcribe + translate + voice
# ELEVENLABS_API_KEY=xi-xxxxxxxx  # optional: direct TTS path / deep fallback
```

Get a Kyma key at [kymaapi.com](https://kymaapi.com) — 60 seconds, no card, free credit at signup.

**Dependencies:** `ffmpeg`, `ffprobe`, `curl`, `python3` (`brew install ffmpeg`).

## Dub

```bash
kyma-dub <video> [options]

  --from <lang>            source language code (default: auto-detect)
  --to <lang>              target language code (default: en)
  --voice <name|id>        charlie | will | liam | brian | rachel | adam | jessica
                           or any voice id from `kyma-dub voices` (default: charlie)
  --tts <engine>           kyma (default — one key, eleven-v3) | elevenlabs (direct)
  --model <id>             translation model (default: qwen-3.7-max)
  --max-speed <n>          max voice speed-up to fit a slot (default: 1.5)
  --chunk-sec <n>          max seconds per dub chunk (default: 22)
  --allow-voice-fallback   permit an independent MiniMax voice if every
                           ElevenLabs path is down (CHANGES the voice)
  --srt                    also write a .srt timed to the dubbed audio
  --bilingual              add bilingual captions: target on top, cleaned
                           source smaller + dimmer below (pair with --burn)
  --burn                   burn the captions into the output video
                           (needs a libass ffmpeg — run `kyma-dub setup-ffmpeg`)
  --out <path>             output file
  --keep-temp              keep intermediate files
  --version / -h
```

## Subtitles

Generate translated subtitles (`.srt` / `.vtt`) from a video — same transcribe + faithful-translate pipeline, written against the original timestamps:

```bash
kyma-dub subs video.mov --to en --format both   # writes video.en.srt + video.en.vtt
kyma-dub subs talk.mp4 --to es                  # Spanish .srt
```

Translation is **faithful by design** — it never invents facts, names, places, or numbers that aren't in the source (when the audio is unclear it stays generic instead of guessing).

To put captions **on the dubbed video** (timed to the new English audio, not the original), dub with `--srt` (separate file) or `--burn` (rendered into the video — needs a libass-enabled ffmpeg):

```bash
kyma-dub talk.mp4 --srt                 # dubbed.mp4 + dubbed.srt (synced to the dub)
kyma-dub talk.mp4 --burn                # captions burned in (great for TikTok/Reels)
kyma-dub talk.mp4 --bilingual --burn    # English on top, cleaned source smaller + dimmer below
```

**Bilingual** captions show the target language on top and a cleaned-up version of the original below (smaller and dimmer), kept inside a centred band so they clear a corner webcam. The source line is tidied by AI (ASR junk removed, light punctuation) but never altered in meaning. `kyma-dub subs <video> --bilingual --burn` does the same on a non-dubbed video.

Burning needs a libass-enabled ffmpeg. Homebrew's ffmpeg ships without it, so run **`kyma-dub setup-ffmpeg`** once (downloads a static libass ffmpeg into `~/.kyma-dub/bin/`, never touching your system ffmpeg). Without it, `--burn` falls back to writing the subtitle file.

`--burn` is optional and the only thing that needs **libass** in your ffmpeg (most Linux and static ffmpeg builds have it; current Homebrew ffmpeg does not). If libass is missing, `--burn` automatically falls back to writing the synced `.srt` so nothing breaks — load it as a soft subtitle or burn it in your editor.

## Discover (the live "door")

Models and voices on Kyma evolve. These query the **live** catalog so you (or an agent) always recommend what's current and matched to the audience:

```bash
kyma-dub models                                   # translation models on Kyma now
kyma-dub voices --gender female --age young --use-case social_media
kyma-dub voices --library --lang es               # search the shared voice library
kyma-dub preview <voice|id> ["sample text"]       # hear a voice before committing
kyma-dub recommend --for "young female, energetic, for TikTok" --smart
kyma-dub whatsnew                                 # what Kyma added since last check
```

Voice labels you can filter on: `gender`, `age`, `accent`, `use-case`, `descriptive`, `language`. `--smart` lets a Kyma model pick from the free-text need.

## How it works

```
video ─▶ extract audio (ffmpeg)
      ─▶ transcribe + timestamps (Kyma whisper-v3-turbo)
      ─▶ group into chunks at natural speech pauses
      ─▶ translate each chunk, fitted to its seconds (Kyma LLM)
      ─▶ TTS each chunk with a locked voice engine
      ─▶ speed each clip ONLY up to fit its slot, reassemble on the timeline
      ─▶ mux new audio over the original video
```

Two things keep it in sync and natural:

1. **Per-chunk timestamp anchoring** — it never translates-then-reads one long block (that drifts). Each chunk is voiced and placed at its original timestamp.
2. **Speed-up-only isochrony** — a chunk is only ever sped up to fit its slot (capped at `--max-speed`), **never slowed** (slowing drags the audio and feels delayed). Leftover slot time becomes a natural pause. Translation length is budgeted per chunk using a per-language characters-per-second model, so it generalises across languages (dense CJK/Thai vs verbose Latin scripts).

## Routing & fallback

By default the **whole pipeline runs on one Kyma key** (transcribe + translate + voice):

| Step | Default route | Notes |
|---|---|---|
| Transcribe | Kyma `whisper-v3-turbo` (or Groq direct) | timestamps |
| Translate | Kyma `qwen-3.7-max` | fitted to timing |
| TTS | Kyma `eleven-v3` | expressive — one key |

Pass `--tts elevenlabs` to voice straight from ElevenLabs (needs `ELEVENLABS_API_KEY`; one less hop). Either way it's the same v3 voice.

The TTS engine is **locked once at job start** so the voice never changes mid-video. The fallback chain (tried in order on a synth probe):

| # | Engine | Voice | Covers |
|---|---|---|---|
| 1 | Kyma → eleven-v3 | preserved | default (one key) |
| 2 | Kyma → eleven-multilingual-v2 | preserved | Kyma v3 backend issue |
| 3 | ElevenLabs v3 (direct) | preserved | Kyma TTS down (needs `ELEVENLABS_API_KEY`) |
| 4 | ElevenLabs multilingual-v2 (direct) | preserved | v3 direct issue |
| 5 | Kyma → minimax-speech-hd | **changes** | full ElevenLabs outage — opt-in via `--allow-voice-fallback` |

(`--tts elevenlabs` puts the two direct engines first.) Layers 1–4 ultimately reach ElevenLabs, so a *full* ElevenLabs outage leaves only layer 5 — an independent provider (MiniMax), at the cost of a different speaker. That's why it's opt-in: the tool refuses to silently swap the voice.

## Desktop (MCP)

Use kyma-dub from Claude desktop, Cursor, or ChatGPT desktop via the published MCP server [`@sonpiaz/kyma-dub-mcp`](https://www.npmjs.com/package/@sonpiaz/kyma-dub-mcp) — it exposes dubbing (job-based) plus live `list_models` / `list_voices` / `recommend_voice` / `preview_voice` / `whatsnew` tools and `kyma-dub://models` + `kyma-dub://voices` resources.

```json
{
  "mcpServers": {
    "kyma-dub": {
      "command": "npx",
      "args": ["-y", "@sonpiaz/kyma-dub-mcp"],
      "env": {
        "KYMA_API_KEY": "kyma-xxxxxxxx",
        "KYMA_DUB_BIN": "/Users/you/.local/bin/kyma-dub"
      }
    }
  }
}
```

> **Note:** the MCP server shells out to the `kyma-dub` CLI, so install the CLI first (above). Desktop apps spawn with a minimal `PATH`, so set **`KYMA_DUB_BIN`** to the absolute CLI path (run `which kyma-dub`) — otherwise the server can't find it. See [mcp-server/README.md](mcp-server/README.md).

## Notes & limits

- Best for narration / presentation / b-roll. It replaces audio only — **no lip-sync**. For talking-head where mouths must match, use a lip-sync product (HeyGen, Sync.so).
- Background music is replaced along with speech. Source-separation (keep the music bed) is not in v0.1.

## License

MIT © Son Piaz
