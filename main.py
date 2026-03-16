import os
import pathlib
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional

import phonenumbers
import yaml
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel


def _is_valid_phone(value: str) -> bool:
    """Return True if value is a valid phone number (RenderCV accepts it)."""
    if not value or not isinstance(value, str):
        return False
    s = value.strip()
    if not s:
        return False
    try:
        parsed = phonenumbers.parse(s, None)
        return phonenumbers.is_valid_number(parsed)
    except phonenumbers.NumberParseException:
        return False


def _sanitize_cv_phone(data: Dict[str, Any]) -> None:
    """
    Remove or fix cv.phone so RenderCV does not reject the document.
    RenderCV validates phone with pydantic_phone_numbers; invalid numbers (e.g. +1234567890) cause 500.
    Modifies data in place.
    """
    cv = data.get("cv")
    if not cv or not isinstance(cv, dict):
        return
    raw = cv.get("phone")
    if raw is None:
        return
    # RenderCV accepts string or list of strings.
    if isinstance(raw, str):
        if _is_valid_phone(raw):
            return
        del cv["phone"]
        return
    if isinstance(raw, list):
        valid: List[str] = []
        for item in raw:
            if isinstance(item, str) and _is_valid_phone(item):
                valid.append(item.strip())
        if valid:
            cv["phone"] = valid if len(valid) != 1 else valid[0]
        else:
            del cv["phone"]
        return
    del cv["phone"]


class RenderCvDocument(BaseModel):
    cv: Dict[str, Any]
    design: Optional[Dict[str, Any]] = None
    locale: Optional[Dict[str, Any]] = None
    settings: Optional[Dict[str, Any]] = None


class RawYamlPayload(BaseModel):
    yaml: str


app = FastAPI(title="RenderCV bridge", version="1.0.0")


def _check_rendercv_available() -> None:
    """Fail fast if rendercv is not importable (e.g. Lambda/serverless wrong runtime)."""
    try:
        import rendercv  # noqa: F401
    except ImportError as e:
        raise RuntimeError(
            f"rendercv is not installed in this Python ({sys.executable}). "
            "This service must run where dependencies are installed (e.g. Docker or Render native Python). "
            "Do not deploy to AWS Lambda or Vercel serverless; use a container or native web service (Render, Railway, Fly.io, Cloud Run)."
        ) from e


@app.on_event("startup")
def startup() -> None:
    _check_rendercv_available()


@app.get("/")
def root() -> dict:
    """Health check; confirms this is the RenderCV service and it accepts POST /rendercv/pdf."""
    return {"service": "RenderCV bridge", "endpoints": ["POST /rendercv/pdf", "POST /rendercv/yaml/pdf"]}


@app.post("/rendercv/pdf", response_class=Response)
@app.post("/rendercv/pdf/", response_class=Response)  # allow trailing slash (some proxies send it)
def rendercv_pdf(doc: RenderCvDocument) -> Response:
    """
    Accepts a RenderCV document (as JSON matching the YAML structure),
    writes it to a temporary YAML file, runs `rendercv render`, and
    returns the generated PDF bytes.
    """
    try:
        with tempfile.TemporaryDirectory() as tmpdir_str:
            tmpdir = pathlib.Path(tmpdir_str)
            input_path = tmpdir / "cv.yaml"
            pdf_path = tmpdir / "cv.pdf"

            data = doc.model_dump()
            # Drop None-valued top-level keys to keep YAML clean.
            data = {k: v for k, v in data.items() if v is not None}

            input_path.write_text(
                yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )

            # Use same Python as this process so rendercv is found in deployment (no 'rendercv' on PATH)
            cmd = [
                sys.executable,
                "-m",
                "rendercv",
                "render",
                str(input_path),
                "--pdf-path",
                pdf_path.name,
                "--dont-generate-markdown",
                "--dont-generate-html",
                "--dont-generate-png",
            ]

            proc = subprocess.run(
                cmd,
                cwd=tmpdir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )

            if not pdf_path.exists():
                detail = "RenderCV failed to generate PDF."
                if proc.stdout:
                    print("RenderCV stdout:", proc.stdout.strip())
                    detail += f" stdout: {proc.stdout.strip()}"
                if proc.stderr:
                    print("RenderCV stderr:", proc.stderr.strip())
                    detail += f" stderr: {proc.stderr.strip()}"
                raise HTTPException(status_code=500, detail=detail)

            pdf_bytes = pdf_path.read_bytes()
            return Response(content=pdf_bytes, media_type="application/pdf")
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=f"RenderCV service error: {exc}") from exc


@app.post("/rendercv/yaml/pdf", response_class=Response)
@app.post("/rendercv/yaml/pdf/", response_class=Response)  # allow trailing slash
def rendercv_yaml_pdf(payload: RawYamlPayload) -> Response:
    """
    Accept a raw RenderCV YAML document, render it, and return the PDF bytes.
    This lets the frontend provide an advanced YAML editor without the backend
    needing to understand the full schema.
    """
    try:
      yaml_text = payload.yaml
      if not yaml_text or not yaml_text.strip():
          raise HTTPException(status_code=400, detail="YAML content is required.")

      # Parse and sanitize phone so RenderCV does not 500 on invalid numbers (e.g. +1234567890).
      try:
          data = yaml.safe_load(yaml_text)
      except yaml.YAMLError as e:
          raise HTTPException(status_code=400, detail=f"Invalid YAML: {e}") from e
      if isinstance(data, dict):
          _sanitize_cv_phone(data)
          yaml_text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)

      with tempfile.TemporaryDirectory() as tmpdir_str:
          tmpdir = pathlib.Path(tmpdir_str)
          input_path = tmpdir / "cv.yaml"
          pdf_path = tmpdir / "cv.pdf"

          input_path.write_text(yaml_text, encoding="utf-8")

          cmd = [
              sys.executable,
              "-m",
              "rendercv",
              "render",
              str(input_path),
              "--pdf-path",
              pdf_path.name,
              "--dont-generate-markdown",
              "--dont-generate-html",
              "--dont-generate-png",
          ]

          proc = subprocess.run(
              cmd,
              cwd=tmpdir,
              stdout=subprocess.PIPE,
              stderr=subprocess.PIPE,
              text=True,
              encoding="utf-8",
              errors="replace",
              env={**os.environ, "PYTHONIOENCODING": "utf-8"},
          )

          if not pdf_path.exists():
              detail = "RenderCV failed to generate PDF."
              if proc.stdout:
                  print("RenderCV stdout:", proc.stdout.strip())
                  detail += f" stdout: {proc.stdout.strip()}"
              if proc.stderr:
                  print("RenderCV stderr:", proc.stderr.strip())
                  detail += f" stderr: {proc.stderr.strip()}"
              raise HTTPException(status_code=500, detail=detail)

          pdf_bytes = pdf_path.read_bytes()
          return Response(content=pdf_bytes, media_type="application/pdf")
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=f"RenderCV YAML service error: {exc}") from exc
