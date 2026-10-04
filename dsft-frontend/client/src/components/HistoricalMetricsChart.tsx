import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";


type HistoricalPoint = {
  time: string;
  cpu?: number;
  memory?: number;
};


type HistoryResponse = {
  range_minutes: number;
  points: HistoricalPoint[];
};


export default function HistoricalMetricsChart() {
  const [data, setData] = useState<HistoricalPoint[]>([]);
  const [minutes, setMinutes] = useState(60);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);


  useEffect(() => {
    let active = true;

    const loadMetrics = async () => {
      try {
        const response = await fetch(
          `http://127.0.0.1:8008/metrics/history?minutes=${minutes}`
        );

        if (!response.ok) {
          throw new Error(
            `Metrics API returned ${response.status}`
          );
        }

        const result: HistoryResponse =
          await response.json();

        if (active) {
          setData(result.points);
          setError(null);
        }

      } catch (err) {
        if (active) {
          setError(
            err instanceof Error
              ? err.message
              : "Unable to load historical metrics"
          );
        }

      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };


    setLoading(true);

    loadMetrics();

    const refreshInterval = window.setInterval(
      loadMetrics,
      10000
    );


    return () => {
      active = false;
      window.clearInterval(refreshInterval);
    };

  }, [minutes]);


  return (
    <section className="w-full rounded-lg border p-4">

      <div className="mb-4 flex items-center justify-between">

        <div>
          <h2 className="text-xl font-semibold">
            Historical CPU & Memory
          </h2>

          <p className="text-sm text-muted-foreground">
            CPU and memory utilization recorded over time.
          </p>
        </div>


        <select
          value={minutes}
          onChange={(event) =>
            setMinutes(Number(event.target.value))
          }
          className="rounded-md border px-3 py-2"
        >
          <option value={15}>
            Last 15 minutes
          </option>

          <option value={60}>
            Last 1 hour
          </option>

          <option value={360}>
            Last 6 hours
          </option>

          <option value={1440}>
            Last 24 hours
          </option>
        </select>

      </div>


      {loading && (
        <p className="py-10 text-center">
          Loading historical metrics...
        </p>
      )}


      {!loading && error && (
        <p className="py-10 text-center">
          Unable to load historical metrics: {error}
        </p>
      )}


      {!loading && !error && data.length === 0 && (
        <p className="py-10 text-center">
          No historical metrics are available for this period.
        </p>
      )}


      {!loading && !error && data.length > 0 && (
        <div className="h-[360px] w-full">

          <ResponsiveContainer
            width="100%"
            height="100%"
          >
            <LineChart data={data}>

              <CartesianGrid
                strokeDasharray="3 3"
              />

              <XAxis
                dataKey="time"
                minTickGap={30}
                tickFormatter={(value) =>
                  new Date(value).toLocaleTimeString(
                    [],
                    {
                      hour: "2-digit",
                      minute: "2-digit",
                    }
                  )
                }
              />

              <YAxis
                domain={[0, 100]}
                unit="%"
              />

              <Tooltip
                labelFormatter={(value) =>
                  new Date(value).toLocaleString()
                }
                formatter={(value) =>
                  `${Number(value).toFixed(1)}%`
                }
              />

              <Legend />

              <Line
                type="monotone"
                dataKey="cpu"
                name="CPU Usage"
                stroke="#2563eb"
                strokeWidth={2}
                dot={false}
                connectNulls
              />

              <Line
                type="monotone"
                dataKey="memory"
                name="Memory Usage"
                stroke="#7c3aed"
                strokeWidth={2}
                dot={false}
                connectNulls
              />

            </LineChart>
          </ResponsiveContainer>

        </div>
      )}

    </section>
  );
}