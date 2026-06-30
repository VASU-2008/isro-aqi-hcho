import { useRef, useEffect, useCallback } from "react";
import { Map as MapLibre, MapMouseEvent, Popup } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useQuery } from "@tanstack/react-query";
import { useMapContext } from "../context/MapContext";
import { api } from "../api";

export function Map() {
  const mapRef   = useRef<HTMLDivElement>(null);
  const mgl      = useRef<MapLibre | null>(null);
  const { date, pollutant, setInspectPoint } = useMapContext();

  const { data: aqiData }     = useQuery({ queryKey: ["aqi", date], queryFn: () => api.aqi(date) });
  const { data: hotspotData } = useQuery({ queryKey: ["hotspots", date], queryFn: () => api.hotspots(date) });
  const { data: stationData } = useQuery({ queryKey: ["stations"], queryFn: () => api.stations(), staleTime: Infinity });

  // Initialize map
  useEffect(() => {
    if (!mapRef.current || mgl.current) return;
    mgl.current = new MapLibre({
      container: mapRef.current,
      style: "https://tiles.openfreemap.org/styles/liberty",
      center: [82, 22],  // India center
      zoom: 4.2,
    });

    mgl.current.on("load", () => {
      const map = mgl.current!;

      // AQI heatmap source + layer
      map.addSource("aqi", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({
        id: "aqi-heat",
        type: "heatmap",
        source: "aqi",
        paint: {
          "heatmap-weight":    ["interpolate", ["linear"], ["get", "aqi"], 0, 0, 500, 1],
          "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 4, 0.6, 8, 2],
          "heatmap-radius":    ["interpolate", ["linear"], ["zoom"], 4, 8,  8, 20],
          "heatmap-color": [
            "interpolate", ["linear"], ["heatmap-density"],
            0,   "rgba(0,0,0,0)",
            0.1, "rgba(0,228,0,0.6)",
            0.3, "rgba(255,255,0,0.7)",
            0.5, "rgba(255,126,0,0.8)",
            0.7, "rgba(255,0,0,0.9)",
            1.0, "rgba(126,0,35,1)",
          ],
          "heatmap-opacity": 0.8,
        },
      });

      // HCHO hotspot polygons
      map.addSource("hotspots", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({
        id: "hotspot-fill",
        type: "fill",
        source: "hotspots",
        paint: {
          "fill-color": "rgba(200,0,200,0.25)",
          "fill-outline-color": "rgba(200,0,200,0.9)",
        },
      });
      map.addLayer({
        id: "hotspot-border",
        type: "line",
        source: "hotspots",
        paint: { "line-color": "#c800c8", "line-width": 2 },
      });

      // CPCB stations
      map.addSource("stations", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({
        id: "station-dots",
        type: "circle",
        source: "stations",
        paint: {
          "circle-radius": 5,
          "circle-color": "#00bcd4",
          "circle-stroke-width": 1.5,
          "circle-stroke-color": "#fff",
        },
      });

      // Click to inspect AQI point
      map.on("click", "aqi-heat", (e: MapMouseEvent) => {
        const { lat, lng } = e.lngLat;
        setInspectPoint({ lat, lon: lng });
      });

      // Hotspot popup
      map.on("click", "hotspot-fill", (e: MapMouseEvent & { features?: any[] }) => {
        const props = e.features?.[0]?.properties ?? {};
        new Popup()
          .setLngLat(e.lngLat)
          .setHTML(`
            <div style="font-size:13px">
              <b>HCHO Hotspot</b><br/>
              Date: ${props.date}<br/>
              Gi* z-score: ${Number(props.mean_z).toFixed(2)}<br/>
              Mean HCHO: ${Number(props.mean_hcho).toExponential(3)} mol/m²<br/>
              Cluster cells: ${props.n_cells}
            </div>
          `)
          .addTo(map);
      });

      map.on("mouseenter", "hotspot-fill",  () => { map.getCanvas().style.cursor = "pointer"; });
      map.on("mouseleave", "hotspot-fill",  () => { map.getCanvas().style.cursor = ""; });
      map.on("mouseenter", "aqi-heat",      () => { map.getCanvas().style.cursor = "crosshair"; });
      map.on("mouseleave", "aqi-heat",      () => { map.getCanvas().style.cursor = ""; });
    });

    return () => { mgl.current?.remove(); mgl.current = null; };
  }, []);  // eslint-disable-line

  // Update AQI layer data
  useEffect(() => {
    const map = mgl.current;
    if (!map || !map.isStyleLoaded()) return;
    const src = map.getSource("aqi") as maplibregl.GeoJSONSource | undefined;
    src?.setData(aqiData ?? { type: "FeatureCollection", features: [] });
  }, [aqiData]);

  // Update hotspot layer
  useEffect(() => {
    const map = mgl.current;
    if (!map || !map.isStyleLoaded()) return;
    const src = map.getSource("hotspots") as maplibregl.GeoJSONSource | undefined;
    src?.setData(hotspotData ?? { type: "FeatureCollection", features: [] });
  }, [hotspotData]);

  // Update station dots
  useEffect(() => {
    const map = mgl.current;
    if (!map || !map.isStyleLoaded()) return;
    const src = map.getSource("stations") as maplibregl.GeoJSONSource | undefined;
    src?.setData(stationData ?? { type: "FeatureCollection", features: [] });
  }, [stationData]);

  return <div ref={mapRef} style={{ width: "100%", height: "100%" }} />;
}
