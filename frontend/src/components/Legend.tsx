export function Legend() {
  const bands = [
    { label: "Good",       color: "#00e400", range: "0–50" },
    { label: "Satisfactory",color: "#92d050", range: "51–100" },
    { label: "Moderate",   color: "#ffff00", range: "101–200" },
    { label: "Poor",       color: "#ff7e00", range: "201–300" },
    { label: "Very Poor",  color: "#ff0000", range: "301–400" },
    { label: "Severe",     color: "#7e0023", range: "401–500" },
  ];

  return (
    <div style={{
      position: "absolute", top: 60, right: 16, zIndex: 10,
      background: "rgba(0,0,0,0.8)", borderRadius: 8, padding: "10px 14px",
      color: "#fff", fontSize: 12,
    }}>
      <div style={{ fontWeight: 600, marginBottom: 6 }}>AQI (CPCB)</div>
      {bands.map((b) => (
        <div key={b.label} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
          <div style={{ width: 16, height: 16, borderRadius: 3, background: b.color }} />
          <span>{b.range}</span>
          <span style={{ color: "#aaa" }}>{b.label}</span>
        </div>
      ))}
      <div style={{ borderTop: "1px solid #444", marginTop: 8, paddingTop: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{ width: 16, height: 3, background: "#c800c8" }} />
          <span>HCHO hotspot</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 4 }}>
          <div style={{ width: 10, height: 10, borderRadius: "50%", background: "#00bcd4" }} />
          <span>CPCB station</span>
        </div>
      </div>
    </div>
  );
}
