import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from ai.provider import AIProvider
from generator.datapack_generator import DatapackGenerator
from generator.models import GenerationResult
from knowledge_retriever import MinecraftKnowledgeRetriever
from repair.models import RepairAttempt, RepairPlan, RepairResult
from validator.datapack_validator import DatapackValidator
from validator.models import ValidationResult


class AIRepairLoop:
    """
    Step 7: AI Repair Loop for Minecraft Java Edition 1.21.11.

    When the deterministic datapack generator produces an invalid datapack,
    this module feeds structured validator errors and Minecraft knowledge
    to the AI to diagnose the failure and produce a corrected implementation plan.
    The corrected plan is then passed back to the deterministic generator
    and re-tested by the validator.
    """

    def __init__(
        self,
        ai_provider: Optional[AIProvider] = None,
        provider: str = "ollama",
        max_attempts: int = 3,
        version: str = "1.21.11",
        generator: Optional[DatapackGenerator] = None,
        validator: Optional[DatapackValidator] = None
    ):
        self.version = version
        self.max_attempts = max_attempts
        self.provider_name = provider

        # Use existing AI provider abstraction
        self.ai = ai_provider or AIProvider(provider=provider)

        # Connect generator and validator
        self.generator = generator or DatapackGenerator(version=version)
        self.validator = validator or DatapackValidator(version=version)

        # Minecraft knowledge retriever for enriching repair context
        self.retriever = MinecraftKnowledgeRetriever(version=version)

    def _system_prompt(self) -> str:
        return f"""You are the AI REPAIR ENGINE of an automatic Minecraft Java Edition datapack generator.

Target:
- Edition: Minecraft Java Edition
- Version: {self.version}
- Pack Format: 94

CONTEXT:
A previously generated datapack failed deterministic validation.
Your job is to:
1. Examine the structured validator errors and warnings.
2. Cross-reference them with the user's requirements and retrieved Minecraft knowledge.
3. Diagnose the root cause of each failure in `repair_reasoning`.
4. Produce a corrected implementation plan that resolves all validation errors.

STRICT ARCHITECTURAL RULES:
1. You must NOT output raw datapack files, directories, or arbitrary JSON files directly.
2. The deterministic datapack generator will build all files from your corrected plan.
3. You must use valid Minecraft Java {self.version} identifiers (e.g. item IDs must exist in Minecraft, loot table paths must follow 1.21+ singular conventions).
4. If modifying loot tables, provide explicit `modifications` with:
   - `loot_table_path`: relative path (e.g. "entities/creeper.json")
   - `item`: valid Minecraft item ID (e.g. "minecraft:diamond")
   - `count`: drop count integer (e.g. 1)
   - `operation`: "add_pool"
5. Do NOT invent unrequested features. Strictly adhere to the user's intent.
"""

    def _build_repair_prompt(
        self,
        understanding: Dict[str, Any],
        context: Dict[str, Any],
        plan: Optional[Dict[str, Any]],
        val_result: ValidationResult
    ) -> str:
        prompt_parts: List[str] = []

        prompt_parts.append("=== ORIGINAL USER UNDERSTANDING & REQUIREMENTS ===")
        req_summary = {
            "understood_request": understanding.get("understood_request", ""),
            "requirements": understanding.get("requirements", [])
        }
        prompt_parts.append(json.dumps(req_summary, indent=2))

        prompt_parts.append("\n=== STRUCTURED VALIDATOR ERRORS ===")
        if val_result.errors:
            for idx, err in enumerate(val_result.errors, 1):
                loc = f" (File: {err.file})" if err.file else ""
                prompt_parts.append(f"  Error {idx}: [{err.code}]{loc} {err.message}")
        else:
            prompt_parts.append("  No specific errors reported.")

        if val_result.warnings:
            prompt_parts.append("\n=== VALIDATOR WARNINGS ===")
            for idx, warn in enumerate(val_result.warnings, 1):
                loc = f" (File: {warn.file})" if warn.file else ""
                prompt_parts.append(f"  Warning {idx}: [{warn.code}]{loc} {warn.message}")

        prompt_parts.append("\n=== PREVIOUS FAILED PLAN ===")
        if plan:
            prev_plan_summary = {
                "summary": plan.get("summary", ""),
                "implementation_plan": plan.get("implementation_plan", [])
            }
            prompt_parts.append(json.dumps(prev_plan_summary, indent=2))
        else:
            prompt_parts.append("  No previous plan recorded.")

        prompt_parts.append("\n=== RETRIEVED MINECRAFT KNOWLEDGE ===")
        knowledge = context.get("knowledge", {})
        retrieved_items = knowledge.get("items", [])
        retrieved_tables = knowledge.get("loot_tables", [])
        retrieved_entities = knowledge.get("entities", [])

        if retrieved_items:
            prompt_parts.append("Relevant Minecraft Items:")
            for item in retrieved_items[:10]:
                prompt_parts.append(f"  - ID: {item.get('id')} ({item.get('name', '')})")

        if retrieved_tables:
            prompt_parts.append("Relevant Loot Tables:")
            for table in retrieved_tables[:5]:
                prompt_parts.append(f"  - Path: {table.get('path')}")

        if retrieved_entities:
            prompt_parts.append("Relevant Entities:")
            for entity in retrieved_entities[:5]:
                prompt_parts.append(f"  - ID: {entity.get('id')}, Loot Table: {entity.get('loot_table')}")

        prompt_parts.append(
            "\nTASK:\n"
            "Diagnose the validation errors and output a corrected RepairPlan JSON matching the schema.\n"
            "Explain your reasoning in `repair_reasoning` and specify the corrected resources/modifications."
        )

        return "\n".join(prompt_parts)

    def _normalize_repair_plan(
        self,
        raw_result: Any,
        understanding: Dict[str, Any]
    ) -> RepairPlan:
        """
        Validates and normalizes raw AI output into a guaranteed RepairPlan model.
        """
        if not isinstance(raw_result, dict):
            raise ValueError(f"Expected AI output to be a dictionary, got {type(raw_result)}")

        reasoning = str(raw_result.get("repair_reasoning", "")).strip()
        if not reasoning:
            reasoning = "Corrected implementation plan based on validator feedback."

        summary = str(raw_result.get("summary", "")).strip()
        if not summary:
            summary = understanding.get("understood_request", "Repaired datapack implementation")

        status = str(raw_result.get("status", "ready")).lower()
        if status not in ("ready", "failed"):
            status = "ready"

        imp_plan = raw_result.get("implementation_plan", [])
        if not isinstance(imp_plan, list):
            imp_plan = []

        modifications = raw_result.get("modifications")
        if modifications is not None and not isinstance(modifications, list):
            modifications = None

        return RepairPlan(
            repair_reasoning=reasoning,
            status=status,
            minecraft_version=self.version,
            summary=summary,
            implementation_plan=imp_plan,
            missing_knowledge=raw_result.get("missing_knowledge", []),
            clarifications=raw_result.get("clarifications", []),
            modifications=modifications
        )

    def repair(
        self,
        understanding: Dict[str, Any],
        context: Dict[str, Any],
        planner_result: Optional[Dict[str, Any]],
        generation_result: GenerationResult,
        validator_result: ValidationResult,
        datapack_name: Optional[str] = None
    ) -> RepairResult:
        """
        Executes the AI repair loop with configurable retry protection.

        1. If validator_result is already valid, immediately returns skipped (0 attempts).
        2. If invalid, iteratively queries AI for repair, regenerates, and re-validates.
        3. Returns successful RepairResult on first valid pass, or structured failure history
           if max_attempts is exhausted.
        """
        # Step 3 requirement: Only invoke AI repair when validation fails.
        if validator_result.is_valid:
            return RepairResult(
                status="skipped",
                attempts=[],
                final_datapack_path=str(generation_result.datapack_path),
                final_validation=validator_result,
                total_attempts=0,
                message="Initial datapack passed validation. Zero repair attempts required."
            )

        attempts: List[RepairAttempt] = []
        current_plan = planner_result
        current_val_result = validator_result
        current_gen_result = generation_result
        current_context = context

        target_name = datapack_name or generation_result.datapack_name

        for attempt_idx in range(1, self.max_attempts + 1):
            # 1. Build prompt containing validator errors and knowledge
            system_prompt = self._system_prompt()
            user_prompt = self._build_repair_prompt(
                understanding=understanding,
                context=current_context,
                plan=current_plan,
                val_result=current_val_result
            )

            # 2. Invoke AI provider to generate structured repair plan
            try:
                raw_response = self.ai.generate_structured(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    schema=RepairPlan.model_json_schema()
                )
            except Exception as ai_err:
                attempt_record = RepairAttempt(
                    attempt_number=attempt_idx,
                    repaired_plan=RepairPlan(
                        status="error",
                        minecraft_version=self.version,
                        summary=f"AI generation failed: {ai_err}",
                        repair_reasoning=f"AI provider failed during repair: {ai_err}"
                    ),
                    validation_status="failed",
                    errors=[f"AI generation error: {ai_err}"]
                )
                attempts.append(attempt_record)
                continue

            # 3. Normalize into RepairPlan
            repair_plan = self._normalize_repair_plan(
                raw_result=raw_response,
                understanding=understanding
            )

            repaired_plan_dict = {
                "status": repair_plan.status,
                "minecraft_version": repair_plan.minecraft_version,
                "summary": repair_plan.summary,
                "implementation_plan": repair_plan.implementation_plan,
                "missing_knowledge": repair_plan.missing_knowledge,
                "clarifications": repair_plan.clarifications,
            }
            if repair_plan.modifications:
                repaired_plan_dict["modifications"] = repair_plan.modifications

            # 4. Clean previous target directory before regeneration
            target_dir = self.generator.output_dir / target_name
            if target_dir.exists():
                shutil.rmtree(target_dir, ignore_errors=True)

            # 5. Deterministic regeneration using existing generator
            try:
                new_gen_result = self.generator.generate(
                    plan=repaired_plan_dict,
                    context=current_context,
                    understanding=understanding,
                    datapack_name=target_name,
                    create_zip=True
                )
            except Exception as gen_err:
                attempt_record = RepairAttempt(
                    attempt_number=attempt_idx,
                    repaired_plan=repair_plan,
                    validation_status="failed",
                    errors=[f"Regeneration error: {gen_err}"]
                )
                attempts.append(attempt_record)
                continue

            # 6. Re-validate generated output
            new_val_result = self.validator.validate(new_gen_result.datapack_path)
            if new_gen_result.zip_path and new_val_result.is_valid:
                zip_val_result = self.validator.validate(new_gen_result.zip_path)
                if not zip_val_result.is_valid:
                    new_val_result = zip_val_result

            # 7. Record attempt history (Requirement 10)
            attempt_record = RepairAttempt(
                attempt_number=attempt_idx,
                validation_status="valid" if new_val_result.is_valid else "invalid",
                validator_errors=list(new_val_result.errors),
                repair_reasoning=repair_plan.repair_reasoning,
                plan=repaired_plan_dict,
                datapack_path=str(new_gen_result.datapack_path)
            )
            attempts.append(attempt_record)

            # Update tracking references
            current_plan = repaired_plan_dict
            current_gen_result = new_gen_result
            current_val_result = new_val_result

            # 8. Check for success (Requirement 11)
            if new_val_result.is_valid:
                return RepairResult(
                    status="success",
                    attempts=attempts,
                    final_datapack_path=str(new_gen_result.datapack_path),
                    final_validation=new_val_result,
                    total_attempts=len(attempts),
                    message=f"Datapack successfully repaired and validated on attempt #{attempt_idx}."
                )

        # 9. Exhausted retries without success (Requirement 12)
        return RepairResult(
            status="failed",
            attempts=attempts,
            final_datapack_path=str(current_gen_result.datapack_path) if current_gen_result else None,
            final_validation=current_val_result,
            total_attempts=len(attempts),
            message=f"Repair failed after {self.max_attempts} attempts. Validation errors remain."
        )
