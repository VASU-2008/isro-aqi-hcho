/// <reference types="vite/client" />

declare module "*.css" {
  const content: string;
  export default content;
}

declare module "maplibre-gl/dist/maplibre-gl.css" {
  const content: string;
  export default content;
}

// GeoJSON types (subset used by the app)
declare namespace GeoJSON {
  interface FeatureCollection {
    type: "FeatureCollection";
    features: Feature[];
  }
  interface Feature {
    type: "Feature";
    geometry: Geometry;
    properties: Record<string, unknown> | null;
  }
  type Geometry = { type: string; coordinates: unknown };
}
