"""
eval/models.py - Pydantic Models for Automated Evaluation Benchmark (Step 22B)

Defines structured data contracts for:
1. BenchmarkCase: Specification of a benchmark evaluation item.
2. CaseEvaluationResult: Outcome of evaluating a single benchmark case.
3. BenchmarkSummary: Aggregated benchmark report with category metrics and timing.
"""

from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, ConfigDict


class BenchmarkCase(BaseModel):
    """
    Specification of a single benchmark case in the evaluation dataset.
    """
    model_config = ConfigDict(extra="allow")

    id: str = Field(..., description="Unique deterministic case identifier (e.g. 'case_01_loot_creeper')")
    category: str = Field(..., description="Capability category (e.g. 'mob_loot', 'functions', 'predicates')")
    request: str = Field(..., description="Natural-language request text")
    description: Optional[str] = Field(default=None, description="Human-readable description of the case")

    # Expected semantic and implementation specifications
    expected_mechanism: Optional[str] = Field(
        default=None,
        description="Expected primary datapack mechanism ('loot_table', 'function', 'function_tag', 'advancement', 'recipe', 'predicate', 'state_machine', 'attribute', 'scoreboard_objective')"
    )
    expected_property: Optional[str] = Field(
        default=None,
        description="Expected semantic property name (e.g. 'speed', 'attack_damage', 'health', 'scale')"
    )
    expected_operation: Optional[str] = Field(
        default=None,
        description="Expected semantic operation ('multiply', 'add', 'subtract', 'set')"
    )
    expected_value_kind: Optional[str] = Field(
        default=None,
        description="Expected semantic value kind ('multiplier', 'relative', 'percentage', 'absolute', 'qualitative')"
    )
    expected_value: Optional[Union[float, int, str]] = Field(
        default=None,
        description="Expected numeric or qualitative value"
    )
    expected_target: Optional[str] = Field(
        default=None,
        description="Expected target entity selector or mob name"
    )

    # Clarification expectations
    requires_clarification: bool = Field(
        default=False,
        description="True if request is ambiguous or underspecified and requires clarification"
    )
    expected_clarification_parameter: Optional[str] = Field(
        default=None,
        description="Expected parameter requiring clarification ('duration', 'property', 'value', 'operation')"
    )

    # Validation and support flags
    expect_validation_success: bool = Field(
        default=True,
        description="True if generated datapack should pass structural and QA validation"
    )
    is_supported: bool = Field(
        default=True,
        description="True if the request is within supported Minecraft 1.21.11 capabilities"
    )
    is_compound: bool = Field(
        default=False,
        description="True if the request consists of multiple independent subparts"
    )

    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional case-specific metadata"
    )


class CaseEvaluationResult(BaseModel):
    """
    Outcome of evaluating a single benchmark case.
    """
    model_config = ConfigDict(extra="allow")

    case_id: str
    category: str
    request: str
    passed: bool
    semantic_interpretation_passed: bool
    clarification_passed: bool
    implementation_passed: bool
    validation_passed: bool
    qa_passed: bool
    intent_passed: bool
    repair_attempts: int = 0
    duration_ms: float = 0.0
    details: str = ""
    errors: List[str] = Field(default_factory=list)


class BenchmarkSummary(BaseModel):
    """
    Aggregated summary of an evaluation benchmark run.
    """
    model_config = ConfigDict(extra="allow")

    total_cases: int
    passed_cases: int
    failed_cases: int
    clarification_cases: int
    validation_failures: int
    qa_failures: int
    intent_failures: int
    repair_attempts: int
    average_duration_ms: float
    category_metrics: Dict[str, Dict[str, Any]]
    results: List[CaseEvaluationResult]
