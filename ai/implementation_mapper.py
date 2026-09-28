"""
ai/implementation_mapper.py - Step 17.5 Deterministic Minecraft Implementation Mapping

Bridges validated semantic PropertyModification models to deterministic Minecraft
gameplay mechanisms (effect, attribute, scoreboard) using the authoritative
PropertyCapabilityRegistry.

Strict architectural principles:
- Consumes ONLY structured semantic data (property, operation, value, target, metadata).
- NEVER re-parses source natural language text.
- NEVER emits raw Minecraft command strings (/effect, /attribute, /scoreboard).
- NEVER creates a secondary property registry; queries PropertyCapabilityRegistry as single source of truth.
- Preserves all value semantics (absolute, relative, percentage, multiplier, qualitative).
- NEVER converts multiplier 10 into effect amplifier 9 in the semantic/mapping layer.
- Handles unsupported, incomplete, or missing inputs with structured unresolved/unsupported states.
"""

from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, ConfigDict

from ai.semantic_models import PropertyModification, SemanticValue, SemanticNumericValue
from ai.property_registry import DEFAULT_PROPERTY_REGISTRY, PropertyCapabilityRegistry, PropertyCapability


class MappedImplementation(BaseModel):
    """
    Structured outcome of mapping a PropertyModification to a Minecraft implementation.
    """
    model_config = ConfigDict(extra="allow")

    status: str = Field(
        ...,
        description="Mapping status: 'ready', 'unresolved', or 'unsupported'"
    )
    property_name: Optional[str] = Field(
        default=None,
        description="Semantic property name (e.g. 'speed', 'attack_damage', 'health')"
    )
    target: str = Field(
        default="@a",
        description="Target entity selector or identifier"
    )
    mechanism_type: Optional[str] = Field(
        default=None,
        description="Selected Minecraft implementation mechanism ('effect', 'attribute', 'scoreboard')"
    )
    minecraft_identifier: Optional[str] = Field(
        default=None,
        description="Minecraft identifier from capability registry (e.g. 'minecraft:speed', 'minecraft:generic.attack_damage')"
    )
    operation: Optional[str] = Field(
        default=None,
        description="Semantic operation: 'set', 'add', 'subtract', 'multiply', or None (qualitative)"
    )
    value: Optional[Union[SemanticNumericValue, SemanticValue]] = Field(
        default=None,
        description="Preserved semantic value with kind and magnitude"
    )
    mechanism_spec: Optional[Any] = Field(
        default=None,
        description="Structured MechanismSpecification for compilation"
    )
    action_spec: Optional[Any] = Field(
        default=None,
        description="Structured ActionSpecification"
    )
    missing: List[str] = Field(
        default_factory=list,
        description="List of missing semantic parameters preventing resolution"
    )
    missing_knowledge: List[str] = Field(
        default_factory=list,
        description="List of unknown property identifiers"
    )
    reason: Optional[str] = Field(
        default=None,
        description="Explanatory reason for the mapping outcome or failure"
    )


class ImplementationMapper:
    """
    Deterministic implementation mapper that maps structured PropertyModification models
    to structured Minecraft implementation specifications without parsing natural language text.
    """

    def __init__(self, registry: Optional[PropertyCapabilityRegistry] = None):
        self.registry = registry or DEFAULT_PROPERTY_REGISTRY

    @staticmethod
    def _resolve_target_selector(raw_target: str) -> tuple[Optional[str], Optional[str]]:
        """
        Resolves raw target into a valid Minecraft selector or execution target using
        entity knowledge. Returns (resolved_target, error_reason).
        """
        clean = str(raw_target).strip().lower()

        # Standard Minecraft selectors
        if clean.startswith("@"):
            return clean, None

        # Player references
        if clean in ("player", "me", "my", "players", "all_players"):
            return "@a", None

        # Query Minecraft entity knowledge
        try:
            from knowledge_retriever import load_entity_knowledge
            entities = load_entity_knowledge()
            if isinstance(entities, list):
                for ent in entities:
                    if isinstance(ent, dict):
                        ent_name = ent.get("name", "").lower()
                        ent_id = ent.get("id", "").lower()
                        if clean in (ent_name, ent_id):
                            short_id = ent_name or ent_id.split(":")[-1]
                            return f"@e[type={short_id}]", None
        except Exception:
            pass

        # Unknown / unresolvable entity type
        return None, f"Target entity '{raw_target}' cannot be safely resolved to a known Minecraft entity selector."

    def map_modification(
        self,
        mod: PropertyModification,
        default_target: Optional[str] = None,
        registry: Optional[PropertyCapabilityRegistry] = None,
        preferred_mechanism: Optional[str] = None,
        step_id: Optional[str] = None,
        action_id: Optional[str] = None,
    ) -> MappedImplementation:
        """
        Maps a single PropertyModification to a MappedImplementation.
        Operates purely on structured fields:
        - mod.property
        - mod.operation
        - mod.value
        - mod.extra_metadata
        - mod.missing
        Does NOT parse or inspect mod.source_text.
        """
        reg = registry or self.registry or DEFAULT_PROPERTY_REGISTRY
        from generator.models import ActionSpecification, MechanismSpecification

        # 1. Target resolution: extracted strictly from structured semantic fields
        extra_meta = getattr(mod, "extra_metadata", None) or {}
        if not isinstance(extra_meta, dict):
            extra_meta = {}

        raw_target = (
            getattr(mod, "target", None)
            or (extra_meta.get("target") if isinstance(extra_meta, dict) else None)
            or default_target
        )

        if not raw_target or raw_target == "missing" or "target" in getattr(mod, "missing", []):
            return MappedImplementation(
                status="unresolved",
                property_name=getattr(mod, "property", None),
                target="",
                value=getattr(mod, "value", None),
                missing=["target"],
                reason="Target is missing for property modification.",
            )

        target, target_err = self._resolve_target_selector(raw_target)
        if target is None:
            return MappedImplementation(
                status="unresolved",
                property_name=getattr(mod, "property", None),
                target=str(raw_target),
                value=getattr(mod, "value", None),
                missing=["target"],
                reason=target_err or f"Invalid target '{raw_target}'.",
            )

        # 2. Check for missing or underspecified property
        if not mod.property or "property" in mod.missing:
            return MappedImplementation(
                status="unresolved",
                target=target,
                missing=["property"],
                reason="Semantic property is missing or underspecified.",
            )

        # 3. Query PropertyCapabilityRegistry for property capabilities
        cap = reg.lookup(mod.property)
        if not cap or not reg.is_known(mod.property):
            return MappedImplementation(
                status="unresolved",
                property_name=mod.property,
                target=target,
                missing_knowledge=[mod.property],
                reason=f"Property '{mod.property}' is not recognized in PropertyCapabilityRegistry.",
            )

        # 4. Check for missing value
        if "value" in mod.missing or mod.value is None or getattr(mod.value, "kind", None) == "missing":
            return MappedImplementation(
                status="unresolved",
                property_name=mod.property,
                target=target,
                missing=["value"],
                reason=f"Value is missing for property '{mod.property}'.",
            )

        # 5. Check qualitative requests
        is_qualitative = mod.value is not None and getattr(mod.value, "kind", None) == "qualitative"
        if is_qualitative:
            # Qualitative requests (e.g. "make me faster") cannot be deterministically mapped
            # to a Minecraft mechanism without inventing an arbitrary magnitude and duration.
            desc = str(getattr(mod.value, "value", "")).strip().lower()
            return MappedImplementation(
                status="unresolved",
                property_name=mod.property,
                target=target,
                operation=None,
                value=mod.value,
                missing=["value"],
                reason=f"Qualitative property modification '{desc or 'qualitative'}' for '{mod.property}' requires clarification of specific magnitude and duration.",
            )

        # 6. Check for missing operation (non-qualitative)
        if mod.operation is None or "operation" in mod.missing:
            return MappedImplementation(
                status="unresolved",
                property_name=mod.property,
                target=target,
                value=mod.value,
                missing=["operation"],
                reason=f"Operation is missing for non-qualitative property '{mod.property}'.",
            )

        # 7. Check for ambiguous numeric values
        if extra_meta.get("ambiguous"):
            return MappedImplementation(
                status="unresolved",
                property_name=mod.property,
                target=target,
                value=mod.value,
                missing=["value"],
                reason=extra_meta.get("reason", f"Ambiguous numeric relationship for property '{mod.property}'."),
            )

        # 8. Mechanism selection: Exact (property, operation, value.kind) capability matching
        val_kind = getattr(mod.value, "kind", None) if mod.value else None
        mech_cap = cap.find_mechanism_for(
            operation=mod.operation,
            value_kind=val_kind,
            preferred=preferred_mechanism,
        )

        if mech_cap is None:
            if preferred_mechanism:
                return MappedImplementation(
                    status="unsupported",
                    property_name=mod.property,
                    target=target,
                    operation=mod.operation,
                    value=mod.value,
                    reason=(
                        f"Requested mechanism '{preferred_mechanism}' is not supported for property '{mod.property}' "
                        f"with operation '{mod.operation}' and value kind '{val_kind}'. "
                        f"Supported mechanisms: {cap.supported_mechanisms}."
                    ),
                )
            return MappedImplementation(
                status="unsupported",
                property_name=mod.property,
                target=target,
                operation=mod.operation,
                value=mod.value,
                reason=(
                    f"No registered mechanism for property '{mod.property}' supports exact semantic "
                    f"combination (operation='{mod.operation}', value_kind='{val_kind}')."
                ),
            )

        impl = mech_cap.mechanism_type
        identifier = mech_cap.minecraft_identifier or cap.minecraft_identifier

        # 9. Construct structured ActionSpecification and MechanismSpecification
        # Values are strictly preserved without conversion (e.g. multiplier 10 stays multiplier 10)
        effective_step_id = (
            step_id
            or (extra_meta.get("step_id") if isinstance(extra_meta, dict) else None)
        )
        effective_action_id = (
            action_id
            or (extra_meta.get("action_id") if isinstance(extra_meta, dict) else None)
        )
        action = ActionSpecification(
            action_type="modify_property",
            target=target,
            property_modification=mod,
            implementation=impl,
            modifier_id=extra_meta.get("modifier_id"),
            step_id=effective_step_id,
            action_id=effective_action_id,
        )

        mech = MechanismSpecification(
            type="property_modification",
            target=target,
            property_modification=mod,
            implementation=impl,
            actions=[action],
            description=f"Deterministic property modification for '{mod.property}' ({mod.operation}) mapped to {impl}.",
        )

        return MappedImplementation(
            status="ready",
            property_name=mod.property,
            target=target,
            mechanism_type=impl,
            minecraft_identifier=identifier,
            operation=mod.operation,
            value=mod.value,
            mechanism_spec=mech,
            action_spec=action,
            reason=f"Successfully mapped property '{mod.property}' to {impl}.",
        )
