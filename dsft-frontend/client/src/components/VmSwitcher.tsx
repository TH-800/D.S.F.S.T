// VmSwitcher.tsx - dropdown to pick which registered VM the dashboard is showing (SCRUM-8)
// plus a small dialog to register a new VM by name + IP (SCRUM-7)
// this is frontend-only for now - once the VM registry backend endpoints (SCRUM-6) are
// ready, addVm/setSelectedVmId in store.tsx should call the real API instead of just
// updating local state

import { useState } from "react";
import { Plus, Server } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogTrigger,
} from "@/components/ui/dialog";
import { useAppState } from "@/lib/store";

// very light IP validation - just checks it looks like four numbers separated by dots
function isValidIp(value: string) {
  const parts = value.trim().split(".");
  if (parts.length !== 4) return false;
  return parts.every((p) => /^\d{1,3}$/.test(p) && Number(p) <= 255);
}

export default function VmSwitcher() {
  const { vms, addVm, selectedVmId, setSelectedVmId } = useAppState();

  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [ip, setIp] = useState("");
  const [error, setError] = useState<string | null>(null);

  function handleAddVm() {
    const trimmedName = name.trim();

    if (!trimmedName) {
      setError("VM name is required.");
      return;
    }
    if (!isValidIp(ip)) {
      setError("Enter a valid IP address, like 192.168.1.50.");
      return;
    }
    if (vms.some((vm) => vm.name.toLowerCase() === trimmedName.toLowerCase())) {
      setError("A VM with that name already exists.");
      return;
    }

    addVm({ name: trimmedName, ip: ip.trim() });
    setName("");
    setIp("");
    setError(null);
    setOpen(false);
  }

  return (
    <div className="flex items-center gap-2">
      {/* VM switcher dropdown - SCRUM-8 */}
      <Select value={selectedVmId} onValueChange={setSelectedVmId}>
        <SelectTrigger className="w-[180px]" data-testid="select-vm-switcher">
          <Server className="h-4 w-4 mr-1 opacity-70" />
          <SelectValue placeholder="Select a VM" />
        </SelectTrigger>
        <SelectContent>
          {vms.map((vm) => (
            <SelectItem key={vm.id} value={vm.id} data-testid={`option-vm-${vm.id}`}>
              {vm.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {/* Add VM dialog - SCRUM-7 */}
      <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) setError(null); }}>
        <DialogTrigger asChild>
          <Button variant="outline" size="icon" data-testid="button-add-vm">
            <Plus className="h-4 w-4" />
          </Button>
        </DialogTrigger>
        <DialogContent data-testid="dialog-add-vm">
          <DialogHeader>
            <DialogTitle>Add VM</DialogTitle>
            <DialogDescription>
              Register a new machine by name and IP address so it shows up in the switcher.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3 py-2">
            <div className="space-y-1">
              <Label htmlFor="vm-name">Name</Label>
              <Input
                id="vm-name"
                placeholder="e.g. dsft-node-02"
                value={name}
                onChange={(e) => setName(e.target.value)}
                data-testid="input-vm-name"
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="vm-ip">IP Address</Label>
              <Input
                id="vm-ip"
                placeholder="e.g. 10.0.0.2"
                value={ip}
                onChange={(e) => setIp(e.target.value)}
                data-testid="input-vm-ip"
              />
            </div>
            {error && (
              <p className="text-sm text-red-500" data-testid="text-add-vm-error">
                {error}
              </p>
            )}
          </div>

          <DialogFooter>
            <Button onClick={handleAddVm} data-testid="button-submit-vm">
              Add VM
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
