import { useQuery } from "@tanstack/react-query";
import { LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer } from "recharts";
import { useMapContext } from "../context/MapContext";
import { api } from "../api";

export function InspectPopup() {
  const { inspectPoint, setInspectPoint, pollutant } = useMapContext();

  const { data, isLoading } = useQuery({
    queryKey: ["timeseries", inspectPoint?.lat, inspectPoint?.lon, pollutant],
    queryFn: () => api.timeseries(inspectPoint!.lat, inspectPoint!.lon, pollutant),
    enabled: !!inspectPoint,
  });

  if (!inspectPoint) return null;

  return (
    <div style={{
      position: "absolute", bottom: 100, right: 16, zIndex: 20,
      background: "rgba(20,20,20,0.93)", borderRadius: 12, padding: 16,
      color: "#fff", width: 360, boxShadow: "0 4px 24px rgba(0,0,0,0.5)",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <div style={{ fontSize: 13, color: "#aaa" }}>
          {inspectPoint.lat.toFixed(3)}°N, {inspectPoint.lon.toFixed(3)}°E — <b style={{ color: "#e67e22" }}>{pollutant}</b>
        </div>
        <button
          onClick={() => setInspectPoint(null)}
          style={{ background: "none", border: "none", color: "#aaa", cursor: "pointer", fontSize: 18, lineHeight: 1 }}
        >
          ×
        </button>
      </div>

      {isLoading && <div style={{ color: "#aaa", fontSize: 13 }}>Loading time series...</div>}

      {data && data.length > 0 && (
        <ResponsiveContainer width="100%" height={160}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#333" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10, fill: "#aaa" }}
              tickFormatter={(v) => v.slice(5)}
            />
            <YAxis tick={{ fontSize: 10, fill: "#aaa" }} domain={[0, 500]} />
            <Tooltip
              contentStyle={{ background: "#111", border: "1px solid #444", fontSize: 12 }}
              formatter={(v) => [`${Number(v).toFixed(1)} AQI`, pollutant]}
            />
            <Line
              type="monotone" dataKey="value"
              stroke="#e67e22" dot={false} strokeWidth={2}
            />
          </LineChart>
        </ResponsiveContainer>
      )}

      {data && data.length === 0 && (
        <div style={{ color: "#aaa", fontSize: 12 }}>No data at this location (no CPCB station nearby)</div>
      )}
    </div>
  );
}
