// store.tsx - shared state for the whole app using React context
// this is where we keep track of experiments, logs, and the data mode toggle
// we use context instead of a state management library to keep it simple

import { createContext, useContext, useState, useCallback, type ReactNode } from "react";

// --- types ---

// each experiment we run gets tracked here
export interface Experiment {
  id: string;
  name: string;
  type: "cpu" | "latency" | "packet_loss" | "memory";
  status: "running" | "stopped" | "completed";
  params: Record<string, number>; // like { cpuPercent: 50, duration: 30 }
  startedAt: string;
  stoppedAt?: string;
}

// log entries for tracking whats happening in the system
export interface LogEntry {
  id: string;
  timestamp: string;
  eventType: "injection_started" | "injection_stopped" | "metric_collected" | "error";
  message: string;
}

// completed experiment reports with before/during/after metrics
export interface Report {
  id: string;
  experimentName: string;
  type: "cpu" | "latency" | "packet_loss" | "memory";
  duration: string;
  completedAt: string;
  metrics: {
    before: Record<string, number>;
    during: Record<string, number>;
    after: Record<string, number>;
  };
}

// the shape of our context - what components can access
interface AppState {
  // are we using real API data or fake mock data?
  isLiveMode: boolean;
  setIsLiveMode: (v: boolean) => void;

  // experiment tracking
  experiments: Experiment[];
  addExperiment: (exp: Experiment) => void;
  updateExperiment: (id: string, updates: Partial<Experiment>) => void;

  // log entries
  logs: LogEntry[];
  addLog: (entry: Omit<LogEntry, "id">) => void;

  // experiment reports
  reports: Report[];
}

// create the context with a default value of undefined
// (we'll throw an error if someone tries to use it outside the provider)
const AppContext = createContext<AppState | undefined>(undefined);

// helper to make a unique id - nothing fancy, just good enough
function makeId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
}

// --- mock reports that we show by default ---
// these are supposed to look like previously completed experiments
const defaultReports: Report[] = [
  {
    id: "rpt-001",
    experimentName: "CPU Stress Test - 50%",
    type: "cpu",
    duration: "60 seconds",
    completedAt: "2026-03-15T14:30:00.000Z",
    metrics: {
      before: { cpu_usage_percent: 38, memory_percent: 55, latency_ms: 18 },
      during: { cpu_usage_percent: 72, memory_percent: 68, latency_ms: 45 },
      after: { cpu_usage_percent: 41, memory_percent: 57, latency_ms: 20 },
    },
  },
  {
    id: "rpt-002",
    experimentName: "Network Latency Injection - 200ms",
    type: "latency",
    duration: "45 seconds",
    completedAt: "2026-03-14T10:15:00.000Z",
    metrics: {
      before: { cpu_usage_percent: 36, memory_percent: 52, latency_ms: 16 },
      during: { cpu_usage_percent: 39, memory_percent: 54, latency_ms: 218 },
      after: { cpu_usage_percent: 37, memory_percent: 53, latency_ms: 19 },
    },
  },
  {
    id: "rpt-003",
    experimentName: "Packet Loss Test - 15%",
    type: "packet_loss",
    duration: "30 seconds",
    completedAt: "2026-03-13T16:45:00.000Z",
    metrics: {
      before: { cpu_usage_percent: 40, memory_percent: 58, latency_ms: 20 },
      during: { cpu_usage_percent: 44, memory_percent: 61, latency_ms: 85 },
      after: { cpu_usage_percent: 41, memory_percent: 59, latency_ms: 22 },
    },
  },
];

// --- the provider component that wraps our app ---

export function AppProvider({ children }: { children: ReactNode }) {
  // default to mock data mode since the backend probably isnt running
  const [isLiveMode, setIsLiveMode] = useState(false);
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [reports] = useState<Report[]>(defaultReports);

  // add a new experiment to the list
  const addExperiment = useCallback((exp: Experiment) => {
    setExperiments((prev) => [exp, ...prev]);
  }, []);

  // update an existing experiment (like changing status from running to stopped)
  const updateExperiment = useCallback((id: string, updates: Partial<Experiment>) => {
    setExperiments((prev) =>
      prev.map((exp) => (exp.id === id ? { ...exp, ...updates } : exp))
    );
  }, []);

  // add a log entry to the log list
  const addLog = useCallback((entry: Omit<LogEntry, "id">) => {
    const newEntry: LogEntry = { ...entry, id: makeId() };
    setLogs((prev) => [newEntry, ...prev]);
  }, []);

  return (
    <AppContext.Provider
      value={{
        isLiveMode,
        setIsLiveMode,
        experiments,
        addExperiment,
        updateExperiment,
        logs,
        addLog,
        reports,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}

// hook to use the app state - throws if you forget the provider
export function useAppState() {
  const ctx = useContext(AppContext);
  if (!ctx) {
    throw new Error("useAppState must be used inside AppProvider");
  }
  return ctx;
}
