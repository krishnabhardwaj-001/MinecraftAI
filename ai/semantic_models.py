"""
ai/semantic_models.py - Generic Semantic Property Modification Models (Step 17.1)

Defines Minecraft-independent semantic data contracts for representing property
modifications, arithmetic operations, and value scales extracted from natural language.

These models do not contain Minecraft command syntax or implementation choices
(such as effects vs. attributes vs. scoreboards).
"""

from typing import Any, Dict, List, Optional, Set, Union
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator


SUPPORTED_OPERATIONS: Set[str] = {
    "set",
    "add",
    "subtract",
    "multiply",
    "divide",
}

SUPPORTED_VALUE_KINDS: Set[str] = {
    "absolute",
    "relative",
    "percentage",
    "multiplier",
    "qualitative",
    "missing",
}

NUMERIC_VALUE_KINDS: Set[str] = {
    "absolute",
    "relative",
    "percentage",
    "multiplier",
}

TYPED_MISSING_PARAMETERS: Set[str] = {
    "property",
    "operation",
    "value",
}


class SemanticValue(BaseModel):
    """
    Represents the semantic value of a property modification.
    Supports numeric magnitudes (absolute, relative, percentage, multiplier),
    qualitative descriptors, and explicitly missing values.
    """
    model_config = ConfigDict(extra="allow")

    kind: str = Field(
        ...,
        description="Value kind: 'absolute', 'relative', 'percentage', 'multiplier', 'qualitative', or 'missing'"
    )
    value: Optional[Union[int, float, str]] = Field(
        default=None,
        description="Numeric value for numeric kinds, descriptor string for qualitative, or None for missing"
    )
    unit: Optional[str] = Field(
        default=None,
        description="Optional unit of measurement (e.g. '%', 'seconds', 'points')"
    )

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("Value kind must be a non-empty string.")
        clean = v.strip().lower()
        if clean not in SUPPORTED_VALUE_KINDS:
            raise ValueError(
                f"Unsupported value kind: '{v}'. Must be one of {sorted(list(SUPPORTED_VALUE_KINDS))}."
            )
        return clean

    @field_validator("value", mode="before")
    @classmethod
    def validate_value_raw(cls, v: Any) -> Any:
        if isinstance(v, bool):
            raise ValueError("Semantic value cannot be a boolean.")
        return v

    @model_validator(mode="after")
    def validate_value_constraints(self) -> "SemanticValue":
        # 1. Reject boolean values explicitly (since isinstance(True, int) is True in Python)
        if isinstance(self.value, bool):
            raise ValueError("Semantic value cannot be a boolean.")

        # 2. Numeric kinds require a numeric value
        if self.kind in NUMERIC_VALUE_KINDS:
            if self.value is None:
                raise ValueError(
                    f"Numeric value kind '{self.kind}' requires a numeric value, got None."
                )
            if not isinstance(self.value, (int, float)):
                raise ValueError(
                    f"Numeric value kind '{self.kind}' requires an int or float, got {type(self.value).__name__} ('{self.value}')."
                )

        # 3. 'missing' kind cannot have a numeric or other value
        elif self.kind == "missing":
            if self.value is not None:
                raise ValueError(
                    f"'missing' value kind cannot have a value, got {self.value}."
                )

        return self


class SemanticNumericValue(SemanticValue):
    """
    Semantic value model representing numeric values, multipliers, percentages,
    or explicit missing values.
    """
    pass


class PropertyModification(BaseModel):
    """
    Structured, Minecraft-independent representation of a semantic property modification.

    Examples:
      - 'make me 10 times faster' -> property='speed', operation='multiply', value=SemanticNumericValue(kind='multiplier', value=10)
      - 'increase zombie attack damage by 5' -> property='attack_damage', operation='add', value=SemanticNumericValue(kind='relative', value=5)
      - 'set zombie attack damage to 10' -> property='attack_damage', operation='set', value=SemanticNumericValue(kind='absolute', value=10)
      - 'make the zombie stronger' -> property=None, missing=['property']
      - 'increase zombie attack damage' -> property='attack_damage', operation='add', value=None, missing=['value']
    """
    model_config = ConfigDict(extra="allow")

    property: Optional[str] = Field(
        default=None,
        description="Target semantic property name (e.g. 'speed', 'attack_damage', 'health') or None if missing"
    )
    operation: Optional[str] = Field(
        default=None,
        description="Operation: 'set', 'add', 'subtract', 'multiply', 'divide' or None if missing"
    )
    value: Optional[SemanticValue] = Field(
        default=None,
        description="Semantic value specification or None if missing"
    )
    missing: List[str] = Field(
        default_factory=list,
        description="List of typed missing parameters: 'property', 'operation', 'value'"
    )
    source_text: Optional[str] = Field(
        default=None,
        description="Raw natural language source phrase"
    )
    extra_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional semantic metadata (e.g. target, ambiguity flags, reason)"
    )

    @field_validator("property")
    @classmethod
    def validate_property_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if not isinstance(v, str) or not v.strip():
            raise ValueError("Property name must be a non-empty string or None.")
        clean = v.strip()
        if clean.lower() == "missing":
            return None
        return clean

    @field_validator("operation")
    @classmethod
    def validate_operation_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if not isinstance(v, str) or not v.strip():
            raise ValueError("Operation must be a non-empty string or None.")
        clean = v.strip().lower()
        if clean == "missing":
            return None
        if clean not in SUPPORTED_OPERATIONS:
            raise ValueError(
                f"Unsupported operation: '{v}'. Must be one of {sorted(list(SUPPORTED_OPERATIONS))}."
            )
        return clean

    @field_validator("missing")
    @classmethod
    def validate_missing_items(cls, v: List[str]) -> List[str]:
        if not isinstance(v, (list, set, tuple)):
            raise ValueError("Missing parameters must be a list of strings.")
        validated: List[str] = []
        for item in v:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("Missing parameter item must be a non-empty string.")
            clean = item.strip().lower()
            if clean not in TYPED_MISSING_PARAMETERS:
                raise ValueError(
                    f"Invalid missing parameter '{item}'. Allowed missing parameters: {sorted(list(TYPED_MISSING_PARAMETERS))}."
                )
            if clean not in validated:
                validated.append(clean)
        return validated

    @model_validator(mode="after")
    def validate_semantic_consistency(self) -> "PropertyModification":
        missing_set = set(self.missing)

        # 1. Property validation
        if self.property is None:
            if "property" not in missing_set:
                raise ValueError(
                    "Missing property must be explicitly declared in 'missing': missing=['property']."
                )
        else:
            if "property" in missing_set:
                raise ValueError(
                    f"Property '{self.property}' is defined but also declared as missing in {self.missing}."
                )

        # 2. Operation validation
        is_qualitative = self.value is not None and self.value.kind == "qualitative"
        if self.operation is None:
            if not is_qualitative and "operation" not in missing_set:
                raise ValueError(
                    "Missing operation must be explicitly declared in 'missing': missing=['operation']."
                )
            if is_qualitative and "operation" in missing_set:
                raise ValueError(
                    "Qualitative value does not require an arithmetic operation; 'operation' should not be in 'missing'."
                )
        else:
            if "operation" in missing_set:
                raise ValueError(
                    f"Operation '{self.operation}' is defined but also declared as missing in {self.missing}."
                )

        # 3. Value validation
        if self.value is None or self.value.kind == "missing":
            if "value" not in missing_set:
                raise ValueError(
                    "Missing value must be explicitly declared in 'missing': missing=['value']."
                )
        else:
            if "value" in missing_set:
                raise ValueError(
                    f"Value is defined (kind='{self.value.kind}') but also declared as missing in {self.missing}."
                )

        return self
