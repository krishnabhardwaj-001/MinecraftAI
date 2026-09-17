from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
# pyrefly: ignore [missing-import]
from pydantic import BaseModel, ConfigDict, Field


class QASeverity(str, Enum):
    """
    Severity level of a QA finding.
    """
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class QACategory(str, Enum):
    """
    Categories of QA findings for autonomous semantic and runtime review.
    """
    FILE_COMPLETENESS = "file_completeness"
    REFERENCE_INTEGRITY = "reference_integrity"
    COMMAND_SEMANTICS = "command_semantics"
    EXECUTION_CONTEXT = "execution_context"
    STATE_MACHINE = "state_machine"
    INITIALIZATION = "initialization"
    TIMING = "timing"
    VERSION_SEMANTICS = "version_semantics"
    INTENT_MISMATCH = "intent_mismatch"
    UNREACHABLE_LOGIC = "unreachable_logic"
    DEAD_LOGIC = "dead_logic"
    RESOURCE_MISMATCH = "resource_mismatch"
    OTHER = "other"


class QAFinding(BaseModel):
    """
    Detailed, structured finding from the Autonomous QA Reviewer.
    """
    model_config = ConfigDict(extra="allow")

    id: str = Field(
        ...,
        description="Unique identifier for this finding (e.g. 'FIND-CTX-001')"
    )
    severity: QASeverity = Field(
        ...,
        description="Severity level: 'error' blocks release; 'warning' documents risks; 'info' provides context"
    )
    category: QACategory = Field(
        ...,
        description="Functional category of the finding"
    )
    file: Optional[str] = Field(
        default=None,
        description="Relative path of the generated datapack resource where the problem was detected"
    )
    line_or_reference: Optional[str] = Field(
        default=None,
        description="Line number, command snippet, or resource ID involved"
    )
    problem: str = Field(
        ...,
        description="Concise description of the semantic or runtime failure"
    )
    explanation: str = Field(
        ...,
        description="Detailed technical reasoning based on Minecraft 1.21.11 execution semantics"
    )
    expected_behavior: str = Field(
        ...,
        description="What the datapack should do according to the intent and specification"
    )
    evidence: Optional[str] = Field(
        default=None,
        description="Authoritative evidence (e.g. server bytecode class, command schema, runtime log)"
    )
    repair_required: Optional[str] = Field(
        default=None,
        description="High-level architectural modification required to resolve this problem"
    )


class IntentVerificationResult(BaseModel):
    """
    Structured outcome of comparing the generated datapack against the original user request.
    """
    model_config = ConfigDict(extra="allow")

    matches_intent: bool = Field(
        ...,
        description="True if the implementation fulfills the user's intent without critical omissions or side-effects"
    )
    confidence: float = Field(
        default=1.0,
        description="Confidence score from 0.0 to 1.0"
    )
    reasoning: str = Field(
        ...,
        description="Detailed comparison between the original prompt/clarification and the final command logic"
    )
    missing_aspects: List[str] = Field(
        default_factory=list,
        description="Requested requirements or constraints that are absent from the implementation"
    )
    unwanted_aspects: List[str] = Field(
        default_factory=list,
        description="Unrequested actions, continuous triggers, or unintended side-effects introduced"
    )


class QAResult(BaseModel):
    """
    Complete structured result returned by the Autonomous QA Reviewer.
    """
    model_config = ConfigDict(extra="allow")

    status: str = Field(
        ...,
        description="'passed', 'failed', or 'warning'"
    )
    summary: str = Field(
        ...,
        description="Concise human-readable summary of the review findings and status"
    )
    findings: List[QAFinding] = Field(
        default_factory=list,
        description="List of all detected QA findings across all categories"
    )
    intent_verification: Optional[IntentVerificationResult] = Field(
        default=None,
        description="Verification comparison against original user intent"
    )
    static_semantic_verification: str = Field(
        default="passed",
        description="'passed' or 'failed'"
    )
    runtime_verification: str = Field(
        default="not_available",
        description="'passed', 'failed', or 'not_available'"
    )

    @property
    def is_pass(self) -> bool:
        """
        True only if there are no ERROR-severity findings and intent verification passes.
        """
        has_errors = any(f.severity == QASeverity.ERROR for f in self.findings)
        intent_ok = self.intent_verification.matches_intent if self.intent_verification else True
        runtime_ok = self.runtime_verification != "failed"
        return (not has_errors) and intent_ok and runtime_ok

    @property
    def error_findings(self) -> List[QAFinding]:
        return [f for f in self.findings if f.severity == QASeverity.ERROR]

    @property
    def warning_findings(self) -> List[QAFinding]:
        return [f for f in self.findings if f.severity == QASeverity.WARNING]


class QARepairPlan(BaseModel):
    """
    Structured repair plan produced by the AI Diagnosis & Repair layer in response to QA failures.
    Specifies changes to the planner's mechanism specifications, NOT raw arbitrary file edits.
    """
    model_config = ConfigDict(extra="allow")

    diagnosis: str = Field(
        ...,
        description="Root cause diagnosis explaining why QA failed and what architectural change is required"
    )
    summary: str = Field(
        ...,
        description="High-level summary of the proposed repair"
    )
    mechanism_modifications: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Updated or replacement MechanismSpecification dictionaries for deterministic regeneration"
    )
    state_machine_guidance: Optional[str] = Field(
        default=None,
        description="Specific instructions for scoreboard objectives, persistent holders, or execution contexts"
    )
    regenerate: bool = Field(
        default=True,
        description="Whether deterministic regeneration should be triggered"
    )
