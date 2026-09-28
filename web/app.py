import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

# Directory configurations
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from pipeline import run_minecraft_pipeline
from run_pipeline import is_ollama_unreachable_error, get_ollama_diagnostic_message
GENERATED_DIR = BASE_DIR / "generated"
STATIC_DIR = Path(__file__).resolve().parent / "static"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

app = FastAPI(
    title="MinecraftAI Web Interface",
    description="User-facing interface for the Minecraft Java 1.21.11 Datapack Generator",
    version="1.21.11"
)

# CORS middleware for local frontend connectivity
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files and HTML templates
if not STATIC_DIR.exists():
    STATIC_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class GeneratePayload(BaseModel):
    request: str = Field(..., description="Natural-language Minecraft datapack request")
    minecraft_version: str = Field(default="1.21.11", description="Target Minecraft Java Edition version")


@app.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    """
    Renders the primary single-page web interface.
    """
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "version": "1.21.11",
            "pack_version": "94.1"
        }
    )


@app.get("/api/health")
async def health_check():
    """
    Health check endpoint returning system and Minecraft target version.
    """
    return {
        "status": "ok",
        "edition": "Java Edition",
        "minecraft_version": "1.21.11",
        "data_pack_version": "94.1",
        "pipeline": "ready"
    }


@app.post("/api/generate")
async def generate_datapack(payload: GeneratePayload):
    """
    Submits a natural-language request to the complete end-to-end MinecraftAI pipeline.
    """
    req_text = payload.request.strip()
    if not req_text:
        raise HTTPException(status_code=400, detail="Request text cannot be empty.")

    try:
        pipeline_result = run_minecraft_pipeline(
            request=req_text,
            minecraft_version=payload.minecraft_version,
            provider="ollama",
            create_zip=True,
            verbose=False
        )
    except Exception as e:
        if is_ollama_unreachable_error(e):
            raise HTTPException(
                status_code=503,
                detail=get_ollama_diagnostic_message()
            )
        raise HTTPException(status_code=500, detail=f"Pipeline execution encountered an unexpected error: {str(e)}")

    # Extract clean download URL and filename
    zip_filename: Optional[str] = None
    download_url: Optional[str] = None
    if pipeline_result.final_zip_path:
        zip_path = Path(pipeline_result.final_zip_path)
        zip_filename = zip_path.name
        download_url = f"/api/download/{zip_filename}"

    # Format context summary
    context_summary: Dict[str, Any] = {}
    if pipeline_result.context:
        knowledge = pipeline_result.context.get("knowledge", {})
        context_summary = {
            "loot_tables": [t.get("path") for t in knowledge.get("loot_tables", []) if isinstance(t, dict)],
            "entities": [e.get("name") for e in knowledge.get("entities", []) if isinstance(e, dict)],
            "items": [i.get("name") for i in knowledge.get("items", []) if isinstance(i, dict)]
        }

    # Format validation details
    validation_summary: Optional[Dict[str, Any]] = None
    if pipeline_result.validation:
        validation_summary = {
            "is_valid": pipeline_result.validation.is_valid,
            "errors": [e.message for e in pipeline_result.validation.errors],
            "warnings": [w.message for w in pipeline_result.validation.warnings]
        }

    # Format repair details
    repair_summary: Optional[Dict[str, Any]] = None
    if pipeline_result.repair:
        repair_summary = {
            "is_success": pipeline_result.repair.is_success,
            "total_attempts": pipeline_result.repair.total_attempts,
            "message": pipeline_result.repair.message,
            "attempts": [
                {
                    "attempt_number": att.attempt_number,
                    "validation_status": att.validation_status,
                    "reasoning": att.repair_reasoning,
                    "errors": att.errors
                }
                for att in pipeline_result.repair.attempts
            ]
        }

    return {
        "status": pipeline_result.status,
        "is_success": pipeline_result.is_success,
        "minecraft_version": pipeline_result.minecraft_version,
        "original_request": pipeline_result.original_request,
        "clarification": pipeline_result.clarification,
        "clarification_requirements": pipeline_result.clarification_requirements or [],
        "execution_summary": pipeline_result.execution_summary,
        "datapack_path": pipeline_result.final_datapack_path,
        "zip_path": pipeline_result.final_zip_path,
        "zip_filename": zip_filename,
        "download_url": download_url,
        "errors": pipeline_result.errors,
        "files_generated": pipeline_result.generation.files_generated if pipeline_result.generation else [],
        "context_summary": context_summary,
        "validation": validation_summary,
        "repair": repair_summary,
        "plan_summary": pipeline_result.plan.get("summary") if pipeline_result.plan else None
    }


@app.get("/api/download/{filename}")
async def download_datapack(filename: str):
    """
    Secure download endpoint for generated datapack ZIP archives.
    Guards against path traversal and serves only files in the generated/ directory.
    """
    # Strict filename validation: alphanumeric, underscore, hyphen, dot only
    if not re.match(r"^[a-zA-Z0-9_\-\.]+\.zip$", filename):
        raise HTTPException(status_code=400, detail="Invalid filename format. Only .zip files are downloadable.")

    target_path = (GENERATED_DIR / filename).resolve()

    # Path traversal guard: must be strictly inside GENERATED_DIR
    try:
        target_path.relative_to(GENERATED_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied: path traversal detected.")

    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=404, detail="Datapack archive not found or not yet generated.")

    return FileResponse(
        path=str(target_path),
        filename=filename,
        media_type="application/zip"
    )
