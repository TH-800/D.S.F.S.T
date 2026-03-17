// Reports.tsx - shows summaries of completed experiments
// each report card has before/during/after metrics so you can see the impact
// theres also a button to export reports as JSON for further analysis

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Download, Cpu, Wifi, AlertTriangle, TrendingUp, TrendingDown, Minus } from "lucide-react";
import { useAppState } from "@/lib/store";

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
  const { reports } = useAppState();

  // exports all reports as a JSON file that the user can download
  function handleExport() {
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

        {/* export button */}
        <Button
          variant="outline"
          onClick={handleExport}
          disabled={reports.length === 0}
          data-testid="button-export-reports"
        >
          <Download className="h-4 w-4 mr-2" />
          Export as JSON
        </Button>
      </div>

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
    </div>
  );
}
