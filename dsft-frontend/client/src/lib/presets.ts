// SCRUM-16: generated with OpenAI Codex assistance.
import { z } from "zod";

export const configurationSchema = z.discriminatedUnion("failure_type", [
  z.object({ failure_type: z.literal("cpu_stress"), parameters: z.object({
    cpu_percent: z.number().int().min(1).max(65),
    duration_seconds: z.number().int().min(1).max(300),
  }).strict() }),
  z.object({ failure_type: z.literal("memory_stress"), parameters: z.object({
    memory_mb: z.number().int().min(64).max(4096),
    duration_seconds: z.number().int().min(1).max(300),
  }).strict() }),
  z.object({ failure_type: z.literal("network_latency"), parameters: z.object({
    latency_ms: z.number().int().min(0).max(500),
  }).strict() }),
  z.object({ failure_type: z.literal("packet_loss"), parameters: z.object({
    packet_loss_percent: z.number().int().min(0).max(50),
  }).strict() }),
]);
export type PresetConfiguration = z.infer<typeof configurationSchema>;
const metadataSchema = z.object({
  preset_id: z.string().min(1), name: z.string().trim().min(1).max(80),
  created_at: z.string(),
});
export const savedPresetSchema = z.preprocess(value => {
  if (!value || typeof value !== "object") return value;
  const record = value as Record<string, unknown>;
  const aliases: Record<string, string> = { cpu: "cpu_stress", memory: "memory_stress", latency: "network_latency" };
  return { ...record, failure_type: typeof record.failure_type === "string"
    ? aliases[record.failure_type] ?? record.failure_type : record.failure_type };
}, configurationSchema.and(metadataSchema));
export type SavedPreset = z.infer<typeof savedPresetSchema>;
const MOCK_KEY = "dsfst.mock-presets.v1";

export function readMockPresets(): SavedPreset[] {
  return z.array(savedPresetSchema).parse(JSON.parse(localStorage.getItem(MOCK_KEY) || "[]"));
}

export function saveMockPreset(name: string, config: PresetConfiguration): SavedPreset {
  const preset = savedPresetSchema.parse({
    ...config, name, preset_id: crypto.randomUUID(), created_at: new Date().toISOString(),
  });
  const presets = readMockPresets();
  // Persist first: a blocked/full browser store must not show false success.
  localStorage.setItem(MOCK_KEY, JSON.stringify([preset, ...presets]));
  return preset;
}

async function presetRequest(path: string, init?: RequestInit): Promise<unknown> {
  const res = await fetch(`/api/8008/presets${path}`, {
    ...init, signal: AbortSignal.timeout(15000),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const detail = typeof body?.detail === "string" ? body.detail : `HTTP ${res.status}`;
    throw new Error(`Preset request failed: ${detail}`);
  }
  return res.json();
}

export async function fetchPresets(offset = 0): Promise<SavedPreset[]> {
  return z.array(savedPresetSchema).parse(await presetRequest(`?limit=200&offset=${offset}`));
}

export async function savePreset(name: string, config: PresetConfiguration): Promise<SavedPreset> {
  const valid = configurationSchema.parse(config);
  return savedPresetSchema.parse(await presetRequest("", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: name.trim(), ...valid }),
  }));
}

export async function fetchPreset(id: string): Promise<SavedPreset> {
  return savedPresetSchema.parse(await presetRequest(`/${encodeURIComponent(id)}`));
}
