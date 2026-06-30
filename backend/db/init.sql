-- PostGIS schema initialization
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS stations (
    id           SERIAL PRIMARY KEY,
    station_name VARCHAR(200) NOT NULL,
    state        VARCHAR(100),
    city         VARCHAR(100),
    lat          DOUBLE PRECISION NOT NULL,
    lon          DOUBLE PRECISION NOT NULL,
    geom         GEOMETRY(Point, 4326)
);

CREATE INDEX IF NOT EXISTS stations_geom_idx ON stations USING GIST (geom);

CREATE TABLE IF NOT EXISTS hotspot_polygons (
    id           SERIAL PRIMARY KEY,
    date         DATE NOT NULL,
    cluster_id   INTEGER NOT NULL,
    n_cells      INTEGER,
    mean_z       DOUBLE PRECISION,
    max_z        DOUBLE PRECISION,
    mean_hcho    DOUBLE PRECISION,
    centroid_lat DOUBLE PRECISION,
    centroid_lon DOUBLE PRECISION,
    geom         GEOMETRY(Geometry, 4326)
);

CREATE INDEX IF NOT EXISTS hotspot_date_idx ON hotspot_polygons (date);
CREATE INDEX IF NOT EXISTS hotspot_geom_idx ON hotspot_polygons USING GIST (geom);

CREATE TABLE IF NOT EXISTS source_regions (
    id     SERIAL PRIMARY KEY,
    name   VARCHAR(100) NOT NULL,
    label  VARCHAR(200),
    geom   GEOMETRY(Polygon, 4326)
);

INSERT INTO source_regions (name, label, geom) VALUES
  ('Punjab_Haryana', 'Punjab/Haryana stubble burning',
   ST_MakeEnvelope(73.0, 28.0, 77.5, 32.0, 4326)),
  ('UP', 'Uttar Pradesh',
   ST_MakeEnvelope(77.5, 24.0, 84.0, 28.5, 4326)),
  ('Delhi_NCR', 'Delhi NCR (receptor)',
   ST_MakeEnvelope(76.8, 28.3, 77.5, 29.0, 4326))
ON CONFLICT DO NOTHING;
