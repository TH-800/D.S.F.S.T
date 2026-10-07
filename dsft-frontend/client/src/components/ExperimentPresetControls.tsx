// AI-assisted SCRUM-16 UI. Save/Load never invokes an experiment-start API.
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useToast } from "@/hooks/use-toast";
import { listPresets, loadPreset, savePreset, validatePresetName,
  type PresetConfiguration, type SavedPreset } from "@/lib/experiment-presets";

interface Props {
  isLiveMode: boolean;
  configuration: PresetConfiguration;
  onLoad: (configuration: PresetConfiguration) => void;
}
export default function ExperimentPresetControls({ isLiveMode, configuration, onLoad }: Props) {
  const { toast } = useToast();
  const [name, setName] = useState("");
  const [presets, setPresets] = useState<SavedPreset[]>([]);
  const [selected, setSelected] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const generation = useRef(0);
  const saving = useRef(false);

  useEffect(() => {
    const token = ++generation.current;
    setError(""); setPresets([]); setSelected("");
    if (!isLiveMode) { setPending(false); return; }
    setPending(true);
    listPresets().then(items => {
      if (token === generation.current) setPresets(items);
    }).catch(err => {
      if (token === generation.current) setError(err instanceof Error ? err.message : "Could not list presets");
    }).finally(() => {
      if (token === generation.current) setPending(false);
    });
    return () => { generation.current++; };
  }, [isLiveMode]);

  async function act(action: "save" | "load" | "refresh") {
    if (!isLiveMode || pending || saving.current) return;
    saving.current = true;
    const token = generation.current;
    setPending(true); setError("");
    try {
      if (action === "save") {
        const item = await savePreset(name, configuration);
        if (token !== generation.current) return;
        setPresets(previous => [item, ...previous.filter(p => p.preset_id !== item.preset_id)]);
        setSelected(item.preset_id); setName("");
        toast({ title: "Preset saved", description: item.name });
      } else if (action === "load") {
        if (!selected) throw new Error("Choose a preset first");
        const item = await loadPreset(selected);
        if (token !== generation.current) return;
        onLoad(item);
        toast({ title: "Preset loaded", description: "Settings restored. No experiment was started." });
      } else {
        const items = await listPresets();
        if (token !== generation.current) return;
        setPresets(items);
        setSelected(previous => items.some(p => p.preset_id === previous) ? previous : "");
      }
    } catch (err) {
      if (token !== generation.current) return;
      const message = err instanceof Error ? err.message : "Preset request failed";
      setError(message);
      toast({ title: "Preset action failed", description: message, variant: "destructive" });
    } finally {
      saving.current = false;
      if (token === generation.current) setPending(false);
    }
  }
  let validName = false;
  try { validatePresetName(name); validName = true; } catch { /* disabled until valid */ }
  const disabled = !isLiveMode || pending;
  return (
    <section className="space-y-3 rounded-md border p-3" aria-label="Saved experiment presets" data-testid="preset-controls">
      <h3 className="text-sm font-medium">Saved Presets</h3>
      <p className="text-xs text-muted-foreground">
        {isLiveMode ? "Stored in this backend's MongoDB. Loading changes settings only."
          : "Switch to Live API to save or load database presets."}
      </p>
      <div className="space-y-2">
        <Label htmlFor="preset-name">Preset name</Label>
        <Input id="preset-name" data-testid="input-preset-name" value={name} maxLength={80}
          onChange={e => setName(e.target.value)} placeholder="Example: CPU baseline test" disabled={disabled} />
        <Button type="button" variant="outline" className="w-full" disabled={disabled || !validName}
          onClick={() => void act("save")} data-testid="button-save-preset">Save Current Settings</Button>
      </div>
      <div className="space-y-2">
        <Label htmlFor="saved-preset">Saved preset</Label>
        <select id="saved-preset" data-testid="select-saved-preset" value={selected}
          onChange={e => setSelected(e.target.value)} disabled={disabled}
          className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm">
          <option value="">{presets.length ? "Choose a preset" : "No presets loaded"}</option>
          {presets.map(p => <option key={p.preset_id} value={p.preset_id}>{p.name} ({p.failure_type})</option>)}
        </select>
        <div className="flex gap-2">
          <Button type="button" variant="outline" disabled={disabled || !selected}
            onClick={() => void act("load")} data-testid="button-load-preset">Load Settings</Button>
          <Button type="button" variant="ghost" disabled={disabled}
            onClick={() => void act("refresh")}>Refresh List</Button>
        </div>
      </div>
      {pending && <p role="status" className="text-xs">Working...</p>}
      {error && <p role="alert" className="text-xs text-red-500">{error}</p>}
    </section>
  );
}
