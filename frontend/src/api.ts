const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const KEY  = import.meta.env.VITE_API_KEY ?? "";

const headers: HeadersInit = KEY ? { "X-API-Key": KEY } : {};

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { headers });
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`);
  return res.json() as Promise<T>;
}

export const api = {
  aqi:        (date: string)                          => get<GeoJSON.FeatureCollection>(`/aqi?date=${date}`),
  hotspots:   (date: string)                          => get<GeoJSON.FeatureCollection>(`/hcho/hotspots?date=${date}`),
  timeseries: (lat: number, lon: number, pol: string) => get<{date: string; value: number}[]>(`/timeseries?lat=${lat}&lon=${lon}&pollutant=${pol}`),
  correlation:(region?: string)                       => get<Record<string, unknown>>(`/hcho/correlation${region ? `?region=${region}` : ""}`),
  stations:   ()                                      => get<GeoJSON.FeatureCollection>(`/stations`),
  tileUrl:    (date: string, layer = "aqi") =>
    `${BASE}/tiles/{z}/{x}/{y}.png?date=${date}&layer=${layer}&${KEY ? `key=${KEY}` : ""}`,
};
