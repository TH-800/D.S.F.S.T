// SCRUM-20: an informational tour; it never starts experiments or changes modes.
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";

export const GUIDE_KEY = "dsfst.walkthrough.v1.seen";
const steps = [
  { title: "Welcome to D.S.F.S.T.", text: "Explore the app in Mock Data mode first. Live API connects to real services and experiments can affect your test VM. This guide only explains the controls." },
  { title: "Dashboard and connection lights", text: "View CPU, memory and network readings. Green means a service is reported online, red means unavailable, and grey means unknown. Green does not mean an experiment is running." },
  { title: "Virtual machines", text: "Register existing VMs using their API addresses. Choose one VM to view measurements, or check several targets to launch the same experiment on them. The VMs page always uses real services, independently of the dashboard's Mock setting." },
  { title: "Experiments and saved presets", text: "Choose a failure type and its settings. Loading a saved preset fills the form without starting a test. Start runs the experiment; Stop requests a reset. CPU and memory have durations. Network faults need a stop or reset." },
  { title: "Logs and reports", text: "Logs show activity and errors. Reports show saved results where measurements are available. Check the result of every stop: an unavailable service may leave a reset unconfirmed. You can reopen this guide from the header anytime." },
];
function unseen() {
  try { return localStorage.getItem(GUIDE_KEY) !== "true"; }
  catch { return true; }
}
export default function FirstUseGuide() {
  const [open, setOpen] = useState(unseen);
  const [step, setStep] = useState(0);
  function changeOpen(next: boolean) {
    setOpen(next);
    if (next) setStep(0);
    else { try { localStorage.setItem(GUIDE_KEY, "true"); } catch { /* Storage can be disabled. */ } }
  }
  return <Dialog open={open} onOpenChange={changeOpen}>
    <DialogTrigger asChild><Button variant="outline" size="sm">Quick guide</Button></DialogTrigger>
    <DialogContent>
      <DialogHeader>
        <p className="text-sm text-muted-foreground" aria-live="polite">Step {step + 1} of {steps.length}</p>
        <DialogTitle>{steps[step].title}</DialogTitle>
        <DialogDescription className="leading-relaxed">{steps[step].text}</DialogDescription>
      </DialogHeader>
      <div className="flex flex-wrap justify-between gap-2">
        <Button variant="ghost" onClick={() => changeOpen(false)}>Skip guide</Button>
        <div className="flex gap-2">
          <Button variant="outline" disabled={step === 0} onClick={() => setStep(step - 1)}>Back</Button>
          {step < steps.length - 1
            ? <Button onClick={() => setStep(step + 1)}>Next</Button>
            : <Button onClick={() => changeOpen(false)}>Finish guide</Button>}
        </div>
      </div>
    </DialogContent>
  </Dialog>;
}
