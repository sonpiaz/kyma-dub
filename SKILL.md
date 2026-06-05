---
name: kyma-dub
description: Dub a video into another language with a natural, time-aligned AI voiceover, all on one Kyma key. Use when the user wants to translate/dub a video (e.g. Vietnamese talk -> English voiceover), asks to "lồng tiếng", "dub this", "voiceover in English", or hands you an mp4 and a target language. Also use to discover/recommend voices and translation models. Keeps narration synced to the original timing.
---

# kyma-dub

Time-aligned AI video dubbing. Transcribes a video, translates it to the
target language fitted to the original timing, speaks it in a natural voice,
and muxes the new audio over the original video. Transcribe + translate +
voice all run through one Kyma key.

## When to use
- "dub this video to English", "lồng tiếng tiếng Anh", "make an English voiceover"
- User hands an mp4 + a target language and wants the audio replaced.
- User asks which voice or model to use → use the discovery commands below.

Best for narration / presentation / b-roll. It replaces audio only (no
lip-sync) — for talking-head where mouths must match, flag that tradeoff.

## Discover BEFORE you recommend (important — stay current)
Models and voices on Kyma change over time. Do NOT recommend from memory or
from this file's examples — query the live catalog so your suggestion is
always current and matched to the user:

```bash
kyma-dub models --json          # translation-capable models on Kyma right now
kyma-dub voices --json [--gender female --age young --use-case social_media --library]
kyma-dub preview <voice|id>     # synth a sample so the user can hear it
kyma-dub recommend --for "young female, energetic, for TikTok" --smart
kyma-dub whatsnew               # what models/voices Kyma added since last check
```
When the user's voice/model preference is unclear, ask their target audience
(gender, age, vibe, platform), then run `kyma-dub voices` / `recommend` to
surface 2-3 fitting voices and offer `kyma-dub preview` so they can listen.
Voice labels available: gender, age, accent, use_case, descriptive, language.

## Dub
```bash
kyma-dub <video> [--from <lang>] [--to <lang>] [--voice <name|id>] [--model <id>] [--tts kyma|elevenlabs] [--max-speed <n>] [--chunk-sec <n>] [--allow-voice-fallback] [--out <path>]
```
Examples:
```bash
kyma-dub talk.mp4                          # auto -> English, voice charlie
kyma-dub talk.mp4 --to es --voice rachel   # dub to Spanish
kyma-dub talk.mp4 --voice <id-from-voices>
```
Built-in voice aliases: charlie (default), will, liam, brian, rachel, adam,
jessica — or any voice id from `kyma-dub voices`.

## Subtitles
Generate translated `.srt` / `.vtt` (no audio change), or bilingual burned-in captions:
```bash
kyma-dub subs <video> [--to <lang>] [--format srt|vtt|both]      # subtitle file
kyma-dub <video> --bilingual --burn                              # dub + burn EN-on-top / source-below captions
kyma-dub subs <video> --bilingual --burn                        # bilingual captions on a non-dubbed video
```
`--bilingual` shows the target language on top and a cleaned-up original below (smaller, dimmer). `--burn` renders captions into the video — needs a libass ffmpeg; if missing, run `kyma-dub setup-ffmpeg` (downloads a static one to `~/.kyma-dub/bin/`).

## How it works
extract audio → transcribe with timestamps → group by speech pauses →
translate each chunk fitted to its seconds → TTS (engine locked once per job
so the voice never changes mid-video) → speed each clip ONLY up to fit its
slot (never slowed — leftover time is a natural pause) → reassemble on the
original timeline → mux into the video.

## Routing & fallback
Default: transcribe + translate + TTS all on one Kyma key (`eleven-v3`).
Engine chain (locked at job start): Kyma eleven-v3 → Kyma eleven-multilingual-v2
→ ElevenLabs v3 direct → v2 direct (all voice-preserved) → Kyma minimax-speech-hd
(voice CHANGES, only with `--allow-voice-fallback`). `--tts elevenlabs` flips to
ElevenLabs-direct first.

## Keys
`KYMA_API_KEY` runs everything. `ELEVENLABS_API_KEY` optional (direct TTS).
Read from `./.env`, `~/.config/kyma-dub/env`, or `~/kyma-api/.env`.

## Notes
- Default translation model: `qwen-3.7-max` (override with `--model`; see
  `kyma-dub models` for current options).
- Output defaults to `<name> [<LANG> dub].mp4` next to the source.
