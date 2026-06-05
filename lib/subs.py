#!/usr/bin/env python3
"""
kyma-dub subs — generate translated subtitles (.srt / .vtt) for a video.

Flow: extract audio -> transcribe with timestamps -> group into readable cues
-> translate each cue to the target language -> write .srt and/or .vtt with the
ORIGINAL timestamps (subtitles display during the speaker's cue; no audio
isochrony needed). Runs on one Kyma key.

Invoked by bin/kyma-dub:  python3 subs.py <config.json>
"""
import sys, os, json, subprocess, tempfile, shutil, urllib.request, urllib.error
import bilingual as bl

LANG_NAMES = {"en": "English", "vi": "Vietnamese", "es": "Spanish", "fr": "French",
              "de": "German", "ja": "Japanese", "ko": "Korean", "zh": "Chinese",
              "pt": "Portuguese", "it": "Italian", "hi": "Hindi", "id": "Indonesian"}

# Cue grouping: merge Whisper fragments into whole sentence-ish cues so each
# subtitle line reads on its own (no "…" continuation between fragments).
SENT_END = (".", "?", "!", "…", "。", "？", "！")
MAX_CUE_SEC = 6.5      # split a cue once it would run longer than this
MAX_CUE_CHARS = 90     # …or longer than this many source chars
MIN_CUE_SEC = 1.2      # don't emit ultra-short cues
GAP_BREAK = 0.45       # a pause this long (with enough cue already) ends a cue


def log(m): print(f"[kyma-dub] {m}", file=sys.stderr, flush=True)
def die(m): log("error: " + m); sys.exit(1)


def extract_audio(video, workdir):
    out = os.path.join(workdir, "src.mp3")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", video,
                    "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k", out], check=True)
    return out


def transcribe(cfg, audio):
    if cfg["mode"] == "kyma":
        endpoint = cfg["kyma_base"] + "/v1/audio/transcriptions"
        auth = "Bearer " + cfg["kyma_key"]; model = "whisper-v3-turbo"
    else:
        endpoint = "https://api.groq.com/openai/v1/audio/transcriptions"
        auth = "Bearer " + cfg["groq_key"]; model = "whisper-large-v3"
    args = ["curl", "-sS", "-X", "POST", "-H", "Authorization: " + auth,
            "-H", "User-Agent: " + cfg["ua"],
            "-F", f"file=@{audio};type=audio/mpeg",
            "-F", "model=" + model, "-F", "response_format=verbose_json"]
    if cfg.get("source_lang") and cfg["source_lang"] != "auto":
        args += ["-F", "language=" + cfg["source_lang"]]
    args += [endpoint]
    d = json.loads(subprocess.check_output(args))
    if not d.get("segments"):
        die("transcription returned no segments")
    return d["segments"], d.get("language", cfg.get("source_lang", "?"))


def build_cues(segments):
    cues, cur = [], None
    for s in segments:
        st, en, tx = float(s["start"]), float(s["end"]), s["text"].strip()
        if not tx:
            continue
        if cur is None:
            cur = {"start": st, "end": en, "src": tx}
            continue
        dur = cur["end"] - cur["start"]
        gap = st - cur["end"]
        ends_sentence = cur["src"].rstrip().endswith(SENT_END)
        too_long = (en - cur["start"]) > MAX_CUE_SEC or len(cur["src"]) > MAX_CUE_CHARS
        big_pause = gap >= GAP_BREAK and dur >= MIN_CUE_SEC
        if (ends_sentence and dur >= MIN_CUE_SEC) or too_long or big_pause:
            cues.append(cur)
            cur = {"start": st, "end": en, "src": tx}
        else:
            cur["end"] = en
            cur["src"] = (cur["src"].rstrip() + " " + tx).strip()
    if cur:
        cues.append(cur)
    for i, c in enumerate(cues):
        c["i"] = i
    return cues


BATCH = 40  # cues per LLM call — keep responses small so they don't time out

def _translate_batch(cfg, batch, sysp):
    brief = [{"i": c["i"], "text": c["src"]} for c in batch]
    body = json.dumps({"model": cfg["translate_model"], "temperature": 0.2,
                       "response_format": {"type": "json_object"},
                       "messages": [{"role": "system", "content": sysp},
                                    {"role": "user", "content": "Cues:\n\n" + json.dumps(brief, ensure_ascii=False)}]}).encode()
    req = urllib.request.Request(cfg["kyma_base"] + "/v1/chat/completions", data=body,
                                 headers={"Authorization": "Bearer " + cfg["kyma_key"],
                                          "Content-Type": "application/json", "User-Agent": cfg["ua"]})
    r = json.load(urllib.request.urlopen(req, timeout=180))
    raw = r["choices"][0]["message"]["content"].strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1].lstrip("json").strip()
    data = json.loads(raw)
    arr = data["cues"] if isinstance(data, dict) and "cues" in data else (
        data if isinstance(data, list) else next(v for v in data.values() if isinstance(v, list)))
    return {o["i"]: o["text"] for o in arr}, r.get("model", cfg["translate_model"])


def translate(cfg, cues):
    src = LANG_NAMES.get(cfg["source_lang"], cfg["source_lang"])
    tgt = LANG_NAMES.get(cfg["target_lang"], cfg["target_lang"])
    sysp = (
        f"You translate {src} video captions into {tgt} subtitles. "
        "For each input cue, return a concise, natural, readable subtitle line in "
        f"{tgt} that preserves the meaning and tone.\n"
        "FAITHFULNESS (most important): translate ONLY what the cue says. NEVER add, "
        "invent, infer, or embellish any fact, name, place, brand, number, or institution "
        "not explicitly in the source. The transcript may be garbled by speech-recognition "
        "errors — when a word is unclear, mistranscribed, or generic, render it with a "
        "GENERIC term (e.g. 'abroad', 'over there', 'a school') or omit it. NEVER substitute "
        "a specific proper noun (city, university, company, person) for an unclear or "
        "generic word — do not guess 'Stanford' or 'San Francisco' from ambiguous audio.\n"
        "Keep names, numbers, and technical terms exactly. Do NOT merge or split cues — "
        "return exactly one line per input cue, same order.\n"
        "Each line is a clean standalone subtitle: do NOT add leading/trailing ellipses "
        "('...' or '…'), dashes, or any continuation marker — just the translated text.\n"
        'OUTPUT: JSON {"cues":[{"i":<index>,"text":"<subtitle>"}, ...]}. ONLY JSON.')
    tr, model = {}, cfg["translate_model"]
    n = len(cues)
    for start in range(0, n, BATCH):
        batch = cues[start:start + BATCH]
        part, model = _translate_batch(cfg, batch, sysp)
        tr.update(part)
        log(f"translated cues {start + 1}-{start + len(batch)} / {n}")
    for c in cues:
        c["tr"] = tr.get(c["i"], c["src"])
    log(f"translated {n} cues via {model}")
    return cues


def _ts(t, vtt=False):
    h = int(t // 3600); m = int(t % 3600 // 60); s = int(t % 60); ms = int(round((t - int(t)) * 1000))
    sep = "." if vtt else ","
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def write_srt(cues, path):
    with open(path, "w") as f:
        for n, c in enumerate(cues, 1):
            f.write(f"{n}\n{_ts(c['start'])} --> {_ts(c['end'])}\n{c['tr']}\n\n")


def write_vtt(cues, path):
    with open(path, "w") as f:
        f.write("WEBVTT\n\n")
        for c in cues:
            f.write(f"{_ts(c['start'], True)} --> {_ts(c['end'], True)}\n{c['tr']}\n\n")


def main():
    cfg = json.load(open(sys.argv[1]))
    workdir = tempfile.mkdtemp(prefix="kyma-subs-")
    try:
        log(f"subs: {os.path.basename(cfg['video'])} | mode={cfg['mode']} | {cfg.get('source_lang','auto')} -> {cfg['target_lang']}")
        audio = extract_audio(cfg["video"], workdir)
        segs, lang = transcribe(cfg, audio)
        if cfg.get("source_lang", "auto") == "auto":
            cfg["source_lang"] = lang
        if cfg.get("bilingual"):
            bcues = bl.bilingual_cues(cfg, segs)
            W, H = bl.video_dims(cfg["video"])
            if cfg.get("burn"):
                ass = os.path.join(workdir, "bilingual.ass"); bl.write_ass(bcues, ass, W, H)
                ff = bl.resolve_libass_ffmpeg()
                if ff:
                    out_mp4 = cfg["out_base"] + ".mp4"
                    log("burning bilingual subtitles into the video (re-encoding)…")
                    bl.burn_ass(ff, cfg["video"], ass, out_mp4)
                    log(f"done -> {out_mp4}"); print(out_mp4); return
                out_ass = cfg["out_base"] + ".ass"; bl.write_ass(bcues, out_ass, W, H)
                log("note: no libass ffmpeg found — wrote the bilingual subtitles instead:")
                log(f"  {out_ass}")
                log("  Run `kyma-dub setup-ffmpeg` to enable burning."); print(out_ass); return
            out_ass = cfg["out_base"] + ".ass"; bl.write_ass(bcues, out_ass, W, H)
            log(f"done -> {out_ass}"); print(out_ass); return
        cues = build_cues(segs)
        log(f"{len(segs)} segments -> {len(cues)} cues (source language={cfg['source_lang']})")
        cues = translate(cfg, cues)
        outs = []
        fmt = cfg.get("format", "srt")
        if fmt in ("srt", "both"):
            p = cfg["out_base"] + ".srt"; write_srt(cues, p); outs.append(p)
        if fmt in ("vtt", "both"):
            p = cfg["out_base"] + ".vtt"; write_vtt(cues, p); outs.append(p)
        for p in outs:
            log(f"done -> {p}")
        print("\n".join(outs))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
