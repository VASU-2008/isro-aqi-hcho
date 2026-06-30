import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MapProvider } from "./context/MapContext";
import { Map } from "./components/Map";
import { DateSlider } from "./components/DateSlider";
import { PollutantToggle } from "./components/PollutantToggle";
import { InspectPopup } from "./components/InspectPopup";
import { Legend } from "./components/Legend";

const qc = new QueryClient({
  defaultOptions: { queries: { staleTime: 5 * 60 * 1000, retry: 1 } },
});

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <MapProvider>
        <div style={{ width: "100vw", height: "100vh", position: "relative", background: "#111" }}>
          {/* Header */}
          <div style={{
            position: "absolute", top: 0, left: 0, right: 0, zIndex: 20,
            background: "rgba(0,0,0,0.85)", padding: "8px 20px",
            display: "flex", alignItems: "center", gap: 12,
          }}>
            <div style={{ color: "#e67e22", fontWeight: 700, fontSize: 16 }}>
              ISRO AQI & HCHO
            </div>
            <div style={{ color: "#aaa", fontSize: 12 }}>
              Surface Air Quality · Hotspot Detection · India · Sentinel-5P + INSAT-3D
            </div>
          </div>

          {/* Map fills full viewport */}
          <div style={{ width: "100%", height: "100%", paddingTop: 40 }}>
            <Map />
          </div>

          {/* Controls */}
          <PollutantToggle />
          <Legend />
          <DateSlider />
          <InspectPopup />
        </div>
      </MapProvider>
    </QueryClientProvider>
  );
}
