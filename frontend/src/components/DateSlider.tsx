import { useMapContext } from "../context/MapContext";

const MIN_DATE = "2022-10-01";
const MAX_DATE = "2022-11-30";

export function DateSlider() {
  const { date, setDate } = useMapContext();

  return (
    <div style={{
      position: "absolute", bottom: 32, left: "50%", transform: "translateX(-50%)",
      background: "rgba(0,0,0,0.75)", borderRadius: 10, padding: "10px 20px",
      zIndex: 10, display: "flex", flexDirection: "column", alignItems: "center", gap: 6,
      minWidth: 340,
    }}>
      <div style={{ color: "#fff", fontWeight: 600, fontSize: 14 }}>
        Date: <span style={{ color: "#e67e22" }}>{date}</span>
        <span style={{ color: "#aaa", fontWeight: 400, marginLeft: 8, fontSize: 12 }}>
          (Oct–Nov 2022 stubble season)
        </span>
      </div>
      <input
        type="range"
        min={new Date(MIN_DATE).getTime()}
        max={new Date(MAX_DATE).getTime()}
        step={86400000}
        value={new Date(date).getTime()}
        onChange={(e) => {
          const d = new Date(Number(e.target.value));
          setDate(d.toISOString().slice(0, 10));
        }}
        style={{ width: "100%", accentColor: "#e67e22" }}
      />
      <div style={{ display: "flex", justifyContent: "space-between", width: "100%", color: "#aaa", fontSize: 11 }}>
        <span>Oct 1</span><span>Oct 15</span><span>Nov 1</span><span>Nov 15</span><span>Nov 30</span>
      </div>
    </div>
  );
}
