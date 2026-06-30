FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gdal-bin libgdal-dev gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Lay out baked serving data where the app expects it (data/ relative to CWD)
RUN mkdir -p data/processed data/serving \
    && cp -r seed/processed/aqi_predictions.zarr data/processed/ \
    && cp seed/serving/hotspot_polygons.geojson data/serving/ \
    && cp seed/serving/fire_hcho_correlation.json data/serving/

EXPOSE 8000

# Seed the database (idempotent) then start the API
CMD ["sh", "-c", "python seed_db.py && uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"]
