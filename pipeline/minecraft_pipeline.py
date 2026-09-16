import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from ai.context import retrieve_minecraft_context
from ai.planner import create_plan
from ai.provider import AIProvider
from ai.understanding import MinecraftUnderstanding
from generator.datapack_generator import DatapackGenerator
from pipeline.models import PipelineResult, PipelineStage
from repair.repair_loop import AIRepairLoop
from validator.datapack_validator import DatapackValidator


def _log(stage: str, message: str, verbose: bool = True) -> None:
    if verbose:
        print(f"[{stage}] {message}")


class MinecraftPipeline:
    """
    Step 8: End-to-End Orchestrator for MinecraftAI.

    Coordinates:
      [1/7] Natural Language Understanding
      [2/7] Minecraft Knowledge Retrieval (RAG)
      [3/7] Implementation Planning
      [4/7] Deterministic Datapack Generation
      [5/7] Deterministic Validation
      [6/7] AI Repair Loop (gated by validation status)
      [7/7] Final Validated Datapack and ZIP Output
    """

    def __init__(
        self,
        provider: str = "ollama",
        version: str = "1.21.11",
        output_dir: Optional[Path] = None,
        max_repair_attempts: int = 3,
        verbose: bool = True,
        understanding_engine: Optional[MinecraftUnderstanding] = None,
        generator: Optional[DatapackGenerator] = None,
        validator: Optional[DatapackValidator] = None,
        repair_loop: Optional[AIRepairLoop] = None,
        ai_provider: Optional[AIProvider] = None
    ):
        self.provider_name = provider
        self.version = version
        self.verbose = verbose
        self.max_repair_attempts = max_repair_attempts

        # Subsystems (supports dependency injection for testing)
        self.ai = ai_provider or AIProvider(provider=provider)
        self.understanding = understanding_engine or MinecraftUnderstanding(provider=provider)
        self.generator = generator or DatapackGenerator(output_dir=output_dir, version=version)
        self.validator = validator or DatapackValidator(version=version)
        self.repair_loop = repair_loop or AIRepairLoop(
            ai_provider=self.ai,
            provider=provider,
            max_attempts=max_repair_attempts,
            version=version,
            generator=self.generator,
            validator=self.validator
        )

    def run(
        self,
        request: str,
        datapack_name: Optional[str] = None,
        create_zip: bool = True
    ) -> PipelineResult:
        """
        Executes the complete pipeline end-to-end.
        """
        request_clean = request.strip()
        if not request_clean:
            return PipelineResult(
                status="failed",
                minecraft_version=self.version,
                original_request=request,
                errors=["Request string cannot be empty."],
                execution_summary="Pipeline aborted: empty request."
            )

        # -------------------------------------------------------------
        # STAGE 1: Natural Language Understanding
        # -------------------------------------------------------------
        _log("1/7", f"Understanding request: '{request_clean}'", self.verbose)
        try:
            understanding = self.understanding.understand(request_clean)
        except Exception as e:
            err_msg = f"AI Understanding failed: {e}"
            _log("1/7", f"ERROR: {err_msg}", self.verbose)
            return PipelineResult(
                status="error",
                minecraft_version=self.version,
                original_request=request_clean,
                errors=[err_msg],
                execution_summary="Pipeline error during natural-language understanding stage."
            )

        # Check for clarification or ambiguity
        clarification_req = understanding.get("clarification")
        status_und = understanding.get("status")

        if status_und == "needs_clarification" or clarification_req:
            question = ""
            if isinstance(clarification_req, dict):
                question = clarification_req.get("question") or clarification_req.get("reason", "")
            elif isinstance(clarification_req, str):
                question = clarification_req
            else:
                question = "Request is ambiguous or underspecified."

            _log("1/7", f"Clarification requested: {question}", self.verbose)
            return PipelineResult(
                status="needs_clarification",
                minecraft_version=self.version,
                original_request=request_clean,
                understanding=understanding,
                clarification=question,
                execution_summary="Pipeline halted at understanding stage: request requires clarification."
            )

        requirements = understanding.get("requirements", [])
        if not requirements:
            err_msg = "Understanding completed but produced zero actionable requirements."
            _log("1/7", f"FAILED: {err_msg}", self.verbose)
            return PipelineResult(
                status="failed",
                minecraft_version=self.version,
                original_request=request_clean,
                understanding=understanding,
                errors=[err_msg],
                execution_summary="Pipeline halted: no requirements extracted."
            )

        # -------------------------------------------------------------
        # STAGE 2: Minecraft Knowledge / RAG Retrieval
        # -------------------------------------------------------------
        _log("2/7", f"Retrieving Minecraft Java {self.version} knowledge...", self.verbose)
        try:
            context = retrieve_minecraft_context(understanding, version=self.version)
        except Exception as e:
            err_msg = f"Knowledge retrieval failed: {e}"
            _log("2/7", f"ERROR: {err_msg}", self.verbose)
            return PipelineResult(
                status="error",
                minecraft_version=self.version,
                original_request=request_clean,
                understanding=understanding,
                errors=[err_msg],
                execution_summary="Pipeline error during knowledge retrieval stage."
            )

        # -------------------------------------------------------------
        # STAGE 3: Implementation Planning
        # -------------------------------------------------------------
        _log("3/7", "Creating implementation plan...", self.verbose)
        try:
            plan = create_plan(understanding, provider=self.provider_name, version=self.version)
        except Exception as e:
            err_msg = f"Planner failed: {e}"
            _log("3/7", f"ERROR: {err_msg}", self.verbose)
            return PipelineResult(
                status="error",
                minecraft_version=self.version,
                original_request=request_clean,
                understanding=understanding,
                context=context,
                errors=[err_msg],
                execution_summary="Pipeline error during planning stage."
            )

        # Check if planner requires clarification
        if plan.get("status") == "needs_clarification" or plan.get("clarifications"):
            clarifications = plan.get("clarifications", [])
            clarif_text = "; ".join(clarifications) if clarifications else "Planner requires clarification on ambiguous parameters."
            _log("3/7", f"Clarification requested by planner: {clarif_text}", self.verbose)
            return PipelineResult(
                status="needs_clarification",
                minecraft_version=self.version,
                original_request=request_clean,
                understanding=understanding,
                context=context,
                plan=plan,
                clarification=clarif_text,
                execution_summary="Pipeline halted at planner stage: implementation requires clarification."
            )

        # -------------------------------------------------------------
        # STAGE 4: Deterministic Datapack Generation
        # -------------------------------------------------------------
        _log("4/7", "Generating datapack deterministically...", self.verbose)
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
            err_msg = f"Generator failed: {e}"
            _log("4/7", f"ERROR: {err_msg}", self.verbose)
            return PipelineResult(
                status="error",
                minecraft_version=self.version,
                original_request=request_clean,
                understanding=understanding,
                context=context,
                plan=plan,
                errors=[err_msg],
                execution_summary="Pipeline error during deterministic datapack generation stage."
            )

        # -------------------------------------------------------------
        # STAGE 5: Deterministic Validation
        # -------------------------------------------------------------
        _log("5/7", "Validating generated datapack...", self.verbose)
        val_result = self.validator.validate(gen_result.datapack_path)

        # Also validate ZIP if created
        if create_zip and gen_result.zip_path and val_result.is_valid:
            zip_val = self.validator.validate(gen_result.zip_path)
            if not zip_val.is_valid:
                val_result = zip_val

        # -------------------------------------------------------------
        # STAGE 6: AI Repair Loop (only if validation fails)
        # -------------------------------------------------------------
        repair_result = None
        final_gen_path = str(gen_result.datapack_path)
        final_zip_path = str(gen_result.zip_path) if gen_result.zip_path else None

        if val_result.is_valid:
            _log("6/7", "Validation passed cleanly. AI repair loop skipped (0 attempts).", self.verbose)
        else:
            _log("6/7", f"Validation reported {len(val_result.errors)} error(s). Invoking AI repair loop...", self.verbose)
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
                err_msg = f"Repair loop encountered unexpected error: {e}"
                _log("6/7", f"ERROR: {err_msg}", self.verbose)
                return PipelineResult(
                    status="failed",
                    minecraft_version=self.version,
                    original_request=request_clean,
                    understanding=understanding,
                    context=context,
                    plan=plan,
                    generation=gen_result,
                    validation=val_result,
                    errors=[err_msg],
                    execution_summary="Pipeline failed: repair loop encountered an unexpected exception."
                )

            if not repair_result.is_success:
                err_msgs = [f"Validation error: [{e.code}] {e.message}" for e in (val_result.errors or [])]
                err_msgs.append(f"Repair loop failed: {repair_result.message}")
                _log("6/7", f"FAILED: Repair loop could not resolve errors after {repair_result.total_attempts} attempt(s).", self.verbose)
                return PipelineResult(
                    status="failed",
                    minecraft_version=self.version,
                    original_request=request_clean,
                    understanding=understanding,
                    context=context,
                    plan=plan,
                    generation=gen_result,
                    validation=val_result,
                    repair=repair_result,
                    errors=err_msgs,
                    execution_summary="Pipeline failed: generated datapack could not be repaired into a valid state."
                )

            # Repair succeeded
            val_result = repair_result.final_validation or val_result
            final_gen_path = repair_result.final_datapack_path or final_gen_path
            # Check for zip path in repaired directory
            if create_zip:
                expected_zip = Path(final_gen_path).with_suffix(".zip")
                if expected_zip.exists():
                    final_zip_path = str(expected_zip)
            _log("6/7", f"SUCCESS: Datapack repaired successfully in {repair_result.total_attempts} attempt(s).", self.verbose)

        # -------------------------------------------------------------
        # STAGE 7: Final Result & Validation Guardrail
        # -------------------------------------------------------------
        _log("7/7", "Finalizing validated datapack package...", self.verbose)

        # Safety Guardrail (Requirement 7): The pipeline must NEVER allow an invalid datapack to be returned as success.
        if not val_result.is_valid:
            return PipelineResult(
                status="failed",
                minecraft_version=self.version,
                original_request=request_clean,
                understanding=understanding,
                context=context,
                plan=plan,
                generation=gen_result,
                validation=val_result,
                repair=repair_result,
                errors=["Final validation guardrail failed: output remains invalid."],
                execution_summary="Pipeline failed: final validation check failed."
            )

        # Validate final ZIP explicitly if zip creation was enabled
        if create_zip and final_zip_path:
            zip_check = self.validator.validate(final_zip_path)
            if not zip_check.is_valid:
                return PipelineResult(
                    status="failed",
                    minecraft_version=self.version,
                    original_request=request_clean,
                    understanding=understanding,
                    context=context,
                    plan=plan,
                    generation=gen_result,
                    validation=zip_check,
                    repair=repair_result,
                    errors=[f"Final ZIP validation failed: {e.message}" for e in zip_check.errors],
                    execution_summary="Pipeline failed: final ZIP archive failed validation."
                )

        _log("7/7", f"SUCCESS! Datapack created at: {final_gen_path}", self.verbose)
        if final_zip_path:
            _log("7/7", f"SUCCESS! Validated ZIP ready at: {final_zip_path}", self.verbose)

        return PipelineResult(
            status="success",
            minecraft_version=self.version,
            original_request=request_clean,
            understanding=understanding,
            context=context,
            plan=plan,
            generation=gen_result,
            validation=val_result,
            repair=repair_result,
            final_datapack_path=final_gen_path,
            final_zip_path=final_zip_path,
            execution_summary="Complete end-to-end pipeline succeeded. Datapack and ZIP validated."
        )


def run_minecraft_pipeline(
    request: str,
    minecraft_version: str = "1.21.11",
    provider: str = "ollama",
    create_zip: bool = True,
    output_dir: Optional[Path] = None,
    max_repair_attempts: int = 3,
    verbose: bool = True
) -> PipelineResult:
    """
    Public convenience entry point for the complete MinecraftAI pipeline.
    """
    pipeline = MinecraftPipeline(
        provider=provider,
        version=minecraft_version,
        output_dir=output_dir,
        max_repair_attempts=max_repair_attempts,
        verbose=verbose
    )
    return pipeline.run(request, create_zip=create_zip)
