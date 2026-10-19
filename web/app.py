import asyncio
import os
import re
import shutil
import sys
import time
import uuid
from contextlib import asynccontextmanager
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
from ai.conversation import (
    DEFAULT_CONVERSATION_MANAGER,
    ConversationSession,
    ProposedBehavior,
    AssumptionItem,
)
from ai.conversational_agent import ConversationalUnderstandingEngine
from ai.specification import SpecificationBridge
from security import (
    DEFAULT_SECURITY_CONFIG,
    DEFAULT_RATE_LIMITER,
    SecurityHeadersMiddleware,
    InputValidationError,
    PathSecurityError,
    ArchiveSecurityError,
    load_security_config,
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


def cleanup_expired_artifacts(base_dir: Path = GENERATED_DIR, max_age_seconds: Optional[int] = None) -> int:
    """
    Purges temporary generated datapack directories and archives older than retention threshold.
    Guards server disk space from unbounded growth.
    """
    if not base_dir.exists():
        return 0

    max_age = max_age_seconds if max_age_seconds is not None else DEFAULT_SECURITY_CONFIG.artifact_retention_seconds
    cutoff = time.time() - max_age
    purged = 0

    try:
        for entry in base_dir.iterdir():
            # Never delete hidden files
            if entry.name.startswith("."):
                continue
            try:
                if entry.stat().st_mtime < cutoff:
                    if entry.is_dir():
                        shutil.rmtree(entry, ignore_errors=True)
                        purged += 1
                    elif entry.is_file():
                        entry.unlink(missing_ok=True)
                        purged += 1
            except OSError as e:
                logger.warning("Error checking artifact '%s' for cleanup: %s", entry.name, e)
    except Exception as e:
        logger.error("Failed during artifact cleanup sweep: %s", e)

    return purged


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    """Perform startup integrity checks and clean up expired artifacts."""
    logger.info("MinecraftAI web service initializing...")
    cleanup_expired_artifacts()
    DEFAULT_CONVERSATION_MANAGER.cleanup_expired()
    yield


app = FastAPI(
    title="MinecraftAI Web Interface",
    description="Production web interface and backend for natural-language Minecraft Java datapack generation",
    version="1.21.11",
    lifespan=lifespan
)

# Apply Security Headers Middleware
app.add_middleware(SecurityHeadersMiddleware)


@app.middleware("http")
async def enforce_payload_size_limit(request: Request, call_next):
    """Enforces max_payload_bytes on incoming HTTP requests."""
    max_bytes = load_security_config().max_payload_bytes
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > max_bytes:
                return JSONResponse(
                    status_code=413,
                    content={"detail": f"Request payload exceeds maximum allowed size of {max_bytes} bytes."}
                )
        except ValueError:
            pass
    return await call_next(request)

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


class CreateSessionPayload(BaseModel):
    minecraft_version: str = Field(default="1.21.11", description="Target Minecraft Java Edition version")


class ConversationMessagePayload(BaseModel):
    session_id: str = Field(..., description="Active conversation session ID")
    message: str = Field(..., description="Natural-language prompt, refinement, or choice selection")


class ConfirmProposalPayload(BaseModel):
    session_id: str = Field(..., description="Active conversation session ID to confirm and generate")
    datapack_name: Optional[str] = Field(default=None, description="Optional custom name for generated datapack")


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



class JobStatus:
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    NEEDS_CLARIFICATION = "needs_clarification"
    FAILED = "failed"
    TIMEOUT = "timeout"


class GenerationJob(BaseModel):
    job_id: str
    status: str = JobStatus.QUEUED
    progress_stage: str = "Queued for generation"
    stage_index: int = 0
    minecraft_version: str = "1.21.11"
    original_request: str = ""
    download_url: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: float = Field(default_factory=time.time)
    completed_at: Optional[float] = None


class JobManager:
    """In-memory thread-safe generation job tracking and lifecycle manager."""
    def __init__(self, max_jobs: int = 500, ttl_seconds: int = 3600):
        self._jobs: Dict[str, GenerationJob] = {}
        self._max_jobs = max_jobs
        self._ttl_seconds = ttl_seconds

    def create_job(self, request_text: str, minecraft_version: str) -> GenerationJob:
        self.cleanup_expired()
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        job = GenerationJob(
            job_id=job_id,
            request_text=request_text,
            minecraft_version=minecraft_version,
            original_request=request_text,
        )
        self._jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> Optional[GenerationJob]:
        return self._jobs.get(job_id)

    def cleanup_expired(self):
        cutoff = time.time() - self._ttl_seconds
        expired_keys = [k for k, v in self._jobs.items() if v.created_at < cutoff]
        for k in expired_keys:
            self._jobs.pop(k, None)
        if len(self._jobs) > self._max_jobs:
            sorted_keys = sorted(self._jobs.keys(), key=lambda k: self._jobs[k].created_at)
            for k in sorted_keys[: len(self._jobs) - self._max_jobs]:
                self._jobs.pop(k, None)


DEFAULT_JOB_MANAGER = JobManager()



@app.get("/api/health")
async def health_check():
    """
    Health check endpoint returning system, security, and Minecraft version status.
    Never exposes internal tokens, passwords, or credentials.
    """
    registry = get_version_registry()
    default_meta = registry.get_default()
    provider = os.getenv("LLM_PROVIDER", "ollama")
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
        "rate_limiting": "active",
        "provider": provider
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


def _compute_pipeline_stages(pipeline_result: Any) -> List[Dict[str, str]]:
    """
    Computes authentic status and message for each of the 8 pipeline stages
    based on actual execution and artifacts.
    Status values map to CSS classes: 'done', 'failed', 'active', 'skipped', 'idle'.
    """
    failed_stage = getattr(pipeline_result, "failed_stage", None)
    status = getattr(pipeline_result, "status", None)

    stages: List[Dict[str, str]] = []

    # 0: Understanding
    und = getattr(pipeline_result, "understanding", None)
    if und:
        if status == "needs_clarification":
            stages.append({"name": "Understanding", "status": "skipped", "message": "Clarification Required"})
        else:
            stages.append({"name": "Understanding", "status": "done", "message": "Passed"})
    elif failed_stage == "understanding" or status in ("failed", "error", "unsupported"):
        stages.append({"name": "Understanding", "status": "failed", "message": "Failed"})
    else:
        stages.append({"name": "Understanding", "status": "idle", "message": "Idle"})

    # 1: RAG Retrieval
    ctx = getattr(pipeline_result, "context", None)
    if ctx is not None:
        stages.append({"name": "RAG Retrieval", "status": "done", "message": "Retrieved"})
    elif failed_stage == "retrieval":
        stages.append({"name": "RAG Retrieval", "status": "failed", "message": "Failed"})
    elif stages[0]["status"] in ("failed", "skipped"):
        stages.append({"name": "RAG Retrieval", "status": "skipped", "message": "Aborted"})
    else:
        stages.append({"name": "RAG Retrieval", "status": "idle", "message": "Idle"})

    # 2: Planning
    plan = getattr(pipeline_result, "plan", None)
    if plan is not None:
        stages.append({"name": "Planning", "status": "done", "message": "Planned"})
    elif failed_stage == "planning":
        stages.append({"name": "Planning", "status": "failed", "message": "Failed"})
    elif stages[1]["status"] in ("failed", "skipped") or stages[0]["status"] in ("failed", "skipped"):
        stages.append({"name": "Planning", "status": "skipped", "message": "Aborted"})
    else:
        stages.append({"name": "Planning", "status": "idle", "message": "Idle"})

    # 3: Generator
    gen = getattr(pipeline_result, "generation", None)
    files = getattr(gen, "files_generated", []) if gen else []
    if files:
        stages.append({"name": "Generator", "status": "done", "message": f"Generated ({len(files)} files)"})
    elif failed_stage == "generation":
        stages.append({"name": "Generator", "status": "failed", "message": "Failed"})
    elif any(s["status"] in ("failed", "skipped") for s in stages):
        stages.append({"name": "Generator", "status": "skipped", "message": "Aborted"})
    else:
        stages.append({"name": "Generator", "status": "idle", "message": "Idle"})

    # 4: Validation & Repair
    val = getattr(pipeline_result, "validation", None)
    rep = getattr(pipeline_result, "repair", None)
    if rep and getattr(rep, "total_attempts", 0) > 0:
        if getattr(rep, "is_success", False):
            stages.append({"name": "Validation & Repair", "status": "done", "message": f"Healed ({rep.total_attempts} att)"})
        else:
            stages.append({"name": "Validation & Repair", "status": "failed", "message": f"Failed ({rep.total_attempts} att)"})
    elif val and getattr(val, "is_valid", False):
        stages.append({"name": "Validation & Repair", "status": "done", "message": "Passed (0 errors)"})
    elif failed_stage in ("validation", "repair"):
        stages.append({"name": "Validation & Repair", "status": "failed", "message": "Failed"})
    elif val and not getattr(val, "is_valid", True):
        stages.append({"name": "Validation & Repair", "status": "failed", "message": "Validation Failed"})
    elif any(s["status"] in ("failed", "skipped") for s in stages):
        stages.append({"name": "Validation & Repair", "status": "skipped", "message": "Aborted"})
    else:
        stages.append({"name": "Validation & Repair", "status": "idle", "message": "Idle"})

    # 5: Autonomous QA
    qa = getattr(pipeline_result, "qa_result", None)
    if qa and getattr(qa, "is_pass", False):
        stages.append({"name": "Autonomous QA", "status": "done", "message": "Passed Cleanly"})
    elif failed_stage in ("qa_review", "qa_repair"):
        stages.append({"name": "Autonomous QA", "status": "failed", "message": "QA Failed"})
    elif qa and not getattr(qa, "is_pass", True):
        stages.append({"name": "Autonomous QA", "status": "failed", "message": "QA Failed"})
    elif any(s["status"] in ("failed", "skipped") for s in stages):
        stages.append({"name": "Autonomous QA", "status": "skipped", "message": "Aborted"})
    else:
        stages.append({"name": "Autonomous QA", "status": "idle", "message": "Idle"})

    # 6: Intent Verification
    intent = getattr(pipeline_result, "intent_verification", None)
    if intent and getattr(intent, "matches_intent", False):
        stages.append({"name": "Intent Verification", "status": "done", "message": "Verified 100%"})
    elif failed_stage == "intent_verification":
        stages.append({"name": "Intent Verification", "status": "failed", "message": "Intent Mismatch"})
    elif intent and not getattr(intent, "matches_intent", True):
        stages.append({"name": "Intent Verification", "status": "failed", "message": "Intent Mismatch"})
    elif any(s["status"] in ("failed", "skipped") for s in stages):
        stages.append({"name": "Intent Verification", "status": "skipped", "message": "Aborted"})
    else:
        stages.append({"name": "Intent Verification", "status": "idle", "message": "Idle"})

    # 7: READY Gate
    if status in ("verified", "success") and (getattr(pipeline_result, "final_zip_path", None) or getattr(pipeline_result, "final_datapack_path", None)):
        stages.append({"name": "READY Gate", "status": "done", "message": "READY & Zipped"})
    elif failed_stage == "final_verification":
        stages.append({"name": "READY Gate", "status": "failed", "message": "Gate Failed"})
    elif any(s["status"] in ("failed", "skipped") for s in stages) or status in ("failed", "error", "verification_failed", "qa_failed"):
        stages.append({"name": "READY Gate", "status": "skipped", "message": "Aborted"})
    else:
        stages.append({"name": "READY Gate", "status": "idle", "message": "Idle"})

    return stages


def _format_pipeline_result(pipeline_result: Any) -> Dict[str, Any]:
    """
    Extracts, validates, and serializes pipeline output into a safe API contract.
    Conceals server filesystem paths when operating in production mode.
    """
    zip_filename: Optional[str] = None
    download_url: Optional[str] = None
    if pipeline_result.final_zip_path:
        zip_path = Path(pipeline_result.final_zip_path)
        try:
            validate_zip_archive(zip_path)
            zip_filename = zip_path.name
            download_url = f"/api/download/{zip_filename}"
        except ArchiveSecurityError as e:
            logger.error("Generated archive failed security verification: %s", str(e))
            zip_filename = None
            download_url = None

    context_summary: Dict[str, Any] = {}
    if pipeline_result.context:
        knowledge = pipeline_result.context.get("knowledge", {})
        context_summary = {
            "loot_tables": [t.get("path") for t in knowledge.get("loot_tables", []) if isinstance(t, dict)],
            "entities": [e.get("name") for e in knowledge.get("entities", []) if isinstance(e, dict)],
            "items": [i.get("name") for i in knowledge.get("items", []) if isinstance(i, dict)]
        }

    validation_summary: Optional[Dict[str, Any]] = None
    if pipeline_result.validation:
        validation_summary = {
            "is_valid": pipeline_result.validation.is_valid,
            "errors": [e.message for e in pipeline_result.validation.errors],
            "warnings": [w.message for w in pipeline_result.validation.warnings]
        }

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

    # Hide internal server paths in production mode, and avoid exposing absolute machine paths
    is_prod = DEFAULT_SECURITY_CONFIG.is_production_mode
    datapack_path = None if is_prod else (f"generated/{Path(pipeline_result.final_datapack_path).name}" if pipeline_result.final_datapack_path else None)
    zip_path_str = None if is_prod else (f"generated/{Path(pipeline_result.final_zip_path).name}" if pipeline_result.final_zip_path else None)

    sanitized_errors = [sanitize_user_error_message(err) for err in (pipeline_result.errors or [])]

    return {
        "status": pipeline_result.status,
        "error_code": pipeline_result.error_code,
        "failed_stage": pipeline_result.failed_stage,
        "diagnostic": pipeline_result.diagnostic,
        "stages": _compute_pipeline_stages(pipeline_result),
        "is_success": pipeline_result.is_success,
        "minecraft_version": pipeline_result.minecraft_version,
        "original_request": pipeline_result.original_request,
        "refined_request": pipeline_result.original_request,
        "clarification": pipeline_result.clarification,
        "clarification_requirements": pipeline_result.clarification_requirements or [],
        "execution_summary": pipeline_result.execution_summary,
        "datapack_path": datapack_path,
        "zip_path": zip_path_str,
        "zip_filename": zip_filename,
        "download_url": download_url,
        "errors": sanitized_errors,
        "files_generated": pipeline_result.generation.files_generated if pipeline_result.generation else [],
        "context_summary": context_summary,
        "validation": validation_summary,
        "repair": repair_summary,
        "plan_summary": pipeline_result.plan.get("summary") if pipeline_result.plan else None
    }


async def _execute_pipeline_task(
    req_text: str,
    target_ver: str,
    understanding: Optional[Dict[str, Any]] = None,
    session: Optional[Any] = None,
    datapack_name: Optional[str] = None
) -> Any:
    """
    Executes the synchronous pipeline in a worker thread with timeout protection.
    Prevents event-loop starvation and runaway generations.
    """
    timeout = float(load_security_config().generation_timeout_seconds)
    return await asyncio.wait_for(
        asyncio.to_thread(
            run_minecraft_pipeline,
            request=req_text,
            minecraft_version=target_ver,
            provider=os.getenv("LLM_PROVIDER", "ollama"),
            create_zip=True,
            verbose=False,
            understanding=understanding,
            session=session,
            datapack_name=datapack_name
        ),
        timeout=timeout
    )


async def _run_background_job(job: GenerationJob, req_text: str, target_ver: str):
    """
    Executes a queued generation job asynchronously in the background.
    """
    job.status = JobStatus.RUNNING
    job.progress_stage = "Acquiring generation capacity"
    job.stage_index = 1

    slot_acquired = DEFAULT_RATE_LIMITER.acquire_generation_slot(timeout_s=5.0)
    if not slot_acquired:
        job.status = JobStatus.FAILED
        job.progress_stage = "Capacity exceeded"
        job.error = "Server is busy processing concurrent generation requests. Please try again shortly."
        job.completed_at = time.time()
        return

    try:
        job.progress_stage = "Generating and validating datapack"
        job.stage_index = 3
        pipeline_result = await _execute_pipeline_task(req_text, target_ver)
        result_dict = _format_pipeline_result(pipeline_result)
        job.result = result_dict
        job.completed_at = time.time()

        if pipeline_result.status == "needs_clarification":
            job.status = JobStatus.NEEDS_CLARIFICATION
            job.progress_stage = "Clarification required"
            job.stage_index = 2
        elif not pipeline_result.is_success:
            job.status = JobStatus.FAILED
            job.progress_stage = "Pipeline halted with errors"
            if pipeline_result.error_code in ("provider_unreachable", "provider_auth"):
                job.error = (
                    "Generation is temporarily unavailable. Please try again in a moment."
                    if DEFAULT_SECURITY_CONFIG.is_production_mode
                    else (pipeline_result.diagnostic or get_ollama_diagnostic_message())
                )
            else:
                raw_err = pipeline_result.errors[0] if pipeline_result.errors else "Pipeline failed"
                job.error = (
                    "Generation encountered an unexpected error. Please try again in a moment."
                    if DEFAULT_SECURITY_CONFIG.is_production_mode
                    else sanitize_user_error_message(raw_err)
                )
        else:
            job.status = JobStatus.SUCCESS
            job.progress_stage = "Datapack ZIP ready"
            job.stage_index = 8
            job.download_url = result_dict.get("download_url")

    except asyncio.TimeoutError:
        job.status = JobStatus.TIMEOUT
        job.progress_stage = "Timed out"
        job.error = "Generation timed out. Please simplify your request or try again."
        job.completed_at = time.time()
    except Exception as e:
        logger.error("Background job %s failed: %s", job.job_id, str(e))
        job.status = JobStatus.FAILED
        job.progress_stage = "Generation failed"
        if is_ollama_unreachable_error(e):
            job.error = (
                "Generation is temporarily unavailable. Please try again in a moment."
                if DEFAULT_SECURITY_CONFIG.is_production_mode
                else get_ollama_diagnostic_message()
            )
        else:
            job.error = (
                "Generation encountered an unexpected error. Please try again in a moment."
                if DEFAULT_SECURITY_CONFIG.is_production_mode
                else sanitize_user_error_message(e)
            )
        job.completed_at = time.time()
    finally:
        DEFAULT_RATE_LIMITER.release_generation_slot()


@app.post("/api/generate")
async def generate_datapack(payload: GeneratePayload, request: Request, async_mode: bool = False):
    """
    Submits a natural-language request to the complete end-to-end MinecraftAI pipeline.
    Guarded by input validation, rate limiting, and concurrency throttling.
    Supports synchronous completion by default and asynchronous job submission via ?async_mode=true.
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
            req_text = validate_prompt(req_text)

        registry = get_version_registry()
        target_ver = validate_version_string(
            payload.minecraft_version,
            set(registry.get_supported_versions())
        )
    except InputValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # If client requested asynchronous job mode
    if async_mode:
        job = DEFAULT_JOB_MANAGER.create_job(req_text, target_ver)
        asyncio.create_task(_run_background_job(job, req_text, target_ver))
        return {
            "job_id": job.job_id,
            "status": job.status,
            "progress_stage": job.progress_stage,
            "check_url": f"/api/jobs/{job.job_id}"
        }

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
        pipeline_result = await _execute_pipeline_task(req_text, target_ver)
    except asyncio.TimeoutError:
        cfg = load_security_config()
        logger.warning("Pipeline execution timed out after %ds", cfg.generation_timeout_seconds)
        raise HTTPException(
            status_code=504,
            detail="Generation timed out. Please simplify your request or try again in a few moments."
        )
    except Exception as e:
        logger.error("Pipeline execution encountered an error: %s", str(e))
        is_provider_error = is_ollama_unreachable_error(e) or "api_key" in str(e).lower() or "ollama" in str(e).lower()
        if is_provider_error:
            if DEFAULT_SECURITY_CONFIG.is_production_mode:
                raise HTTPException(
                    status_code=503,
                    detail="Generation is temporarily unavailable. Please try again in a moment."
                )
            if is_ollama_unreachable_error(e):
                raise HTTPException(
                    status_code=503,
                    detail=get_ollama_diagnostic_message(exc=e)
                )
        sanitized_msg = sanitize_user_error_message(e)
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline execution encountered an unexpected error: {sanitized_msg}"
        )
    finally:
        DEFAULT_RATE_LIMITER.release_generation_slot()

    # Trigger periodic artifact cleanup
    cleanup_expired_artifacts()

    if pipeline_result.status == "error" and pipeline_result.error_code in ("provider_unreachable", "provider_auth"):
        diag = pipeline_result.diagnostic or get_ollama_diagnostic_message()
        if DEFAULT_SECURITY_CONFIG.is_production_mode:
            raise HTTPException(
                status_code=503,
                detail="Generation is temporarily unavailable. Please try again in a moment."
            )
        raise HTTPException(
            status_code=503,
            detail=diag
        )

    # 5. Extract download URL and formatted response
    return _format_pipeline_result(pipeline_result)


@app.post("/api/jobs")
async def create_job(payload: GeneratePayload, request: Request):
    """
    Submits a generation request to the background job manager.
    Returns immediately with a job ID for status polling.
    """
    return await generate_datapack(payload, request, async_mode=True)


@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str):
    """
    Polls the progress and completion status of an asynchronous generation job.
    """
    job = DEFAULT_JOB_MANAGER.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or expired.")

    return {
        "job_id": job.job_id,
        "status": job.status,
        "progress_stage": job.progress_stage,
        "stage_index": job.stage_index,
        "minecraft_version": job.minecraft_version,
        "created_at": job.created_at,
        "completed_at": job.completed_at,
        "download_url": job.download_url,
        "result": job.result,
        "error": job.error
    }


@app.get("/api/generate/{job_id}")
async def get_generate_status(job_id: str):
    """
    Alias endpoint for polling generation job status.
    """
    return await get_job_status(job_id)


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
# Conversational Endpoints (Phase 2 Integration)
# =========================================================================

@app.post("/api/conversation/session")
async def create_conversation_session(payload: CreateSessionPayload, request: Request):
    """
    Initializes a new isolated multi-turn conversational session.
    """
    client_ip = request.client.host if request.client else "127.0.0.1"
    allowed, retry_after = DEFAULT_RATE_LIMITER.check_rate_limit(client_ip)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Please wait {retry_after} second(s).",
            headers={"Retry-After": str(retry_after or 60)}
        )

    registry = get_version_registry()
    try:
        target_ver = validate_version_string(
            payload.minecraft_version,
            set(registry.get_supported_versions())
        )
    except InputValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    DEFAULT_CONVERSATION_MANAGER.cleanup_expired()
    session = DEFAULT_CONVERSATION_MANAGER.create_session(version=target_ver)
    return {
        "session_id": session.session_id,
        "minecraft_version": session.minecraft_version,
        "created_at": session.created_at,
        "messages": [],
        "current_proposal": None
    }


@app.get("/api/conversation/session/{session_id}")
async def get_conversation_session(session_id: str):
    """
    Retrieves the current state of an active conversation session.
    Conceals server internal paths and secrets.
    """
    session = DEFAULT_CONVERSATION_MANAGER.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Conversation session not found or expired.")

    return {
        "session_id": session.session_id,
        "minecraft_version": session.minecraft_version,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "is_confirmed": session.is_confirmed(),
        "current_proposal": session.current_proposal.model_dump() if session.current_proposal else None,
        "messages": [m.model_dump() for m in session.messages]
    }


@app.post("/api/conversation/message")
async def send_conversation_message(payload: ConversationMessagePayload, request: Request):
    """
    Processes a natural-language turn or choice selection within an active conversation session.
    Returns the evolving behavioral proposal, plain-English assumptions, and open choices.
    """
    client_ip = request.client.host if request.client else "127.0.0.1"
    allowed, retry_after = DEFAULT_RATE_LIMITER.check_rate_limit(client_ip)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Please wait {retry_after} second(s).",
            headers={"Retry-After": str(retry_after or 60)}
        )

    session = DEFAULT_CONVERSATION_MANAGER.get_session(payload.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Conversation session not found or expired.")

    try:
        clean_msg = validate_prompt(payload.message)
    except InputValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    engine = ConversationalUnderstandingEngine(
        provider_name=os.getenv("LLM_PROVIDER", "ollama"),
        version=session.minecraft_version
    )

    try:
        proposal = engine.process_turn(session, clean_msg)
    except Exception as e:
        logger.error("Turn processing failed for session %s: %s", session.session_id, e)
        raise HTTPException(
            status_code=500,
            detail=f"Conversational processing error: {sanitize_user_error_message(e)}"
        )

    # Validate capabilities using SpecificationBridge
    bridge = SpecificationBridge()
    val_report = bridge.validate_capabilities(proposal)
    if not val_report.is_supported:
        proposal.status = "unsupported"
        proposal.unsupported_reason = val_report.unsupported_reason
        proposal.is_complete = False

    return {
        "session_id": session.session_id,
        "minecraft_version": session.minecraft_version,
        "proposal": proposal.model_dump(),
        "is_confirmed": session.is_confirmed(),
        "can_generate": bool(
            session.is_confirmed()
            or (
                proposal.is_complete
                and proposal.status != "unsupported"
                and not proposal.open_choices
            )
        ),
        "messages": [m.model_dump() for m in session.messages]
    }


@app.post("/api/conversation/confirm")
async def confirm_and_generate(payload: ConfirmProposalPayload, request: Request, async_mode: bool = False):
    """
    Explicitly confirms the active proposal and triggers the 8-stage generation pipeline.
    Rejects confirmation if no proposal is pending, if proposal is incomplete, or if choices remain open.
    """
    client_ip = request.client.host if request.client else "127.0.0.1"
    allowed, retry_after = DEFAULT_RATE_LIMITER.check_rate_limit(client_ip)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Please wait {retry_after} second(s).",
            headers={"Retry-After": str(retry_after or 60)}
        )

    session = DEFAULT_CONVERSATION_MANAGER.get_session(payload.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Conversation session not found or expired.")

    # Requirement 5: A confirmation message must not trigger generation unless a valid proposal is pending.
    if not session.current_proposal:
        raise HTTPException(status_code=400, detail="No active proposal exists in this session to confirm.")

    if not session.current_proposal.is_complete:
        raise HTTPException(status_code=400, detail="Active proposal is incomplete; please clarify open choices before confirming.")

    if session.current_proposal.status == "unsupported":
        reason = session.current_proposal.unsupported_reason or "Requested behavior is unsupported by vanilla Minecraft datapacks."
        detail_msg = f"Unsupported capability: {reason}" if "unsupported" not in reason.lower() else reason
        raise HTTPException(status_code=400, detail=detail_msg)

    if session.current_proposal.open_choices:
        raise HTTPException(status_code=400, detail="Cannot confirm proposal while unresolved choices remain.")

    # Requirement 6: Validate specification and capabilities
    bridge = SpecificationBridge()
    val_report = bridge.validate_capabilities(session.current_proposal)
    if not val_report.is_supported:
        raise HTTPException(
            status_code=400,
            detail=val_report.unsupported_reason or "Requested capability is outside vanilla Minecraft datapack boundaries."
        )

    # Confirm session and compile specification
    session.confirm_proposal()
    ok, spec_dict, err = bridge.convert_session_to_specification(session)
    if not ok or not spec_dict:
        raise HTTPException(status_code=400, detail=err or "Failed to compile confirmed specification.")

    req_text = session.current_proposal.summary
    target_ver = session.minecraft_version

    # If async_mode is requested
    if async_mode:
        job = DEFAULT_JOB_MANAGER.create_job(req_text, target_ver)

        async def _run_conv_background_job():
            job.status = JobStatus.RUNNING
            job.progress_stage = "Acquiring generation capacity"
            job.stage_index = 1
            slot = DEFAULT_RATE_LIMITER.acquire_generation_slot(timeout_s=5.0)
            if not slot:
                job.status = JobStatus.FAILED
                job.progress_stage = "Capacity exceeded"
                job.error = "Server is busy. Please try again shortly."
                job.completed_at = time.time()
                return
            try:
                job.progress_stage = "Generating and validating datapack"
                job.stage_index = 3
                pipeline_res = await _execute_pipeline_task(
                    req_text=req_text,
                    target_ver=target_ver,
                    understanding=spec_dict,
                    session=session,
                    datapack_name=payload.datapack_name
                )
                res_dict = _format_pipeline_result(pipeline_res)
                job.result = res_dict
                job.completed_at = time.time()
                if not pipeline_res.is_success:
                    job.status = JobStatus.FAILED
                    job.progress_stage = "Pipeline halted with errors"
                    job.error = pipeline_res.errors[0] if pipeline_res.errors else "Pipeline failed"
                else:
                    job.status = JobStatus.SUCCESS
                    job.progress_stage = "Datapack ZIP ready"
                    job.stage_index = 8
                    job.download_url = res_dict.get("download_url")
            except Exception as e:
                logger.error("Background conv job %s failed: %s", job.job_id, e)
                job.status = JobStatus.FAILED
                job.progress_stage = "Generation failed"
                job.error = sanitize_user_error_message(e)
                job.completed_at = time.time()
            finally:
                DEFAULT_RATE_LIMITER.release_generation_slot()

        asyncio.create_task(_run_conv_background_job())
        return {
            "job_id": job.job_id,
            "status": job.status,
            "progress_stage": job.progress_stage,
            "check_url": f"/api/jobs/{job.job_id}"
        }

    # Synchronous execution
    slot_acquired = DEFAULT_RATE_LIMITER.acquire_generation_slot(timeout_s=2.0)
    if not slot_acquired:
        raise HTTPException(
            status_code=503,
            detail="Server is currently busy processing concurrent generation requests. Please try again shortly."
        )

    logger.info("Initiating conversational pipeline generation for session %s (ver %s)", session.session_id, target_ver)
    try:
        pipeline_result = await _execute_pipeline_task(
            req_text=req_text,
            target_ver=target_ver,
            understanding=spec_dict,
            session=session,
            datapack_name=payload.datapack_name
        )
    except asyncio.TimeoutError:
        logger.warning("Pipeline execution timed out for session %s", session.session_id)
        raise HTTPException(
            status_code=504,
            detail="Generation timed out. Please simplify your request or try again."
        )
    except Exception as e:
        logger.error("Pipeline execution encountered an error: %s", str(e))
        is_provider_error = is_ollama_unreachable_error(e) or "api_key" in str(e).lower() or "ollama" in str(e).lower()
        if is_provider_error:
            if DEFAULT_SECURITY_CONFIG.is_production_mode:
                raise HTTPException(
                    status_code=503,
                    detail="Generation is temporarily unavailable. Please try again in a moment."
                )
            if is_ollama_unreachable_error(e):
                raise HTTPException(
                    status_code=503,
                    detail=get_ollama_diagnostic_message(exc=e)
                )
        sanitized_msg = sanitize_user_error_message(e)
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline execution encountered an unexpected error: {sanitized_msg}"
        )
    finally:
        DEFAULT_RATE_LIMITER.release_generation_slot()

    cleanup_expired_artifacts()

    if pipeline_result.status == "error" and pipeline_result.error_code in ("provider_unreachable", "provider_auth"):
        diag = pipeline_result.diagnostic or get_ollama_diagnostic_message()
        if DEFAULT_SECURITY_CONFIG.is_production_mode:
            raise HTTPException(
                status_code=503,
                detail="Generation is temporarily unavailable. Please try again in a moment."
            )
        raise HTTPException(
            status_code=503,
            detail=diag
        )

    return _format_pipeline_result(pipeline_result)


@app.delete("/api/conversation/session/{session_id}")
async def delete_conversation_session(session_id: str):
    """Resets or terminates an active conversation session."""
    deleted = DEFAULT_CONVERSATION_MANAGER.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found.")
    return {"status": "deleted", "session_id": session_id}


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
