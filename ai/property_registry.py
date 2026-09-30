"""
ai/property_registry.py - Extensible Minecraft Property Capability Registry

Provides a data-driven mapping of semantic properties (e.g. speed, attack_damage, health)
to their supported Minecraft implementation mechanisms (effect, attribute, scoreboard)
and the exact operations and value kinds each mechanism can represent.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class MechanismCapability(BaseModel):
    """
    Defines what a specific Minecraft mechanism (e.g. attribute, effect, scoreboard)
    can represent for a given semantic property.
    """
    mechanism_type: str  # 'attribute', 'effect', 'scoreboard'
    minecraft_identifier: Optional[str] = None
    supported_operations: List[str] = Field(default_factory=list)
    supported_value_kinds: List[str] = Field(default_factory=list)
    operation_value_kinds: Dict[str, List[str]] = Field(default_factory=dict)
    supports_qualitative: bool = False
    description: Optional[str] = None

    def supports(self, operation: Optional[str], value_kind: Optional[str]) -> bool:
        """
        Returns True if this mechanism can represent the given (operation, value_kind) combination.
        """
        if value_kind == "qualitative":
            return self.supports_qualitative

        if not operation or not value_kind:
            return False

        op_lower = operation.strip().lower()
        kind_lower = value_kind.strip().lower()

        if self.operation_value_kinds:
            allowed_kinds = self.operation_value_kinds.get(op_lower, [])
            return kind_lower in allowed_kinds

        return (op_lower in self.supported_operations) and (kind_lower in self.supported_value_kinds)


class PropertyCapability(BaseModel):
    """
    Defines how a semantic property can be realized in Minecraft Java Edition across
    one or more mechanisms.
    """
    property_name: str
    primary_mechanism: str  # 'effect', 'attribute', 'scoreboard'
    supported_mechanisms: List[str] = Field(default_factory=list)
    minecraft_identifier: Optional[str] = None
    description: Optional[str] = None
    mechanisms: Dict[str, MechanismCapability] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        """
        Ensures mechanisms dictionary is populated from supported_mechanisms
        if not explicitly provided.
        """
        if not self.supported_mechanisms and self.primary_mechanism:
            self.supported_mechanisms = [self.primary_mechanism]

        if not self.mechanisms:
            for m in self.supported_mechanisms:
                m_type = m.strip().lower()
                ident = self.minecraft_identifier
                if m_type == "attribute":
                    if not ident or not ident.startswith("minecraft:generic."):
                        ident = f"minecraft:generic.{self.property_name}"
                    self.mechanisms[m_type] = MechanismCapability(
                        mechanism_type="attribute",
                        minecraft_identifier=ident,
                        supported_operations=["set", "add", "subtract", "multiply", "divide"],
                        supported_value_kinds=["absolute", "relative", "percentage", "multiplier"],
                        operation_value_kinds={
                            "set": ["absolute"],
                            "add": ["relative", "percentage"],
                            "subtract": ["relative", "percentage"],
                            "multiply": ["multiplier"],
                            "divide": ["multiplier"],
                        },
                        supports_qualitative=False,
                        description=f"{self.property_name} attribute modifier",
                    )
                elif m_type == "effect":
                    if not ident or not ident.startswith("minecraft:"):
                        ident = f"minecraft:{self.property_name}"
                    self.mechanisms[m_type] = MechanismCapability(
                        mechanism_type="effect",
                        minecraft_identifier=ident,
                        supported_operations=["set"],
                        supported_value_kinds=["absolute"],
                        operation_value_kinds={
                            "set": ["absolute"],
                        },
                        supports_qualitative=True,
                        description=f"{self.property_name} status effect",
                    )
                elif m_type == "scoreboard":
                    self.mechanisms[m_type] = MechanismCapability(
                        mechanism_type="scoreboard",
                        minecraft_identifier=ident or self.property_name,
                        supported_operations=["set", "add", "subtract", "multiply", "divide"],
                        supported_value_kinds=["absolute", "relative", "multiplier"],
                        operation_value_kinds={
                            "set": ["absolute"],
                            "add": ["relative"],
                            "subtract": ["relative"],
                            "multiply": ["multiplier"],
                            "divide": ["multiplier"],
                        },
                        supports_qualitative=False,
                        description=f"{self.property_name} scoreboard objective",
                    )
        else:
            if not self.supported_mechanisms:
                self.supported_mechanisms = list(self.mechanisms.keys())

    def get_mechanism(self, mechanism_type: str) -> Optional[MechanismCapability]:
        return self.mechanisms.get(mechanism_type.strip().lower())

    def find_mechanism_for(
        self,
        operation: Optional[str],
        value_kind: Optional[str],
        preferred: Optional[str] = None
    ) -> Optional[MechanismCapability]:
        """
        Finds a mechanism that supports the exact (operation, value_kind) combination.
        Respects preferred mechanism if it supports the combination.
        Otherwise checks primary_mechanism, then other registered mechanisms.
        """
        # 1. If preferred mechanism is explicitly requested, strictly evaluate it
        if preferred:
            pref_lower = preferred.strip().lower()
            mech_cap = self.mechanisms.get(pref_lower)
            if mech_cap and mech_cap.supports(operation, value_kind):
                return mech_cap
            return None

        # 2. Check primary mechanism
        if self.primary_mechanism:
            prim_lower = self.primary_mechanism.strip().lower()
            if prim_lower in self.mechanisms:
                mech_cap = self.mechanisms[prim_lower]
                if mech_cap.supports(operation, value_kind):
                    return mech_cap

        # 3. Check all other registered mechanisms
        for m_type, mech_cap in self.mechanisms.items():
            if m_type != self.primary_mechanism and mech_cap.supports(operation, value_kind):
                return mech_cap

        return None


class PropertyCapabilityRegistry:
    """
    Registry of Minecraft capabilities for semantic properties.
    Extensible and data-driven without hardcoding inside planner control flow.
    """

    def __init__(self):
        self._registry: Dict[str, PropertyCapability] = {}
        self._init_defaults()

    def _init_defaults(self) -> None:
        defaults = [
            # Movement / Speed
            PropertyCapability(
                property_name="speed",
                primary_mechanism="attribute",
                supported_mechanisms=["attribute", "effect"],
                minecraft_identifier="minecraft:generic.movement_speed",
                description="Movement speed via generic.movement_speed attribute or speed status effect",
                mechanisms={
                    "attribute": MechanismCapability(
                        mechanism_type="attribute",
                        minecraft_identifier="minecraft:generic.movement_speed",
                        supported_operations=["set", "add", "subtract", "multiply", "divide"],
                        supported_value_kinds=["absolute", "relative", "percentage", "multiplier"],
                        operation_value_kinds={
                            "set": ["absolute"],
                            "add": ["relative", "percentage"],
                            "subtract": ["relative", "percentage"],
                            "multiply": ["multiplier"],
                            "divide": ["multiplier"],
                        },
                        supports_qualitative=False,
                        description="generic.movement_speed attribute modifier",
                    ),
                    "effect": MechanismCapability(
                        mechanism_type="effect",
                        minecraft_identifier="minecraft:speed",
                        supported_operations=["set"],
                        supported_value_kinds=["absolute"],
                        operation_value_kinds={"set": ["absolute"]},
                        supports_qualitative=False,
                        description="Speed status effect tier",
                    ),
                }
            ),
            PropertyCapability(
                property_name="movement_speed",
                primary_mechanism="attribute",
                supported_mechanisms=["attribute", "effect"],
                minecraft_identifier="minecraft:generic.movement_speed",
                description="Movement speed attribute or effect",
                mechanisms={
                    "attribute": MechanismCapability(
                        mechanism_type="attribute",
                        minecraft_identifier="minecraft:generic.movement_speed",
                        supported_operations=["set", "add", "subtract", "multiply", "divide"],
                        supported_value_kinds=["absolute", "relative", "percentage", "multiplier"],
                        operation_value_kinds={
                            "set": ["absolute"],
                            "add": ["relative", "percentage"],
                            "subtract": ["relative", "percentage"],
                            "multiply": ["multiplier"],
                            "divide": ["multiplier"],
                        },
                        supports_qualitative=False,
                        description="generic.movement_speed attribute modifier",
                    ),
                    "effect": MechanismCapability(
                        mechanism_type="effect",
                        minecraft_identifier="minecraft:speed",
                        supported_operations=["set"],
                        supported_value_kinds=["absolute"],
                        operation_value_kinds={"set": ["absolute"]},
                        supports_qualitative=False,
                        description="Speed status effect tier",
                    ),
                }
            ),
            # Combat / Offense
            PropertyCapability(
                property_name="attack_damage",
                primary_mechanism="attribute",
                supported_mechanisms=["attribute", "effect"],
                minecraft_identifier="minecraft:generic.attack_damage",
                description="Attack damage attribute or strength effect",
                mechanisms={
                    "attribute": MechanismCapability(
                        mechanism_type="attribute",
                        minecraft_identifier="minecraft:generic.attack_damage",
                        supported_operations=["set", "add", "subtract", "multiply", "divide"],
                        supported_value_kinds=["absolute", "relative", "percentage", "multiplier"],
                        operation_value_kinds={
                            "set": ["absolute"],
                            "add": ["relative", "percentage"],
                            "subtract": ["relative", "percentage"],
                            "multiply": ["multiplier"],
                            "divide": ["multiplier"],
                        },
                        supports_qualitative=False,
                        description="generic.attack_damage attribute modifier",
                    ),
                    "effect": MechanismCapability(
                        mechanism_type="effect",
                        minecraft_identifier="minecraft:strength",
                        supported_operations=["set"],
                        supported_value_kinds=["absolute"],
                        operation_value_kinds={"set": ["absolute"]},
                        supports_qualitative=False,
                        description="Strength status effect tier",
                    ),
                }
            ),
            PropertyCapability(
                property_name="damage",
                primary_mechanism="attribute",
                supported_mechanisms=["attribute", "effect"],
                minecraft_identifier="minecraft:generic.attack_damage",
                description="Entity attack damage",
                mechanisms={
                    "attribute": MechanismCapability(
                        mechanism_type="attribute",
                        minecraft_identifier="minecraft:generic.attack_damage",
                        supported_operations=["set", "add", "subtract", "multiply", "divide"],
                        supported_value_kinds=["absolute", "relative", "percentage", "multiplier"],
                        operation_value_kinds={
                            "set": ["absolute"],
                            "add": ["relative", "percentage"],
                            "subtract": ["relative", "percentage"],
                            "multiply": ["multiplier"],
                            "divide": ["multiplier"],
                        },
                        supports_qualitative=False,
                        description="generic.attack_damage attribute modifier",
                    ),
                    "effect": MechanismCapability(
                        mechanism_type="effect",
                        minecraft_identifier="minecraft:strength",
                        supported_operations=["set"],
                        supported_value_kinds=["absolute"],
                        operation_value_kinds={"set": ["absolute"]},
                        supports_qualitative=False,
                        description="Strength status effect tier",
                    ),
                }
            ),
            PropertyCapability(
                property_name="attack_speed",
                primary_mechanism="attribute",
                supported_mechanisms=["attribute"],
                minecraft_identifier="minecraft:generic.attack_speed",
                description="Attack speed attribute"
            ),
            PropertyCapability(
                property_name="knockback_resistance",
                primary_mechanism="attribute",
                supported_mechanisms=["attribute"],
                minecraft_identifier="minecraft:generic.knockback_resistance",
                description="Knockback resistance attribute"
            ),
            # Health / Defense
            PropertyCapability(
                property_name="health",
                primary_mechanism="attribute",
                supported_mechanisms=["attribute", "effect"],
                minecraft_identifier="minecraft:generic.max_health",
                description="Maximum health attribute or instant health/absorption effect",
                mechanisms={
                    "attribute": MechanismCapability(
                        mechanism_type="attribute",
                        minecraft_identifier="minecraft:generic.max_health",
                        supported_operations=["set", "add", "subtract", "multiply", "divide"],
                        supported_value_kinds=["absolute", "relative", "percentage", "multiplier"],
                        operation_value_kinds={
                            "set": ["absolute"],
                            "add": ["relative", "percentage"],
                            "subtract": ["relative", "percentage"],
                            "multiply": ["multiplier"],
                            "divide": ["multiplier"],
                        },
                        supports_qualitative=False,
                        description="generic.max_health attribute modifier",
                    ),
                    "effect": MechanismCapability(
                        mechanism_type="effect",
                        minecraft_identifier="minecraft:instant_health",
                        supported_operations=["set"],
                        supported_value_kinds=["absolute"],
                        operation_value_kinds={"set": ["absolute"]},
                        supports_qualitative=False,
                        description="Instant health effect",
                    ),
                }
            ),
            PropertyCapability(
                property_name="max_health",
                primary_mechanism="attribute",
                supported_mechanisms=["attribute"],
                minecraft_identifier="minecraft:generic.max_health",
                description="Max health attribute"
            ),
            PropertyCapability(
                property_name="armor",
                primary_mechanism="attribute",
                supported_mechanisms=["attribute"],
                minecraft_identifier="minecraft:generic.armor",
                description="Armor defense attribute"
            ),
            PropertyCapability(
                property_name="defense",
                primary_mechanism="attribute",
                supported_mechanisms=["attribute"],
                minecraft_identifier="minecraft:generic.armor_toughness",
                description="Armor toughness / defense attribute"
            ),
            PropertyCapability(
                property_name="armor_toughness",
                primary_mechanism="attribute",
                supported_mechanisms=["attribute"],
                minecraft_identifier="minecraft:generic.armor_toughness",
                description="Armor toughness attribute"
            ),
            # Mobility / Physics
            PropertyCapability(
                property_name="jump_height",
                primary_mechanism="attribute",
                supported_mechanisms=["attribute", "effect"],
                minecraft_identifier="minecraft:generic.jump_strength",
                description="Jump strength attribute or jump boost effect",
                mechanisms={
                    "attribute": MechanismCapability(
                        mechanism_type="attribute",
                        minecraft_identifier="minecraft:generic.jump_strength",
                        supported_operations=["set", "add", "subtract", "multiply", "divide"],
                        supported_value_kinds=["absolute", "relative", "percentage", "multiplier"],
                        operation_value_kinds={
                            "set": ["absolute"],
                            "add": ["relative", "percentage"],
                            "subtract": ["relative", "percentage"],
                            "multiply": ["multiplier"],
                            "divide": ["multiplier"],
                        },
                        supports_qualitative=False,
                        description="generic.jump_strength attribute modifier",
                    ),
                    "effect": MechanismCapability(
                        mechanism_type="effect",
                        minecraft_identifier="minecraft:jump_boost",
                        supported_operations=["set"],
                        supported_value_kinds=["absolute"],
                        operation_value_kinds={"set": ["absolute"]},
                        supports_qualitative=True,
                        description="Jump boost effect tier",
                    ),
                }
            ),
            PropertyCapability(
                property_name="gravity",
                primary_mechanism="attribute",
                supported_mechanisms=["attribute", "effect"],
                minecraft_identifier="minecraft:generic.gravity",
                description="Gravity attribute or levitation/slow falling effect"
            ),
            PropertyCapability(
                property_name="flying_speed",
                primary_mechanism="attribute",
                supported_mechanisms=["attribute"],
                minecraft_identifier="minecraft:generic.flying_speed",
                description="Flying speed attribute"
            ),
            PropertyCapability(
                property_name="scale",
                primary_mechanism="attribute",
                supported_mechanisms=["attribute"],
                minecraft_identifier="minecraft:generic.scale",
                description="Entity scale attribute (Java 1.20.5+)"
            ),
            PropertyCapability(
                property_name="step_height",
                primary_mechanism="attribute",
                supported_mechanisms=["attribute"],
                minecraft_identifier="minecraft:generic.step_height",
                description="Step height attribute"
            ),
            PropertyCapability(
                property_name="follow_range",
                primary_mechanism="attribute",
                supported_mechanisms=["attribute"],
                minecraft_identifier="minecraft:generic.follow_range",
                description="Mob follow range attribute"
            ),
            PropertyCapability(
                property_name="safe_fall_distance",
                primary_mechanism="attribute",
                supported_mechanisms=["attribute"],
                minecraft_identifier="minecraft:generic.safe_fall_distance",
                description="Safe fall distance attribute"
            ),
            PropertyCapability(
                property_name="fall_damage_multiplier",
                primary_mechanism="attribute",
                supported_mechanisms=["attribute"],
                minecraft_identifier="minecraft:generic.fall_damage_multiplier",
                description="Fall damage multiplier attribute"
            ),
        ]
        for cap in defaults:
            self.register(cap)

    def register(self, capability: PropertyCapability) -> None:
        self._registry[capability.property_name.strip().lower()] = capability

    def lookup(self, property_name: Optional[str]) -> Optional[PropertyCapability]:
        if not property_name or not isinstance(property_name, str):
            return None
        return self._registry.get(property_name.strip().lower())

    def is_known(self, property_name: Optional[str]) -> bool:
        return self.lookup(property_name) is not None

    def get_implementation(self, property_name: Optional[str]) -> Optional[str]:
        cap = self.lookup(property_name)
        return cap.primary_mechanism if cap else None

    def get_registered_property_names(self) -> List[str]:
        """
        Returns all registered semantic property names in registration order.
        """
        return list(self._registry.keys())

    def get_supported_properties(self) -> List[str]:
        """
        Returns supported semantic property names for user-facing clarification options.
        """
        return self.get_registered_property_names()

    def resolve_attribute_identifier(
        self,
        property_name: Optional[str],
        version_context: Optional[Any] = None
    ) -> Optional[str]:
        """
        Resolves the Minecraft attribute identifier for a semantic property,
        taking into account the target version context.
        For Minecraft 1.21.11, preserves 'minecraft:generic.movement_speed'
        and other established generic identifiers.
        """
        cap = self.lookup(property_name)
        if not cap:
            return None
        mech = cap.get_mechanism("attribute")
        if not mech:
            return None
        return mech.minecraft_identifier


# Module-level default registry instance
DEFAULT_PROPERTY_REGISTRY = PropertyCapabilityRegistry()


def resolve_attribute_identifier(
    property_name: Optional[str],
    version_context: Optional[Any] = None,
    registry: Optional[PropertyCapabilityRegistry] = None
) -> Optional[str]:
    """
    Convenience function resolving the attribute identifier for a semantic property.
    """
    reg = registry or DEFAULT_PROPERTY_REGISTRY
    return reg.resolve_attribute_identifier(property_name, version_context)

