#!/usr/bin/env node
/**
 * kyma-dub MCP stdio server.
 *
 * Exposes dubbing (job-based) + live model/voice discovery as MCP tools,
 * and models/voices as MCP resources so a host can read current
 * capabilities. Shells out to the local `kyma-dub` CLI (KYMA_DUB_BIN to
 * override the path).
 *
 * Spec: ../SPEC.md
 */

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  ListResourcesRequestSchema,
  ReadResourceRequestSchema,
  type CallToolResult,
} from "@modelcontextprotocol/sdk/types.js";

import {
  listModels, listVoices, recommendVoice, previewVoice, whatsNew,
  dubStart, dubStatus, readResource, RESOURCES,
  type DubArgs,
} from "./dub-tools.js";

const SERVER_NAME = "kyma-dub-mcp";
const SERVER_VERSION = "0.2.0";

const TOOLS = [
  {
    name: "dub_start",
    description:
      "Start dubbing a local video into another language with a natural, time-aligned AI voiceover (transcribe -> translate -> voice, synced to the original timing). Long-running: returns a job_id immediately — poll dub_status. Replaces audio only (no lip-sync).",
    inputSchema: {
      type: "object" as const,
      properties: {
        video_path: { type: "string", description: "Absolute path to the local video file." },
        source_lang: { type: "string", description: "Source language code (e.g. vi). Omit to auto-detect." },
        target_lang: { type: "string", description: "Target language code (default: en)." },
        voice: { type: "string", description: "Voice alias (charlie|will|liam|brian|rachel|adam|jessica) or an ElevenLabs voice id from list_voices." },
        model: { type: "string", description: "Translation model id (default: qwen-3.7-max; see list_models)." },
        tts: { type: "string", enum: ["kyma", "elevenlabs"], description: "TTS route (default: kyma — one key)." },
        max_speed: { type: "number", description: "Max voice speed-up to fit a slot (default 1.5). Never slows below 1.0." },
        chunk_sec: { type: "number", description: "Max seconds per dub chunk (default 22)." },
        allow_voice_fallback: { type: "boolean", description: "Permit an independent MiniMax voice if every ElevenLabs path is down (changes the voice)." },
        srt: { type: "boolean", description: "Also write a .srt timed to the dubbed audio." },
        bilingual: { type: "boolean", description: "Bilingual captions: target language on top, cleaned source smaller + dimmer below. Pair with burn." },
        burn: { type: "boolean", description: "Burn captions into the output video (needs a libass ffmpeg; otherwise writes the subtitle file)." },
        out: { type: "string", description: "Output file path. Defaults to '<name> [<LANG> dub].mp4' next to the source." },
      },
      required: ["video_path"],
      additionalProperties: false,
    },
  },
  {
    name: "dub_status",
    description: "Poll a dubbing job started with dub_start. Returns status (running|done|error), output_path when done, and a log tail.",
    inputSchema: {
      type: "object" as const,
      properties: { job_id: { type: "string", description: "The job_id returned by dub_start." } },
      required: ["job_id"],
      additionalProperties: false,
    },
  },
  {
    name: "list_models",
    description: "List translation-capable models available on Kyma right now (live). Use to recommend the current best model before dubbing.",
    inputSchema: { type: "object" as const, properties: {}, additionalProperties: false },
  },
  {
    name: "list_voices",
    description: "List available voices with gender/age/use-case/accent/language labels (live). Filter to match the user's audience, or search the shared library.",
    inputSchema: {
      type: "object" as const,
      properties: {
        gender: { type: "string", description: "male | female" },
        age: { type: "string", description: "young | middle_aged | old" },
        use_case: { type: "string", description: "e.g. social_media | narrative_story | conversational | characters | entertainment_tv" },
        accent: { type: "string" },
        lang: { type: "string", description: "Language code (e.g. en, es)." },
        library: { type: "boolean", description: "Search the shared voice library instead of the account voices." },
      },
      additionalProperties: false,
    },
  },
  {
    name: "recommend_voice",
    description: "Recommend voices (and the current best translation model) for a user's need. Set smart=true to let a Kyma model pick from a free-text description.",
    inputSchema: {
      type: "object" as const,
      properties: {
        need: { type: "string", description: "Free-text description, e.g. 'young female, energetic, for TikTok, English'." },
        smart: { type: "boolean", description: "Use a Kyma LLM to pick (default false = rule filter)." },
        gender: { type: "string" }, age: { type: "string" }, use_case: { type: "string" },
        accent: { type: "string" }, lang: { type: "string" }, library: { type: "boolean" },
      },
      required: ["need"],
      additionalProperties: false,
    },
  },
  {
    name: "preview_voice",
    description: "Synthesize a short sample of a voice so the user can hear it before dubbing. Returns the saved mp3 path.",
    inputSchema: {
      type: "object" as const,
      properties: {
        voice: { type: "string", description: "Voice alias or ElevenLabs voice id." },
        text: { type: "string", description: "Optional sample text." },
      },
      required: ["voice"],
      additionalProperties: false,
    },
  },
  {
    name: "whatsnew",
    description: "Report which models and voices Kyma added or removed since the last check (snapshot diff).",
    inputSchema: { type: "object" as const, properties: {}, additionalProperties: false },
  },
];

async function dispatch(name: string, args: Record<string, unknown>): Promise<CallToolResult> {
  switch (name) {
    case "dub_start": return dubStart(args as unknown as DubArgs) as Promise<CallToolResult>;
    case "dub_status": return dubStatus(args as { job_id: string }) as Promise<CallToolResult>;
    case "list_models": return listModels() as Promise<CallToolResult>;
    case "list_voices": return listVoices(args) as Promise<CallToolResult>;
    case "recommend_voice": return recommendVoice(args as { need: string; smart?: boolean }) as Promise<CallToolResult>;
    case "preview_voice": return previewVoice(args as { voice: string; text?: string }) as Promise<CallToolResult>;
    case "whatsnew": return whatsNew() as Promise<CallToolResult>;
    default: throw new Error(`unknown tool: ${name}`);
  }
}

async function main(): Promise<void> {
  const server = new Server(
    { name: SERVER_NAME, version: SERVER_VERSION },
    { capabilities: { tools: {}, resources: {} } },
  );

  server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: TOOLS }));
  server.setRequestHandler(CallToolRequestSchema, async (request): Promise<CallToolResult> =>
    dispatch(request.params.name, (request.params.arguments ?? {}) as Record<string, unknown>));

  server.setRequestHandler(ListResourcesRequestSchema, async () => ({ resources: RESOURCES }));
  server.setRequestHandler(ReadResourceRequestSchema, async (request) =>
    readResource(request.params.uri));

  const transport = new StdioServerTransport();
  await server.connect(transport);

  const shutdown = async () => {
    try { await server.close(); } finally { process.exit(0); }
  };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);
}

main().catch((err) => {
  process.stderr.write(`[kyma-dub-mcp] fatal: ${err instanceof Error ? err.message : String(err)}\n`);
  process.exit(1);
});
