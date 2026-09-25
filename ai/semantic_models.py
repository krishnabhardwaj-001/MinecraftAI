"""
Step 17.1 semantic modification contracts.

This module represents generic property modifications before Minecraft-specific
implementation is selected. It deliberately does not encode Minecraft command
syntax or effect/attribute-specific behavior.
"""

from typing import Any, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


MODIFICATION_OPERATIONS = {
    "set",
    "add",
    "subtract",
    "multiply",
    "divide",
}

VALUE_KINDS = {
    "absolute",
    "relative",
    "percentage",
    "multiplier",
    "qualitative",
    "missing",
}

MISSING_PARAMETER_TYPES = {
    "property",
    "operation",
    "value",
}


class MissingSemanticParameter(BaseModel):
    """A typed semantic parameter that is required but not yet known."""

    model_config = ConfigDict(extra="allow")

    parameter: str = Field(
        ...,
        description="Missing semantic parameter: property, operation, or value",
    )
    reason: Optional[str] = Field(
        default=None,
        description="Why this parameter is required",
    )

    @field_validator("parameter")
    @classmethod
    def validate_parameter(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in MISSING_PARAMETER_TYPES:
            raise ValueError(
                f"Invalid missing semantic parameter '{value}'. "
                f"Supported parameters: {sorted(MISSING_PARAMETER_TYPES)}"
            )
        return value


class SemanticNumericValue(BaseModel):
    """
    Generic value representation.

    Examples:
      10              -> absolute, 10
      increase by 5  -> relative, 5
      50%             -> percentage, 50
      2x              -> multiplier, 2
      unknown amount -> missing, None
    """

    model_config = ConfigDict(extra="allow")

    kind: str = Field(
        ...,
        description=(
            "Value interpretation: absolute, relative, percentage, "
            "multiplier, qualitative, or missing"
        ),
    )
    value: Optional[Union[int, float]] = Field(
        default=None,
        description="Numeric value when the kind is numeric",
    )
    unit: Optional[str] = Field(
        default=None,
        description="Optional unit preserved from semantic parsing",
    )

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in VALUE_KINDS:
            raise ValueError(
                f"Invalid semantic value kind '{value}'. "
                f"Supported kinds: {sorted(VALUE_KINDS)}"
            )
        return value

    @model_validator(mode="after")
    def validate_value(self) -> "SemanticNumericValue":
        if self.kind in {"absolute", "relative", "percentage", "multiplier"}:
            if self.value is None:
                raise ValueError(
                    f"Value kind '{self.kind}' requires a numeric value."
                )
        elif self.kind in {"qualitative", "missing"}:
            if self.value is not None:
                raise ValueError(
                    f"Value kind '{self.kind}' cannot contain a numeric value."
                )
        return self


class PropertyModification(BaseModel):
    """
    Generic semantic property modification.

    This is intentionally Minecraft-independent. It answers:
      - what property is being changed?
      - how is it being changed?
      - what kind of value was supplied?
      - is anything still missing?

    Minecraft-specific implementation belongs to the Planner/knowledge layer
    and deterministic generator, not this contract.
    """

    model_config = ConfigDict(extra="allow")

    type: str = Field(
        default="property_modification",
        description="Semantic contract type identifier",
    )
    property: Optional[str] = Field(
        default=None,
        description="Semantic property being modified",
    )
    operation: Optional[str] = Field(
        default=None,
        description="Modification operation: set/add/subtract/multiply/divide",
    )
    value: Optional[SemanticNumericValue] = Field(
        default=None,
        description="Structured value representation",
    )
    missing: List[MissingSemanticParameter] = Field(
        default_factory=list,
        description="Typed semantic parameters still required",
    )
    source_text: Optional[str] = Field(
        default=None,
        description="Original phrase retained for traceability",
    )

    @field_validator("property")
    @classmethod
    def normalize_property(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("operation")
    @classmethod
    def validate_operation(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip().lower()
        if value not in MODIFICATION_OPERATIONS:
            raise ValueError(
                f"Invalid modification operation '{value}'. "
                f"Supported operations: {sorted(MODIFICATION_OPERATIONS)}"
            )
        return value

    @model_validator(mode="after")
    def validate_contract(self) -> "PropertyModification":
        missing_names = {item.parameter for item in self.missing}

        if self.property is None and "property" not in missing_names:
            raise ValueError(
                "PropertyModification requires 'property' or a typed "
                "'property' missing parameter."
            )

        if self.operation is None and "operation" not in missing_names:
            raise ValueError(
                "PropertyModification requires 'operation' or a typed "
                "'operation' missing parameter."
            )

        if self.value is None and "value" not in missing_names:
            raise ValueError(
                "PropertyModification requires 'value' or a typed "
                "'value' missing parameter."
            )

        if self.value is not None and self.value.kind == "missing":
            if "value" not in missing_names:
                raise ValueError(
                    "A 'missing' value kind must also declare a typed "
                    "'value' missing parameter."
                )

        return self
