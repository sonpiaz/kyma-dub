#!/usr/bin/env bash
# Shared env loader for kyma-dub.
#
# Discovery order:
#   1. process env (already exported)
#   2. ./.env in current working directory
#   3. ~/.config/kyma-dub/env
#   4. ~/kyma-api/.env  (Son's canonical key store — convenience only)
#
# Routing (default = everything on one Kyma key):
#   - Transcribe + translate + TTS all run through Kyma (api.kymaapi.com).
#     ELEVENLABS_API_KEY is optional — used as a direct TTS path / deep
#     fallback. GROQ_API_KEY is an optional direct STT fallback.

[[ -n "${KYMA_DUB_ENV_LOADED:-}" ]] && return 0
export KYMA_DUB_ENV_LOADED=1

# shellcheck source=version.sh
source "$(dirname "${BASH_SOURCE[0]}")/version.sh"
export KYMA_DUB_USER_AGENT="kyma-dub/${KYMA_DUB_VERSION}"

_load_dotenv() {
  local file="$1"
  [[ -f "$file" ]] || return 0
  while IFS='=' read -r key value; do
    [[ -z "$key" || "$key" == \#* ]] && continue
    [[ "$key" =~ ^[A-Z_][A-Z0-9_]*$ ]] || continue
    if [[ -z "${!key:-}" ]]; then
      value="${value%\"}"; value="${value#\"}"
      value="${value%\'}"; value="${value#\'}"
      export "$key=$value"
    fi
  done < "$file"
}

_load_dotenv "./.env"
_load_dotenv "$HOME/.config/kyma-dub/env"
_load_dotenv "$HOME/kyma-api/.env"

export KYMA_DUB_BASE="${KYMA_DUB_BASE:-https://api.kymaapi.com}"

# Determine routing mode for the STT + translate gates.
if [[ -n "${KYMA_API_KEY:-}" ]]; then
  export KYMA_DUB_MODE="kyma"
elif [[ -n "${GROQ_API_KEY:-}" ]]; then
  export KYMA_DUB_MODE="direct"   # transcribe via Groq; translate still needs a Kyma key
else
  export KYMA_DUB_MODE="none"
fi

kyma_dub_keys_check() {
  if [[ "$KYMA_DUB_MODE" == "none" ]]; then
    echo "[kyma-dub] No API key found." >&2
    echo "[kyma-dub] Recommended: get a Kyma key at https://kymaapi.com (60s, no card)." >&2
    echo "[kyma-dub]   export KYMA_API_KEY=kyma-xxxxxxxx" >&2
    echo "[kyma-dub] One key runs transcribe + translate + voice." >&2
    return 1
  fi
  if [[ "$KYMA_DUB_MODE" == "direct" && -z "${KYMA_API_KEY:-}" ]]; then
    echo "[kyma-dub] GROQ_API_KEY found but KYMA_API_KEY is missing — translation + TTS run through Kyma." >&2
    echo "[kyma-dub] Get a Kyma key at https://kymaapi.com or export KYMA_API_KEY." >&2
    return 1
  fi
  return 0
}
