// Logs.tsx - shows a scrollable list of all the events that have happened
// each log entry has a timestamp, type, and message
// you can filter by event type to find what youre looking for

import { useState, useMemo, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Play, Square, Activity, AlertCircle, RefreshCw } from "lucide-react";
import { useAppState, type LogEntry } from "@/lib/store";
import { fetchDbLogs, type DbLogEntry } from "@/lib/api";

// the event types we track
type EventFilter = "all" | "injection_started" | "injection_stopped" | "metric_collected" | "error";

// gives us a nice formatted time string
function formatTimestamp(ts: string) {
  try {
    const d = new Date(ts);
    return d.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return ts;
  }
}

// returns the right badge color/style for each event type
function getEventBadge(eventType: string) {
  switch (eventType) {
    case "injection_started":
      return (
        <Badge className="bg-emerald-500/10 text-emerald-500 border-emerald-500/20 text-xs">
          <Play className="h-3 w-3 mr-1" />
          Started
        </Badge>
      );
    case "injection_stopped":
      return (
        <Badge className="bg-yellow-500/10 text-yellow-500 border-yellow-500/20 text-xs">
          <Square className="h-3 w-3 mr-1" />
          Stopped
        </Badge>
      );
    case "metric_collected":
      return (
        <Badge className="bg-blue-500/10 text-blue-500 border-blue-500/20 text-xs">
          <Activity className="h-3 w-3 mr-1" />
          Metric
        </Badge>
      );
    case "error":
      return (
        <Badge className="bg-red-500/10 text-red-500 border-red-500/20 text-xs">
          <AlertCircle className="h-3 w-3 mr-1" />
          Error
        </Badge>
      );
    default:
      return <Badge variant="secondary" className="text-xs">{eventType}</Badge>;
  }
}

export default function Logs() {
  const { logs, isLiveMode } = useAppState();
  const [filter, setFilter] = useState<EventFilter>("all");
  const [dbLogs, setDbLogs] = useState<DbLogEntry[]>([]);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // fetch persisted logs from MongoDB when in live mode
  const refreshDbLogs = useCallback(async () => {
    if (!isLiveMode) return;
    setIsRefreshing(true);
    try {
      const remote = await fetchDbLogs(200);
      setDbLogs(remote);
    } catch {
      // database might not be running, thats fine
    }
    setIsRefreshing(false);
  }, [isLiveMode]);

  // load db logs on mount and when live mode changes
  useEffect(() => {
    refreshDbLogs();
  }, [refreshDbLogs]);

  // merge local session logs with persisted database logs
  // we convert db logs to the same shape as local logs so the list looks uniform
  // then deduplicate by timestamp+message to avoid showing the same event twice
  const mergedLogs = useMemo(() => {
    if (!isLiveMode || dbLogs.length === 0) return logs;

    // convert db logs to the local LogEntry shape
    const converted: LogEntry[] = dbLogs.map((dbLog) => ({
      id: dbLog.log_id,
      timestamp: dbLog.timestamp,
      eventType: dbLog.event_type as LogEntry["eventType"],
      message: dbLog.message,
    }));

    // merge and deduplicate - use a set of "timestamp|message" to check for dupes
    const seen = new Set(logs.map((l) => `${l.timestamp}|${l.message}`));
    const unique = converted.filter((c) => !seen.has(`${c.timestamp}|${c.message}`));

    // combine and sort newest first
    return [...logs, ...unique].sort(
      (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
    );
  }, [logs, dbLogs, isLiveMode]);

  // filter the logs based on what the user selected
  const filteredLogs = useMemo(() => {
    if (filter === "all") return mergedLogs;
    return mergedLogs.filter((log) => log.eventType === filter);
  }, [mergedLogs, filter]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold" data-testid="text-logs-title">
            Event Logs
          </h2>
          <p className="text-sm text-muted-foreground">
            System events and experiment activity
          </p>
        </div>

        {/* filter dropdown and refresh button */}
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">Filter:</span>
          <Select value={filter} onValueChange={(v) => setFilter(v as EventFilter)}>
            <SelectTrigger className="w-[180px]" data-testid="select-log-filter">
              <SelectValue placeholder="All events" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Events</SelectItem>
              <SelectItem value="injection_started">Injection Started</SelectItem>
              <SelectItem value="injection_stopped">Injection Stopped</SelectItem>
              <SelectItem value="metric_collected">Metric Collected</SelectItem>
              <SelectItem value="error">Errors</SelectItem>
            </SelectContent>
          </Select>
          {/* refresh button to re-fetch logs from the database */}
          {isLiveMode && (
            <Button
              variant="outline"
              size="sm"
              onClick={refreshDbLogs}
              disabled={isRefreshing}
              data-testid="button-refresh-logs"
            >
              <RefreshCw className={`h-4 w-4 ${isRefreshing ? "animate-spin" : ""}`} />
            </Button>
          )}
        </div>
      </div>

      <Card data-testid="card-logs">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium">
            {filteredLogs.length} {filteredLogs.length === 1 ? "entry" : "entries"}
            {filter !== "all" && ` (filtered)`}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {filteredLogs.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <Activity className="h-8 w-8 mx-auto mb-3 opacity-50" />
              <p className="text-sm">No log entries yet</p>
              <p className="text-xs mt-1">
                Events will appear here as you use the dashboard and run experiments
              </p>
            </div>
          ) : (
            <ScrollArea className="h-[500px]">
              <div className="space-y-2">
                {filteredLogs.map((log) => (
                  <div
                    key={log.id}
                    className="flex items-start gap-3 p-3 rounded-md border bg-card text-sm"
                    data-testid={`log-entry-${log.id}`}
                  >
                    {/* timestamp on the left */}
                    <span className="text-xs text-muted-foreground whitespace-nowrap font-mono pt-0.5">
                      {formatTimestamp(log.timestamp)}
                    </span>
                    {/* event type badge */}
                    <div className="flex-shrink-0">
                      {getEventBadge(log.eventType)}
                    </div>
                    {/* the actual log message */}
                    <span className="text-sm min-w-0 break-words">{log.message}</span>
                  </div>
                ))}
              </div>
            </ScrollArea>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
