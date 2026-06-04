#!/usr/bin/env python3
"""
kyma-dub discovery — the live "door" agents read to stay current.

Subcommands (invoked by bin/kyma-dub):
  models     [--json]                          translation-capable models on Kyma now
  voices     [filters] [--library] [--json]    available voices + gender/age/use-case labels
  preview    <voice> ["text"]                  synth a short sample to hear a voice
  recommend  --for "<need>" [--smart] [--json] suggest a voice (+model) for a user profile
  whatsnew                                     what models/voices Kyma added since last run

Everything is queried LIVE from Kyma /v1/models and ElevenLabs voices, so a
new model or voice shows up with zero tool update. Keys/base come from the
env that bin/kyma-dub exports (KYMA_API_KEY, ELEVENLABS_API_KEY, KYMA_DUB_*).
"""
import sys, os, json, argparse, urllib.request, urllib.error, subprocess

KYMA_BASE = os.environ.get("KYMA_DUB_BASE", "https://api.kymaapi.com")
KYMA_KEY = os.environ.get("KYMA_API_KEY", "")
XI_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
UA = os.environ.get("KYMA_DUB_USER_AGENT", "kyma-dub/0.1.0")
SNAPSHOT = os.path.expanduser("~/.config/kyma-dub/snapshot.json")
DEFAULT_TRANSLATE_MODEL = "qwen-3.7-max"

# Curated voice aliases (friendly defaults) — the full catalog is live below.
VOICE_ALIASES = {
    "charlie": "IKne3meq5aSn9XLyUdCD", "will": "bIHbv24MWmeRgasZH58o",
    "liam": "TX3LPaxmHKxFdv7VOQHJ", "brian": "nPczCjzI2devNBz1zQrb",
    "rachel": "21m00Tcm4TlvDq8ikWAM", "adam": "pNInz6obpgDQGcFmaJgB",
    "jessica": "cgSgspJ2msm6clMCkdW9",
}


def die(m): print(f"[kyma-dub] error: {m}", file=sys.stderr); sys.exit(1)

def _get_json(url, headers):
    req = urllib.request.Request(url, headers=headers)
    return json.load(urllib.request.urlopen(req, timeout=30))

def _kyma_models():
    if not KYMA_KEY:
        die("KYMA_API_KEY not set — needed to list models")
    d = _get_json(KYMA_BASE + "/v1/models",
                  {"Authorization": "Bearer " + KYMA_KEY, "User-Agent": UA})
    return d.get("data", d if isinstance(d, list) else [])

def _is_text_model(m):
    out = m.get("output_modalities") or ["text"]
    inp = m.get("input_modalities") or ["text"]
    return "text" in out and "text" in inp

def _translation_models(models):
    """Text models suited to dub translation, best-first."""
    out = []
    for m in models:
        if not _is_text_model(m):
            continue
        rec = m.get("recommended_for") or []
        if not (set(rec) & {"general", "multilingual", "reasoning", "coding"}):
            continue
        out.append(m)
    rank = {"frontier-open": 0, "frontier": 0, "strong": 1}
    out.sort(key=lambda m: (rank.get(m.get("quality_tier"), 3),
                            0 if m.get("id") == DEFAULT_TRANSLATE_MODEL else 1,
                            m.get("name", "")))
    return out


# ── models ──────────────────────────────────────────────────────────
def cmd_models(args):
    models = _translation_models(_kyma_models())
    if args.json:
        print(json.dumps([{
            "id": m["id"], "name": m.get("name"), "creator": m.get("owned_by"),
            "quality_tier": m.get("quality_tier"), "cost_tier": m.get("cost_tier"),
            "context_window": m.get("context_window"),
            "recommended_for": m.get("recommended_for"),
            "release_stage": m.get("release_stage"),
            "default": m["id"] == DEFAULT_TRANSLATE_MODEL,
        } for m in models], indent=2))
        return
    print(f"Translation-capable models on Kyma ({len(models)}), best first:\n")
    for m in models:
        star = " ★ default" if m["id"] == DEFAULT_TRANSLATE_MODEL else ""
        print(f"  {m['id']:<22} {m.get('quality_tier',''):<14} "
              f"{m.get('owned_by',''):<10} {m.get('cost_tier','')}{star}")
        print(f"      {m.get('description','')[:78]}")
    print(f"\nUse:  kyma-dub <video> --model <id>   (default: {DEFAULT_TRANSLATE_MODEL})")


# ── voices ──────────────────────────────────────────────────────────
def _account_voices():
    if not XI_KEY:
        return []
    d = _get_json("https://api.elevenlabs.io/v1/voices", {"xi-api-key": XI_KEY, "User-Agent": UA})
    out = []
    for v in d.get("voices", []):
        lb = v.get("labels", {}) or {}
        out.append({"name": v.get("name"), "voice_id": v.get("voice_id"),
                    "gender": lb.get("gender"), "age": lb.get("age"),
                    "accent": lb.get("accent"), "use_case": lb.get("use_case"),
                    "descriptive": lb.get("descriptive"), "language": lb.get("language"),
                    "source": "account"})
    return out

def _library_voices(args):
    if not XI_KEY:
        return []
    q = []
    if args.gender: q.append("gender=" + args.gender)
    if args.age: q.append("age=" + args.age)
    if args.use_case: q.append("use_cases=" + args.use_case)
    if args.lang: q.append("language=" + args.lang)
    if args.accent: q.append("accent=" + args.accent)
    q.append("page_size=24")
    url = "https://api.elevenlabs.io/v1/shared-voices?" + "&".join(q)
    d = _get_json(url, {"xi-api-key": XI_KEY, "User-Agent": UA})
    out = []
    for v in d.get("voices", []):
        out.append({"name": v.get("name"), "voice_id": v.get("voice_id"),
                    "gender": v.get("gender"), "age": v.get("age"),
                    "accent": v.get("accent"), "use_case": v.get("use_case"),
                    "descriptive": v.get("descriptive"), "language": v.get("language"),
                    "source": "library"})
    return out

def _filter_voices(voices, args):
    def ok(v):
        for key, want in (("gender", args.gender), ("age", args.age),
                          ("use_case", args.use_case), ("accent", args.accent),
                          ("language", args.lang)):
            if want and (v.get(key) or "").lower() != want.lower():
                return False
        return True
    return [v for v in voices if ok(v)]

def cmd_voices(args):
    voices = _library_voices(args) if args.library else _filter_voices(_account_voices(), args)
    if args.json:
        print(json.dumps(voices, indent=2)); return
    where = "shared library" if args.library else "your account"
    print(f"Voices in {where} ({len(voices)}):\n")
    for v in voices:
        meta = "/".join(x for x in (v.get("gender"), v.get("age"), v.get("accent")) if x)
        print(f"  {(v.get('name') or '')[:26]:<26} {meta:<26} "
              f"use={v.get('use_case') or '-'} lang={v.get('language') or '-'}")
        print(f"      id={v.get('voice_id')}")
    print("\nHear one:  kyma-dub preview <voice_id|alias>")
    print("Use one:   kyma-dub <video> --voice <voice_id|alias>")


# ── preview ─────────────────────────────────────────────────────────
def cmd_preview(args):
    if not (XI_KEY or KYMA_KEY):
        die("need ELEVENLABS_API_KEY or KYMA_API_KEY to synth a preview")
    vid = VOICE_ALIASES.get(args.voice.lower(), args.voice)
    text = args.text or "Hi, this is a quick sample of how this voice sounds for your dub."
    out = os.path.abspath(f"kyma-dub-preview-{vid[:8]}.mp3")
    if XI_KEY:
        body = json.dumps({"text": text, "model_id": "eleven_v3",
                           "voice_settings": {"stability": 0.4, "similarity_boost": 0.8,
                                              "use_speaker_boost": True}}).encode()
        req = urllib.request.Request(f"https://api.elevenlabs.io/v1/text-to-speech/{vid}",
                                     data=body, headers={"xi-api-key": XI_KEY, "Content-Type": "application/json",
                                                         "Accept": "audio/mpeg", "User-Agent": UA})
    else:
        body = json.dumps({"model": "eleven-v3", "input": text, "voice": vid}).encode()
        req = urllib.request.Request(KYMA_BASE + "/v1/audio/speech", data=body,
                                     headers={"Authorization": "Bearer " + KYMA_KEY,
                                              "Content-Type": "application/json", "User-Agent": UA})
    try:
        data = urllib.request.urlopen(req, timeout=120).read()
    except urllib.error.HTTPError as e:
        die(f"preview failed (HTTP {e.code}): {e.read().decode()[:200]}")
    open(out, "wb").write(data)
    print(out)
    if sys.platform == "darwin":
        subprocess.run(["open", out], check=False)


# ── recommend ───────────────────────────────────────────────────────
def cmd_recommend(args):
    need = args.for_
    models = _translation_models(_kyma_models())
    best_model = next((m["id"] for m in models), DEFAULT_TRANSLATE_MODEL)
    if args.smart:
        # Dogfood Kyma: let an LLM map the free-text need to filters + a pick.
        pool = (_library_voices(args) if args.library else _account_voices())[:40]
        sysp = ("You match a dubbing voice to a user's need. Given a need and a list of "
                "voices with gender/age/use_case/accent/descriptive labels, pick the 3 best "
                "voice_ids and say why in one short line each. "
                'Output JSON {"picks":[{"voice_id":..,"name":..,"why":..}],"note":".."}. JSON only.')
        body = json.dumps({"model": "best", "temperature": 0.4,
                           "response_format": {"type": "json_object"},
                           "messages": [{"role": "system", "content": sysp},
                                        {"role": "user", "content": f"Need: {need}\nVoices: {json.dumps(pool)}"}]}).encode()
        req = urllib.request.Request(KYMA_BASE + "/v1/chat/completions", data=body,
                                     headers={"Authorization": "Bearer " + KYMA_KEY,
                                              "Content-Type": "application/json", "User-Agent": UA})
        try:
            r = json.load(urllib.request.urlopen(req, timeout=120))
            raw = r["choices"][0]["message"]["content"].strip()
            if raw.startswith("```"): raw = raw.split("```")[1].lstrip("json").strip()
            picks = json.loads(raw)
        except Exception as e:
            die(f"smart recommend failed: {e}")
        if args.json:
            print(json.dumps({"model": best_model, **picks}, indent=2)); return
        print(f"Suggested translate model: {best_model}\n\nVoice picks for: {need}\n")
        for p in picks.get("picks", []):
            print(f"  {p.get('name','?'):<24} id={p.get('voice_id')}\n      {p.get('why','')}")
        if picks.get("note"): print("\n" + picks["note"])
        return
    # rule mode: filter by any structured hints in --for via flags
    voices = _library_voices(args) if args.library else _filter_voices(_account_voices(), args)
    voices = voices[:5]
    if args.json:
        print(json.dumps({"model": best_model, "voices": voices}, indent=2)); return
    print(f"Suggested translate model: {best_model}\n\nVoice matches ({len(voices)}):\n")
    for v in voices:
        meta = "/".join(x for x in (v.get("gender"), v.get("age"), v.get("accent")) if x)
        print(f"  {(v.get('name') or '')[:24]:<24} {meta:<22} use={v.get('use_case') or '-'}  id={v.get('voice_id')}")
    print("\nHear one:  kyma-dub preview <voice_id>    (or add --smart for an LLM pick)")


# ── whatsnew ────────────────────────────────────────────────────────
def _snapshot_now():
    models = sorted(m["id"] for m in _kyma_models())
    voices = sorted((v["voice_id"]) for v in _account_voices())
    names = {m["id"]: m.get("name") for m in _kyma_models()}
    vnames = {v["voice_id"]: v.get("name") for v in _account_voices()}
    return {"models": models, "voices": voices, "model_names": names, "voice_names": vnames}

def cmd_whatsnew(args):
    cur = _snapshot_now()
    prev = None
    if os.path.exists(SNAPSHOT):
        try: prev = json.load(open(SNAPSHOT))
        except Exception: prev = None
    os.makedirs(os.path.dirname(SNAPSHOT), exist_ok=True)
    json.dump(cur, open(SNAPSHOT, "w"), indent=1)
    if prev is None:
        print("First run — saved a snapshot of current Kyma models + voices.")
        print(f"  {len(cur['models'])} models, {len(cur['voices'])} voices tracked.")
        print("Run `kyma-dub whatsnew` again later to see what changed.")
        return
    new_m = [m for m in cur["models"] if m not in set(prev.get("models", []))]
    gone_m = [m for m in prev.get("models", []) if m not in set(cur["models"])]
    new_v = [v for v in cur["voices"] if v not in set(prev.get("voices", []))]
    gone_v = [v for v in prev.get("voices", []) if v not in set(cur["voices"])]
    if not any((new_m, gone_m, new_v, gone_v)):
        print("Nothing new since last check — models and voices are unchanged."); return
    if new_m:
        print("🆕 New models:")
        for m in new_m: print(f"  + {m}  ({cur['model_names'].get(m,'')})")
    if new_v:
        print("🆕 New voices:")
        for v in new_v: print(f"  + {cur['voice_names'].get(v,'')}  id={v}")
    if gone_m: print("➖ Removed models: " + ", ".join(gone_m))
    if gone_v: print("➖ Removed voices: " + str(len(gone_v)))


def main():
    p = argparse.ArgumentParser(prog="kyma-dub", add_help=True)
    sub = p.add_subparsers(dest="cmd", required=True)

    pm = sub.add_parser("models"); pm.add_argument("--json", action="store_true")

    def add_filters(sp):
        sp.add_argument("--gender"); sp.add_argument("--age")
        sp.add_argument("--use-case", dest="use_case"); sp.add_argument("--accent")
        sp.add_argument("--lang"); sp.add_argument("--library", action="store_true")
        sp.add_argument("--json", action="store_true")
    pv = sub.add_parser("voices"); add_filters(pv)
    pp = sub.add_parser("preview"); pp.add_argument("voice"); pp.add_argument("text", nargs="?")
    pr = sub.add_parser("recommend"); pr.add_argument("--for", dest="for_", required=True)
    pr.add_argument("--smart", action="store_true"); add_filters(pr)
    sub.add_parser("whatsnew")

    args = p.parse_args()
    {"models": cmd_models, "voices": cmd_voices, "preview": cmd_preview,
     "recommend": cmd_recommend, "whatsnew": cmd_whatsnew}[args.cmd](args)


if __name__ == "__main__":
    main()
