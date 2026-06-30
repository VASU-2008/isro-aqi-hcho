# Deployment Guide — ISRO AQI & HCHO System

Backend → **Railway** (FastAPI + Postgres/PostGIS + Redis). Frontend → **Vercel** (React/Vite).
Precomputed serving data (~28 MB) is baked into the backend image under `backend/seed/`.

## 1. Push to GitHub
```bash
gh auth login          # one-time
gh repo create isro-aqi-hcho --public --source=. --remote=origin --push
```

## 2. Backend on Railway (dashboard import)
1. https://railway.app → **New Project → Deploy from GitHub repo** → pick `isro-aqi-hcho`.
2. **Root directory**: `backend`  (Settings → Root Directory). Railway auto-detects the Dockerfile.
3. Add **PostgreSQL** plugin (New → Database → PostgreSQL) — it ships with PostGIS.
4. Add **Redis** plugin (New → Database → Redis).
5. Backend service **Variables**:
   - `DATABASE_URL` → reference the Postgres plugin's `DATABASE_URL`
   - `REDIS_URL` → reference the Redis plugin's `REDIS_URL`
   - `API_KEY` → a strong secret (used by the frontend)
   - `CORS_ORIGINS` → `https://<your-vercel-app>.vercel.app` (fill after step 3)
6. Deploy. On boot the container runs `seed_db.py` (loads 50 stations + 3002 hotspots into PostGIS), then uvicorn.
7. Copy the public URL, e.g. `https://isro-api.up.railway.app`. Check `/health` returns `{"status":"ok","db":true}`.

## 3. Frontend on Vercel (dashboard import)
1. https://vercel.com → **Add New → Project** → import `isro-aqi-hcho`.
2. **Root Directory**: `frontend`. Framework preset: **Vite**.
3. **Environment Variables**:
   - `VITE_API_BASE_URL` → the Railway backend URL from step 2.7
   - `VITE_API_KEY` → the same `API_KEY` value set on Railway
4. Deploy. Vercel builds `npm run build` and serves `dist/`.
5. Copy the Vercel URL and add it to Railway's `CORS_ORIGINS` (step 2.5), then redeploy the backend.

## 4. Verify live
- `curl https://<railway-url>/health` → `{"status":"ok","zarr":true,"db":true}`
- Open the Vercel URL → India map with AQI heatmap, hotspots, date slider.

## Notes
- The 283 MB raw `aqi_cube.zarr` is **not** shipped; the `hcho` raster-tile layer is the only feature that used it and the frontend defaults to the `aqi` layer (predictions, baked).
- To refresh data: rerun the local ETL + `predict`, re-copy outputs into `backend/seed/`, commit, push — Railway redeploys.
- Real ground data: set `OPENAQ_API_KEY` and run the ETL on a window within the last 90 days (OpenAQ history limit).
