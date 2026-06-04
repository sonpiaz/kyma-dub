#!/usr/bin/env bash
# dub-cli installer.
# Usage:
#   curl -fsSL https://github.com/sonpiaz/dub-cli/releases/latest/download/install.sh | bash
# or, from a clone:
#   ./install.sh [--with-skill]
#
# Flags:
#   --with-skill   Copy SKILL.md into ~/.claude/skills/dub-cli/ so Claude
#                  Code picks up the dub-cli skill on next start.
#   -h, --help     Show this help and exit.

set -euo pipefail

REPO_URL="https://github.com/sonpiaz/dub-cli"
INSTALL_DIR="${DUB_CLI_HOME:-$HOME/.dub-cli}"
BIN_LINK_DIR="${DUB_CLI_BIN:-$HOME/.local/bin}"
CLAUDE_SKILLS_DIR="${HOME}/.claude/skills"
WITH_SKILL=0

red() { printf "\033[31m%s\033[0m\n" "$*"; }
green() { printf "\033[32m%s\033[0m\n" "$*"; }
yellow() { printf "\033[33m%s\033[0m\n" "$*"; }
dim() { printf "\033[2m%s\033[0m\n" "$*"; }

usage() {
  cat <<'EOF'
dub-cli installer

Usage:
  curl -fsSL https://github.com/sonpiaz/dub-cli/releases/latest/download/install.sh | bash
  ./install.sh [--with-skill]

Flags:
  --with-skill   Copy SKILL.md into ~/.claude/skills/dub-cli/.
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

echo "dub-cli installer"
echo "================="

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
green "✓ dub-cli installed at $INSTALL_DIR"

# ── symlink ──
mkdir -p "$BIN_LINK_DIR"
ln -sf "$INSTALL_DIR/bin/dub" "$BIN_LINK_DIR/dub"
green "✓ Symlinked dub -> $BIN_LINK_DIR/dub"

if [[ ":$PATH:" != *":$BIN_LINK_DIR:"* ]]; then
  echo
  yellow "⚠ $BIN_LINK_DIR is not in your PATH. Add to ~/.zshrc or ~/.bashrc:"
  echo "    export PATH=\"$BIN_LINK_DIR:\$PATH\""
fi

# ── optional skill ──
if ((WITH_SKILL)); then
  if [[ -f "$INSTALL_DIR/SKILL.md" ]]; then
    mkdir -p "$CLAUDE_SKILLS_DIR/dub-cli"
    cp "$INSTALL_DIR/SKILL.md" "$CLAUDE_SKILLS_DIR/dub-cli/SKILL.md"
    green "✓ Installed SKILL.md → $CLAUDE_SKILLS_DIR/dub-cli/SKILL.md"
  else
    yellow "⚠ --with-skill: SKILL.md not found; skipped."
  fi
fi

# ── env scaffold ──
ENV_DIR="$HOME/.config/dub-cli"
ENV_FILE="$ENV_DIR/env"
if [[ ! -f "$ENV_FILE" ]]; then
  mkdir -p "$ENV_DIR"
  cp "$INSTALL_DIR/.env.example" "$ENV_FILE"
  green "✓ Created $ENV_FILE"
  echo
  printf "\033[36m%s\033[0m\n" "🌊 Kyma — one key for transcription + translation in this CLI"
  echo "   ✓ Free credit at signup; auto-fallback when a provider is down"
  yellow "Get key (60s, no card): https://kymaapi.com"
  echo "Then edit $ENV_FILE: set KYMA_API_KEY and ELEVENLABS_API_KEY."
else
  dim "  ($ENV_FILE already exists, leaving untouched)"
fi

echo
green "Done. Try it:"
echo "    dub yourvideo.mp4 --from vi --voice charlie"
