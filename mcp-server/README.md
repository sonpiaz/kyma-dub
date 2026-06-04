# @sonpiaz/kyma-dub-mcp

MCP stdio server for [kyma-dub](https://github.com/sonpiaz/kyma-dub) — dub videos into another language with a natural, time-aligned AI voiceover, plus live model/voice discovery. Brings kyma-dub into MCP-capable desktops (Claude desktop, Cursor, ChatGPT desktop).

## Prerequisite

The `kyma-dub` CLI must be installed and on `PATH` (it does the work; this server just wraps it):

```bash
curl -fsSL https://github.com/sonpiaz/kyma-dub/releases/latest/download/install.sh | bash
```

Set `KYMA_API_KEY` (in `~/.config/kyma-dub/env` or your environment). Override the CLI path with `KYMA_DUB_BIN` if it isn't on `PATH`.

## Install & build

```bash
cd mcp-server
npm install
npm run build
```

## Configure your host

**Claude desktop** (`claude_desktop_config.json`) / **Cursor** (`~/.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "kyma-dub": {
      "command": "npx",
      "args": ["-y", "@sonpiaz/kyma-dub-mcp"],
      "env": {
        "KYMA_API_KEY": "kyma-xxxxxxxx",
        "KYMA_DUB_BIN": "/Users/you/.local/bin/kyma-dub"
      }
    }
  }
}
```

> **Set `KYMA_DUB_BIN`** to the absolute path of the `kyma-dub` CLI (run `which kyma-dub`). Desktop apps spawn the server with a minimal `PATH` that usually omits `~/.local/bin`, so without this the server reports `tag=missing-dep:kyma-dub`.

Published on npm: [`@sonpiaz/kyma-dub-mcp`](https://www.npmjs.com/package/@sonpiaz/kyma-dub-mcp). (For local dev, point `command` to `node` + `dist/index.js` instead.)

## Tools

| Tool | What it does |
|---|---|
| `dub_start` | Start dubbing a local video. Long-running → returns a `job_id`. |
| `dub_status` | Poll a dub job: `running` / `done` (with `output_path`) / `error`. |
| `list_models` | Translation-capable models on Kyma right now (live). |
| `list_voices` | Voices + gender/age/use-case/accent/language labels; `library` to search the shared catalog. |
| `recommend_voice` | Suggest voices (+ best model) for a need; `smart` lets a Kyma model pick. |
| `preview_voice` | Synthesize a short sample so the user can hear a voice first. |
| `whatsnew` | What models/voices Kyma added since last check. |

## Resources

| URI | Content |
|---|---|
| `kyma-dub://models` | Live translation models (JSON) |
| `kyma-dub://voices` | Live account voices with labels (JSON) |

Dubbing is **job-based** (`dub_start` → `dub_status`) because a dub takes minutes — this avoids host call-timeouts. Discovery tools are synchronous.

## License

MIT © Son Piaz
