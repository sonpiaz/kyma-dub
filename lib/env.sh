#!/usr/bin/env bash
# Shared env loader for dub-cli.
#
# Discovery order:
#   1. process env (already exported)
#   2. ./.env in current working directory
#   3. ~/.config/dub-cli/env
#   4. ~/kyma-api/.env  (Son's canonical key store — convenience only)
#
# Routing:
#   - Transcribe + translate: Kyma mode (recommended) when KYMA_API_KEY
#     is set → api.kymaapi.com. One key opens the STT + LLM gates.
#     Direct/BYOK fallback: GROQ_API_KEY (transcribe) + a Kyma key is
#     still required for translation today.
#   - TTS: ElevenLabs direct (best quality, model eleven_v3) when
#     ELEVENLABS_API_KEY is set; otherwise routed through Kyma. A
#     provider-independent last-resort TTS (MiniMax via Kyma) only
#     engages with --allow-voice-fallback because it changes the voice.

[[ -n "${DUB_CLI_ENV_LOADED:-}" ]] && return 0
export DUB_CLI_ENV_LOADED=1

# shellcheck source=version.sh
source "$(dirname "${BASH_SOURCE[0]}")/version.sh"
export DUB_CLI_USER_AGENT="dub-cli/${DUB_CLI_VERSION}"

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
_load_dotenv "$HOME/.config/dub-cli/env"
_load_dotenv "$HOME/kyma-api/.env"

export DUB_KYMA_BASE="${DUB_KYMA_BASE:-https://api.kymaapi.com}"

# Determine routing mode for the STT + translate gates.
if [[ -n "${KYMA_API_KEY:-}" ]]; then
  export DUB_MODE="kyma"
elif [[ -n "${GROQ_API_KEY:-}" ]]; then
  export DUB_MODE="direct"   # transcribe via Groq; translate still needs a Kyma key
else
  export DUB_MODE="none"
fi

dub_keys_check() {
  if [[ "$DUB_MODE" == "none" ]]; then
    echo "[dub] No API key found for transcription/translation." >&2
    echo "[dub] Recommended: get a Kyma key at https://kymaapi.com (60s, no card)." >&2
    echo "[dub]   export KYMA_API_KEY=kyma-xxxxxxxx" >&2
    echo "[dub] Or set GROQ_API_KEY for transcription (translation still needs KYMA_API_KEY)." >&2
    return 1
  fi
  if [[ "$DUB_MODE" == "direct" && -z "${KYMA_API_KEY:-}" ]]; then
    echo "[dub] GROQ_API_KEY found but KYMA_API_KEY is missing — translation runs through Kyma." >&2
    echo "[dub] Get a Kyma key at https://kymaapi.com or export KYMA_API_KEY." >&2
    return 1
  fi
  if [[ -z "${ELEVENLABS_API_KEY:-}" && -z "${KYMA_API_KEY:-}" ]]; then
    echo "[dub] No TTS provider: set ELEVENLABS_API_KEY (best, eleven_v3) or KYMA_API_KEY." >&2
    return 1
  fi
  return 0
}
