/**
 * kyma-dub MCP tool + resource handlers.
 *
 * Shells out to the local `kyma-dub` CLI (override with KYMA_DUB_BIN).
 * Discovery tools are synchronous (fast `--json` calls). Dubbing is long
 * (minutes), so it is job-based: `dub_start` spawns a background job and
 * returns a job_id immediately; `dub_status` polls it. This avoids host
 * call-timeouts on long videos.
 */

import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { ErrorCode, McpError } from "@modelcontextprotocol/sdk/types.js";

const BIN = process.env.KYMA_DUB_BIN || "kyma-dub";
const STDERR_TAIL = 1500;

export interface CliResult {
  exitCode: number;
  stdout: string;
  stderr: string;
}

function runCli(args: string[]): Promise<CliResult> {
  return new Promise((resolve, reject) => {
    const child = spawn(BIN, args, { stdio: ["ignore", "pipe", "pipe"] });
    const out: Buffer[] = [];
    const err: Buffer[] = [];
    child.stdout.on("data", (b: Buffer) => out.push(b));
    child.stderr.on("data", (b: Buffer) => err.push(b));
    child.on("error", (e: NodeJS.ErrnoException) => {
      if (e.code === "ENOENT") {
        reject(new McpError(ErrorCode.InternalError,
          "tag=missing-dep:kyma-dub — install via https://github.com/sonpiaz/kyma-dub (curl install.sh | bash), or set KYMA_DUB_BIN"));
        return;
      }
      reject(new McpError(ErrorCode.InternalError, `failed to spawn kyma-dub: ${e.message}`));
    });
    child.on("close", (code) => resolve({
      exitCode: code ?? 1,
      stdout: Buffer.concat(out).toString("utf8"),
      stderr: Buffer.concat(err).toString("utf8"),
    }));
  });
}

function tail(s: string): string {
  return s.length <= STDERR_TAIL ? s.trim() : s.slice(s.length - STDERR_TAIL).trim();
}

async function runJson(args: string[]): Promise<unknown> {
  const r = await runCli(args);
  if (r.exitCode !== 0) {
    throw new McpError(ErrorCode.InternalError, `kyma-dub ${args[0]} failed (exit ${r.exitCode}): ${tail(r.stderr)}`);
  }
  try {
    return JSON.parse(r.stdout.trim());
  } catch (e) {
    throw new McpError(ErrorCode.InternalError, `kyma-dub ${args[0]} produced invalid JSON: ${(e as Error).message}`);
  }
}

function asText(v: unknown): { content: Array<{ type: "text"; text: string }> } {
  return { content: [{ type: "text", text: typeof v === "string" ? v : JSON.stringify(v, null, 2) }] };
}

// ── discovery (sync) ────────────────────────────────────────────────
export async function listModels() {
  return asText(await runJson(["models", "--json"]));
}

interface VoiceFilters {
  gender?: string; age?: string; use_case?: string; accent?: string; lang?: string; library?: boolean;
}
function voiceArgs(a: VoiceFilters): string[] {
  const args: string[] = [];
  if (a.gender) args.push("--gender", a.gender);
  if (a.age) args.push("--age", a.age);
  if (a.use_case) args.push("--use-case", a.use_case);
  if (a.accent) args.push("--accent", a.accent);
  if (a.lang) args.push("--lang", a.lang);
  if (a.library) args.push("--library");
  return args;
}

export async function listVoices(a: VoiceFilters) {
  return asText(await runJson(["voices", ...voiceArgs(a), "--json"]));
}

export async function recommendVoice(a: { need: string; smart?: boolean } & VoiceFilters) {
  if (!a?.need) throw new McpError(ErrorCode.InvalidParams, "tag=usage-error — required field `need` is missing");
  const args = ["recommend", "--for", a.need, ...voiceArgs(a), "--json"];
  if (a.smart) args.push("--smart");
  return asText(await runJson(args));
}

export async function previewVoice(a: { voice: string; text?: string }) {
  if (!a?.voice) throw new McpError(ErrorCode.InvalidParams, "tag=usage-error — required field `voice` is missing");
  const args = ["preview", a.voice];
  if (a.text) args.push(a.text);
  const r = await runCli(args);
  if (r.exitCode !== 0) throw new McpError(ErrorCode.InternalError, `preview failed: ${tail(r.stderr)}`);
  return asText(`Saved sample to: ${r.stdout.trim()}`);
}

export async function whatsNew() {
  const r = await runCli(["whatsnew"]);
  if (r.exitCode !== 0) throw new McpError(ErrorCode.InternalError, `whatsnew failed: ${tail(r.stderr)}`);
  return asText(r.stdout.trim());
}

// ── dubbing (job-based) ─────────────────────────────────────────────
type JobStatus = "running" | "done" | "error";
interface Job {
  id: string; status: JobStatus; video: string;
  outputPath?: string; error?: string; logTail: string; startedAt: number; finishedAt?: number;
}
const jobs = new Map<string, Job>();

export interface DubArgs {
  video_path: string; source_lang?: string; target_lang?: string; voice?: string;
  model?: string; tts?: string; max_speed?: number; chunk_sec?: number;
  allow_voice_fallback?: boolean; srt?: boolean; bilingual?: boolean; burn?: boolean; out?: string;
}

export async function dubStart(a: DubArgs) {
  if (!a?.video_path) throw new McpError(ErrorCode.InvalidParams, "tag=usage-error — required field `video_path` is missing");
  const args = [a.video_path];
  if (a.source_lang) args.push("--from", a.source_lang);
  if (a.target_lang) args.push("--to", a.target_lang);
  if (a.voice) args.push("--voice", a.voice);
  if (a.model) args.push("--model", a.model);
  if (a.tts) args.push("--tts", a.tts);
  if (a.max_speed != null) args.push("--max-speed", String(a.max_speed));
  if (a.chunk_sec != null) args.push("--chunk-sec", String(a.chunk_sec));
  if (a.allow_voice_fallback) args.push("--allow-voice-fallback");
  if (a.srt) args.push("--srt");
  if (a.bilingual) args.push("--bilingual");
  if (a.burn) args.push("--burn");
  if (a.out) args.push("--out", a.out);

  const id = randomUUID().slice(0, 8);
  const job: Job = { id, status: "running", video: a.video_path, logTail: "", startedAt: Date.now() };
  jobs.set(id, job);

  const child = spawn(BIN, args, { stdio: ["ignore", "pipe", "pipe"] });
  const out: Buffer[] = [];
  const err: Buffer[] = [];
  child.stdout.on("data", (b: Buffer) => out.push(b));
  child.stderr.on("data", (b: Buffer) => { err.push(b); job.logTail = tail(Buffer.concat(err).toString("utf8")); });
  child.on("error", (e: NodeJS.ErrnoException) => {
    job.status = "error";
    job.error = e.code === "ENOENT"
      ? "tag=missing-dep:kyma-dub — install kyma-dub or set KYMA_DUB_BIN"
      : `spawn failed: ${e.message}`;
    job.finishedAt = Date.now();
  });
  child.on("close", (code) => {
    job.finishedAt = Date.now();
    if (code === 0) {
      job.status = "done";
      job.outputPath = Buffer.concat(out).toString("utf8").trim().split("\n").pop() ?? "";
    } else {
      job.status = "error";
      job.error = `kyma-dub exited ${code}`;
      job.logTail = tail(Buffer.concat(err).toString("utf8"));
    }
  });

  return asText({ job_id: id, status: "running", message: "Dubbing started. Poll dub_status with this job_id." });
}

export async function dubStatus(a: { job_id: string }) {
  if (!a?.job_id) throw new McpError(ErrorCode.InvalidParams, "tag=usage-error — required field `job_id` is missing");
  const job = jobs.get(a.job_id);
  if (!job) throw new McpError(ErrorCode.InvalidParams, `tag=unknown-job — no job with id ${a.job_id}`);
  return asText({
    job_id: job.id,
    status: job.status,
    output_path: job.outputPath ?? null,
    error: job.error ?? null,
    elapsed_sec: Math.round(((job.finishedAt ?? Date.now()) - job.startedAt) / 1000),
    log_tail: job.logTail,
  });
}

// ── resources (the capability "door") ───────────────────────────────
export const RESOURCES = [
  { uri: "kyma-dub://models", name: "kyma-dub: translation models", description: "Translation-capable models available on Kyma right now (live).", mimeType: "application/json" },
  { uri: "kyma-dub://voices", name: "kyma-dub: voices", description: "Voices available in your account with gender/age/use-case labels (live).", mimeType: "application/json" },
];

export async function readResource(uri: string) {
  if (uri === "kyma-dub://models") {
    const data = await runJson(["models", "--json"]);
    return { contents: [{ uri, mimeType: "application/json", text: JSON.stringify(data, null, 2) }] };
  }
  if (uri === "kyma-dub://voices") {
    const data = await runJson(["voices", "--json"]);
    return { contents: [{ uri, mimeType: "application/json", text: JSON.stringify(data, null, 2) }] };
  }
  throw new McpError(ErrorCode.InvalidParams, `unknown resource: ${uri}`);
}
