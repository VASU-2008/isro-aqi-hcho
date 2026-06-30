import { createContext, useContext, useState, ReactNode } from "react";

interface MapState {
  date: string;
  setDate: (d: string) => void;
  pollutant: string;
  setPollutant: (p: string) => void;
  inspectPoint: { lat: number; lon: number } | null;
  setInspectPoint: (pt: { lat: number; lon: number } | null) => void;
}

const MapContext = createContext<MapState | null>(null);

export function MapProvider({ children }: { children: ReactNode }) {
  const [date, setDate]               = useState("2022-10-20");
  const [pollutant, setPollutant]     = useState("PM2.5");
  const [inspectPoint, setInspectPoint] = useState<{ lat: number; lon: number } | null>(null);

  return (
    <MapContext.Provider value={{ date, setDate, pollutant, setPollutant, inspectPoint, setInspectPoint }}>
      {children}
    </MapContext.Provider>
  );
}

export function useMapContext() {
  const ctx = useContext(MapContext);
  if (!ctx) throw new Error("useMapContext must be used inside MapProvider");
  return ctx;
}
