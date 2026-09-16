from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from validator.models import ValidationIssue, ValidationResult


class RepairAttempt(BaseModel):
    """
    Diagnostic record of a single repair attempt within the AI repair loop.
    """
    model_config = ConfigDict(extra="allow")

    attempt_number: int = Field(
        ...,
        description="1-indexed sequence number of this repair attempt"
    )
    validation_status: str = Field(
        ...,
        description="'valid' or 'invalid'"
    )
    validator_errors: List[ValidationIssue] = Field(
        default_factory=list,
        description="Structured validator errors encountered before or during this attempt"
    )
    repair_reasoning: str = Field(
        default="",
        description="AI reasoning explaining the root cause and proposed correction"
    )
    plan: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Corrected implementation plan produced by the AI for this attempt"
    )
    datapack_path: Optional[str] = Field(
        default=None,
        description="Filesystem path of the datapack directory or ZIP generated in this attempt"
    )


class RepairPlan(BaseModel):
    """
    Structured output schema returned by the AI repair engine.
    Conforms to the planner result structure with additional diagnostic reasoning and modifications.
    """
    model_config = ConfigDict(extra="allow")

    repair_reasoning: str = Field(
        ...,
        description="Detailed diagnosis of validator errors and explanation of how the corrected plan resolves them"
    )
    status: str = Field(
        default="ready",
        description="'ready' or 'failed'"
    )
    minecraft_version: str = Field(
        default="1.21.11",
        description="Target Minecraft Java Edition version"
    )
    summary: str = Field(
        ...,
        description="Summary of the repaired implementation plan"
    )
    implementation_plan: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Corrected implementation plan blocks containing objectives, mechanisms, steps, and resources"
    )
    missing_knowledge: List[str] = Field(
        default_factory=list,
        description="Any missing Minecraft knowledge that prevented complete planning"
    )
    clarifications: List[str] = Field(
        default_factory=list,
        description="Clarifications if the request remains ambiguous"
    )
    modifications: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Optional list of explicit corrected loot table modifications (loot_table_path, item, count)"
    )


class RepairResult(BaseModel):
    """
    Final result returned by the AI Repair Loop.
    """
    model_config = ConfigDict(extra="allow")

    status: str = Field(
        ...,
        description="'success', 'failed', or 'skipped' (if initial datapack was already valid)"
    )
    attempts: List[RepairAttempt] = Field(
        default_factory=list,
        description="Full sequential history of all repair attempts performed"
    )
    final_datapack_path: Optional[str] = Field(
        default=None,
        description="Path to the final datapack directory or ZIP archive"
    )
    final_validation: Optional[ValidationResult] = Field(
        default=None,
        description="Final ValidationResult after the last attempt"
    )
    total_attempts: int = Field(
        default=0,
        description="Total number of repair iterations executed"
    )
    message: Optional[str] = Field(
        default=None,
        description="Human-readable outcome summary"
    )

    @property
    def is_success(self) -> bool:
        return self.status in ("success", "skipped")

    def summary(self) -> str:
        lines = [
            f"Repair Loop Result: {self.status.upper()}",
            f"Total Attempts: {self.total_attempts}",
            f"Final Target: {self.final_datapack_path or 'None'}",
            f"Outcome: {self.message or 'N/A'}"
        ]
        if self.attempts:
            lines.append("\nAttempt History:")
            for att in self.attempts:
                status_label = att.validation_status.upper()
                lines.append(
                    f"  - Attempt #{att.attempt_number} [{status_label}]: "
                    f"Errors: {len(att.validator_errors)}, "
                    f"Reasoning: {att.repair_reasoning[:80]}..."
                )
        return "\n".join(lines)
