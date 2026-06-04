---
name: dub-cli
description: Dub a video into another language with a natural, time-aligned AI voiceover. Use when the user wants to translate/dub a video (e.g. Vietnamese talk -> English voiceover), asks to "lồng tiếng", "dub this", "voiceover in English", or hands you an mp4 and a target language. Keeps narration synced to the original timing.
---

# dub-cli

Time-aligned AI video dubbing. Transcribes a video, translates it to the
target language fitted to the original timing, speaks it in a natural
voice, and muxes the new audio over the original video.

## When to use
- "dub this video to English", "lồng tiếng tiếng Anh", "make an English voiceover"
- User hands an mp4 + a target language and wants the audio replaced.

Best for narration / presentation / b-roll videos. For talking-head where
lip-sync matters, dub-cli replaces audio only (no lip-sync) — flag that
tradeoff to the user.

## Usage
```bash
dub <video> [--from <lang>] [--to <lang>] [--voice <name>] [--tts elevenlabs|kyma] [--allow-voice-fallback] [--out <path>]
```
Examples:
```bash
dub talk.mp4                          # auto-detect -> English, voice charlie
dub talk.mp4 --from vi --voice will   # pick a voice
dub talk.mp4 --to es --voice rachel   # dub to Spanish
dub talk.mp4 --tts kyma               # route TTS through Kyma (one key)
```
Voices: charlie (default, young casual), will, liam, brian, rachel, adam,
jessica — or pass a raw ElevenLabs voice id.

## How it works
extract audio → transcribe with timestamps → group by speech pauses →
translate each chunk fitted to its seconds → TTS (engine locked once) →
time-stretch each clip to its slot → reassemble on the original timeline →
mux into the video.

## Routing
- transcribe + translate: Kyma (`KYMA_API_KEY`) or Groq direct for STT.
- TTS engine chain (locked at job start so the voice never changes
  mid-video): ElevenLabs v3 → ElevenLabs v2 → Kyma eleven-multilingual-v2
  (voice preserved) → Kyma minimax-speech-hd (voice CHANGES, only with
  `--allow-voice-fallback`).

## Keys
`KYMA_API_KEY` (recommended) + `ELEVENLABS_API_KEY` (best voice). Read from
`./.env`, `~/.config/dub-cli/env`, or `~/kyma-api/.env`.

## Notes
- English usually runs shorter than Vietnamese; the tool slows/speeds each
  chunk within a natural range (0.7–1.6x) to keep slide sync.
- Output defaults to `<name> [<LANG> dub].mp4` next to the source.
