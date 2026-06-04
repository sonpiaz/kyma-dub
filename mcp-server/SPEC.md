# kyma-dub MCP server — spec

Thin MCP stdio wrapper over the `kyma-dub` CLI. The CLI does all work; this
server maps MCP tool/resource calls to CLI invocations.

## CLI resolution
- Binary: `process.env.KYMA_DUB_BIN` or `kyma-dub` on `PATH`.
- ENOENT on spawn → `tag=missing-dep:kyma-dub` (install hint).
- Child inherits the server process env (keys resolve as the CLI normally does).

## Tools
- `dub_start(video_path, …)` → spawns `kyma-dub <video> [flags]`, registers an
  in-memory job, returns `{job_id, status:"running"}` immediately. The job's
  `output_path` is the CLI's final stdout line on exit 0.
- `dub_status(job_id)` → `{status, output_path, error, elapsed_sec, log_tail}`.
  Jobs live for the server process lifetime (in-memory Map).
- `list_models` → `kyma-dub models --json`.
- `list_voices(filters)` → `kyma-dub voices [--gender …] --json`.
- `recommend_voice(need, smart, filters)` → `kyma-dub recommend --for … [--smart] --json`.
- `preview_voice(voice, text?)` → `kyma-dub preview …` → returns saved mp3 path.
- `whatsnew` → `kyma-dub whatsnew` (text).

## Resources
- `kyma-dub://models` → live `kyma-dub models --json`.
- `kyma-dub://voices` → live `kyma-dub voices --json`.

## Error mapping
- Missing required arg → `McpError(InvalidParams, "tag=usage-error — …")`.
- CLI non-zero exit → `McpError(InternalError, "… exit N: <stderr tail>")`.
- Invalid JSON from a `--json` call → `McpError(InternalError, "invalid JSON")`.

## Why job-based dubbing
A dub takes minutes (transcribe + per-chunk TTS + ffmpeg). A synchronous tool
call risks host timeouts, so `dub_start`/`dub_status` decouples kickoff from
completion. Discovery tools are fast and stay synchronous.
