// Reports.tsx - shows summaries of completed experiments
// each report card has before/during/after metrics so you can see the impact
// in live mode, pulls from the database backend instead of using mock reports
// theres also a button to export reports from the backend or as local JSON

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Download, Cpu, Wifi, AlertTriangle, MemoryStick, TrendingUp, TrendingDown, Minus, BarChart3, ChevronDown, ChevronUp } from "lucide-react";
import { useAppState } from "@/lib/store";
import {
  fetchReportsSummary,
  fetchExperimentReport,
  fetchAggregateStats,
  fetchExperimentExportUrl,
  type ReportSummary,
  type ExperimentReport,
  type AggregateStats,
} from "@/lib/api";

// format a date string to something readable
function formatDate(ts: string) {
  try {
    return new Date(ts).toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return ts;
  }
}

// pick the right icon for the experiment type
function getTypeIcon(type: string) {
  switch (type) {
    case "cpu":
      return <Cpu className="h-4 w-4" />;
    case "latency":
      return <Wifi className="h-4 w-4" />;
    case "packet_loss":
      return <AlertTriangle className="h-4 w-4" />;
    case "memory":
      return <MemoryStick className="h-4 w-4" />;
    default:
      return null;
  }
}

// get a nice label for the experiment type
function getTypeLabel(type: string) {
  switch (type) {
    case "cpu":
      return "CPU Stress";
    case "latency":
      return "Network Latency";
    case "packet_loss":
      return "Packet Loss";
    case "memory":
      return "Memory Stress";
    default:
      return type;
  }
}

// shows a little trend arrow comparing two values
function TrendIndicator({ before, during }: { before: number; during: number }) {
  const diff = during - before;
  const pct = before > 0 ? Math.round((diff / before) * 100) : 0;

  if (Math.abs(pct) < 5) {
    return (
      <span className="flex items-center gap-1 text-xs text-muted-foreground">
        <Minus className="h-3 w-3" /> {pct > 0 ? "+" : ""}{pct}%
      </span>
    );
  }

  if (diff > 0) {
    return (
      <span className="flex items-center gap-1 text-xs text-red-400">
        <TrendingUp className="h-3 w-3" /> +{pct}%
      </span>
    );
  }

  return (
    <span className="flex items-center gap-1 text-xs text-emerald-400">
      <TrendingDown className="h-3 w-3" /> {pct}%
    </span>
  );
}

export default function Reports() {
  const { reports, isLiveMode } = useAppState();

  // live mode state - reports from the database and aggregate stats
  const [summaries, setSummaries] = useState<ReportSummary[]>([]);
  const [aggregateStats, setAggregateStats] = useState<AggregateStats | null>(null);
  // tracks which experiment reports the user has expanded to see details
  const [expandedReports, setExpandedReports] = useState<Record<string, ExperimentReport>>({});
  const [loadingReport, setLoadingReport] = useState<string | null>(null);

  // fetch report summaries and aggregate stats from the backend
  const refreshReports = useCallback(async () => {
    if (!isLiveMode) return;
    try {
      const [sums, stats] = await Promise.allSettled([
        fetchReportsSummary(20),
        fetchAggregateStats(),
      ]);
      if (sums.status === "fulfilled") setSummaries(sums.value);
      if (stats.status === "fulfilled") setAggregateStats(stats.value);
    } catch {
      // backend might not be running
    }
  }, [isLiveMode]);

  useEffect(() => {
    refreshReports();
  }, [refreshReports]);

  // toggles the detailed report view for a specific experiment
  // fetches the full report from the backend the first time its expanded
  async function toggleReport(id: string) {
    if (expandedReports[id]) {
      // collapse it
      const next = { ...expandedReports };
      delete next[id];
      setExpandedReports(next);
      return;
    }

    // fetch the detailed report
    setLoadingReport(id);
    try {
      const report = await fetchExperimentReport(id);
      setExpandedReports((prev) => ({ ...prev, [id]: report }));
    } catch {
      // couldnt fetch - maybe the experiment doesnt have metrics yet
    }
    setLoadingReport(null);
  }

  // exports all reports as a JSON file that the user can download
  // in mock mode this exports the local reports, in live mode we use the backend URL
  function handleExport(experimentId?: string) {
    if (isLiveMode && experimentId) {
      // use the backend export endpoint - opens a download in a new tab
      const url = fetchExperimentExportUrl(experimentId, "json");
      window.open(url, "_blank");
      return;
    }

    // fallback: export local reports as JSON
    const json = JSON.stringify(reports, null, 2);
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);

    // create a temporary link and click it to trigger the download
    const a = document.createElement("a");
    a.href = url;
    a.download = "dsft-reports.json";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  // decide which reports to show - live summaries from the database or local mock reports
  const showLiveReports = isLiveMode && summaries.length > 0;

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold" data-testid="text-reports-title">
            Experiment Reports
          </h2>
          <p className="text-sm text-muted-foreground">
            Summaries and metrics from completed experiments
          </p>
        </div>

        {/* export button - in mock mode exports local data, in live mode its per-experiment */}
        {!showLiveReports && (
          <Button
            variant="outline"
            onClick={() => handleExport()}
            disabled={reports.length === 0}
            data-testid="button-export-reports"
          >
            <Download className="h-4 w-4 mr-2" />
            Export as JSON
          </Button>
        )}
      </div>

      {/* aggregate stats from the reports aggregator (port 8010) */}
      {isLiveMode && aggregateStats && (
        <Card data-testid="card-aggregate-stats">
          <CardHeader className="pb-3">
            <div className="flex items-center gap-2">
              <BarChart3 className="h-4 w-4 text-muted-foreground" />
              <CardTitle className="text-sm font-medium">Overall Statistics</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <div>
                <p className="text-muted-foreground text-xs">Total Experiments</p>
                <p className="text-xl font-bold">{aggregateStats.total_experiments}</p>
              </div>
              <div>
                <p className="text-muted-foreground text-xs">Completed</p>
                <p className="text-xl font-bold text-emerald-500">{aggregateStats.completed}</p>
              </div>
              <div>
                <p className="text-muted-foreground text-xs">Failed</p>
                <p className="text-xl font-bold text-red-500">{aggregateStats.failed}</p>
              </div>
              <div>
                <p className="text-muted-foreground text-xs">Avg Duration</p>
                <p className="text-xl font-bold">{Math.round(aggregateStats.avg_duration_seconds)}s</p>
              </div>
            </div>
            {/* breakdown by failure type */}
            {aggregateStats.failure_type_counts && Object.keys(aggregateStats.failure_type_counts).length > 0 && (
              <div className="mt-3 pt-3 border-t flex flex-wrap gap-2">
                {Object.entries(aggregateStats.failure_type_counts).map(([type, count]) => (
                  <Badge key={type} variant="outline" className="text-xs">
                    {getTypeLabel(type)}: {count}
                  </Badge>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* live reports from the database - clickable to expand detailed metrics */}
      {showLiveReports ? (
        <div className="grid grid-cols-1 gap-4">
          {summaries.map((summary) => {
            const detail = expandedReports[summary.id];
            const isLoading = loadingReport === summary.id;

            return (
              <Card key={summary.id} data-testid={`card-report-${summary.id}`}>
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-3">
                      <div className="p-2 rounded-md bg-primary/10">
                        {getTypeIcon(summary.type)}
                      </div>
                      <div>
                        <CardTitle className="text-sm font-medium">
                          {summary.experimentName}
                        </CardTitle>
                        <p className="text-xs text-muted-foreground">
                          Completed: {formatDate(summary.completedAt)}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant="outline">{getTypeLabel(summary.type)}</Badge>
                      <Badge variant="secondary">{summary.status}</Badge>
                      {/* download this experiment's data from the backend */}
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleExport(summary.id)}
                        data-testid={`button-export-${summary.id}`}
                      >
                        <Download className="h-4 w-4" />
                      </Button>
                      {/* expand/collapse to see detailed before/during/after metrics */}
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => toggleReport(summary.id)}
                        disabled={isLoading}
                        data-testid={`button-toggle-${summary.id}`}
                      >
                        {isLoading ? (
                          <span className="text-xs">Loading...</span>
                        ) : detail ? (
                          <ChevronUp className="h-4 w-4" />
                        ) : (
                          <ChevronDown className="h-4 w-4" />
                        )}
                      </Button>
                    </div>
                  </div>
                </CardHeader>

                {/* expanded detail view with baseline/peak/avg metrics */}
                {detail && (
                  <CardContent>
                    <div className="rounded-md border overflow-hidden">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="bg-muted/50">
                            <th className="text-left p-2 font-medium text-xs">Metric</th>
                            <th className="text-right p-2 font-medium text-xs">Baseline</th>
                            <th className="text-right p-2 font-medium text-xs">Peak</th>
                            <th className="text-right p-2 font-medium text-xs">Avg During</th>
                            <th className="text-right p-2 font-medium text-xs">Impact</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr className="border-t">
                            <td className="p-2 text-muted-foreground">CPU Usage</td>
                            <td className="p-2 text-right font-mono">{detail.baseline.cpuPercent}%</td>
                            <td className="p-2 text-right font-mono font-medium">{detail.peak.cpuPercent}%</td>
                            <td className="p-2 text-right font-mono">{detail.avgDuringTest.cpuPercent}%</td>
                            <td className="p-2 text-right">
                              <TrendIndicator before={detail.baseline.cpuPercent} during={detail.peak.cpuPercent} />
                            </td>
                          </tr>
                          <tr className="border-t">
                            <td className="p-2 text-muted-foreground">Memory</td>
                            <td className="p-2 text-right font-mono">{detail.baseline.memoryPercent}%</td>
                            <td className="p-2 text-right font-mono font-medium">{detail.peak.memoryPercent}%</td>
                            <td className="p-2 text-right font-mono">{detail.avgDuringTest.memoryPercent}%</td>
                            <td className="p-2 text-right">
                              <TrendIndicator before={detail.baseline.memoryPercent} during={detail.peak.memoryPercent} />
                            </td>
                          </tr>
                          <tr className="border-t">
                            <td className="p-2 text-muted-foreground">Latency</td>
                            <td className="p-2 text-right font-mono">{detail.baseline.latencyMs} ms</td>
                            <td className="p-2 text-right font-mono font-medium">{detail.peak.latencyMs} ms</td>
                            <td className="p-2 text-right font-mono">{detail.avgDuringTest.latencyMs} ms</td>
                            <td className="p-2 text-right">
                              <TrendIndicator before={detail.baseline.latencyMs} during={detail.peak.latencyMs} />
                            </td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </CardContent>
                )}
              </Card>
            );
          })}
        </div>
      ) : (
        // mock mode or no live data - show the local reports as before
        <>
          {reports.length === 0 ? (
            <Card>
              <CardContent className="py-12 text-center text-muted-foreground">
                <p className="text-sm">No completed experiments to report on</p>
                <p className="text-xs mt-1">
                  Run some experiments and theyll show up here when done
                </p>
              </CardContent>
            </Card>
          ) : (
            <div className="grid grid-cols-1 gap-4">
              {reports.map((report) => (
                <Card key={report.id} data-testid={`card-report-${report.id}`}>
                  <CardHeader className="pb-3">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-3">
                        <div className="p-2 rounded-md bg-primary/10">
                          {getTypeIcon(report.type)}
                        </div>
                        <div>
                          <CardTitle className="text-sm font-medium">
                            {report.experimentName}
                          </CardTitle>
                          <p className="text-xs text-muted-foreground">
                            Completed: {formatDate(report.completedAt)}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant="outline">{getTypeLabel(report.type)}</Badge>
                        <Badge variant="secondary">{report.duration}</Badge>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent>
                    {/* metrics comparison table - before / during / after */}
                    <div className="rounded-md border overflow-hidden">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="bg-muted/50">
                            <th className="text-left p-2 font-medium text-xs">Metric</th>
                            <th className="text-right p-2 font-medium text-xs">Before</th>
                            <th className="text-right p-2 font-medium text-xs">During</th>
                            <th className="text-right p-2 font-medium text-xs">After</th>
                            <th className="text-right p-2 font-medium text-xs">Impact</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr className="border-t">
                            <td className="p-2 text-muted-foreground">CPU Usage</td>
                            <td className="p-2 text-right font-mono">
                              {report.metrics.before.cpu_usage_percent}%
                            </td>
                            <td className="p-2 text-right font-mono font-medium">
                              {report.metrics.during.cpu_usage_percent}%
                            </td>
                            <td className="p-2 text-right font-mono">
                              {report.metrics.after.cpu_usage_percent}%
                            </td>
                            <td className="p-2 text-right">
                              <TrendIndicator
                                before={report.metrics.before.cpu_usage_percent}
                                during={report.metrics.during.cpu_usage_percent}
                              />
                            </td>
                          </tr>
                          <tr className="border-t">
                            <td className="p-2 text-muted-foreground">Memory</td>
                            <td className="p-2 text-right font-mono">
                              {report.metrics.before.memory_percent}%
                            </td>
                            <td className="p-2 text-right font-mono font-medium">
                              {report.metrics.during.memory_percent}%
                            </td>
                            <td className="p-2 text-right font-mono">
                              {report.metrics.after.memory_percent}%
                            </td>
                            <td className="p-2 text-right">
                              <TrendIndicator
                                before={report.metrics.before.memory_percent}
                                during={report.metrics.during.memory_percent}
                              />
                            </td>
                          </tr>
                          <tr className="border-t">
                            <td className="p-2 text-muted-foreground">Latency</td>
                            <td className="p-2 text-right font-mono">
                              {report.metrics.before.latency_ms} ms
                            </td>
                            <td className="p-2 text-right font-mono font-medium">
                              {report.metrics.during.latency_ms} ms
                            </td>
                            <td className="p-2 text-right font-mono">
                              {report.metrics.after.latency_ms} ms
                            </td>
                            <td className="p-2 text-right">
                              <TrendIndicator
                                before={report.metrics.before.latency_ms}
                                during={report.metrics.during.latency_ms}
                              />
                            </td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
