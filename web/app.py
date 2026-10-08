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
from ai.version_registry import get_version_registry
from security import (
    DEFAULT_SECURITY_CONFIG,
    DEFAULT_RATE_LIMITER,
    SecurityHeadersMiddleware,
    InputValidationError,
    PathSecurityError,
    ArchiveSecurityError,
    validate_prompt,
    validate_version_string,
    validate_clarification_answer,
    validate_zip_download_filename,
    resolve_safe_path,
    validate_zip_archive,
    sanitize_user_error_message,
    get_safe_logger,
    mask_ip_address,
    sanitize_prompt_for_logging,
)

logger = get_safe_logger("minecraft_ai.web")

GENERATED_DIR = BASE_DIR / "generated"
STATIC_DIR = Path(__file__).resolve().parent / "static"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
LEGAL_DIR = BASE_DIR / "security" / "legal"

app = FastAPI(
    title="MinecraftAI Web Interface",
    description="Production web interface and backend for natural-language Minecraft Java datapack generation",
    version="1.21.11"
)

# Apply Security Headers Middleware
app.add_middleware(SecurityHeadersMiddleware)

# CORS middleware with explicit allowed origins
cors_origins = DEFAULT_SECURITY_CONFIG.allowed_cors_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
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
    clarification_answer: Optional[str] = Field(default=None, description="Optional answer to previous clarification inquiry")
    previous_request: Optional[str] = Field(default=None, description="Original request when answering clarification")


def _markdown_to_html(md_text: str) -> str:
    """
    Lightweight, safe markdown-to-HTML converter for rendering legal documents
    without adding external heavyweight markdown dependencies.
    """
    lines = md_text.splitlines()
    html_lines = []
    in_list = False
    in_blockquote = False

    for line in lines:
        trimmed = line.strip()

        # Close list if not a list item
        if in_list and not trimmed.startswith(("* ", "- ", "1. ", "2. ", "3. ", "4. ", "5. ")):
            html_lines.append("</ul>")
            in_list = False

        # Close blockquote if empty
        if in_blockquote and not trimmed.startswith(">"):
            html_lines.append("</blockquote>")
            in_blockquote = False

        if not trimmed:
            continue

        # Horizontal rule
        if trimmed in ("---", "***", "___"):
            html_lines.append("<hr>")
            continue

        # Headings
        if trimmed.startswith("# "):
            html_lines.append(f"<h2>{trimmed[2:]}</h2>")
        elif trimmed.startswith("## "):
            html_lines.append(f"<h2>{trimmed[3:]}</h2>")
        elif trimmed.startswith("### "):
            html_lines.append(f"<h3>{trimmed[4:]}</h3>")
        elif trimmed.startswith("#### "):
            html_lines.append(f"<h4>{trimmed[5:]}</h4>")

        # Blockquote
        elif trimmed.startswith(">"):
            b_text = trimmed[1:].strip()
            if not in_blockquote:
                html_lines.append("<blockquote>")
                in_blockquote = True
            html_lines.append(f"<p>{b_text}</p>")

        # Unordered list
        elif trimmed.startswith(("* ", "- ")):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            item_text = trimmed[2:]
            html_lines.append(f"<li>{item_text}</li>")

        # Ordered list
        elif re.match(r"^\d+\.\s+", trimmed):
            if not in_list:
                html_lines.append("<ol>")
                in_list = True
            item_text = re.sub(r"^\d+\.\s+", "", trimmed)
            html_lines.append(f"<li>{item_text}</li>")

        # Regular paragraph
        else:
            html_lines.append(f"<p>{trimmed}</p>")

    if in_list:
        html_lines.append("</ul>")
    if in_blockquote:
        html_lines.append("</blockquote>")

    result = "\n".join(html_lines)
    # Inline formatting: bold, italic, code
    result = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", result)
    result = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", result)
    result = re.sub(r"`([^`]+)`", r"<code>\1</code>", result)
    result = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', result)

    return result


@app.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    """
    Renders the primary single-page web interface.
    """
    registry = get_version_registry()
    default_meta = registry.get_default()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "version": default_meta.version_id,
            "pack_version": default_meta.data_pack_version or str(default_meta.pack_format),
            "supported_versions": registry.get_supported_versions(),
            "default_version": default_meta.version_id
        }
    )


@app.get("/api/health")
async def health_check():
    """
    Health check endpoint returning system, security, and Minecraft version status.
    """
    registry = get_version_registry()
    default_meta = registry.get_default()
    return {
        "status": "ok",
        "health": "healthy",
        "edition": "Java Edition",
        "minecraft_version": default_meta.version_id,
        "minecraft_versions": registry.get_supported_versions(),
        "data_pack_version": default_meta.data_pack_version or str(default_meta.pack_format),
        "supported_versions": registry.get_supported_versions(),
        "generator": "ready",
        "validator": "ready",
        "pipeline": "ready",
        "security": "enforced",
        "rate_limiting": "active"
    }


@app.get("/api/versions")
async def list_versions():
    """
    Returns registered, officially supported Minecraft versions and capabilities.
    """
    registry = get_version_registry()
    return {
        "supported_versions": registry.get_supported_versions(),
        "default_version": registry.get_default().version_id,
        "versions": [
            {
                "version_id": meta.version_id,
                "pack_format": meta.pack_format,
                "data_pack_version": meta.data_pack_version,
                "directory_layout": meta.directory_layout,
                "description": meta.description
            }
            for meta in [registry.get(v) for v in registry.get_supported_versions()]
        ]
    }


@app.post("/api/generate")
async def generate_datapack(payload: GeneratePayload, request: Request):
    """
    Submits a natural-language request to the complete end-to-end MinecraftAI pipeline.
    Guarded by input validation, rate limiting, and concurrency throttling.
    """
    client_ip = request.client.host if request.client else "127.0.0.1"

    # 1. Rate Limiting Check
    allowed, retry_after = DEFAULT_RATE_LIMITER.check_rate_limit(client_ip)
    if not allowed:
        logger.warning("Rate limit exceeded for client: %s", mask_ip_address(client_ip))
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Please wait {retry_after} second(s) before submitting another request.",
            headers={"Retry-After": str(retry_after or 60)}
        )

    # 2. Input Security Validation
    try:
        raw_req = payload.request
        req_text = validate_prompt(raw_req)

        # Handle clarification refinement if provided
        if payload.clarification_answer:
            ans_clean = validate_clarification_answer(payload.clarification_answer)
            base_req = validate_prompt(payload.previous_request or req_text)
            req_text = f"{base_req} Specifically: {ans_clean}."

        registry = get_version_registry()
        target_ver = validate_version_string(
            payload.minecraft_version,
            set(registry.get_supported_versions())
        )
    except InputValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 3. Concurrency Slot Acquisition
    slot_acquired = DEFAULT_RATE_LIMITER.acquire_generation_slot(timeout_s=2.0)
    if not slot_acquired:
        raise HTTPException(
            status_code=503,
            detail="Server is currently busy processing concurrent generation requests. Please try again in a few moments."
        )

    # 4. Pipeline Execution
    logger.info(
        "Initiating pipeline for version %s. Prompt: %s",
        target_ver,
        sanitize_prompt_for_logging(req_text)
    )

    try:
        pipeline_result = run_minecraft_pipeline(
            request=req_text,
            minecraft_version=target_ver,
            provider=os.getenv("LLM_PROVIDER", "ollama"),
            create_zip=True,
            verbose=False
        )
    except Exception as e:
        if is_ollama_unreachable_error(e):
            raise HTTPException(
                status_code=503,
                detail=get_ollama_diagnostic_message()
            )
        sanitized_msg = sanitize_user_error_message(e)
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline execution encountered an unexpected error: {sanitized_msg}"
        )
    finally:
        DEFAULT_RATE_LIMITER.release_generation_slot()

    # 5. Extract download URL and filename with archive security validation
    zip_filename: Optional[str] = None
    download_url: Optional[str] = None
    if pipeline_result.final_zip_path:
        zip_path = Path(pipeline_result.final_zip_path)
        try:
            # Verify the generated archive structure before offering download
            validate_zip_archive(zip_path)
            zip_filename = zip_path.name
            download_url = f"/api/download/{zip_filename}"
        except ArchiveSecurityError as e:
            logger.error("Generated archive failed security verification: %s", str(e))
            zip_filename = None
            download_url = None

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
    Guards against path traversal, validates filename format, and inspects archive contents.
    """
    # 1. Filename validation
    try:
        clean_filename = validate_zip_download_filename(filename)
    except PathSecurityError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 2. Path sandboxing
    try:
        target_path = resolve_safe_path(clean_filename, GENERATED_DIR)
    except PathSecurityError as e:
        raise HTTPException(status_code=403, detail=str(e))

    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=404, detail="Datapack archive not found or expired.")

    # 3. Archive security inspection before serving
    try:
        validate_zip_archive(target_path)
    except ArchiveSecurityError as e:
        logger.error("Download blocked: archive '%s' failed validation: %s", clean_filename, str(e))
        raise HTTPException(status_code=400, detail="Requested archive failed integrity verification.")

    return FileResponse(
        path=str(target_path),
        filename=clean_filename,
        media_type="application/zip"
    )


# =========================================================================
# Legal & Policy Routes
# =========================================================================

@app.get("/privacy", response_class=HTMLResponse)
async def privacy_page(request: Request):
    """Renders the Privacy Policy page."""
    policy_path = LEGAL_DIR / "privacy_policy.md"
    content_md = policy_path.read_text(encoding="utf-8") if policy_path.exists() else "# Privacy Policy\nContent unavailable."
    content_html = _markdown_to_html(content_md)
    return templates.TemplateResponse(
        request=request,
        name="legal.html",
        context={
            "title": "Privacy Policy",
            "description": "MinecraftAI Privacy Policy and data processing practices.",
            "content": content_html
        }
    )


@app.get("/terms", response_class=HTMLResponse)
async def terms_page(request: Request):
    """Renders the Terms of Service page."""
    terms_path = LEGAL_DIR / "terms_of_service.md"
    content_md = terms_path.read_text(encoding="utf-8") if terms_path.exists() else "# Terms of Service\nContent unavailable."
    content_html = _markdown_to_html(content_md)
    return templates.TemplateResponse(
        request=request,
        name="legal.html",
        context={
            "title": "Terms of Service",
            "description": "MinecraftAI Terms of Service and acceptable use policy.",
            "content": content_html
        }
    )


@app.get("/security", response_class=HTMLResponse)
async def security_page(request: Request):
    """Renders the Security Policy page."""
    sec_path = LEGAL_DIR / "security_policy.md"
    content_md = sec_path.read_text(encoding="utf-8") if sec_path.exists() else "# Security Policy\nContent unavailable."
    content_html = _markdown_to_html(content_md)
    return templates.TemplateResponse(
        request=request,
        name="legal.html",
        context={
            "title": "Security Policy",
            "description": "MinecraftAI Security Policy and responsible vulnerability disclosure.",
            "content": content_html
        }
    )


@app.get("/api/legal/{doc_name}")
async def get_legal_document(doc_name: str):
    """
    Returns legal document content as JSON for API clients.
    """
    valid_docs = {
        "privacy": LEGAL_DIR / "privacy_policy.md",
        "privacy_policy": LEGAL_DIR / "privacy_policy.md",
        "terms": LEGAL_DIR / "terms_of_service.md",
        "terms_of_service": LEGAL_DIR / "terms_of_service.md",
        "security": LEGAL_DIR / "security_policy.md",
        "security_policy": LEGAL_DIR / "security_policy.md",
    }
    if doc_name not in valid_docs:
        raise HTTPException(status_code=404, detail="Requested legal document not found.")

    doc_file = valid_docs[doc_name]
    if not doc_file.exists():
        raise HTTPException(status_code=404, detail="Document content file missing.")

    text_content = doc_file.read_text(encoding="utf-8")
    return {
        "document": doc_name,
        "content": text_content,
        "content_markdown": text_content
    }
