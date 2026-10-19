import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from ai.context import retrieve_minecraft_context
from ai.planner import create_plan
from ai.provider import (
    AIProvider,
    classify_provider_error,
    get_ollama_diagnostic_message,
    is_ollama_unreachable_error,
)
from ai.understanding import MinecraftUnderstanding
from generator.datapack_generator import DatapackGenerator
from pipeline.models import PipelineResult, PipelineStage
from qa.models import QAResult, QASeverity
from qa.repair import QARepairEngine
from qa.reviewer import AutonomousQAReviewer
from qa.runtime import RuntimeTestMode, RuntimeTestRunner
from repair.repair_loop import AIRepairLoop
from validator.datapack_validator import DatapackValidator
from ai.version_registry import VersionContext
from ai.specification import SpecificationBridge
from security.error_sanitizer import sanitize_user_error_message


def _log(stage: str, message: str, verbose: bool = True) -> None:
    if verbose:
        try:
            print(f"[{stage}] {message}")
        except UnicodeEncodeError:
            safe_message = message.encode("ascii", errors="replace").decode("ascii")
            print(f"[{stage}] {safe_message}")


def _normalize_text_for_comparison(text: str) -> set:
    """Extract normalized word tokens for comparison."""
    import re
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    return set(cleaned.split())


def _is_question_already_answered(
    new_question: str,
    clarification_history: Optional[List[Dict[str, str]]]
) -> bool:
    """
    Check if a proposed clarification question was already asked or answered.
    Compares new clarification against earlier question/answer pairs.
    """
    if not clarification_history or not new_question:
        return False

    new_tokens = _normalize_text_for_comparison(new_question)
    stop_words = {
        "what", "which", "how", "by", "amount", "value", "set", "the", "a", "an",
        "is", "should", "be", "or", "to", "for", "in", "of", "please", "specify",
        "percentage", "multiplier", "parameter", "parameters"
    }
    meaningful_new_tokens = new_tokens - stop_words
    if not meaningful_new_tokens:
        meaningful_new_tokens = new_tokens

    for entry in clarification_history:
        prev_q = entry.get("question", "")
        prev_a = entry.get("answer", "")

        prev_q_tokens = _normalize_text_for_comparison(prev_q)
        meaningful_prev_q = prev_q_tokens - stop_words or prev_q_tokens

        intersection = meaningful_new_tokens.intersection(meaningful_prev_q)
        union = meaningful_new_tokens.union(meaningful_prev_q)
        similarity = len(intersection) / len(union) if union else 0.0
        if similarity >= 0.50:
            return True

        prev_a_tokens = _normalize_text_for_comparison(prev_a)
        if meaningful_new_tokens and len(meaningful_new_tokens.intersection(prev_a_tokens)) >= max(1, len(meaningful_new_tokens) // 2):
            return True

    return False


def _is_fundamentally_unsupported_mechanic(text: str, understanding: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """
    Detect mechanics fundamentally unsupported by vanilla Minecraft Java Edition datapacks:
    - Dynamic player health synchronization / shared HP / shared damage pool across players
      (player Health NBT is read-only in Java; /damage only accepts fixed float literals, not dynamic scoreboard scores; no arbitrary dynamic heal command)
    - Dynamic player hunger synchronization / shared hunger
      (player foodLevel NBT is read-only)
    """
    lower = (text or "").lower()

    is_shared = any(w in lower for w in ("shared", "share", "shares", "same hp", "same health", "same hearts", "sync health", "pool", "share one"))
    has_health = any(w in lower for w in ("health", "hp", "heart", "hearts", "damage", "heals", "healing", "life", "lives"))
    has_players = any(p in lower for p in ("player", "players", "everyone", "all"))
    if (is_shared and has_health) or (has_health and "share" in lower and has_players):
        return (
            "Dynamic player health synchronization (shared HP/hearts/damage across players) is fundamentally "
            "unsupported by vanilla Minecraft Java Edition datapacks: player Health NBT is read-only, "
            "the /damage command does not accept dynamic scoreboard variables, and there is no arbitrary dynamic healing command."
        )

    has_hunger = any(w in lower for w in ("hunger", "food", "saturation", "food level"))
    if (is_shared and has_hunger) or (has_hunger and "share" in lower and has_players):
        return (
            "Dynamic player hunger synchronization (shared hunger/food level across players) is fundamentally "
            "unsupported by vanilla Minecraft Java Edition datapacks: player foodLevel NBT is read-only."
        )

    return None



class MinecraftPipeline:
    """
    Step 14: End-to-End Orchestrator for MinecraftAI with Autonomous QA & Auto-Repair.

    Coordinates:
      [1/8] Natural Language Understanding
      [2/8] Minecraft Knowledge Retrieval (RAG)
      [3/8] Implementation Planning
      [4/8] Deterministic Datapack Generation
      [5/8] Deterministic Structural Validation (with Structural Repair Loop)
      [6/8] Autonomous QA Review (with Bounded QA Repair Loop)
      [7/8] User Intent Verification
      [8/8] Final Verification & READY Gate (with Runtime Simulation)
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        version: Optional[str] = None,
        version_context: Optional[VersionContext] = None,
        output_dir: Optional[Path] = None,
        max_repair_attempts: int = 3,
        max_qa_repair_attempts: int = 3,
        verbose: bool = True,
        understanding_engine: Optional[MinecraftUnderstanding] = None,
        generator: Optional[DatapackGenerator] = None,
        validator: Optional[DatapackValidator] = None,
        repair_loop: Optional[AIRepairLoop] = None,
        qa_reviewer: Optional[AutonomousQAReviewer] = None,
        qa_repair_engine: Optional[QARepairEngine] = None,
        runtime_runner: Optional[RuntimeTestRunner] = None,
        ai_provider: Optional[AIProvider] = None
    ):
        self.provider_name = (provider or os.getenv("LLM_PROVIDER") or "ollama").lower()
        self.version_context = version_context or VersionContext.from_version(version)
        self.version = self.version_context.version_id
        self.verbose = verbose
        self.max_repair_attempts = max_repair_attempts
        self.max_qa_repair_attempts = max_qa_repair_attempts

        # Subsystems (supports dependency injection for testing)
        self.ai = ai_provider or AIProvider(provider=self.provider_name)
        self.understanding = understanding_engine or MinecraftUnderstanding(
            provider=self.provider_name,
            ai_provider=self.ai,
            version=self.version,
            version_context=self.version_context
        )
        self.generator = generator or DatapackGenerator(output_dir=output_dir, version=self.version, version_context=self.version_context)
        self.validator = validator or DatapackValidator(version=self.version, version_context=self.version_context)
        self.repair_loop = repair_loop or AIRepairLoop(
            ai_provider=self.ai,
            provider=provider,
            max_attempts=max_repair_attempts,
            version=self.version,
            generator=self.generator,
            validator=self.validator
        )
        self.qa_reviewer = qa_reviewer or AutonomousQAReviewer(
            ai_provider=self.ai,
            provider=provider,
            version=self.version,
            version_context=self.version_context
        )
        self.qa_repair_engine = qa_repair_engine or QARepairEngine(
            ai_provider=self.ai,
            provider=provider,
            version=self.version,
            version_context=self.version_context
        )
        self.runtime_runner = runtime_runner or RuntimeTestRunner(version=self.version, version_context=self.version_context)

    def run(
        self,
        request: str,
        datapack_name: Optional[str] = None,
        create_zip: bool = True,
        understanding: Optional[Dict[str, Any]] = None,
        session: Optional[Any] = None,
        clarification_history: Optional[List[Dict[str, str]]] = None,
        clarification_round: int = 0
    ) -> PipelineResult:
        """
        Executes the complete pipeline end-to-end.
        Accepts optional pre-confirmed understanding or conversation session from Phase 2.
        """
        request_clean = request.strip()
        history_list = list(clarification_history or [])
        pipeline_assumptions: List[str] = []

        if not request_clean:
            return PipelineResult(
                status="failed",
                failed_stage="understanding",
                minecraft_version=self.version,
                original_request=request,
                clarification_history=history_list,
                clarification_round=clarification_round,
                errors=["Request string cannot be empty."],
                execution_summary="Pipeline aborted: empty request."
            )

        # Re-run prompt validation on composed history if present
        if history_list:
            full_context_parts = [request_clean]
            for h in history_list:
                a = h.get("answer", "")
                if a:
                    full_context_parts.append(f"Specifically: {a}.")
            composed_request = " ".join(full_context_parts)
            try:
                from security.input_security import validate_prompt
                validate_prompt(composed_request)
            except Exception as e:
                return PipelineResult(
                    status="failed",
                    failed_stage="understanding",
                    minecraft_version=self.version,
                    original_request=request_clean,
                    clarification_history=history_list,
                    clarification_round=clarification_round,
                    errors=[f"Prompt validation failed on composed clarification: {e}"],
                    execution_summary="Pipeline aborted: prompt validation failed."
                )

        # -------------------------------------------------------------
        # STAGE 1: Natural Language Understanding / Specification Bridge
        # -------------------------------------------------------------
        if understanding is None and session is not None:
            bridge = SpecificationBridge()
            ok, spec_dict, err = bridge.convert_session_to_specification(session)
            if not ok or not spec_dict:
                err_msg = err or "Failed to extract specification from conversation session."
                _log("1/8", f"ERROR: {err_msg}", self.verbose)
                return PipelineResult(
                    status="failed",
                    failed_stage="understanding",
                    minecraft_version=self.version,
                    original_request=request_clean,
                    clarification_history=history_list,
                    clarification_round=clarification_round,
                    errors=[err_msg],
                    execution_summary="Pipeline aborted: conversation session is unconfirmed or invalid."
                )
            understanding = spec_dict

        # Check for fundamentally unsupported capability upfront
        unsupported_reason = _is_fundamentally_unsupported_mechanic(request_clean, understanding)
        if unsupported_reason:
            _log("1/8", f"Unsupported request rejected upfront: {unsupported_reason}", self.verbose)
            return PipelineResult(
                status="unsupported",
                failed_stage="understanding",
                minecraft_version=self.version,
                original_request=request_clean,
                understanding=understanding,
                clarification_history=history_list,
                clarification_round=clarification_round,
                assumptions=pipeline_assumptions,
                errors=[unsupported_reason],
                execution_summary=f"Pipeline halted: {unsupported_reason}"
            )

        if understanding is not None:
            _log("1/8", f"Using pre-confirmed understanding specification: '{request_clean}'", self.verbose)
        else:
            _log("1/8", f"Understanding request: '{request_clean}'", self.verbose)
            try:
                understanding = self.understanding.understand(request_clean, clarification_history=history_list)
            except Exception as e:
                err_code, diag = classify_provider_error(e)
                sanitized_err = sanitize_user_error_message(e)
                _log("1/8", f"ERROR: AI Understanding failed: {sanitized_err}", self.verbose)
                return PipelineResult(
                    status="error",
                    error_code=err_code,
                    failed_stage="understanding",
                    diagnostic=diag,
                    minecraft_version=self.version,
                    original_request=request_clean,
                    clarification_history=history_list,
                    clarification_round=clarification_round,
                    assumptions=pipeline_assumptions,
                    errors=[f"AI Understanding failed: {sanitized_err}"],
                    execution_summary="Pipeline error during natural-language understanding stage."
                )

        # Check for unsupported capability from understanding
        status_und = understanding.get("status") if understanding else None
        if status_und == "unsupported":
            clarification_req = understanding.get("clarification")
            reason = "Unsupported capability"
            if isinstance(clarification_req, dict):
                reason = clarification_req.get("reason") or "Unsupported capability"
            _log("1/8", f"Unsupported request rejected: {reason}", self.verbose)
            return PipelineResult(
                status="unsupported",
                failed_stage="understanding",
                minecraft_version=self.version,
                original_request=request_clean,
                understanding=understanding,
                clarification_history=history_list,
                clarification_round=clarification_round,
                assumptions=pipeline_assumptions,
                errors=[reason],
                execution_summary=f"Pipeline halted: {reason}"
            )

        # Check for clarification or ambiguity
        clarification_req = understanding.get("clarification")

        if status_und == "needs_clarification" or clarification_req:
            question = ""
            clarif_reqs = []
            if isinstance(clarification_req, dict):
                question = clarification_req.get("question") or clarification_req.get("reason", "")
                clarif_reqs = [clarification_req]
            elif isinstance(clarification_req, list):
                question = "; ".join([str(c) for c in clarification_req])
                clarif_reqs = clarification_req
            elif isinstance(clarification_req, str):
                question = clarification_req
            else:
                question = "Request is ambiguous or underspecified."

            loop_broken = (clarification_round >= 2) or _is_question_already_answered(question, history_list)
            if loop_broken:
                _log("1/8", f"Clarification loop breaker triggered (round={clarification_round}, question_repeated={_is_question_already_answered(question, history_list)})", self.verbose)
                unsupported_reason = _is_fundamentally_unsupported_mechanic(request_clean, understanding)
                if unsupported_reason:
                    return PipelineResult(
                        status="unsupported",
                        failed_stage="understanding",
                        minecraft_version=self.version,
                        original_request=request_clean,
                        understanding=understanding,
                        clarification_history=history_list,
                        clarification_round=clarification_round,
                        errors=[unsupported_reason],
                        execution_summary=f"Pipeline halted: {unsupported_reason}"
                    )
                assumption_note = f"Clarification limit reached or question already answered; assumed defaults for '{question}'"
                pipeline_assumptions.append(assumption_note)
                understanding["status"] = "understood"
                understanding["clarification"] = None
                understanding["assumptions"] = understanding.get("assumptions", []) + [assumption_note]
                if not understanding.get("requirements"):
                    understanding["requirements"] = [{
                        "intent": "custom_gameplay",
                        "subject": "player",
                        "description": request_clean
                    }]
            else:
                _log("1/8", f"Clarification requested: {question}", self.verbose)
                return PipelineResult(
                    status="needs_clarification",
                    minecraft_version=self.version,
                    original_request=request_clean,
                    understanding=understanding,
                    clarification=question,
                    clarification_requirements=clarif_reqs,
                    clarification_history=history_list,
                    clarification_round=clarification_round,
                    assumptions=pipeline_assumptions,
                    execution_summary="Pipeline halted at understanding stage: request requires clarification."
                )

        requirements = understanding.get("requirements", [])
        if not requirements:
            err_msg = "Understanding completed but produced zero actionable requirements."
            _log("1/8", f"FAILED: {err_msg}", self.verbose)
            return PipelineResult(
                status="failed",
                failed_stage="understanding",
                minecraft_version=self.version,
                original_request=request_clean,
                understanding=understanding,
                clarification_history=history_list,
                clarification_round=clarification_round,
                assumptions=pipeline_assumptions,
                errors=[err_msg],
                execution_summary="Pipeline halted: no requirements extracted."
            )

        # -------------------------------------------------------------
        # STAGE 2: Minecraft Knowledge / RAG Retrieval
        # -------------------------------------------------------------
        _log("2/8", f"Retrieving Minecraft Java {self.version} knowledge...", self.verbose)
        try:
            context = retrieve_minecraft_context(understanding, version=self.version)
        except Exception as e:
            err_code, diag = classify_provider_error(e)
            sanitized_err = sanitize_user_error_message(e)
            _log("2/8", f"ERROR: Knowledge retrieval failed: {sanitized_err}", self.verbose)
            return PipelineResult(
                status="error",
                error_code=err_code,
                failed_stage="retrieval",
                diagnostic=diag,
                minecraft_version=self.version,
                original_request=request_clean,
                understanding=understanding,
                clarification_history=history_list,
                clarification_round=clarification_round,
                assumptions=pipeline_assumptions,
                errors=[f"Knowledge retrieval failed: {sanitized_err}"],
                execution_summary="Pipeline error during knowledge retrieval stage."
            )

        # -------------------------------------------------------------
        # STAGE 3: Implementation Planning
        # -------------------------------------------------------------
        _log("3/8", "Creating implementation plan...", self.verbose)
        try:
            plan = create_plan(understanding, provider=self.provider_name, version=self.version, ai_provider=self.ai, context=context)
        except Exception as e:
            err_code, diag = classify_provider_error(e)
            sanitized_err = sanitize_user_error_message(e)
            _log("3/8", f"ERROR: Planner failed: {sanitized_err}", self.verbose)
            return PipelineResult(
                status="error",
                error_code=err_code,
                failed_stage="planning",
                diagnostic=diag,
                minecraft_version=self.version,
                original_request=request_clean,
                understanding=understanding,
                context=context,
                clarification_history=history_list,
                clarification_round=clarification_round,
                assumptions=pipeline_assumptions,
                errors=[f"Planner failed: {sanitized_err}"],
                execution_summary="Pipeline error during planning stage."
            )

        # Check if planner requires clarification
        if plan.get("status") == "needs_clarification" or plan.get("clarifications") or plan.get("clarification_requirements"):
            clarifications = plan.get("clarifications", [])
            clarif_reqs = plan.get("clarification_requirements", [])
            if clarifications:
                clarif_text = "; ".join(clarifications)
            elif clarif_reqs:
                clarif_text = "; ".join([c.get("question", "") for c in clarif_reqs if isinstance(c, dict) and c.get("question")]) or "Planner requires clarification on ambiguous parameters."
            else:
                clarif_text = "Planner requires clarification on ambiguous parameters."

            loop_broken = (clarification_round >= 2) or _is_question_already_answered(clarif_text, history_list)
            if loop_broken:
                _log("3/8", f"Planner clarification loop breaker triggered (round={clarification_round}, question_repeated={_is_question_already_answered(clarif_text, history_list)})", self.verbose)
                unsupported_reason = _is_fundamentally_unsupported_mechanic(request_clean, understanding)
                if unsupported_reason:
                    return PipelineResult(
                        status="unsupported",
                        failed_stage="planning",
                        minecraft_version=self.version,
                        original_request=request_clean,
                        understanding=understanding,
                        context=context,
                        plan=plan,
                        clarification_history=history_list,
                        clarification_round=clarification_round,
                        assumptions=pipeline_assumptions,
                        errors=[unsupported_reason],
                        execution_summary=f"Pipeline halted: {unsupported_reason}"
                    )
                assumption_note = f"Clarification round limit reached for planner; assumed defaults for '{clarif_text}'"
                pipeline_assumptions.append(assumption_note)
                plan["status"] = "ready"
                plan["clarifications"] = []
                plan["clarification_requirements"] = []
                plan["assumptions"] = plan.get("assumptions", []) + [assumption_note]
            else:
                _log("3/8", f"Clarification requested by planner: {clarif_text}", self.verbose)
                return PipelineResult(
                    status="needs_clarification",
                    minecraft_version=self.version,
                    original_request=request_clean,
                    understanding=understanding,
                    context=context,
                    plan=plan,
                    clarification=clarif_text,
                    clarification_requirements=clarif_reqs,
                    clarification_history=history_list,
                    clarification_round=clarification_round,
                    assumptions=pipeline_assumptions,
                    execution_summary="Pipeline halted at planner stage: implementation requires clarification."
                )

        # -------------------------------------------------------------
        # STAGE 4: Deterministic Datapack Generation
        # -------------------------------------------------------------
        _log("4/8", "Generating datapack deterministically...", self.verbose)
        try:
            gen_result = self.generator.generate(
                plan=plan,
                context=context,
                understanding=understanding,
                datapack_name=datapack_name,
                create_zip=create_zip,
                clean=True
            )
        except Exception as e:
            err_code, diag = classify_provider_error(e)
            sanitized_err = sanitize_user_error_message(e)
            _log("4/8", f"ERROR: Generator failed: {sanitized_err}", self.verbose)
            return PipelineResult(
                status="error",
                error_code=err_code,
                failed_stage="generation",
                diagnostic=diag,
                minecraft_version=self.version,
                original_request=request_clean,
                understanding=understanding,
                context=context,
                plan=plan,
                clarification_history=history_list,
                clarification_round=clarification_round,
                assumptions=pipeline_assumptions,
                errors=[f"Generator failed: {sanitized_err}"],
                execution_summary="Pipeline error during deterministic datapack generation stage."
            )

        # -------------------------------------------------------------
        # STAGE 5: Deterministic Structural Validation
        # -------------------------------------------------------------
        _log("5/8", "Validating generated datapack...", self.verbose)
        val_result = self.validator.validate(gen_result.datapack_path)

        # Also validate ZIP if created
        if create_zip and gen_result.zip_path and val_result.is_valid:
            zip_val = self.validator.validate(gen_result.zip_path)
            if not zip_val.is_valid:
                val_result = zip_val

        # If structural validation fails, invoke structural repair loop
        repair_result = None
        final_gen_path = str(gen_result.datapack_path)
        final_zip_path = str(gen_result.zip_path) if gen_result.zip_path else None

        if val_result.is_valid:
            _log("5/8", "Structural validation passed cleanly. AI repair loop skipped (0 attempts).", self.verbose)
        else:
            _log("5/8", f"Validation reported {len(val_result.errors)} error(s). Invoking AI structural repair loop...", self.verbose)
            try:
                repair_result = self.repair_loop.repair(
                    understanding=understanding,
                    context=context,
                    planner_result=plan,
                    generation_result=gen_result,
                    validator_result=val_result,
                    datapack_name=datapack_name or gen_result.datapack_name
                )
            except Exception as e:
                err_code, diag = classify_provider_error(e)
                sanitized_err = sanitize_user_error_message(e)
                _log("5/8", f"ERROR: Repair loop encountered unexpected error: {sanitized_err}", self.verbose)
                return PipelineResult(
                    status="error" if err_code else "failed",
                    error_code=err_code,
                    failed_stage="repair",
                    diagnostic=diag,
                    minecraft_version=self.version,
                    original_request=request_clean,
                    understanding=understanding,
                    context=context,
                    plan=plan,
                    generation=gen_result,
                    validation=val_result,
                    clarification_history=history_list,
                    clarification_round=clarification_round,
                    assumptions=pipeline_assumptions,
                    errors=[f"Repair loop encountered unexpected error: {sanitized_err}"],
                    execution_summary="Pipeline failed: structural repair loop encountered an unexpected exception."
                )

            if not repair_result.is_success:
                err_msgs = [f"Validation error: [{e.code}] {e.message}" for e in (val_result.errors or [])]
                err_msgs.append(f"Repair loop failed: {repair_result.message}")
                _log("5/8", f"FAILED: Structural repair loop could not resolve errors after {repair_result.total_attempts} attempt(s).", self.verbose)
                return PipelineResult(
                    status="failed",
                    failed_stage="repair",
                    verification_status="verification_failed",
                    minecraft_version=self.version,
                    original_request=request_clean,
                    understanding=understanding,
                    context=context,
                    plan=plan,
                    generation=gen_result,
                    validation=val_result,
                    repair=repair_result,
                    clarification_history=history_list,
                    clarification_round=clarification_round,
                    assumptions=pipeline_assumptions,
                    errors=err_msgs,
                    execution_summary="Pipeline failed: generated datapack could not be repaired into a valid state."
                )

            # Repair succeeded
            val_result = repair_result.final_validation or val_result
            final_gen_path = repair_result.final_datapack_path or final_gen_path
            if create_zip:
                expected_zip = Path(final_gen_path).with_suffix(".zip")
                if expected_zip.exists():
                    final_zip_path = str(expected_zip)
            _log("5/8", f"SUCCESS: Datapack repaired successfully in {repair_result.total_attempts} attempt(s).", self.verbose)

        # -------------------------------------------------------------
        # STAGE 6: Autonomous QA Review & Bounded QA Repair Loop
        # -------------------------------------------------------------
        _log("6/8", "Autonomous QA review over complete datapack...", self.verbose)
        try:
            qa_result = self.qa_reviewer.review(
                datapack_dir=Path(final_gen_path),
                original_request=request_clean,
                understanding=understanding,
                plan=plan,
                context=context,
                val_result=val_result
            )
        except Exception as e:
            err_code, diag = classify_provider_error(e)
            sanitized_err = sanitize_user_error_message(e)
            _log("6/8", f"ERROR: QA review failed: {sanitized_err}", self.verbose)
            return PipelineResult(
                status="error" if err_code else "qa_failed",
                error_code=err_code,
                failed_stage="qa_review",
                diagnostic=diag,
                minecraft_version=self.version,
                original_request=request_clean,
                understanding=understanding,
                context=context,
                plan=plan,
                generation=gen_result,
                validation=val_result,
                clarification_history=history_list,
                clarification_round=clarification_round,
                assumptions=pipeline_assumptions,
                errors=[f"QA review failed: {sanitized_err}"],
                execution_summary="Pipeline error during QA review stage."
            )

        qa_attempt_history: List[Dict[str, Any]] = []
        qa_attempt = 0

        while not qa_result.is_pass and qa_attempt < self.max_qa_repair_attempts:
            err_findings = qa_result.error_findings
            _log("6/8", f"QA reported {len(err_findings)} error(s). Invoking QA repair loop (Attempt {qa_attempt+1}/{self.max_qa_repair_attempts})...", self.verbose)
            for f in err_findings[:3]:
                _log("6/8", f"  [{f.category.value}] {f.problem}", self.verbose)

            qa_attempt_history.append({
                "attempt": qa_attempt + 1,
                "error_finding_ids": [f.id for f in err_findings]
            })

            try:
                qa_repair_plan, repaired_plan = self.qa_repair_engine.diagnose_and_repair(
                    qa_result=qa_result,
                    plan=plan,
                    understanding=understanding,
                    context=context,
                    previous_attempts=qa_attempt_history
                )
            except Exception as e:
                err_code, diag = classify_provider_error(e)
                sanitized_err = sanitize_user_error_message(e)
                _log("6/8", f"ERROR: QA diagnosis failed: {sanitized_err}", self.verbose)
                return PipelineResult(
                    status="error" if err_code else "verification_failed",
                    error_code=err_code,
                    failed_stage="qa_repair",
                    diagnostic=diag,
                    minecraft_version=self.version,
                    original_request=request_clean,
                    understanding=understanding,
                    context=context,
                    plan=plan,
                    generation=gen_result,
                    validation=val_result,
                    qa_result=qa_result,
                    clarification_history=history_list,
                    clarification_round=clarification_round,
                    assumptions=pipeline_assumptions,
                    errors=[f"QA diagnosis failed: {sanitized_err}"],
                    execution_summary="Pipeline error during QA diagnosis stage."
                )

            if not qa_repair_plan.regenerate:
                _log("6/8", f"QA repair loop halted: {qa_repair_plan.diagnosis}", self.verbose)
                break

            plan = repaired_plan
            qa_attempt += 1

            # Regenerate deterministically from repaired plan
            _log("6/8", "Regenerating datapack deterministically from repaired plan...", self.verbose)
            try:
                gen_result = self.generator.generate(
                    plan=plan,
                    context=context,
                    understanding=understanding,
                    datapack_name=datapack_name,
                    create_zip=create_zip,
                    clean=True
                )
                final_gen_path = str(gen_result.datapack_path)
                final_zip_path = str(gen_result.zip_path) if gen_result.zip_path else None
            except Exception as e:
                err_code, diag = classify_provider_error(e)
                sanitized_err = sanitize_user_error_message(e)
                _log("6/8", f"ERROR: Regeneration failed during QA repair: {sanitized_err}", self.verbose)
                return PipelineResult(
                    status="error" if err_code else "verification_failed",
                    error_code=err_code,
                    failed_stage="qa_repair",
                    diagnostic=diag,
                    minecraft_version=self.version,
                    original_request=request_clean,
                    understanding=understanding,
                    context=context,
                    plan=plan,
                    generation=gen_result,
                    validation=val_result,
                    repair=repair_result,
                    qa_result=qa_result,
                    clarification_history=history_list,
                    clarification_round=clarification_round,
                    assumptions=pipeline_assumptions,
                    errors=[f"Regeneration failed during QA repair: {sanitized_err}"],
                    execution_summary="Pipeline failed: regeneration failed during QA repair loop."
                )

            # Re-validate structurally
            val_result = self.validator.validate(gen_result.datapack_path)
            if not val_result.is_valid:
                _log("6/8", f"WARNING: Repaired datapack produced structural validation errors: {len(val_result.errors)}", self.verbose)

            # Re-run QA review
            qa_result = self.qa_reviewer.review(
                datapack_dir=Path(final_gen_path),
                original_request=request_clean,
                understanding=understanding,
                plan=plan,
                context=context,
                val_result=val_result
            )

        if not qa_result.is_pass:
            _log("6/8", f"VERIFICATION FAILED: Unresolved QA findings after {qa_attempt} repair attempt(s).", self.verbose)
            return PipelineResult(
                status="verification_failed",
                failed_stage="qa_review",
                verification_status="qa_failed",
                minecraft_version=self.version,
                original_request=request_clean,
                understanding=understanding,
                context=context,
                plan=plan,
                generation=gen_result,
                validation=val_result,
                repair=repair_result,
                qa_result=qa_result,
                intent_verification=qa_result.intent_verification,
                clarification_history=history_list,
                clarification_round=clarification_round,
                assumptions=pipeline_assumptions,
                errors=[f"QA Failure: [{f.category.value}] {f.problem}" for f in qa_result.error_findings],
                execution_summary="Pipeline failed: Autonomous QA could not verify datapack."
            )

        _log("6/8", "Autonomous QA review PASSED cleanly.", self.verbose)

        # -------------------------------------------------------------
        # STAGE 7: Intent Verification
        # -------------------------------------------------------------
        _log("7/8", "Verifying user intent...", self.verbose)
        intent_res = qa_result.intent_verification
        if intent_res and not intent_res.matches_intent:
            _log("7/8", f"VERIFICATION FAILED: Intent mismatch: {intent_res.reasoning}", self.verbose)
            return PipelineResult(
                status="verification_failed",
                failed_stage="intent_verification",
                verification_status="verification_failed",
                minecraft_version=self.version,
                original_request=request_clean,
                understanding=understanding,
                context=context,
                plan=plan,
                generation=gen_result,
                validation=val_result,
                repair=repair_result,
                qa_result=qa_result,
                intent_verification=intent_res,
                clarification_history=history_list,
                clarification_round=clarification_round,
                assumptions=pipeline_assumptions,
                errors=[f"Intent mismatch: {missing}" for missing in intent_res.missing_aspects],
                execution_summary="Pipeline failed: Intent verification rejected implementation."
            )
        _log("7/8", "Intent verification PASSED.", self.verbose)

        # -------------------------------------------------------------
        # STAGE 8: Final Verification & READY Gate
        # -------------------------------------------------------------
        _log("8/8", "Final verification & READY gate...", self.verbose)

        # 1. Structural validity is a hard requirement for READY regardless of create_zip
        struct_check = self.validator.validate(Path(final_gen_path))
        if not struct_check.is_valid:
            _log("8/8", f"VERIFICATION FAILED: Structural validation failed: {len(struct_check.errors)} error(s).", self.verbose)
            return PipelineResult(
                status="verification_failed",
                failed_stage="final_verification",
                verification_status="structural_validation_failed",
                minecraft_version=self.version,
                original_request=request_clean,
                understanding=understanding,
                context=context,
                plan=plan,
                generation=gen_result,
                validation=struct_check,
                repair=repair_result,
                qa_result=qa_result,
                intent_verification=intent_res,
                clarification_history=history_list,
                clarification_round=clarification_round,
                assumptions=pipeline_assumptions,
                errors=[f"Structural validation error: {e.message}" for e in struct_check.errors],
                execution_summary="Pipeline failed: Datapack failed structural validation at READY gate."
            )

        # 2. Execute runtime simulation
        runtime_res = self.runtime_runner.run(
            datapack_dir=Path(final_gen_path),
            mode=RuntimeTestMode.STATIC_SIMULATION
        )
        if not runtime_res.passed:
            _log("8/8", f"VERIFICATION FAILED: Runtime simulation failed: {runtime_res.details}", self.verbose)
            return PipelineResult(
                status="verification_failed",
                failed_stage="final_verification",
                verification_status="verification_failed",
                minecraft_version=self.version,
                original_request=request_clean,
                understanding=understanding,
                context=context,
                plan=plan,
                generation=gen_result,
                validation=struct_check,
                repair=repair_result,
                qa_result=qa_result,
                intent_verification=intent_res,
                runtime_result=runtime_res,
                clarification_history=history_list,
                clarification_round=clarification_round,
                assumptions=pipeline_assumptions,
                errors=[f"Runtime simulation error: {runtime_res.details}"],
                execution_summary="Pipeline failed: Runtime simulation failed."
            )

        # 3. Validate final ZIP explicitly if zip creation was enabled
        if create_zip and final_zip_path:
            zip_check = self.validator.validate(final_zip_path)
            if not zip_check.is_valid:
                return PipelineResult(
                    status="verification_failed",
                    failed_stage="final_verification",
                    verification_status="verification_failed",
                    minecraft_version=self.version,
                    original_request=request_clean,
                    understanding=understanding,
                    context=context,
                    plan=plan,
                    generation=gen_result,
                    validation=zip_check,
                    repair=repair_result,
                    qa_result=qa_result,
                    intent_verification=intent_res,
                    runtime_result=runtime_res,
                    clarification_history=history_list,
                    clarification_round=clarification_round,
                    assumptions=pipeline_assumptions,
                    errors=[f"Final ZIP validation failed: {e.message}" for e in zip_check.errors],
                    execution_summary="Pipeline failed: final ZIP archive failed validation."
                )

        _log("8/8", "VERIFICATION PASSED! All structural, QA, intent, and runtime checks passed.", self.verbose)
        _log("8/8", f"SUCCESS! Datapack is READY at: {final_gen_path}", self.verbose)
        if final_zip_path:
            _log("8/8", f"SUCCESS! Validated ZIP ready at: {final_zip_path}", self.verbose)

        return PipelineResult(
            status="success",
            verification_status="verified",
            minecraft_version=self.version,
            original_request=request_clean,
            understanding=understanding,
            context=context,
            plan=plan,
            generation=gen_result,
            validation=val_result,
            repair=repair_result,
            qa_result=qa_result,
            intent_verification=intent_res,
            runtime_result=runtime_res,
            final_datapack_path=final_gen_path,
            final_zip_path=final_zip_path,
            clarification_history=history_list,
            clarification_round=clarification_round,
            assumptions=pipeline_assumptions,
            execution_summary="Complete end-to-end pipeline verified successfully. Datapack is READY."
        )


def run_minecraft_pipeline(
    request: str,
    minecraft_version: Optional[str] = None,
    version_context: Optional[VersionContext] = None,
    provider: Optional[str] = None,
    create_zip: bool = True,
    output_dir: Optional[Path] = None,
    max_repair_attempts: int = 3,
    max_qa_repair_attempts: int = 3,
    verbose: bool = True,
    understanding: Optional[Dict[str, Any]] = None,
    session: Optional[Any] = None,
    datapack_name: Optional[str] = None,
    clarification_history: Optional[List[Dict[str, str]]] = None,
    clarification_round: int = 0
) -> PipelineResult:
    """
    Public convenience entry point for the complete MinecraftAI pipeline.
    """
    resolved_provider = provider or os.getenv("LLM_PROVIDER") or "ollama"
    pipeline = MinecraftPipeline(
        provider=resolved_provider,
        version=minecraft_version,
        version_context=version_context,
        output_dir=output_dir,
        max_repair_attempts=max_repair_attempts,
        max_qa_repair_attempts=max_qa_repair_attempts,
        verbose=verbose
    )
    return pipeline.run(
        request=request,
        datapack_name=datapack_name,
        create_zip=create_zip,
        understanding=understanding,
        session=session,
        clarification_history=clarification_history,
        clarification_round=clarification_round
    )

