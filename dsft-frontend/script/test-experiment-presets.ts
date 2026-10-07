// AI-assisted tests. Run with the locally installed tsx; no injection is started.
import assert from "node:assert/strict";
import { validateConfiguration, validatePresetName, listPresets, loadPreset, savePreset } from "../client/src/lib/experiment-presets";

const valid = [
  { failure_type: "cpu", parameters: { cpu_percent: 20, duration_seconds: 10 } },
  { failure_type: "latency", parameters: { latency_ms: 12.5 } },
  { failure_type: "packet_loss", parameters: { packet_loss_percent: 2.5 } },
  { failure_type: "memory", parameters: { memory_mb: 128, duration_seconds: 10 } },
];
for (const item of valid) assert.deepEqual(validateConfiguration(item), item);
for (const item of [
  { failure_type: "cpu", parameters: { cpu_percent: 66, duration_seconds: 10 } },
  { failure_type: "cpu", parameters: { cpu_percent: 20, duration_seconds: 1.5 } },
  { failure_type: "cpu", parameters: { cpu_percent: true, duration_seconds: 10 } },
  { failure_type: "cpu", parameters: { cpu_percent: NaN, duration_seconds: 10 } },
  { failure_type: "cpu", parameters: { cpu_percent: 20 } },
  { failure_type: "cpu", parameters: { cpu_percent: 20, duration_seconds: 10, extra: 1 } },
  { failure_type: "memory", parameters: { memory_mb: 4097, duration_seconds: 10 } },
  { failure_type: "latency", parameters: { latency_ms: -1 } },
  { failure_type: "packet_loss", parameters: { packet_loss_percent: 51 } },
  { failure_type: "__proto__", parameters: {} },
]) assert.throws(() => validateConfiguration(item));
assert.equal(validatePresetName("  Demo  "), "Demo");
for (const name of [" ", "x".repeat(81), "x\nY"]) assert.throws(() => validatePresetName(name));

const originalFetch = globalThis.fetch;
const calls: { url: string; method: string; body?: string }[] = [];
const saved = { ...valid[0], preset_id: "preset-1", name: "Demo", created_at: "2026-10-07T19:00:00Z" };
try {
  globalThis.fetch = (async (input: unknown, init?: RequestInit) => {
    calls.push({ url: String(input), method: init?.method ?? "GET", body: init?.body as string | undefined });
    const response = init?.method === "POST" ? saved : String(input).includes("?limit=") ? [saved] : saved;
    return new Response(JSON.stringify(response), { status: init?.method === "POST" ? 201 : 200 });
  }) as typeof fetch;
  assert.deepEqual(await savePreset("Demo", valid[0] as any), saved);
  assert.deepEqual(await listPresets(), [saved]);
  assert.deepEqual(await loadPreset("preset-1"), saved);
  assert.ok(calls.every(call => call.url.startsWith("/api/8008/presets")));
  assert.ok(calls.every(call => !call.url.includes("/start") && !call.url.includes("/inject")));
  assert.equal(JSON.parse(calls[0].body!).parameters.cpu_percent, 20);
  globalThis.fetch = (async () => new Response(JSON.stringify({ detail: "Preset name already exists" }), { status: 409 })) as typeof fetch;
  await assert.rejects(() => savePreset("Demo", valid[0] as any), /already exists/);
  globalThis.fetch = (async () => new Response(JSON.stringify({ error: "VM API 8008 is unavailable" }), { status: 502 })) as typeof fetch;
  await assert.rejects(() => listPresets(), /unavailable/);
  globalThis.fetch = (async () => new Response("{}", { status: 200 })) as typeof fetch;
  await assert.rejects(() => listPresets(), /invalid preset list/);
} finally { globalThis.fetch = originalFetch; }
console.log("PASS: four preset types, validation, API save/list/load, errors, and no start/inject requests.");
