# RenderCV service

FastAPI app that runs the RenderCV CLI to generate PDFs. Used by the Node backend (set `RENDERCV_SERVICE_URL` to this service’s URL).

**Requires:** Python 3.10+, LaTeX (for RenderCV). Not suitable for Vercel; deploy on Render, Railway, Fly.io, or similar.

### Local run

```bash
cd rendercv-service
pip install -r requirements.txt
uvicorn main:app --reload --port 9000
```

Default URL: `http://localhost:9000`. The Node backend uses `RENDERCV_SERVICE_URL=http://localhost:9000` for local dev.
