// SCRUM-12/16 interaction regressions. Simulated DOM and API; no injections.
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";
import React from "react";
const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost:3000' });
Object.assign(globalThis, {
  window: dom.window, document: dom.window.document, HTMLElement: dom.window.HTMLElement,
  localStorage: dom.window.localStorage, React,
});
Object.defineProperty(globalThis, 'navigator', { value: dom.window.navigator, configurable: true });
const { render, screen, fireEvent, waitFor, cleanup } = await import('@testing-library/react');
const { default: PresetControls } = await import('../client/src/components/PresetControls');
const { default: ServiceConnections } = await import('../client/src/components/ServiceConnections');
const { getMockStatusData } = await import('../client/src/lib/api');
const { configurationSchema } = await import('../client/src/lib/presets');

let records: any[] = [];
let writes = 0;
let failSave = false;
let monitorFails = false;
let loaded: any = null;
const calls: string[] = [];
globalThis.fetch = async (input: any, options: any = {}) => {
  const url = String(input);
  calls.push(url);
  if (url === '/api/8000/status') {
    if (monitorFails) return new Response('{}', { status: 502 });
    const status = getMockStatusData();
    status.services['8002'].online = false;
    return Response.json(status);
  }
  assert.ok(url.startsWith('/api/8008/presets'), `Unexpected API call: ${url}`);
  if (options.method === 'POST') {
    writes++;
    if (failSave) return Response.json({ detail: 'Database unavailable' }, { status: 503 });
    const saved = { ...JSON.parse(options.body), preset_id: `p${writes}`, created_at: new Date().toISOString() };
    records.unshift(saved);
    return Response.json(saved, { status: 201 });
  }
  if (url.includes('?')) return Response.json(records);
  const item = records.find(p => url.endsWith('/' + p.preset_id));
  return item ? Response.json(item) : new Response('{}', { status: 404 });
};
const cpu = { failure_type: 'cpu_stress', parameters: { cpu_percent: 25, duration_seconds: 10 } } as const;
const configs = [cpu,
  { failure_type: 'memory_stress', parameters: { memory_mb: 128, duration_seconds: 5 } },
  { failure_type: 'network_latency', parameters: { latency_ms: 0 } },
  { failure_type: 'packet_loss', parameters: { packet_loss_percent: 0 } },
] as const;

for (const [i, config] of configs.entries()) {
  render(<PresetControls live configuration={config} onLoad={value => { loaded = value; }} />);
  await waitFor(() => assert.equal((screen.getByRole('button', { name: 'Save current settings' }) as HTMLButtonElement).disabled, false));
  fireEvent.change(screen.getByLabelText('Preset name'), { target: { value: `Preset ${i}` } });
  fireEvent.click(screen.getByRole('button', { name: 'Save current settings' }));
  await screen.findByText(`Saved “Preset ${i}”. No experiment was started.`);
  assert.equal(loaded, null);
  fireEvent.click(screen.getByRole('button', { name: 'Load preset' }));
  await waitFor(() => assert.deepEqual(loaded, config));
  loaded = null;
  cleanup();
}
render(<PresetControls live configuration={cpu} onLoad={value => { loaded = value; }} />);
await waitFor(() => assert.equal((screen.getByRole('button', { name: 'Save current settings' }) as HTMLButtonElement).disabled, false));
assert.equal(screen.getByLabelText('Choose a saved preset').querySelectorAll('option').length, 5);
// Missing record must leave the form unchanged.
fireEvent.change(screen.getByLabelText('Choose a saved preset'), { target: { value: records[0].preset_id } });
records = [];
fireEvent.click(screen.getByRole('button', { name: 'Load preset' }));
await screen.findByRole('alert');
assert.equal(loaded, null);
// A failed save must not report success.
failSave = true;
fireEvent.change(screen.getByLabelText('Preset name'), { target: { value: 'Unavailable' } });
fireEvent.click(screen.getByRole('button', { name: 'Save current settings' }));
await screen.findByText(/Save was not confirmed/);
cleanup();

const beforeMock = calls.length;
render(<PresetControls live={false} configuration={cpu} onLoad={value => { loaded = value; }} />);
await waitFor(() => assert.equal((screen.getByRole('button', { name: 'Save current settings' }) as HTMLButtonElement).disabled, false));
fireEvent.change(screen.getByLabelText('Preset name'), { target: { value: 'Mock only' } });
fireEvent.click(screen.getByRole('button', { name: 'Save current settings' }));
await screen.findByText('Saved “Mock only”. No experiment was started.');
cleanup();
render(<PresetControls live={false} configuration={cpu} onLoad={value => { loaded = value; }} />);
await waitFor(() => assert.equal(screen.getByLabelText('Choose a saved preset').querySelectorAll('option').length, 2));
assert.equal(calls.length, beforeMock);
cleanup();

render(<ServiceConnections live />);
await waitFor(() => assert.ok(screen.getByLabelText('CPU monitoring (8002): Unreachable')));
assert.ok(screen.getByLabelText('Metrics and presets (8008): Online'));
monitorFails = true;
await waitFor(() => assert.ok(screen.getByLabelText('Service monitor (8000): Unreachable')), { timeout: 6500 });
assert.ok(screen.getByLabelText('Metrics and presets (8008): Not checked'));
monitorFails = false;
await waitFor(() => assert.ok(screen.getByLabelText('Service monitor (8000): Online')), { timeout: 6500 });
cleanup();
assert.equal(configurationSchema.safeParse({ ...cpu, parameters: { cpu_percent: 66, duration_seconds: 10 } }).success, false);
assert.equal(configurationSchema.safeParse({ ...cpu, parameters: { cpu_percent: 25.5, duration_seconds: 10 } }).success, false);
assert.ok(!calls.some(url => url.includes('/api/8009') || url.includes('/inject/')));
console.log('PASS: four preset types, remount persistence, mock isolation, failed save/load, limits, red/green/unknown lights and monitor recovery; no injection calls.');
