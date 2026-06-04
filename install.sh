#!/usr/bin/env bash
# kyma-dub installer.
# Usage:
#   curl -fsSL https://github.com/sonpiaz/kyma-dub/releases/latest/download/install.sh | bash
# or, from a clone:
#   ./install.sh [--with-skill]
#
# Flags:
#   --with-skill   Copy SKILL.md into ~/.claude/skills/kyma-dub/ so Claude
#                  Code picks up the kyma-dub skill on next start.
#   -h, --help     Show this help and exit.

set -euo pipefail

REPO_URL="https://github.com/sonpiaz/kyma-dub"
INSTALL_DIR="${KYMA_DUB_HOME:-$HOME/.kyma-dub}"
BIN_LINK_DIR="${KYMA_DUB_BIN:-$HOME/.local/bin}"
CLAUDE_SKILLS_DIR="${HOME}/.claude/skills"
WITH_SKILL=0

red() { printf "\033[31m%s\033[0m\n" "$*"; }
green() { printf "\033[32m%s\033[0m\n" "$*"; }
yellow() { printf "\033[33m%s\033[0m\n" "$*"; }
dim() { printf "\033[2m%s\033[0m\n" "$*"; }

usage() {
  cat <<'EOF'
kyma-dub installer

Usage:
  curl -fsSL https://github.com/sonpiaz/kyma-dub/releases/latest/download/install.sh | bash
  ./install.sh [--with-skill]

Flags:
  --with-skill   Copy SKILL.md into ~/.claude/skills/kyma-dub/.
  -h, --help     Show this help and exit.
EOF
}

while (($# > 0)); do
  case "$1" in
    --with-skill) WITH_SKILL=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) red "Unknown flag: $1"; echo; usage; exit 64 ;;
  esac
done

echo "kyma-dub installer"
echo "=================="

# ── deps ──
missing=()
for cmd in ffmpeg ffprobe curl python3; do
  command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
done
if ((${#missing[@]} > 0)); then
  red "Missing dependencies: ${missing[*]}"
  echo "  macOS:  brew install ffmpeg"
  echo "  Debian: sudo apt install ffmpeg curl python3"
  exit 1
fi
green "✓ Dependencies present (ffmpeg, ffprobe, curl, python3)"

# ── install/update ──
if [[ -d "$INSTALL_DIR/.git" ]]; then
  yellow "Updating existing clone at $INSTALL_DIR …"
  git -C "$INSTALL_DIR" pull --rebase --quiet
else
  yellow "Cloning into $INSTALL_DIR …"
  rm -rf "$INSTALL_DIR"
  git clone --quiet "$REPO_URL" "$INSTALL_DIR"
fi
green "✓ kyma-dub installed at $INSTALL_DIR"

# ── symlink ──
mkdir -p "$BIN_LINK_DIR"
ln -sf "$INSTALL_DIR/bin/kyma-dub" "$BIN_LINK_DIR/kyma-dub"
green "✓ Symlinked kyma-dub -> $BIN_LINK_DIR/kyma-dub"

if [[ ":$PATH:" != *":$BIN_LINK_DIR:"* ]]; then
  echo
  yellow "⚠ $BIN_LINK_DIR is not in your PATH. Add to ~/.zshrc or ~/.bashrc:"
  echo "    export PATH=\"$BIN_LINK_DIR:\$PATH\""
fi

# ── optional skill ──
if ((WITH_SKILL)); then
  if [[ -f "$INSTALL_DIR/SKILL.md" ]]; then
    mkdir -p "$CLAUDE_SKILLS_DIR/kyma-dub"
    cp "$INSTALL_DIR/SKILL.md" "$CLAUDE_SKILLS_DIR/kyma-dub/SKILL.md"
    green "✓ Installed SKILL.md → $CLAUDE_SKILLS_DIR/kyma-dub/SKILL.md"
  else
    yellow "⚠ --with-skill: SKILL.md not found; skipped."
  fi
fi

# ── env scaffold ──
ENV_DIR="$HOME/.config/kyma-dub"
ENV_FILE="$ENV_DIR/env"
if [[ ! -f "$ENV_FILE" ]]; then
  mkdir -p "$ENV_DIR"
  cp "$INSTALL_DIR/.env.example" "$ENV_FILE"
  green "✓ Created $ENV_FILE"
  echo
  printf "\033[36m%s\033[0m\n" "🌊 Kyma — one key runs transcribe + translate + voice"
  echo "   ✓ Free credit at signup; auto-fallback when a provider is down"
  yellow "Get key (60s, no card): https://kymaapi.com"
  echo "Then edit $ENV_FILE: set KYMA_API_KEY."
else
  dim "  ($ENV_FILE already exists, leaving untouched)"
fi

echo
green "Done. Try it:"
echo "    kyma-dub yourvideo.mp4 --from vi --voice charlie"
echo "    kyma-dub voices --gender female --age young"
