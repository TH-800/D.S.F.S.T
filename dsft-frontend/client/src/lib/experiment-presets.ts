// AI-assisted SCRUM-16 implementation. Configuration storage does not start experiments.
export type PresetInjectionType = "cpu" | "latency" | "packet_loss" | "memory";
export interface PresetConfiguration {
  failure_type: PresetInjectionType;
  parameters: Record<string, number>;
}
export interface SavedPreset extends PresetConfiguration {
  preset_id: string;
  name: string;
  created_at: string;
}
const rules: Record<PresetInjectionType, Record<string, readonly [number, number, boolean]>> = {
  cpu: { cpu_percent: [1, 65, true], duration_seconds: [1, 300, true] },
  latency: { latency_ms: [0, 500, false] },
  packet_loss: { packet_loss_percent: [0, 50, false] },
  memory: { memory_mb: [64, 4096, true], duration_seconds: [1, 300, true] },
};
function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
export function validateConfiguration(value: unknown): PresetConfiguration {
  if (!record(value) || typeof value.failure_type !== "string" ||
      !Object.prototype.hasOwnProperty.call(rules, value.failure_type)) {
    throw new Error("Unsupported injection type");
  }
  const failure_type = value.failure_type as PresetInjectionType;
  const schema = rules[failure_type];
  const params = value.parameters;
  if (!record(params) || Object.keys(params).length !== Object.keys(schema).length ||
      !Object.keys(schema).every(key => Object.prototype.hasOwnProperty.call(params, key))) {
    throw new Error("Parameters must match the selected injection type");
  }
  const parameters: Record<string, number> = {};
  for (const [key, [low, high, integer]] of Object.entries(schema)) {
    const number = params[key];
    if (typeof number !== "number" || !Number.isFinite(number) || number < low || number > high ||
        (integer && !Number.isInteger(number))) {
      throw new Error(`${key} must be ${integer ? "a whole number " : ""}between ${low} and ${high}`);
    }
    parameters[key] = number;
  }
  return { failure_type, parameters };
}
export function validatePresetName(value: string): string {
  const name = value.trim();
  if (!name || name.length > 80 || /[\u0000-\u001f]/.test(name)) {
    throw new Error("Use a preset name of 1-80 characters without control characters");
  }
  return name;
}
function parsePreset(value: unknown): SavedPreset {
  if (!record(value) || typeof value.preset_id !== "string" || !value.preset_id ||
      typeof value.name !== "string" || typeof value.created_at !== "string") {
    throw new Error("Backend returned an invalid preset");
  }
  return { ...validateConfiguration(value), preset_id: value.preset_id,
    name: validatePresetName(value.name), created_at: value.created_at };
}
async function request(path: string, init?: RequestInit): Promise<unknown> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(`/api/8008/presets${path}`, { ...init, signal: controller.signal });
    const body: unknown = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = record(body) && typeof body.detail === "string" ? body.detail
        : record(body) && typeof body.error === "string" ? body.error : `HTTP ${response.status}`;
      throw new Error(`Preset request failed: ${detail}`);
    }
    return body;
  } finally { clearTimeout(timer); }
}
export async function listPresets(): Promise<SavedPreset[]> {
  const body = await request("?limit=200");
  if (!Array.isArray(body)) throw new Error("Backend returned an invalid preset list");
  return body.map(parsePreset);
}
export async function savePreset(name: string, configuration: PresetConfiguration): Promise<SavedPreset> {
  const body = { name: validatePresetName(name), ...validateConfiguration(configuration) };
  return parsePreset(await request("", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body) }));
}
export async function loadPreset(id: string): Promise<SavedPreset> {
  return parsePreset(await request(`/${encodeURIComponent(id)}`));
}
