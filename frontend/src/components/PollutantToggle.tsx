import { useMapContext } from "../context/MapContext";

const POLLUTANTS = ["PM2.5", "NO2", "SO2", "CO", "O3", "HCHO"];

export function PollutantToggle() {
  const { pollutant, setPollutant } = useMapContext();

  return (
    <div style={{
      position: "absolute", top: 12, left: "50%", transform: "translateX(-50%)",
      display: "flex", gap: 6, background: "rgba(0,0,0,0.75)", borderRadius: 8,
      padding: "6px 10px", zIndex: 10,
    }}>
      {POLLUTANTS.map((p) => (
        <button
          key={p}
          onClick={() => setPollutant(p)}
          style={{
            padding: "4px 12px", borderRadius: 5, border: "none", cursor: "pointer",
            fontWeight: pollutant === p ? 700 : 400,
            background: pollutant === p ? "#e67e22" : "#555",
            color: "#fff", fontSize: 13,
          }}
        >
          {p}
        </button>
      ))}
    </div>
  );
}
