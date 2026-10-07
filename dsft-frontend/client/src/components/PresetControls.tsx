// SCRUM-16: generated with OpenAI Codex assistance.
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  configurationSchema, fetchPreset, fetchPresets, readMockPresets,
  saveMockPreset, savePreset, type PresetConfiguration, type SavedPreset,
} from "@/lib/presets";

interface Props {
  live: boolean;
  configuration: PresetConfiguration;
  onLoad: (configuration: PresetConfiguration) => void;
  disabled?: boolean;
}

export default function PresetControls({ live, configuration, onLoad, disabled }: Props) {
  const [presets, setPresets] = useState<SavedPreset[]>([]);
  const [name, setName] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [busy, setBusy] = useState(true);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [hasMore, setHasMore] = useState(false);
  const active = useRef(false);

  async function refresh(append = false) {
    setBusy(true);
    setError("");
    try {
      const result = live ? await fetchPresets(append ? presets.length : 0) : readMockPresets();
      if (!active.current) return;
      setPresets(previous => append ? [...previous, ...result] : result);
      setHasMore(live && result.length === 200);
      if (!append) setSelectedId("");
    } catch {
      if (active.current) setError(live
        ? "Could not read presets from this VM. Check the Metrics API and database, then refresh."
        : "Could not read browser presets. Browser storage may be blocked or contain invalid data.");
    } finally {
      if (active.current) setBusy(false);
    }
  }

  useEffect(() => {
    active.current = true;
    void refresh();
    return () => { active.current = false; };
  }, [live]);

  async function handleSave() {
    setMessage("");
    setError("");
    if (!name.trim()) { setError("Enter a preset name."); return; }
    if (!configurationSchema.safeParse(configuration).success) {
      setError("Check the experiment values. Use whole numbers within the displayed limits.");
      return;
    }
    setBusy(true);
    try {
      const preset = live ? await savePreset(name, configuration) : saveMockPreset(name, configuration);
      if (!active.current) return;
      setPresets(previous => [preset, ...previous]);
      setSelectedId(preset.preset_id);
      setName("");
      setMessage(`Saved “${preset.name}”. No experiment was started.`);
    } catch {
      if (active.current) setError("Save was not confirmed. Refresh the list before retrying to avoid a duplicate.");
    } finally {
      if (active.current) setBusy(false);
    }
  }

  async function handleLoad() {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const preset = live ? await fetchPreset(selectedId) : readMockPresets().find(p => p.preset_id === selectedId);
      if (!preset) throw new Error("Preset not found");
      const valid = configurationSchema.parse(preset);
      if (!active.current) return;
      onLoad(valid);
      setMessage(`Loaded “${preset.name}”. Review the settings, then choose Start Experiment when ready.`);
    } catch {
      if (active.current) setError("Could not load this preset. It may be unavailable or have unsupported settings. Your settings were not changed.");
    } finally {
      if (active.current) setBusy(false);
    }
  }

  return (
    <section aria-label="Saved experiment presets" className="space-y-3 border-t pt-4">
      <h3 className="text-sm font-medium">Saved presets</h3>
      <p className="text-xs text-muted-foreground">
        {live ? "Saved in this VM’s database." : "Mock mode: saved only in this browser, separately from live presets."}
      </p>
      <Label htmlFor="preset-name">Preset name</Label>
      <Input id="preset-name" maxLength={80} value={name} disabled={busy || disabled}
        onChange={event => setName(event.target.value)} placeholder="e.g. CPU 30 percent for 10 seconds" />
      <Button variant="outline" className="w-full" onClick={handleSave} disabled={busy || disabled}>
        Save current settings
      </Button>
      <Label htmlFor="saved-preset">Choose a saved preset</Label>
      <select id="saved-preset" value={selectedId} onChange={event => setSelectedId(event.target.value)}
        disabled={busy || disabled} className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm">
        <option value="">{presets.length ? "Select a preset" : "No presets loaded"}</option>
        {presets.map(p => <option key={p.preset_id} value={p.preset_id}>{p.name} — {p.failure_type}</option>)}
      </select>
      <div className="flex flex-wrap gap-2">
        <Button onClick={handleLoad} disabled={!selectedId || busy || disabled}>Load preset</Button>
        <Button variant="outline" onClick={() => void refresh()} disabled={busy || disabled}>Refresh presets</Button>
        {hasMore && <Button variant="outline" onClick={() => void refresh(true)} disabled={busy || disabled}>More presets</Button>}
      </div>
      {busy && <p role="status" className="text-xs">Working…</p>}
      {message && <p role="status" className="text-xs">{message}</p>}
      {error && <p role="alert" className="text-sm text-red-500">{error}</p>}
    </section>
  );
}
