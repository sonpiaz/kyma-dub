#!/usr/bin/env python3
"""
kyma-dub bilingual subtitles — shared by the dub pipeline and `subs`.

Builds short one-line cues from a transcript, translates each to a faithful
target-language line PLUS a cleaned-up source line, writes a styled .ass
(target on top, source smaller + dimmer below, kept inside a centred band so
it clears a corner webcam), and burns it in with a libass-enabled ffmpeg.
"""
import os, re, sys, json, subprocess, urllib.request

LANG_NAMES = {"en": "English", "vi": "Vietnamese", "es": "Spanish", "fr": "French",
              "de": "German", "ja": "Japanese", "ko": "Korean", "zh": "Chinese",
              "pt": "Portuguese", "it": "Italian", "hi": "Hindi", "id": "Indonesian"}

# Short cues so each translated line fits on ONE row.
_SENT = (".", "?", "!", "…", "。", "？", "！")
_MAX_SEC = 4.2
_MAX_CHARS = 58
_MIN_SEC = 1.0
_GAP = 0.4
_BATCH = 40


def _log(m): print(f"[kyma-dub] {m}", file=sys.stderr, flush=True)


def _short_cues(segments):
    cues, cur = [], None
    for s in segments:
        st, en, tx = float(s["start"]), float(s["end"]), s["text"].strip()
        if not tx:
            continue
        if cur is None:
            cur = {"start": st, "end": en, "src": tx}; continue
        dur = cur["end"] - cur["start"]; gap = st - cur["end"]
        if (cur["src"].rstrip().endswith(_SENT) and dur >= _MIN_SEC) \
           or (en - cur["start"]) > _MAX_SEC or len(cur["src"]) > _MAX_CHARS \
           or (gap >= _GAP and dur >= _MIN_SEC):
            cues.append(cur); cur = {"start": st, "end": en, "src": tx}
        else:
            cur["end"] = en; cur["src"] = (cur["src"] + " " + tx).strip()
    if cur:
        cues.append(cur)
    for i, c in enumerate(cues):
        c["i"] = i
    return cues


def bilingual_cues(cfg, segments):
    """Return cues with start/end/en (translation)/vi (cleaned source)."""
    cues = _short_cues(segments)
    src = LANG_NAMES.get(cfg["source_lang"], cfg["source_lang"])
    tgt = LANG_NAMES.get(cfg["target_lang"], cfg["target_lang"])
    sysp = (
        f"You build bilingual subtitles from a {src} auto-transcript. For EACH cue return "
        f'"en" = a faithful, natural {tgt} subtitle (concise, ONE line, no ellipses), and '
        f'"src" = the SAME {src} cleaned up (remove speech-recognition junk and stray filler '
        "like a leading 'không'/'ờ'/'à' or repeated words, add light punctuation and "
        "capitalization, no ellipses) WITHOUT changing meaning or adding anything.\n"
        "FAITHFULNESS: never invent facts, names, places, brands, numbers, or institutions "
        "not in the source; when audio is unclear keep it generic (e.g. 'abroad'), never "
        "guess a proper noun.\n"
        'OUTPUT JSON {"cues":[{"i":<i>,"en":"...","src":"..."}]} same order. ONLY JSON.')
    out = {}
    for start in range(0, len(cues), _BATCH):
        batch = cues[start:start + _BATCH]
        body = json.dumps({"model": cfg["translate_model"], "temperature": 0.2,
                           "response_format": {"type": "json_object"},
                           "messages": [{"role": "system", "content": sysp},
                                        {"role": "user", "content": "Cues:\n\n" + json.dumps(
                                            [{"i": c["i"], "text": c["src"]} for c in batch], ensure_ascii=False)}]}).encode()
        req = urllib.request.Request(cfg["kyma_base"] + "/v1/chat/completions", data=body,
                                     headers={"Authorization": "Bearer " + cfg["kyma_key"],
                                              "Content-Type": "application/json", "User-Agent": cfg["ua"]})
        r = json.load(urllib.request.urlopen(req, timeout=180))
        raw = r["choices"][0]["message"]["content"].strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1].lstrip("json").strip()
        for o in json.loads(raw)["cues"]:
            out[o["i"]] = o
        _log(f"bilingual cues {min(start + _BATCH, len(cues))}/{len(cues)}")
    for c in cues:
        o = out.get(c["i"], {})
        c["en"] = (o.get("en") or "").strip()
        c["vi"] = (o.get("src") or c["src"]).strip()
    return cues


def _ass_ts(t):
    h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def write_ass(cues, path, width, height):
    en = int(height * 0.040); vi = int(en * 0.66); margin = 200
    hdr = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {width}\nPlayResY: {height}\nWrapStyle: 0\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Bi,Arial,{en},&H00FFFFFF,&H000000FF,&H00000000,&H64000000,0,0,0,0,100,100,"
        f"0,0,1,3,2,2,{margin},{margin},90,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    lines = [hdr]
    for c in cues:
        e = c["en"].replace("\n", " ").strip()
        v = c["vi"].replace("\n", " ").strip()
        lines.append(f"Dialogue: 0,{_ass_ts(c['start'])},{_ass_ts(c['end'])},Bi,,0,0,0,,"
                     f"{e}\\N{{\\fs{vi}\\alpha&H66&}}{v}")
    open(path, "w").write("\n".join(lines) + "\n")


def video_dims(video):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height", "-of", "csv=p=0:s=x", video]).decode().strip()
    w, h = out.split("x")[:2]
    return int(w), int(h)


def resolve_libass_ffmpeg():
    """Find an ffmpeg that can render subtitles (libass). Order: KYMA_DUB_FFMPEG,
    the bundled ~/.kyma-dub/bin/ffmpeg, then system ffmpeg. None if absent."""
    import shutil
    for ff in (os.environ.get("KYMA_DUB_FFMPEG"),
               os.path.expanduser("~/.kyma-dub/bin/ffmpeg"),
               shutil.which("ffmpeg")):
        if ff and os.path.exists(ff if os.path.isabs(ff) else (shutil.which(ff) or "")):
            real = ff if os.path.isabs(ff) else shutil.which(ff)
            try:
                filt = subprocess.check_output([real, "-hide_banner", "-filters"],
                                               stderr=subprocess.DEVNULL).decode()
                if re.search(r"\b(ass|subtitles)\b", filt):
                    return real
            except Exception:
                pass
    return None


def burn_ass(ff, video, ass_path, out, audio_track=None):
    cmd = [ff, "-hide_banner", "-loglevel", "error", "-y", "-i", video]
    maps = ["-map", "0:v:0"]
    if audio_track:
        cmd += ["-i", audio_track]; maps += ["-map", "1:a:0"]
    else:
        maps += ["-map", "0:a:0?"]
    cmd += maps + ["-vf", f"ass={ass_path}", "-c:v", "libx264", "-preset", "veryfast",
                   "-crf", "20", "-c:a", "aac", "-b:a", "192k", out]
    subprocess.run(cmd, check=True)
