#!/usr/bin/env python3
"""
dub-cli pipeline — time-aligned AI video dubbing.

Flow:
  extract audio -> transcribe(+timestamps) -> chunk by speech pauses
  -> translate each chunk fitted to its duration -> TTS (locked engine,
  fallback chain) -> fit each clip to its slot -> reassemble on the
  original timeline (silences preserved) -> mux into the source video.

Invoked by bin/dub:  python3 pipeline.py <config.json>

Routing (see lib/env.sh):
  transcribe + translate  -> Kyma (dogfood) or Groq direct for STT
  TTS engine chain (locked once at job start to keep one voice):
    1 eleven_v3      ElevenLabs direct, expressive   [voice preserved]
    2 eleven_v2      ElevenLabs direct, stable        [voice preserved]
    3 kyma_eleven    Kyma -> eleven-multilingual-v2   [voice preserved]
    4 kyma_minimax   Kyma -> minimax-speech-hd        [VOICE CHANGES — opt-in]
  Layers 1-3 share the ElevenLabs upstream; only layer 4 is a truly
  independent provider, so it only runs with allow_voice_fallback=true.
"""
import sys, os, json, subprocess, tempfile, shutil, urllib.request, urllib.error

# friendly voice name -> ElevenLabs voice id
VOICES = {
    "charlie": "IKne3meq5aSn9XLyUdCD",  # young, casual (default)
    "will":    "bIHbv24MWmeRgasZH58o",  # young, friendly
    "liam":    "TX3LPaxmHKxFdv7VOQHJ",  # young narration
    "brian":   "nPczCjzI2devNBz1zQrb",  # mature narration
    "rachel":  "21m00Tcm4TlvDq8ikWAM",  # warm female
    "adam":    "pNInz6obpgDQGcFmaJgB",  # deep male
    "jessica": "cgSgspJ2msm6clMCkdW9",  # young female, expressive
}
MINIMAX_FALLBACK_VOICE = "English_expressive_narrator"

LANG_NAMES = {"en": "English", "vi": "Vietnamese", "es": "Spanish", "fr": "French",
              "de": "German", "ja": "Japanese", "ko": "Korean", "zh": "Chinese",
              "pt": "Portuguese", "it": "Italian", "hi": "Hindi", "id": "Indonesian"}

# Natural speaking rate in characters/second at speed 1.0, by language.
# Logographic scripts pack ~1 syllable/char -> far fewer chars/sec; long-
# compound languages sit lower than Latin scripts. (Same model as echoly.)
SPEECH_CPS = {"zh": 5, "ja": 5, "ko": 5, "th": 6, "de": 13}
DEFAULT_CPS = 15  # en, vi, es, fr, pt, id, it, hi, ...

def chars_per_sec(lang):
    return SPEECH_CPS.get((lang or "").lower().split("-")[0], DEFAULT_CPS)

# Isochrony: only ever speed the voice UP to fit a slot, never slow it
# down (slowing drags the audio and feels delayed). Leftover slot time
# becomes a natural pause. Capped so dense lines don't go chipmunk.
MIN_SPEED = 1.0
DEFAULT_MAX_SPEED = 1.5


def log(m): print(f"[kyma-dub] {m}", file=sys.stderr, flush=True)
def die(m, code=1): log("error: " + m); sys.exit(code)
def ffprobe_dur(f):
    return float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", f]).strip())
def ff(args):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"] + args,
                   check=True)


# ── HTTP helpers ────────────────────────────────────────────────────
def _http_json(url, body, headers, timeout=240):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
    return json.load(urllib.request.urlopen(req, timeout=timeout))

def _http_bytes(url, body, headers, timeout=180):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
    return urllib.request.urlopen(req, timeout=timeout).read()


# ── 1. extract audio ────────────────────────────────────────────────
def extract_audio(video, workdir):
    out = os.path.join(workdir, "src.mp3")
    ff(["-i", video, "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k", out])
    return out


# ── 2. transcribe with timestamps ───────────────────────────────────
def transcribe(cfg, audio):
    if cfg["mode"] == "kyma":
        endpoint = cfg["kyma_base"] + "/v1/audio/transcriptions"
        auth = "Bearer " + cfg["kyma_key"]; model = "whisper-v3-turbo"
    else:
        endpoint = "https://api.groq.com/openai/v1/audio/transcriptions"
        auth = "Bearer " + cfg["groq_key"]; model = "whisper-large-v3"
    # curl handles multipart + the explicit MIME type Kyma requires.
    args = ["curl", "-sS", "-X", "POST", "-H", "Authorization: " + auth,
            "-H", "User-Agent: " + cfg["ua"],
            "-F", f"file=@{audio};type=audio/mpeg",
            "-F", "model=" + model, "-F", "response_format=verbose_json"]
    if cfg.get("source_lang") and cfg["source_lang"] != "auto":
        args += ["-F", "language=" + cfg["source_lang"]]
    args += [endpoint]
    out = subprocess.check_output(args)
    d = json.loads(out)
    if "segments" not in d or not d["segments"]:
        die("transcription returned no segments: " + out.decode()[:200])
    return d["segments"], d.get("language", cfg.get("source_lang", "?"))


# ── 3. chunk by natural speech pauses ───────────────────────────────
def chunk_segments(segments, max_dur=22.0, gap_break=1.0, min_dur=8.0):
    # Fewer, larger chunks pack the voice continuously and leave little
    # dead air (smaller chunks scatter trailing silence -> feels laggy).
    chunks, cur = [], None
    for s in segments:
        st, en, tx = float(s["start"]), float(s["end"]), s["text"].strip()
        if not tx:
            continue
        if cur is None:
            cur = {"start": st, "end": en, "vi": tx}; continue
        gap = st - cur["end"]; dur = cur["end"] - cur["start"]
        if (dur >= min_dur and gap >= gap_break) or (en - cur["start"]) > max_dur:
            chunks.append(cur); cur = {"start": st, "end": en, "vi": tx}
        else:
            cur["end"] = en; cur["vi"] += " " + tx
    if cur:
        chunks.append(cur)
    for i, c in enumerate(chunks):
        c["i"] = i; c["dur"] = round(c["end"] - c["start"], 2)
    return chunks


# ── 4. translate, fitted to each chunk's duration ───────────────────
def translate(cfg, chunks):
    src = LANG_NAMES.get(cfg["source_lang"], cfg["source_lang"])
    tgt = LANG_NAMES.get(cfg["target_lang"], cfg["target_lang"])
    cps = chars_per_sec(cfg["target_lang"])
    # Per-chunk budget the model must fit: a max_seconds slot plus a soft
    # character ceiling derived from the target language's speaking rate.
    # Seconds is the language-agnostic contract; char ceiling guides verbose
    # vs dense scripts (CJK get far fewer chars than Latin for the same time).
    brief = [{"i": c["i"], "max_seconds": c["dur"],
              "max_chars": int(round(c["dur"] * cps)),
              "source_text": c["vi"]} for c in chunks]
    sysp = (
        f"You are an expert video-dubbing scriptwriter. Convert a {src} transcript "
        f"(auto-transcribed, may contain ASR errors) into a natural, expressive {tgt} "
        "voiceover, chunk by chunk. EACH chunk must be SPEAKABLE within its max_seconds "
        "at a natural pace.\n"
        "ISOCHRONY (critical for sync): make each translation short enough to be spoken "
        "naturally within max_seconds. Use contraction and paraphrase for verbose "
        "languages; stay at or under max_chars. It is far better to be slightly short "
        "(a natural pause fills the rest) than too long. Never pad to fill time.\n"
        "STYLE: keep first person if the source is, warm confident speaker energy, "
        "natural spoken language with contractions, NOT a literal translation. Add "
        "natural rhythm with commas, em-dashes, and occasional ellipses so it never "
        "sounds robotic. Vary sentence length. Fix obvious ASR errors using context. "
        "Preserve names, technical terms, and any explicit ordering/numbering so it "
        "tracks the visuals.\n"
        'OUTPUT: JSON {"chunks":[{"i":<index>,"text":"<translated>"}, ...]} in the same '
        "order, one per input chunk. Output ONLY the JSON.")
    body = {"model": cfg["translate_model"], "temperature": 0.7,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": sysp},
                         {"role": "user", "content": "Chunks:\n\n" + json.dumps(brief, ensure_ascii=False)}]}
    headers = {"Authorization": "Bearer " + cfg["kyma_key"], "Content-Type": "application/json",
               "User-Agent": cfg["ua"]}
    r = _http_json(cfg["kyma_base"] + "/v1/chat/completions", body, headers)
    raw = r["choices"][0]["message"]["content"].strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1].lstrip("json").strip()
    data = json.loads(raw)
    arr = data["chunks"] if isinstance(data, dict) and "chunks" in data else (
        data if isinstance(data, list) else next(v for v in data.values() if isinstance(v, list)))
    en = {o["i"]: o["text"] for o in arr}
    for c in chunks:
        c["en"] = en.get(c["i"], "")
        if not c["en"]:
            die(f"chunk {c['i']} got no translation")
    log(f"translated {len(chunks)} chunks via {r.get('model', cfg['translate_model'])}")
    return chunks


# ── 5. TTS engine chain (locked once, fallback) ─────────────────────
def tts_bytes(cfg, engine, text):
    if engine in ("eleven_v3", "eleven_v2"):
        model = "eleven_v3" if engine == "eleven_v3" else "eleven_multilingual_v2"
        headers = {"xi-api-key": cfg["eleven_key"], "Content-Type": "application/json",
                   "Accept": "audio/mpeg", "User-Agent": cfg["ua"]}
        body = {"text": text, "model_id": model,
                "voice_settings": {"stability": 0.4, "similarity_boost": 0.8,
                                   "use_speaker_boost": True}}
        return _http_bytes(f"https://api.elevenlabs.io/v1/text-to-speech/{cfg['voice_id']}", body, headers)
    if engine in ("kyma_v3", "kyma_eleven"):
        model = "eleven-v3" if engine == "kyma_v3" else "eleven-multilingual-v2"
        headers = {"Authorization": "Bearer " + cfg["kyma_key"], "Content-Type": "application/json",
                   "User-Agent": cfg["ua"]}
        body = {"model": model, "input": text, "voice": cfg["voice_id"]}
        return _http_bytes(cfg["kyma_base"] + "/v1/audio/speech", body, headers)
    if engine == "kyma_minimax":
        headers = {"Authorization": "Bearer " + cfg["kyma_key"], "Content-Type": "application/json",
                   "User-Agent": cfg["ua"]}
        body = {"model": "minimax-speech-hd", "input": text, "voice": cfg["minimax_voice"]}
        return _http_bytes(cfg["kyma_base"] + "/v1/audio/speech", body, headers)
    raise ValueError("unknown engine " + engine)


def build_engine_chain(cfg):
    chain = []
    if cfg["tts"] == "kyma":  # default — dogfood everything on one Kyma key
        if cfg.get("kyma_key"):
            chain += ["kyma_v3", "kyma_eleven"]    # v3 via Kyma, then v2 via Kyma
        if cfg.get("eleven_key"):
            chain += ["eleven_v3", "eleven_v2"]    # direct as deep fallback if Kyma TTS down
    else:  # elevenlabs — TTS straight to ElevenLabs
        if cfg.get("eleven_key"):
            chain += ["eleven_v3", "eleven_v2"]
        if cfg.get("kyma_key"):
            chain += ["kyma_v3", "kyma_eleven"]
    # voice-changing last resort, opt-in only (independent provider)
    if cfg.get("allow_voice_fallback") and cfg.get("kyma_key"):
        chain += ["kyma_minimax"]
    return chain


def lock_engine(cfg):
    chain = build_engine_chain(cfg)
    if not chain:
        die("no TTS engine available (need ELEVENLABS_API_KEY or KYMA_API_KEY)")
    for e in chain:
        try:
            b = tts_bytes(cfg, e, "Testing, one two three.")
            if b and len(b) > 1000:
                if e == "kyma_minimax":
                    log(f"⚠ TTS engine locked = {e}: VOICE WILL DIFFER from '{cfg['voice']}' "
                        "(independent provider, ElevenLabs unavailable).")
                else:
                    log(f"TTS engine locked = {e} (voice '{cfg['voice']}' preserved)")
                return e
        except urllib.error.HTTPError as ex:
            log(f"engine {e} unavailable (HTTP {ex.code}) — trying next")
        except Exception as ex:
            log(f"engine {e} unavailable ({ex}) — trying next")
    die("every TTS engine in the chain failed. Re-run with --allow-voice-fallback "
        "to permit the independent MiniMax voice as a last resort.")


def synth_chunk(cfg, engine, text, out_mp3, retries=2):
    last = None
    for attempt in range(retries + 1):
        try:
            b = tts_bytes(cfg, engine, text)
            if b and len(b) > 500:
                open(out_mp3, "wb").write(b); return
            last = "empty audio"
        except Exception as ex:
            last = str(ex)
    die(f"locked engine '{engine}' failed on a chunk after {retries+1} tries ({last}). "
        "Refusing to swap voice mid-video.")


# ── 6. fit each clip — speed UP only, never slow ────────────────────
def speed_fit(raw, slot, max_speed, out_wav):
    """Resample so spoken length fits the slot, but only by speeding up
    (>=1.0). Shorter-than-slot audio is left alone — the gap becomes a
    natural pause in assembly. Returns (speed, spoken_seconds)."""
    cd = ffprobe_dur(raw)
    speed = min(max_speed, max(MIN_SPEED, cd / slot if slot > 0 else MIN_SPEED))
    if abs(speed - 1.0) < 0.01:
        ff(["-i", raw, "-ar", "44100", "-ac", "2", out_wav])
        return 1.0, cd
    ff(["-i", raw, "-filter:a", f"atempo={speed:.4f}", "-ar", "44100", "-ac", "2", out_wav])
    return speed, ffprobe_dur(out_wav)


# ── 7. reassemble on the original timeline ──────────────────────────
def _silence(workdir, idx, secs):
    sil = os.path.join(workdir, f"sil_{idx}.wav")
    ff(["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", f"{secs:.3f}", sil])
    return sil

def assemble(chunks, total_dur, workdir):
    # Anchor each clip at its start time; if the previous clip overran its
    # slot (dense speech sped to the cap), push this one later instead of
    # overlapping. Leftover time between clips is silence — no dragging.
    parts, prev_end, overrun = [], 0.0, 0.0
    for c in chunks:
        pos = max(c["start"], prev_end)
        gap = pos - prev_end
        if gap > 0.02:
            parts.append(_silence(workdir, c["i"], gap))
        elif pos > c["start"] + 0.05:
            overrun += pos - c["start"]
        parts.append(c["fit"])
        prev_end = pos + c["spoken"]
    if total_dur - prev_end > 0.02:
        parts.append(_silence(workdir, "tail", total_dur - prev_end))
    if overrun > 0.3:
        log(f"⚠ {overrun:.1f}s of cumulative push from dense chunks (sped to the cap). "
            "Raise --max-speed or let the translation be more concise to tighten sync.")
    listf = os.path.join(workdir, "concat.txt")
    with open(listf, "w") as fh:
        for p in parts:
            fh.write(f"file '{p}'\n")
    track = os.path.join(workdir, "track.mp3")
    ff(["-f", "concat", "-safe", "0", "-i", listf, "-c:a", "libmp3lame", "-q:a", "2", track])
    return track


# ── 8. mux ──────────────────────────────────────────────────────────
def mux(video, track, out):
    ff(["-i", video, "-i", track, "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", out])


def main():
    cfg = json.load(open(sys.argv[1]))
    video = cfg["video"]
    total_dur = ffprobe_dur(video)
    workdir = tempfile.mkdtemp(prefix="dub-")
    try:
        log(f"source: {os.path.basename(video)} ({total_dur:.1f}s) | mode={cfg['mode']} | tts={cfg['tts']} | voice={cfg['voice']}")
        audio = extract_audio(video, workdir)
        segs, lang = transcribe(cfg, audio)
        if cfg.get("source_lang", "auto") == "auto":
            cfg["source_lang"] = lang
        log(f"transcribed: {len(segs)} segments, source language={cfg['source_lang']}")
        chunks = chunk_segments(segs, max_dur=cfg.get("chunk_sec", 22.0))
        if not chunks:
            die("no speech chunks to dub")
        log(f"grouped into {len(chunks)} chunks")
        chunks = translate(cfg, chunks)
        engine = lock_engine(cfg)
        max_speed = cfg.get("max_speed", DEFAULT_MAX_SPEED)
        for c in chunks:
            raw = os.path.join(workdir, f"raw_{c['i']}.mp3")
            synth_chunk(cfg, engine, c["en"], raw)
            c["fit"] = os.path.join(workdir, f"fit_{c['i']}.wav")
            speed, spoken = speed_fit(raw, c["dur"], max_speed, c["fit"])
            c["spoken"] = spoken
            tag = f"speed={speed:.2f}" if speed > 1.0 else f"+{c['dur'] - spoken:.1f}s pause"
            log(f"  chunk {c['i']:>2} slot={c['dur']:>5.1f}s spoken={spoken:>5.1f}s {tag}")
        track = assemble(chunks, total_dur, workdir)
        mux(video, track, cfg["out"])
        log(f"done -> {cfg['out']}")
        print(cfg["out"])
    finally:
        if not cfg.get("keep_temp"):
            shutil.rmtree(workdir, ignore_errors=True)
        else:
            log(f"temp kept at {workdir}")


if __name__ == "__main__":
    main()
