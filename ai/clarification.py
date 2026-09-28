"""
ai/clarification.py - Step 17.4 Clarification Boundary Architecture

Provides a clean separation between:
1. Semantic interpretation (ai/numeric_interpreter.py)
2. Clarification analysis (ClarificationAnalyzer)
3. Clarification question generation (ClarificationQuestionGenerator)
4. Planner implementation (ai/planner.py)

Enforces structured, machine-readable ClarificationRequirement models
specifying exact missing semantic parameters, technical reasons, user-facing
questions, and actionable options without inventing implementations or commands.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict

from ai.semantic_models import PropertyModification
from ai.property_registry import DEFAULT_PROPERTY_REGISTRY, PropertyCapabilityRegistry


class ClarificationRequirement(BaseModel):
    """
    Structured, machine-readable specification of missing or ambiguous semantic information.
    """
    model_config = ConfigDict(extra="allow")

    parameter: str = Field(
        ...,
        description="Missing/ambiguous parameter: 'property', 'operation', 'value', 'target', etc."
    )
    reason: str = Field(
        ...,
        description="Technical explanation of why clarification is required"
    )
    question: str = Field(
        ...,
        description="Targeted, user-facing clarification question asking for specific information"
    )
    options: List[str] = Field(
        default_factory=list,
        description="Concrete selectable options or examples to resolve the ambiguity"
    )
    source_text: Optional[str] = Field(
        default=None,
        description="Source natural language phrase that produced the ambiguity"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional structured context (e.g. target entity, property name, extracted numbers)"
    )


class ClarificationIssue(BaseModel):
    """
    Intermediate representation of a detected semantic ambiguity or missing parameter.
    """
    model_config = ConfigDict(extra="allow")

    issue_type: str = Field(
        ...,
        description="Category: 'missing_property', 'missing_value', 'missing_operation', 'ambiguous_value', 'unknown_property'"
    )
    parameter: str = Field(
        ...,
        description="The target parameter: 'property', 'operation', or 'value'"
    )
    details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Structured context extracted from the semantic modification"
    )


class ClarificationAnalyzer:
    """
    Performs purely semantic clarification analysis on PropertyModification models.
    Identifies whether clarification is needed and what specific issue exists,
    isolated from natural language question templating and command generation.
    """

    def analyze(
        self,
        mod: PropertyModification,
        registry: Optional[PropertyCapabilityRegistry] = None,
    ) -> Optional[ClarificationIssue]:
        reg = registry or DEFAULT_PROPERTY_REGISTRY
        extra_meta = getattr(mod, "extra_metadata", None) or {}
        if not isinstance(extra_meta, dict):
            extra_meta = {}

        # 1. Check for missing property
        if "property" in mod.missing or mod.property is None:
            target = extra_meta.get("target") or "the entity"
            return ClarificationIssue(
                issue_type="missing_property",
                parameter="property",
                details={
                    "target": target,
                    "source_text": mod.source_text,
                    "raw_value": mod.value.model_dump() if mod.value else None,
                },
            )

        # 2. Check for qualitative requests
        is_qualitative = mod.value is not None and mod.value.kind == "qualitative"
        if is_qualitative:
            # If property is unknown, flag unknown property; otherwise qualitative intent is complete
            if not reg.is_known(mod.property):
                return ClarificationIssue(
                    issue_type="unknown_property",
                    parameter="property",
                    details={
                        "property": mod.property,
                        "source_text": mod.source_text,
                    },
                )
            # Valid qualitative request (e.g. "make me faster") -> NO clarification required!
            return None

        # 3. Check for missing operation (non-qualitative)
        if "operation" in mod.missing or mod.operation is None:
            return ClarificationIssue(
                issue_type="missing_operation",
                parameter="operation",
                details={
                    "property": mod.property,
                    "value": mod.value,
                    "source_text": mod.source_text,
                    "target": extra_meta.get("target"),
                },
            )

        # 4. Check for ambiguous numeric relationships (e.g. "faster by 10")
        if extra_meta.get("ambiguous"):
            return ClarificationIssue(
                issue_type="ambiguous_value",
                parameter="value",
                details={
                    "property": mod.property,
                    "ambiguous_number": extra_meta.get("ambiguous_number"),
                    "reason": extra_meta.get("reason"),
                    "source_text": mod.source_text,
                    "target": extra_meta.get("target"),
                },
            )

        # 5. Check for missing value magnitude (e.g. "increase speed")
        if "value" in mod.missing or mod.value is None or mod.value.kind == "missing":
            return ClarificationIssue(
                issue_type="missing_value",
                parameter="value",
                details={
                    "property": mod.property,
                    "operation": mod.operation,
                    "source_text": mod.source_text,
                    "target": extra_meta.get("target"),
                },
            )

        # 6. Check for unknown/unsupported property
        if not reg.is_known(mod.property):
            return ClarificationIssue(
                issue_type="unknown_property",
                parameter="property",
                details={
                    "property": mod.property,
                    "source_text": mod.source_text,
                    "target": extra_meta.get("target"),
                },
            )

        # Complete and valid request -> NO clarification required
        return None


class ClarificationQuestionGenerator:
    """
    Translates structured ClarificationIssue specifications into targeted,
    precise user-facing questions and options without generic ambiguity strings.
    Options and capabilities are dynamically sourced from PropertyCapabilityRegistry.
    """

    def __init__(self, registry: Optional[PropertyCapabilityRegistry] = None):
        self._registry = registry

    @staticmethod
    def _format_target_description(target: Any) -> str:
        if not target:
            return "the target"
        tgt_str = str(target).strip()
        if tgt_str.lower() in ("me", "my", "player", "@a", "@p", "@s"):
            return "the player"
        if tgt_str.startswith("@"):
            return tgt_str
        if tgt_str.lower().startswith(("the ", "a ", "an ")):
            return tgt_str
        return f"the {tgt_str}"

    def generate(
        self,
        issue: ClarificationIssue,
        registry: Optional[PropertyCapabilityRegistry] = None,
    ) -> ClarificationRequirement:
        reg = registry or self._registry or DEFAULT_PROPERTY_REGISTRY
        issue_type = issue.issue_type
        details = issue.details
        source_text = details.get("source_text")

        if issue_type == "missing_property":
            target = details.get("target")
            target_desc = self._format_target_description(target)

            reason = f"Target property is missing or underspecified for {target_desc}."
            question = (
                f"Which specific property of {target_desc} should be modified?"
            )
            options = reg.get_supported_properties()
            return ClarificationRequirement(
                parameter="property",
                reason=reason,
                question=question,
                options=options,
                source_text=source_text,
                metadata={"target": target, "issue_type": issue_type},
            )

        elif issue_type == "missing_value":
            prop = details.get("property")
            prop_desc = prop.replace("_", " ") if prop else "the property"
            op = details.get("operation")
            if op == "add":
                op_phrase = "increased"
            elif op == "subtract":
                op_phrase = "decreased"
            elif op == "set":
                op_phrase = "set"
            else:
                op_phrase = "modified"

            reason = f"Value magnitude or relationship is missing for property '{prop or prop_desc}'."
            question = f"By what amount, percentage, or multiplier should {prop_desc} be {op_phrase}?"
            options = ["amount (e.g. 5)", "percentage (e.g. 25%)", "multiplier (e.g. 2x)"]
            return ClarificationRequirement(
                parameter="value",
                reason=reason,
                question=question,
                options=options,
                source_text=source_text,
                metadata={"property": prop, "operation": op, "issue_type": issue_type},
            )

        elif issue_type == "missing_operation":
            prop = details.get("property")
            prop_desc = prop.replace("_", " ") if prop else "the property"
            val = details.get("value")
            val_num = getattr(val, "value", None)
            val_phrase = f" by {val_num}" if val_num is not None else ""

            reason = f"Operation is missing or unspecified for property '{prop or prop_desc}'."
            question = f"How should {prop_desc} be modified{val_phrase} (e.g. add, subtract, multiply, or set)?"
            options = ["add", "subtract", "multiply", "set"]
            return ClarificationRequirement(
                parameter="operation",
                reason=reason,
                question=question,
                options=options,
                source_text=source_text,
                metadata={"property": prop, "value": val_num, "issue_type": issue_type},
            )

        elif issue_type == "ambiguous_value":
            prop = details.get("property")
            prop_desc = prop.replace("_", " ") if prop else "the property"
            num = details.get("ambiguous_number")
            reason = details.get(
                "reason",
                f"Ambiguous numeric relationship: '{source_text}' does not specify whether the number is relative (+), multiplier (x), or percentage (%)."
            )
            if num is not None:
                question = (
                    f"Ambiguous numeric relationship for {prop_desc}: does '{source_text or f'{prop_desc} by {num}'}' "
                    f"mean an increase of {num} points (+{num}), {num}x multiplier, or a {num}% boost?"
                )
                options = [f"+{num} points", f"{num}x multiplier", f"+{num}% boost"]
            else:
                question = (
                    f"Ambiguous numeric relationship for {prop_desc}: does '{source_text}' "
                    f"specify a relative change (+/-), multiplier (x), or percentage (%)?"
                )
                options = ["relative (+/-)", "multiplier (x)", "percentage (%)"]

            return ClarificationRequirement(
                parameter="value",
                reason=reason,
                question=question,
                options=options,
                source_text=source_text,
                metadata={"property": prop, "ambiguous_number": num, "issue_type": issue_type},
            )

        elif issue_type == "unknown_property":
            prop = details.get("property")
            prop_display = f"'{prop}'" if prop else "The requested property"
            reason = f"Property {prop_display} is not recognized or supported by Minecraft implementation mechanisms."
            question = (
                f"Property {prop_display} is not recognized or supported in Minecraft Java Edition. "
                f"Which standard property should be modified?"
            )
            options = reg.get_supported_properties()
            return ClarificationRequirement(
                parameter="property",
                reason=reason,
                question=question,
                options=options,
                source_text=source_text,
                metadata={"property": prop, "unknown": True, "issue_type": issue_type},
            )

        # Fallback for generic issues
        return ClarificationRequirement(
            parameter=issue.parameter,
            reason="Ambiguous or incomplete semantic request.",
            question="Please clarify the requested Minecraft modification parameters.",
            options=[],
            source_text=source_text,
            metadata={"issue_type": issue_type},
        )


class SemanticClarificationEngine:
    """
    Coordinating clarification engine providing high-level analysis and question generation.
    """

    def __init__(
        self,
        analyzer: Optional[ClarificationAnalyzer] = None,
        generator: Optional[ClarificationQuestionGenerator] = None,
        registry: Optional[PropertyCapabilityRegistry] = None,
    ):
        self.analyzer = analyzer or ClarificationAnalyzer()
        self.registry = registry or DEFAULT_PROPERTY_REGISTRY
        self.generator = generator or ClarificationQuestionGenerator(registry=self.registry)

    def analyze_modification(
        self,
        mod: PropertyModification,
        registry: Optional[PropertyCapabilityRegistry] = None,
    ) -> Optional[ClarificationRequirement]:
        """
        Analyzes a single PropertyModification. Returns a ClarificationRequirement
        if clarification is needed, or None if the modification is complete.
        """
        reg = registry or self.registry or DEFAULT_PROPERTY_REGISTRY
        issue = self.analyzer.analyze(mod, registry=reg)
        if issue is None:
            return None
        return self.generator.generate(issue, registry=reg)

    def analyze_modifications(
        self,
        mods: List[PropertyModification],
        registry: Optional[PropertyCapabilityRegistry] = None,
    ) -> List[ClarificationRequirement]:
        """
        Analyzes a list of PropertyModifications, returning all required ClarificationRequirements.
        """
        reg = registry or self.registry or DEFAULT_PROPERTY_REGISTRY
        requirements: List[ClarificationRequirement] = []
        for mod in mods:
            req = self.analyze_modification(mod, registry=reg)
            if req:
                requirements.append(req)
        return requirements

    def is_qualitative_complete(
        self,
        mod: PropertyModification,
        registry: Optional[PropertyCapabilityRegistry] = None,
    ) -> bool:
        """
        Returns True if the modification is a valid qualitative request that does
        not require arithmetic operations or clarification.
        """
        if mod.value is None or mod.value.kind != "qualitative":
            return False
        reg = registry or DEFAULT_PROPERTY_REGISTRY
        return mod.property is not None and reg.is_known(mod.property)


# Module-level default clarification engine instance
DEFAULT_CLARIFICATION_ENGINE = SemanticClarificationEngine()
