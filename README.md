# RenderCV service

FastAPI app that runs the RenderCV CLI to generate PDFs. Used by the Node backend (set `RENDERCV_SERVICE_URL` to this service’s URL).

**Requires:** Python 3.10+, LaTeX (for RenderCV). Not suitable for Vercel or AWS Lambda; deploy on **Render**, **Railway**, **Fly.io**, or **Cloud Run** (container or native Python).

### Where to deploy (important)

- **Do not use:** AWS Lambda, Vercel serverless, or any environment where the running process uses a different Python (e.g. `/var/lang/bin/python`) that doesn’t have your `pip install` packages. You will get “No module named rendercv”.
- **Use instead:**
  - **Render:** Web Service, Root Directory = `rendercv-service`, Build = `pip install -r requirements.txt`, Start = `uvicorn main:app --host 0.0.0.0 --port $PORT`. Same Python runs build and start.
  - **Docker (Render/Railway/Fly/Cloud Run):** Use the included **Dockerfile** in this folder. Build and run the image; it installs LaTeX and Python deps so `rendercv` runs in the same process. On Render: New → Web Service → connect repo, Root Directory = `rendercv-service`, set to **Docker** and use the Dockerfile.
  - **Railway / Fly.io:** Native Python or Docker; ensure the start command uses the same environment where `pip install -r requirements.txt` ran.

### Scaling for many users (~100 concurrent)

The **NestJS backend** (Vercel) scales with traffic; the limit is the **RenderCV service**. One instance handles one PDF at a time (LaTeX is CPU-bound), so 100 concurrent requests will queue and latency grows.

**Improve RenderCV throughput:**

1. **Multiple Uvicorn workers (one machine)**  
   Run more than one process so one instance can handle several PDFs in parallel (each worker runs one `rendercv` at a time):
   ```bash
   uvicorn main:app --host 0.0.0.0 --port $PORT --workers 4
   ```
   Use `--workers` ≤ CPU cores. Too many workers on a small instance can slow everything down.

2. **Horizontal scaling (recommended for ~100 users)**  
   Run **multiple instances** of the RenderCV service behind a **load balancer**; the backend calls the load balancer URL.
   - **Render:** In the Web Service, set **Instance count** to 2–5+ (or use a paid plan and scale). Render’s load balancer shares traffic across instances.
   - **Google Cloud Run:** Set **min instances** / **max instances** and **request concurrency**; Cloud Run scales instances automatically.
   - **Railway / Fly.io:** Scale replicas in the dashboard; put a load balancer (or platform default) in front.

3. **Single entry URL**  
   Keep **one** `RENDERCV_SERVICE_URL` in the backend (the load balancer or first instance). Do not round‑robin from the backend; let the platform’s load balancer distribute traffic across instances.

4. **Optional: queue + workers**  
   For very high load, you can accept requests immediately, push a job to a queue (e.g. Redis, SQS), and have a pool of workers generate PDFs and store/return them. That requires API and client changes (e.g. async job ID + polling). For ~100 users, scaling instances + workers is usually enough.

### Local run

```bash
cd rendercv-service
pip install -r requirements.txt
uvicorn main:app --reload --port 9000
```

Default URL: `http://localhost:9000`. The Node backend uses `RENDERCV_SERVICE_URL=http://localhost:9000` for local dev.
