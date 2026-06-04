#!/usr/bin/env bash
# Dub every .mp4 in a folder to English with the charlie voice.
#   ./batch-dub.sh /path/to/videos [voice] [target-lang]
set -euo pipefail
DIR="${1:?usage: batch-dub.sh <dir> [voice] [lang]}"
VOICE="${2:-charlie}"
LANG="${3:-en}"
shopt -s nullglob
for f in "$DIR"/*.mp4; do
  case "$f" in *"[ "*"dub]"*.mp4) continue ;; esac   # skip already-dubbed outputs
  echo "==> dubbing: $f"
  kyma-dub "$f" --to "$LANG" --voice "$VOICE"
done
