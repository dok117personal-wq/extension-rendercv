# RenderCV bridge: FastAPI + RenderCV CLI + LaTeX. Use this image on Render (Docker), Railway, Fly, or Cloud Run.
# Do NOT use AWS Lambda or Vercel serverless — they use a different Python without these deps.

FROM python:3.12-slim-bookworm

# Install LaTeX (required by RenderCV for PDF output). Keep image smaller with --no-install-recommends.
RUN apt-get update && apt-get install -y --no-install-recommends \
    texlive-base \
    texlive-latex-extra \
    texlive-fonts-recommended \
    fontconfig \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .

# Render/Railway/Fly set PORT; default for local.
# Set UVICORN_WORKERS=4 (or similar) to handle more concurrent PDFs per instance.
ENV PORT=9000
ENV UVICORN_WORKERS=1
EXPOSE ${PORT}
CMD sh -c 'uvicorn main:app --host 0.0.0.0 --port ${PORT} --workers ${UVICORN_WORKERS}'
