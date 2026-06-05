# kyma-dub

[![npm: @sonpiaz/kyma-dub-mcp](https://img.shields.io/npm/v/@sonpiaz/kyma-dub-mcp?label=mcp%20server&color=cb3837&logo=npm)](https://www.npmjs.com/package/@sonpiaz/kyma-dub-mcp) [![license: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

**Dub any video into another language with a natural, time-aligned AI voiceover — one command, one [Kyma](https://kymaapi.com) key.**

kyma-dub composes `ffmpeg` + a Whisper-class ASR + an LLM + a natural text-to-speech voice into a single command that takes a video speaking one language and hands you back the same video speaking another. The new voice lands where the original speaker was — it tracks the picture instead of drifting — and it never puts words in their mouth: when the audio is unclear, it stays generic rather than inventing a name, place, or fact that was never said.

```bash
kyma-dub talk.mov --from vi --voice charlie
# -> talk [EN dub].mp4
```

Any source language Whisper can hear, any target language you ask for. Works on `mp4`, `mov`, `mkv`, `webm` — anything ffmpeg reads.

## What you can make

One command in, a finished artifact out:

| Run | Get back |
|---|---|
| `kyma-dub talk.mov` | the same video, now speaking English, synced to the original timing |
| `kyma-dub talk.mov --voice will` | a different voice — browse them with `kyma-dub voices` |
| `kyma-dub talk.mov --to es` | a Spanish dub |
| `kyma-dub talk.mov --bilingual --burn` | captions burned in: target on top, the original below |
| `kyma-dub subs talk.mov --to en` | a translated `.srt` / `.vtt` subtitle file |
| `kyma-dub recommend --for "young female, TikTok"` | a voice (and model) matched to your audience |

## How it works

```
video ─▶ extract audio (ffmpeg)
      ─▶ transcribe + word timing (Whisper)
      ─▶ group into chunks at natural speech pauses
      ─▶ translate each chunk, fitted to its seconds (LLM)
      ─▶ speak each chunk in a locked voice (TTS)
      ─▶ speed each clip ONLY up to fit its slot, reassemble on the timeline
      ─▶ mux the new audio back over the original video
```

Two ideas keep it in sync and natural:

1. **Per-chunk timestamp anchoring** — it never translates one long block and reads it straight (that drifts further off with every sentence). Each chunk is voiced and placed back at its original timestamp.
2. **Speed-up-only isochrony** — a chunk is only ever sped up to fit its slot (capped by `--max-speed`), **never slowed**, because slowing drags the audio and feels delayed. Leftover time becomes a natural pause. The translation length is budgeted per chunk from a per-language characters-per-second model, so the timing holds across dense scripts (CJK/Thai) and verbose ones (Latin) alike.

## Why this exists

Dubbing a video usually means a subscription product, an upload, and trusting a black box with your footage — and the polished ones still hallucinate, smoothing a mis-heard word into a confident wrong fact (turning a plain "university" into "Stanford," or a vague location into a city that was never said). For a clip about *you*, that's not a rough edge; it's a lie in your voice.

kyma-dub is one local command instead. **Faithfulness is the first rule** — unclear audio stays generic, it never guesses a proper noun, and it translates only what's there. It runs the whole pipeline on a **single Kyma key** (transcribe, translate, and voice), so there's no provider juggling. And it's **open source**, so you can read exactly what it does to your words before you publish them. The voice *and* the captions come out of the same command — not an editor.

## Install

```bash
curl -fsSL https://github.com/sonpiaz/kyma-dub/releases/latest/download/install.sh | bash
```

Then set one key:

```bash
# ~/.config/kyma-dub/env  (created by the installer)
KYMA_API_KEY=kyma-xxxxxxxx        # transcribe + translate + voice
# ELEVENLABS_API_KEY=xi-xxxxxxxx  # optional: direct voice path / deep fallback
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
  --tts <engine>           kyma (default — one key) | elevenlabs (direct)
  --model <id>             translation model (default: qwen-3.7-max)
  --max-speed <n>          max voice speed-up to fit a slot (default: 1.5)
  --chunk-sec <n>          max seconds per dub chunk (default: 22)
  --allow-voice-fallback   permit an independent voice if every primary path is down
  --srt                    also write a .srt timed to the dubbed audio
  --bilingual              bilingual captions: target on top, cleaned source below
  --burn                   burn the captions into the output video
  --out <path>             output file
  --keep-temp              keep intermediate files
  --version / -h
```

## Subtitles & bilingual captions

Generate translated subtitles without changing the audio, or burn bilingual captions into the video:

```bash
kyma-dub subs talk.mov --to en --format both   # talk.en.srt + talk.en.vtt
kyma-dub talk.mov --srt                        # dub + a .srt timed to the dubbed audio
kyma-dub talk.mov --bilingual --burn           # dub + burned captions: target on top, original below
kyma-dub subs talk.mov --bilingual --burn      # bilingual captions on a non-dubbed video
```

**Bilingual** captions put the target language on top and a tidied-up version of the original below (smaller and dimmer), one line each, inside a centred band that clears a corner webcam. The original line is cleaned by AI (recognition junk removed, light punctuation) but never changed in meaning.

Burning needs a libass-enabled ffmpeg. Homebrew's ffmpeg ships without it, so run **`kyma-dub setup-ffmpeg`** once — it drops a static libass ffmpeg into `~/.kyma-dub/bin/` and never touches your system ffmpeg. Without it, `--burn` falls back to writing the subtitle file, so nothing breaks.

## Discover

Models and voices on Kyma change over time, so kyma-dub reads them **live** — you (or an agent driving it) always pick from what's current and matched to the audience:

```bash
kyma-dub models                                  # translation models on Kyma now
kyma-dub voices --gender female --age young --use-case social_media
kyma-dub voices --library --lang es              # search the shared voice library
kyma-dub preview <voice|id> ["sample text"]      # hear a voice before committing
kyma-dub recommend --for "energetic, for TikTok" --smart
kyma-dub whatsnew                                # what Kyma added since last check
```

Filter voices by `gender`, `age`, `accent`, `use-case`, `descriptive`, `language`. `--smart` lets a model pick from a free-text description.

## Routing & fallback

By default the whole pipeline runs on **one Kyma key**. The voice engine is locked once at job start so it never changes mid-video, with a fallback chain underneath: if the primary voice path is unavailable, it falls back through equivalent paths that **preserve the voice**, and only swaps to an independent voice as a last resort — and only when you opt in with `--allow-voice-fallback`, because a tool should never silently change how you sound. Pass `--tts elevenlabs` to voice straight from ElevenLabs (one less hop; needs `ELEVENLABS_API_KEY`).

## Desktop (MCP)

Drive kyma-dub from Claude desktop, Cursor, or ChatGPT desktop via the published MCP server [`@sonpiaz/kyma-dub-mcp`](https://www.npmjs.com/package/@sonpiaz/kyma-dub-mcp) — job-based dubbing plus live `list_models` / `list_voices` / `recommend_voice` / `preview_voice` / `whatsnew` tools and `kyma-dub://models` + `kyma-dub://voices` resources.

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

> The MCP server shells out to the `kyma-dub` CLI, so install the CLI first. Desktop apps spawn with a minimal `PATH`, so set **`KYMA_DUB_BIN`** to the absolute CLI path (`which kyma-dub`). See [mcp-server/README.md](mcp-server/README.md).

## Notes & limits

- Best for narration, presentation, and b-roll. It replaces the audio — there's **no lip-sync**, so for tight talking-head shots the mouth won't match the new language.
- Background music is replaced along with the speech (source-separation to keep the music bed isn't in yet).

## License

MIT © Son Piaz
