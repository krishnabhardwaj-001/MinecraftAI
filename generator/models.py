import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
# pyrefly: ignore [missing-import]
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

from ai.semantic_models import PropertyModification


class LootTableModification(BaseModel):
    model_config = ConfigDict(extra="allow")

    loot_table_path: str = Field(
        ...,
        description="Relative path of the loot table (e.g. 'entities/creeper.json')"
    )
    item: str = Field(
        ...,
        description="Resource ID of the item to add (e.g. 'minecraft:diamond')"
    )
    count: Union[int, Dict[str, Any]] = Field(
        default=1,
        description="Deterministic drop count (integer or distribution dict)"
    )
    operation: str = Field(
        default="add_pool",
        description="Operation to apply: 'add_pool' preserves existing pools and appends a new one"
    )
    conditions: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Optional loot table / pool conditions"
    )
    functions: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Optional loot functions (e.g. set_count, looting)"
    )
    rolls: float = Field(
        default=1.0,
        description="Rolls for the new pool"
    )


class DatapackResource(BaseModel):
    """
    Represents an individual generated datapack file.
    """
    model_config = ConfigDict(extra="allow")

    relative_path: str = Field(
        ...,
        description="Relative path inside datapack (e.g. 'data/minecraft/function/main.mcfunction')"
    )
    content: Union[str, bytes] = Field(
        ...,
        description="Text (UTF-8) or binary content of the resource"
    )
    resource_type: str = Field(
        default="generic",
        description="Resource category (e.g. 'loot_table', 'function', 'tag', 'advancement')"
    )



# ==============================================================================
# SCOREBOARD CONSTANTS & VALIDATION HELPERS (Minecraft Java 1.21.11)
# ==============================================================================

OBJECTIVE_NAME_REGEX = re.compile(r"^[a-zA-Z0-9_.\+\-]+$")

VALID_SCORE_OPERATIONS = {"=", "+=", "-=", "*=", "/=", "%=", "<", ">", "><"}

VALID_SCORE_COMPARISONS = {"<", "<=", "=", ">=", ">"}

VALID_BASE_DISPLAY_SLOTS = {"sidebar", "list", "below_name"}

VALID_TEAM_COLORS = {
    "black", "dark_blue", "dark_green", "dark_aqua", "dark_red", "dark_purple",
    "gold", "gray", "dark_gray", "blue", "green", "aqua", "red", "light_purple",
    "yellow", "white",
}

VALID_BUILTIN_CRITERIA = {
    "dummy", "trigger", "deathCount", "playerKillCount", "totalKillCount",
    "health", "xp", "level", "food", "air", "armor",
}

VALID_STAT_PREFIXES = (
    "minecraft.custom:",
    "minecraft.mined:",
    "minecraft.crafted:",
    "minecraft.used:",
    "minecraft.broken:",
    "minecraft.picked_up:",
    "minecraft.dropped:",
    "minecraft.killed:",
    "minecraft.killed_by:",
    "teamkill.",
    "killedByTeam.",
)


def validate_objective_name(name: str) -> str:
    r"""
    Validates a Minecraft Java 1.21.11 scoreboard objective name.
    Constraint: 1 to 16 characters matching ^[a-zA-Z0-9_.\+\-]+$.
    """
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Objective name must be a non-empty string.")
    clean = name.strip()
    if len(clean) > 16:
        raise ValueError(
            f"Objective name '{clean}' exceeds maximum length of 16 characters ({len(clean)} characters)."
        )
    if not OBJECTIVE_NAME_REGEX.match(clean):
        raise ValueError(
            f"Objective name '{clean}' contains invalid characters. "
            "Allowed characters: letters (A-Z, a-z), digits (0-9), '_', '.', '+', and '-'."
        )
    return clean


def validate_criteria(criteria: str) -> str:
    """
    Validates scoreboard criteria against Minecraft Java 1.21.11 authoritative knowledge.
    Supports built-in criteria, team criteria, and statistic criteria prefixes.
    """
    if not isinstance(criteria, str) or not criteria.strip():
        raise ValueError("Criteria must be a non-empty string.")
    clean = criteria.strip()
    norm = clean
    if norm.startswith("minecraft:"):
        norm = norm[10:]
    if norm in VALID_BUILTIN_CRITERIA:
        return clean
    if any(norm.startswith(p) for p in VALID_STAT_PREFIXES):
        return clean
    if any(norm.startswith(p) for p in ("custom:", "mined:", "crafted:", "used:", "broken:", "picked_up:", "dropped:", "killed:", "killed_by:")):
        return clean
    raise ValueError(
        f"Invalid scoreboard criteria: '{clean}'. "
        f"Must be a built-in criteria (e.g. {sorted(list(VALID_BUILTIN_CRITERIA))}) or statistic criteria."
    )


def validate_display_slot(slot: str) -> str:
    """
    Validates scoreboard display slot against Minecraft Java 1.21.11 knowledge.
    Allowed: 'sidebar', 'list', 'below_name', 'sidebar.team.<color>'.
    """
    if not isinstance(slot, str) or not slot.strip():
        raise ValueError("Display slot must be a non-empty string.")
    clean = slot.strip().lower()
    if clean in VALID_BASE_DISPLAY_SLOTS:
        return clean
    if clean.startswith("sidebar.team."):
        team_color = clean[len("sidebar.team."):]
        if team_color in VALID_TEAM_COLORS:
            return clean
        raise ValueError(
            f"Invalid team color '{team_color}' in display slot '{clean}'. "
            f"Supported colors: {sorted(list(VALID_TEAM_COLORS))}"
        )
    raise ValueError(
        f"Invalid display slot: '{clean}'. "
        f"Supported display slots: {sorted(list(VALID_BASE_DISPLAY_SLOTS))} or 'sidebar.team.<color>'."
    )


def validate_score_operation(op: str) -> str:
    """
    Validates scoreboard operation against Minecraft Java 1.21.11 knowledge.
    Allowed: '=', '+=', '-=', '*=', '/=', '%=', '<', '>', '><'.
    """
    if not isinstance(op, str) or not op.strip():
        raise ValueError("Score operation must be a non-empty string.")
    clean = op.strip()
    if clean in VALID_SCORE_OPERATIONS:
        return clean
    raise ValueError(
        f"Invalid score operation: '{clean}'. "
        f"Supported operations: {sorted(list(VALID_SCORE_OPERATIONS))}"
    )


def validate_comparison_operator(op: str) -> str:
    """
    Validates scoreboard comparison operator against Minecraft Java 1.21.11 knowledge.
    Allowed: '<', '<=', '=', '>', '>='.
    """
    if not isinstance(op, str) or not op.strip():
        raise ValueError("Comparison operator must be a non-empty string.")
    clean = op.strip()
    if clean not in VALID_SCORE_COMPARISONS:
        raise ValueError(
            f"Invalid score comparison operator: '{clean}'. "
            f"Supported comparison operators: {sorted(list(VALID_SCORE_COMPARISONS))}"
        )
    return clean


class ScoreCompareCondition(BaseModel):
    """
    Structured specification of a score-to-score comparison condition.
    Maps to Minecraft: execute (if|unless) score <target> <target_objective> <operator> <source> <source_objective>
    """
    model_config = ConfigDict(extra="allow")

    type: str = Field(
        default="score_compare",
        description="Condition type: 'score_compare'"
    )
    target: str = Field(
        ...,
        description="Target selector or score holder being compared (e.g. '@s', '@p', '#global')"
    )
    target_objective: str = Field(
        ...,
        description="Objective name for target score"
    )
    operator: str = Field(
        ...,
        description="Comparison operator: '<', '<=', '=', '>', '>='"
    )
    source: str = Field(
        ...,
        description="Source selector or score holder to compare against (e.g. '#global', '@s')"
    )
    source_objective: str = Field(
        ...,
        description="Objective name for source score"
    )
    inverted: bool = Field(
        default=False,
        description="Whether condition is inverted ('unless score ...' vs 'if score ...')"
    )

    @field_validator("target_objective", "source_objective")
    @classmethod
    def validate_objective_fields(cls, v: str) -> str:
        return validate_objective_name(v)

    @field_validator("operator")
    @classmethod
    def validate_operator_field(cls, v: str) -> str:
        return validate_comparison_operator(v)

    @field_validator("target", "source")
    @classmethod
    def validate_holders(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("Target and source score holders must be non-empty strings.")
        return v.strip()


class ScoreboardObjectiveDefinition(BaseModel):
    """
    Structured specification of a Minecraft scoreboard objective definition.
    Represents objective creation and display configuration for Java 1.21.11.
    """
    model_config = ConfigDict(extra="allow")

    type: str = Field(
        default="scoreboard_objective",
        description="Type identifier, defaults to 'scoreboard_objective'"
    )
    objective: str = Field(
        ...,
        description="Scoreboard objective name (1-16 chars, [a-zA-Z0-9_.-+])"
    )
    criteria: str = Field(
        default="dummy",
        description="Objective criteria (e.g. 'dummy', 'deathCount', 'health', 'minecraft.custom:...')"
    )
    display_name: Optional[Union[str, Dict[str, Any]]] = Field(
        default=None,
        description="Optional display name (string or raw JSON text component)"
    )
    display_slot: Optional[str] = Field(
        default=None,
        description="Optional display slot: 'sidebar', 'list', 'below_name', 'sidebar.team.<color>'"
    )

    @field_validator("objective")
    @classmethod
    def validate_objective(cls, v: str) -> str:
        return validate_objective_name(v)

    @field_validator("criteria")
    @classmethod
    def validate_criteria_field(cls, v: str) -> str:
        return validate_criteria(v)

    @field_validator("display_slot")
    @classmethod
    def validate_display_slot_field(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return validate_display_slot(v)


ALLOWED_ACTION_TYPES = {
    "modify_property", "property_modification",
    "apply_effect", "effect", "give_effect",
    "clear_effect", "remove_effect",
    "give_item", "give", "item",
    "clear_item", "remove_item", "clear",
    "set_score", "score_set",
    "add_score", "score_add",
    "remove_score", "score_remove",
    "reset_score", "score_reset",
    "remove_objective", "objective_remove",
    "operation_score", "score_operation",
    "play_sound", "sound",
    "spawn_particle", "particle",
    "send_message", "message", "say",
    "summon_entity", "summon",
    "teleport",
    "raw_command",
}


class ActionSpecification(BaseModel):

    """
    Structured specification of a gameplay action for Minecraft Java 1.21.11.
    The Generator synthesizes exact Minecraft command syntax from these fields.
    """
    model_config = ConfigDict(extra="allow")

    action_type: str = Field(
        ...,
        description="Action category: 'apply_effect', 'clear_effect', 'give_item', 'clear_item', 'set_score', 'add_score', 'remove_score', 'reset_score', 'operation_score', 'play_sound', 'spawn_particle', 'send_message', 'summon_entity', 'teleport'"
    )
    target: str = Field(
        default="@a",
        description="Target selector or score holder (e.g. '@a', '@p', '@s', '#global')"
    )
    execution_context: Optional[Dict[str, Any]] = Field(
        default_factory=lambda: {"as_target": True, "at_target": True},
        description="Context anchors for execution (e.g. 'as' and 'at')"
    )
    conditions: Optional[List[Union[Dict[str, Any], ScoreCompareCondition]]] = Field(
        default_factory=list,
        description="Optional execution conditions (predicate checks or scoreboard checks)"
    )

    # Semantic property modification parameters (Step 17.3)
    property_modification: Optional[PropertyModification] = Field(
        default=None,
        description="Structured semantic property modification"
    )
    implementation: Optional[str] = Field(
        default=None,
        description="Structural Minecraft implementation mechanism ('effect', 'attribute', 'scoreboard', etc.)"
    )
    modifier_id: Optional[str] = Field(
        default=None,
        description="Explicit deterministic modifier ID for attribute actions (e.g. 'speed_bonus_1')"
    )
    step_id: Optional[str] = Field(
        default=None,
        description="Deterministic step identity (e.g. 'step_0')"
    )
    action_id: Optional[str] = Field(
        default=None,
        description="Deterministic action identity (e.g. 'act_0')"
    )

    # Item parameters
    item: Optional[str] = Field(default=None, description="Resource ID of item (e.g. 'minecraft:diamond')")
    count: Optional[int] = Field(default=1, description="Item quantity")

    # Entity parameters
    entity: Optional[str] = Field(default=None, description="Resource ID of entity (e.g. 'minecraft:zombie')")

    # Effect parameters
    effect: Optional[str] = Field(default=None, description="Resource ID of effect (e.g. 'minecraft:speed')")
    duration: Optional[Union[int, str]] = Field(
        default=None,
        description="Duration in seconds (int >= 1), 'infinite', or None for default"
    )
    amplifier: Optional[int] = Field(default=0, description="Effect amplifier (0 = level 1)")
    show_particles: Optional[bool] = Field(default=True, description="Whether effect particles are visible")

    @field_validator("duration", mode="before")
    @classmethod
    def validate_duration(cls, v: Any) -> Optional[Union[int, str]]:
        if v is None:
            return None
        if isinstance(v, bool):
            raise ValueError("Duration cannot be a boolean")
        if isinstance(v, float):
            raise ValueError(
                f"Duration cannot be a float: {v}. Must be an integer >= 1 or 'infinite'."
            )
        if isinstance(v, int):
            if v < 1:
                raise ValueError(f"Duration must be a positive integer (>= 1 second). Got {v}")
            return v
        if isinstance(v, str):
            v_str = v.strip()
            if not v_str:
                return None
            if v_str.isdigit():
                int_v = int(v_str)
                if int_v < 1:
                    raise ValueError(f"Duration must be a positive integer (>= 1 second). Got {int_v}")
                return int_v
            if v_str.startswith("-") and v_str[1:].isdigit():
                raise ValueError(f"Duration must be a positive integer (>= 1 second). Got {v_str}")
            if "." in v_str:
                raise ValueError(
                    f"Duration cannot be a float string: '{v}'. Must be an integer >= 1 or 'infinite'."
                )
            if v_str.lower() == "infinite":
                return "infinite"
            raise ValueError(
                f"Invalid duration: '{v}'. Duration must be an integer >= 1 or 'infinite'."
            )
        raise ValueError(
            f"Invalid duration type: {type(v).__name__}. Duration must be an integer >= 1 or 'infinite'."
        )

    # Scoreboard parameters
    objective: Optional[str] = Field(default=None, description="Scoreboard objective name")
    score_holder: Optional[str] = Field(default=None, description="Score holder (e.g. '#global' or '@s')")
    score_value: Optional[int] = Field(default=None, description="Score integer value")
    operation: Optional[str] = Field(default=None, description="Score operation: '=', '+=', '-=', '*=', '/=', '%=', '<', '>', '><'")
    source_holder: Optional[str] = Field(default=None, description="Source score holder for operation_score")
    source_objective: Optional[str] = Field(default=None, description="Source objective name for operation_score")

    @field_validator("score_value", mode="before")
    @classmethod
    def validate_score_value(cls, v: Any) -> Optional[int]:
        if v is None:
            return None
        if isinstance(v, bool):
            raise ValueError(f"Score value cannot be a boolean: {v}")
        if isinstance(v, float):
            raise ValueError(
                f"Score value cannot be a float: {v}. Must be an integer."
            )
        if isinstance(v, str):
            v_str = v.strip()
            if not v_str:
                return None
            if "." in v_str:
                raise ValueError(
                    f"Score value cannot be a float string: '{v}'. Must be an integer."
                )
            try:
                return int(v_str)
            except ValueError:
                raise ValueError(f"Invalid score value string: '{v}'. Must be an integer.")
        if isinstance(v, int):
            return v
        raise ValueError(
            f"Invalid score value type: {type(v).__name__}. Must be an integer."
        )

    @field_validator("conditions", mode="before")
    @classmethod
    def validate_conditions(cls, v: Any) -> Optional[List[Any]]:
        if v is None:
            return []
        if not isinstance(v, list):
            raise ValueError(f"conditions must be a list, got {type(v).__name__}")
        validated = []
        for cond in v:
            if isinstance(cond, ScoreCompareCondition):
                validated.append(cond)
            elif isinstance(cond, dict):
                c_type = str(cond.get("type", "")).strip().lower()
                if c_type == "score_compare":
                    validated_cond = ScoreCompareCondition(**cond)
                    validated.append(validated_cond.model_dump())
                elif c_type == "score":
                    if "objective" in cond and cond["objective"]:
                        validate_objective_name(cond["objective"])
                    validated.append(cond)
                else:
                    validated.append(cond)
            else:
                validated.append(cond)
        return validated

    @model_validator(mode="after")
    def validate_action_fields(self) -> "ActionSpecification":
        a_type = (self.action_type or "").strip().lower()
        if not a_type or a_type not in ALLOWED_ACTION_TYPES:
            raise ValueError(
                f"Invalid action_type: '{self.action_type}'. Must be one of {sorted(ALLOWED_ACTION_TYPES)}"
            )

        if self.objective:
            self.objective = validate_objective_name(self.objective)

        if a_type in ("set_score", "score_set"):
            holder = self.score_holder or self.target
            if not holder:
                raise ValueError("set_score requires 'target' or 'score_holder'.")
            if not self.objective:
                raise ValueError("set_score requires 'objective' to be specified.")

        elif a_type in ("add_score", "score_add"):
            holder = self.score_holder or self.target
            if not holder:
                raise ValueError("add_score requires 'target' or 'score_holder'.")
            if not self.objective:
                raise ValueError("add_score requires 'objective' to be specified.")
            if self.score_value is not None and self.score_value < 0:
                raise ValueError(
                    f"add_score score_value must be non-negative (>= 0). Got {self.score_value}. "
                    "Use remove_score or operation_score '-=' to subtract scores."
                )

        elif a_type in ("remove_score", "score_remove"):
            holder = self.score_holder or self.target
            if not holder:
                raise ValueError("remove_score requires 'target' or 'score_holder'.")
            if not self.objective:
                raise ValueError("remove_score requires 'objective' to be specified.")
            if self.score_value is None:
                raise ValueError("remove_score requires 'score_value' to be specified.")
            if self.score_value < 0:
                raise ValueError(
                    f"remove_score score_value must be non-negative (>= 0). Got {self.score_value}."
                )

        elif a_type == "operation_score":
            holder = self.score_holder or self.target
            if not holder:
                raise ValueError("operation_score requires 'target' (or 'score_holder').")
            if not self.objective:
                raise ValueError("operation_score requires 'objective'.")
            if not self.operation:
                raise ValueError("operation_score requires 'operation' to be specified.")
            validate_score_operation(self.operation)
            if not self.source_holder:
                raise ValueError("operation_score requires 'source_holder' to be specified.")
            if not self.source_objective:
                raise ValueError("operation_score requires 'source_objective' to be specified.")
            validate_objective_name(self.source_objective)

        elif a_type in ("reset_score", "score_reset"):
            holder = self.score_holder or self.target
            if not holder:
                raise ValueError("reset_score requires 'target' or 'score_holder'.")

        return self

    # Audio / Visual
    sound: Optional[str] = Field(default=None, description="Sound event identifier")
    particle: Optional[str] = Field(default=None, description="Particle identifier")

    # Communication
    message: Optional[str] = Field(default=None, description="Text message")

    # Escape hatch for genuinely unmodeled operations (strictly audited)
    raw_command: Optional[str] = Field(default=None, description="Raw command fallback for unmodeled advanced operations")


class FunctionDefinition(BaseModel):
    """
    Specification for a Minecraft .mcfunction resource.
    """
    model_config = ConfigDict(extra="allow")

    function_path: str = Field(
        ...,
        description="Relative function path without .mcfunction extension (e.g. 'main' or 'tick')"
    )
    actions: Optional[List[ActionSpecification]] = Field(
        default_factory=list,
        description="Structured gameplay actions to synthesize into commands"
    )
    commands: List[str] = Field(
        default_factory=list,
        description="List of Minecraft commands to execute in this function (legacy fallback)"
    )
    namespace: str = Field(
        default="minecraft",
        description="Datapack namespace (default: 'minecraft')"
    )
    description: Optional[str] = Field(
        default=None,
        description="Optional comment header description for the function"
    )



class FunctionTagDefinition(BaseModel):
    """
    Specification for a function tag JSON resource (e.g. tick.json, load.json).
    """
    model_config = ConfigDict(extra="allow")

    tag_name: str = Field(
        ...,
        description="Tag identifier without .json extension (e.g. 'tick' or 'load')"
    )
    values: List[str] = Field(
        default_factory=list,
        description="Function names or tag references (e.g. ['minecraft:tick'])"
    )
    namespace: str = Field(
        default="minecraft",
        description="Tag namespace (default: 'minecraft')"
    )
    replace: bool = Field(
        default=False,
        description="Whether this tag overrides previous values"
    )


class AdvancementDefinition(BaseModel):
    """
    Specification for an advancement JSON resource.
    """
    model_config = ConfigDict(extra="allow")

    advancement_path: str = Field(
        ...,
        description="Relative advancement path without .json extension (e.g. 'kill_creeper')"
    )
    criteria: Dict[str, Any] = Field(
        default_factory=dict,
        description="Criteria and triggers for the advancement"
    )
    rewards: Dict[str, Any] = Field(
        default_factory=dict,
        description="Rewards awarded upon completion (e.g. function, experience, loot)"
    )
    namespace: str = Field(
        default="minecraft",
        description="Advancement namespace (default: 'minecraft')"
    )
    display: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional advancement display information"
    )


class RecipeDefinition(BaseModel):
    """
    Specification for a Minecraft Java 1.21.11 recipe JSON resource.
    Supports crafting_shaped, crafting_shapeless, smelting, blasting, smoking, campfire_cooking, stonecutting.
    """
    model_config = ConfigDict(extra="allow")

    recipe_path: str = Field(
        ...,
        description="Relative recipe path without .json extension (e.g. 'diamond_sword' or 'saddle')"
    )
    recipe_type: str = Field(
        default="crafting_shapeless",
        description="Minecraft recipe type serializer (e.g. 'crafting_shaped', 'crafting_shapeless', 'smelting')"
    )
    result_item: str = Field(
        ...,
        description="Item ID produced by the recipe (e.g. 'minecraft:diamond_sword')"
    )
    result_count: int = Field(
        default=1,
        description="Quantity of result item produced"
    )
    ingredients: List[str] = Field(
        default_factory=list,
        description="List of ingredient item IDs for shapeless/cooking recipes"
    )
    pattern: List[str] = Field(
        default_factory=list,
        description="Row grid pattern for shaped recipes (e.g. ['X', 'X', '#'])"
    )
    key: Dict[str, str] = Field(
        default_factory=dict,
        description="Symbol mapping for shaped pattern (e.g. {'#': 'minecraft:stick', 'X': 'minecraft:diamond'})"
    )
    experience: float = Field(
        default=0.0,
        description="Experience awarded upon smelting/cooking"
    )
    cooking_time: int = Field(
        default=200,
        description="Cooking time in ticks"
    )
    category: Optional[str] = Field(
        default="misc",
        description="Recipe book category (e.g. 'building', 'redstone', 'equipment', 'misc')"
    )
    group: Optional[str] = Field(
        default=None,
        description="Optional recipe group"
    )
    namespace: str = Field(
        default="minecraft",
        description="Recipe namespace (default: 'minecraft')"
    )


class PredicateDefinition(BaseModel):
    """
    Specification for a Minecraft Java 1.21.11 predicate JSON resource.
    Saved to data/<namespace>/predicate/<predicate_path>.json.
    """
    model_config = ConfigDict(extra="allow")

    predicate_path: str = Field(
        ...,
        description="Relative predicate path without .json extension (e.g. 'is_raining', 'is_night')"
    )
    condition_type: str = Field(
        default="minecraft:weather_check",
        description="Minecraft condition type (e.g. 'minecraft:weather_check', 'minecraft:time_check', 'minecraft:random_chance', 'minecraft:location_check', 'minecraft:entity_properties', 'minecraft:match_tool', 'minecraft:inverted', 'minecraft:any_of', 'minecraft:all_of', 'minecraft:reference', 'minecraft:entity_scores')"
    )
    condition_params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Parameters for the condition (e.g. {'raining': True}, {'chance': 0.5}, {'value': {'min': 13000, 'max': 24000}})"
    )
    terms: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Sub-conditions for composite conditions ('any_of', 'all_of')"
    )
    term: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Sub-condition for inverted condition ('inverted')"
    )
    namespace: str = Field(
        default="minecraft_ai",
        description="Predicate namespace (default: 'minecraft_ai')"
    )


class DatapackManifest(BaseModel):
    model_config = ConfigDict(extra="allow")

    pack_format: int = Field(
        default=94,
        description="Minecraft Java 1.21.11 major data pack format"
    )
    min_format: Optional[List[int]] = Field(
        default_factory=lambda: [94, 0],
        description="Minimum supported pack format [major, minor]"
    )
    max_format: Optional[List[int]] = Field(
        default_factory=lambda: [94, 1],
        description="Maximum supported pack format [major, minor] (1.21.11 is 94.1)"
    )
    description: str = Field(
        default="Generated by MinecraftAI",
        description="Description of the datapack in pack.mcmeta"
    )


class GenerationResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    datapack_name: str
    datapack_path: Path
    zip_path: Optional[Path] = None
    files_generated: List[str] = Field(default_factory=list)
    status: str = "success"
    message: Optional[str] = None


class MechanismSpecification(BaseModel):
    """
    Structured specification of a Minecraft datapack implementation mechanism.
    Serves as the clean, typed boundary between the AI Planner and Deterministic Generator.
    """
    model_config = ConfigDict(extra="allow")

    type: str = Field(
        ...,
        description="Mechanism category: 'loot_table', 'function', 'function_tag', 'advancement', etc."
    )
    description: Optional[str] = Field(
        default=None,
        description="Optional human-readable explanation of why this mechanism is used"
    )
    namespace: Optional[str] = Field(
        default="minecraft_ai",
        description="Resource namespace (e.g. 'minecraft', 'minecraft_ai', or custom namespace)"
    )
    path: Optional[str] = Field(
        default=None,
        description="Resource path (e.g. 'tick', 'combat/heal', 'story/root')"
    )
    target: Optional[str] = Field(
        default=None,
        description="Target resource identifier or file (e.g. 'entities/creeper.json')"
    )

    # Semantic property modification parameters (Step 17.3)
    property_modification: Optional[PropertyModification] = Field(
        default=None,
        description="Structured semantic property modification"
    )
    implementation: Optional[str] = Field(
        default=None,
        description="Structural Minecraft implementation category ('effect', 'attribute', 'scoreboard', etc.)"
    )

    # Loot table parameters
    item: Optional[str] = Field(
        default=None,
        description="Minecraft item ID (e.g. 'minecraft:diamond')"
    )
    count: Optional[Union[int, Dict[str, Any]]] = Field(
        default=1,
        description="Item drop count or distribution"
    )
    operation: Optional[str] = Field(
        default="add_pool",
        description="Operation: 'add_pool' or 'replace'"
    )
    conditions: Optional[List[Dict[str, Any]]] = Field(
        default_factory=list,
        description="Loot table conditions"
    )
    functions: Optional[List[Dict[str, Any]]] = Field(
        default_factory=list,
        description="Loot table item functions"
    )
    rolls: Optional[float] = Field(
        default=1.0,
        description="Number of rolls for the pool"
    )

    # Function & Action parameters
    actions: Optional[List[Union[ActionSpecification, Dict[str, Any]]]] = Field(
        default_factory=list,
        description="Structured actions for function or continuous_action mechanisms"
    )
    commands: Optional[List[str]] = Field(
        default_factory=list,
        description="List of Minecraft commands for function resources (legacy fallback)"
    )

    # State machine & Scoreboard parameters
    state_scope: Optional[str] = Field(
        default="global",
        description="Scope of state machine: 'global' (e.g. environment/world) or 'player'"
    )
    objective: Optional[str] = Field(
        default=None,
        description="Scoreboard objective name for state machine tracking or scoreboard mechanism"
    )
    condition_predicate: Optional[str] = Field(
        default=None,
        description="Resource identifier of condition predicate (e.g. 'minecraft_ai:is_raining')"
    )
    on_enter: Optional[List[Union[ActionSpecification, Dict[str, Any]]]] = Field(
        default_factory=list,
        description="Actions triggered when the state transition activates"
    )
    on_exit: Optional[List[Union[ActionSpecification, Dict[str, Any]]]] = Field(
        default_factory=list,
        description="Actions triggered when the state transition deactivates"
    )
    trigger: Optional[str] = Field(
        default=None,
        description="Trigger hook: 'tick', 'load', 'custom'"
    )

    # Scoreboard-specific parameters
    display_name: Optional[Union[str, Dict[str, Any]]] = Field(
        default=None,
        description="Optional display name for scoreboard objective"
    )
    display_slot: Optional[str] = Field(
        default=None,
        description="Optional display slot: 'sidebar', 'list', 'below_name', 'sidebar.team.<color>'"
    )
    source_holder: Optional[str] = Field(
        default=None,
        description="Source score holder for scoreboard operation actions"
    )
    source_objective: Optional[str] = Field(
        default=None,
        description="Source objective name for scoreboard operation actions"
    )

    # Function tag parameters
    tag_name: Optional[str] = Field(
        default=None,
        description="Tag name (e.g. 'tick', 'load')"
    )
    values: Optional[List[str]] = Field(
        default_factory=list,
        description="Function identifiers included in tag"
    )
    replace: Optional[bool] = Field(
        default=False,
        description="Whether this tag overrides previous values"
    )

    # Advancement & Scoreboard criteria parameters
    criteria: Optional[Union[Dict[str, Any], str]] = Field(
        default=None,
        description="Criteria and triggers for advancement (dict) or scoreboard objective (str, e.g. 'dummy', 'deathCount')"
    )
    rewards: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Rewards awarded upon advancement completion"
    )
    display: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional display information for the advancement"
    )

    # Recipe parameters
    recipe_type: Optional[str] = Field(
        default="crafting_shapeless",
        description="Recipe type: 'crafting_shaped', 'crafting_shapeless', 'smelting', 'blasting', 'smoking', 'campfire_cooking', 'stonecutting'"
    )
    result_item: Optional[str] = Field(
        default=None,
        description="Result item ID for recipes (e.g. 'minecraft:diamond')"
    )
    result_count: Optional[int] = Field(
        default=1,
        description="Count of result items produced"
    )
    ingredients: Optional[List[str]] = Field(
        default_factory=list,
        description="Ingredient item IDs for shapeless/smelting recipes"
    )
    pattern: Optional[List[str]] = Field(
        default_factory=list,
        description="Pattern grid for shaped crafting"
    )
    key: Optional[Dict[str, str]] = Field(
        default_factory=dict,
        description="Key mapping characters to item IDs for shaped crafting"
    )
    experience: Optional[float] = Field(
        default=0.0,
        description="Experience awarded from cooking/smelting"
    )
    cooking_time: Optional[int] = Field(
        default=200,
        description="Cooking/smelting time in ticks"
    )
    category: Optional[str] = Field(
        default="misc",
        description="Recipe book category"
    )
    group: Optional[str] = Field(
        default=None,
        description="Optional recipe group"
    )

    # Predicate parameters
    condition_type: Optional[str] = Field(
        default=None,
        description="Condition type for predicate mechanism (e.g. 'minecraft:weather_check', 'minecraft:time_check', 'minecraft:random_chance', 'minecraft:location_check', 'minecraft:entity_properties', 'minecraft:match_tool', 'minecraft:inverted', 'minecraft:any_of', 'minecraft:all_of', 'minecraft:reference', 'minecraft:entity_scores')"
    )
    condition_params: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Parameters for the condition (e.g. {'raining': True} or {'chance': 0.5})"
    )
    terms: Optional[List[Dict[str, Any]]] = Field(
        default_factory=list,
        description="Sub-conditions for composite predicate types ('any_of', 'all_of')"
    )
    term: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Sub-condition for inverted predicate type ('inverted')"
    )

    def validate_completeness(self) -> None:
        """
        Validates that required fields for this mechanism type are populated.
        Raises ValueError if the specification is incomplete.
        """
        validate_mechanism_specification(self)

    def to_loot_modification(self) -> LootTableModification:
        lt_path = self.target or self.path
        if not lt_path:
            raise ValueError("Cannot convert to LootTableModification: missing 'target' or 'path'")
        if not self.item:
            raise ValueError("Cannot convert to LootTableModification: missing 'item'")

        return LootTableModification(
            loot_table_path=lt_path,
            item=self.item,
            count=self.count if self.count is not None else 1,
            operation=self.operation or "add_pool",
            conditions=self.conditions or [],
            functions=self.functions or [],
            rolls=self.rolls if self.rolls is not None else 1.0
        )

    def to_function_definition(self) -> FunctionDefinition:
        f_path = self.path
        if not f_path or f_path.startswith("@") or " " in f_path or "[" in f_path:
            prop = getattr(self.property_modification, "property", None) or getattr(self.property_modification, "property_name", None)
            if prop:
                clean_prop = re.sub(r'[^a-z0-9_.-]', '_', str(prop).lower())
                f_path = f"modify_{clean_prop}"
            elif self.target and not self.target.startswith("@") and " " not in self.target and "[" not in self.target:
                f_path = self.target
            else:
                f_path = "main"
        parsed_actions: List[ActionSpecification] = []
        for act in (self.actions or []):
            if isinstance(act, ActionSpecification):
                parsed_actions.append(act)
            elif isinstance(act, dict):
                parsed_actions.append(ActionSpecification(**act))

        return FunctionDefinition(
            function_path=f_path,
            actions=parsed_actions,
            commands=self.commands or [],
            namespace=self.namespace or "minecraft_ai",
            description=self.description
        )

    def to_tag_definition(self) -> FunctionTagDefinition:
        t_name = self.tag_name or self.path or self.target or "tick"
        return FunctionTagDefinition(
            tag_name=t_name,
            values=self.values or [],
            namespace=self.namespace or "minecraft",
            replace=bool(self.replace)
        )

    def to_scoreboard_objective_definition(self) -> ScoreboardObjectiveDefinition:
        obj_name = self.objective or self.path or self.target
        if not obj_name:
            raise ValueError(
                "Cannot convert to ScoreboardObjectiveDefinition: missing 'objective', 'path', or 'target'"
            )
        crit = self.criteria or "dummy"
        if isinstance(crit, dict):
            raise ValueError(f"Scoreboard criteria must be a string, got dict: {crit}")
        return ScoreboardObjectiveDefinition(
            objective=str(obj_name),
            criteria=str(crit),
            display_name=self.display_name,
            display_slot=self.display_slot
        )

    def to_advancement_definition(self) -> AdvancementDefinition:
        a_path = self.path or self.target or "root"
        crit = self.criteria if isinstance(self.criteria, dict) else {}
        return AdvancementDefinition(
            advancement_path=a_path,
            criteria=crit,
            rewards=self.rewards or {},
            namespace=self.namespace or "minecraft_ai",
            display=self.display
        )

    def to_recipe_definition(self) -> RecipeDefinition:
        r_path = self.path or self.target or "custom_recipe"
        res_item = self.result_item or self.item
        if not res_item:
            raise ValueError("Cannot convert to RecipeDefinition: missing 'result_item' or 'item'")

        return RecipeDefinition(
            recipe_path=r_path,
            recipe_type=self.recipe_type or "crafting_shapeless",
            result_item=res_item,
            result_count=self.result_count if self.result_count is not None else 1,
            ingredients=self.ingredients or [],
            pattern=self.pattern or [],
            key=self.key or {},
            experience=self.experience if self.experience is not None else 0.0,
            cooking_time=self.cooking_time if self.cooking_time is not None else 200,
            category=self.category or "misc",
            group=self.group,
            namespace=self.namespace or "minecraft"
        )

    def to_predicate_definition(self) -> PredicateDefinition:
        p_path = self.path or self.target or "custom_predicate"
        c_type = self.condition_type or "minecraft:weather_check"
        if not c_type.startswith("minecraft:"):
            c_type = f"minecraft:{c_type}"

        return PredicateDefinition(
            predicate_path=p_path,
            condition_type=c_type,
            condition_params=self.condition_params or {},
            terms=self.terms or [],
            term=self.term,
            namespace=self.namespace or "minecraft_ai"
        )


def validate_mechanism_specification(spec: Union[MechanismSpecification, Dict[str, Any], ScoreboardObjectiveDefinition]) -> None:
    """
    Strictly validates a mechanism specification for completeness.
    Raises ValueError if required parameters are missing or invalid.
    """
    if isinstance(spec, dict):
        spec_type = str(spec.get("type", "")).lower()
        target = spec.get("target") or spec.get("path")
        item = spec.get("item")
        actions = spec.get("actions")
        commands = spec.get("commands")
        path = spec.get("path") or spec.get("function_path") or spec.get("target")
        tag_name = spec.get("tag_name") or spec.get("path") or spec.get("target")
        values = spec.get("values")
        criteria = spec.get("criteria")
        recipe_type = str(spec.get("recipe_type", "crafting_shapeless")).lower()
        result_item = spec.get("result_item") or spec.get("item")
        ingredients = spec.get("ingredients")
        pattern = spec.get("pattern")
        key = spec.get("key")
        condition_type = spec.get("condition_type") or spec.get("condition")
        condition_params = spec.get("condition_params") or {}
        terms = spec.get("terms")
        term = spec.get("term")
        objective = spec.get("objective") or spec.get("path")
        condition_predicate = spec.get("condition_predicate") or spec.get("predicate")
        on_enter = spec.get("on_enter") or spec.get("actions")
        display_name = spec.get("display_name")
        display_slot = spec.get("display_slot")
        source_holder = spec.get("source_holder")
        source_objective = spec.get("source_objective")
    elif isinstance(spec, MechanismSpecification):
        spec_type = str(spec.type).lower()
        target = spec.target or spec.path
        item = spec.item
        actions = spec.actions
        commands = spec.commands
        path = spec.path or spec.target
        tag_name = spec.tag_name or spec.path or spec.target
        values = spec.values
        criteria = spec.criteria
        recipe_type = str(spec.recipe_type or "crafting_shapeless").lower()
        result_item = spec.result_item or spec.item
        ingredients = spec.ingredients
        pattern = spec.pattern
        key = spec.key
        condition_type = spec.condition_type
        condition_params = spec.condition_params or {}
        terms = spec.terms
        term = spec.term
        objective = spec.objective or spec.path
        condition_predicate = spec.condition_predicate
        on_enter = spec.on_enter or spec.actions
        display_name = spec.display_name
        display_slot = spec.display_slot
        source_holder = spec.source_holder
        source_objective = spec.source_objective
    elif isinstance(spec, ScoreboardObjectiveDefinition):
        spec_type = "scoreboard_objective"
        target = None
        item = None
        actions = None
        commands = None
        path = None
        tag_name = None
        values = None
        criteria = spec.criteria
        recipe_type = "crafting_shapeless"
        result_item = None
        ingredients = None
        pattern = None
        key = None
        condition_type = None
        condition_params = {}
        terms = None
        term = None
        objective = spec.objective
        condition_predicate = None
        on_enter = None
        display_name = spec.display_name
        display_slot = spec.display_slot
        source_holder = None
        source_objective = None
    else:
        raise ValueError(f"Expected MechanismSpecification, ScoreboardObjectiveDefinition, or dict, got {type(spec)}")

    if not spec_type:
        raise ValueError("Mechanism specification missing required 'type'.")

    # 1. Function tag (check before function to prevent substring collision)
    if spec_type in ["function_tag", "tag", "tick_tag", "load_tag"] or "tag" in spec_type:
        if not tag_name or not str(tag_name).strip():
            raise ValueError(f"Incomplete function_tag specification: missing 'tag_name' or 'path'. Got tag_name={tag_name}")
        if values is None or not isinstance(values, list) or len(values) == 0:
            raise ValueError(f"Incomplete function_tag specification: 'values' must be a non-empty list. Got values={values}")

    # 2. Function
    elif spec_type in ["function", "mcfunction", "command", "function_command"]:
        if not path or not str(path).strip():
            raise ValueError(f"Incomplete function specification: missing 'path'. Got path={path}")
        has_cmds = commands is not None and isinstance(commands, list) and len(commands) > 0
        has_actions = actions is not None and isinstance(actions, list) and len(actions) > 0
        if not (has_cmds or has_actions):
            raise ValueError(f"Incomplete function specification: must provide non-empty 'actions' or 'commands'. Got actions={actions}, commands={commands}")
        if actions:
            if not isinstance(actions, list):
                raise ValueError(f"Incomplete function specification: 'actions' must be a list. Got actions={actions}")
            for act in actions:
                if isinstance(act, dict):
                    ActionSpecification(**act)
                elif isinstance(act, ActionSpecification):
                    pass
                else:
                    raise ValueError(f"Invalid action item in function mechanism: {type(act).__name__}")

    # 3. State Machine
    elif spec_type in ["state_machine", "event_latch", "event_trigger"]:
        if not objective or not str(objective).strip():
            raise ValueError(f"Incomplete state_machine specification: missing 'objective'. Got objective={objective}")
        validate_objective_name(str(objective))
        if not condition_predicate or not str(condition_predicate).strip():
            raise ValueError(f"Incomplete state_machine specification: missing 'condition_predicate'. Got condition_predicate={condition_predicate}")
        if not on_enter or not isinstance(on_enter, list) or len(on_enter) == 0:
            raise ValueError(f"Incomplete state_machine specification: 'on_enter' must be a non-empty list of actions. Got on_enter={on_enter}")
        for act in on_enter:
            if isinstance(act, dict):
                ActionSpecification(**act)

    # 4. Continuous Action
    elif spec_type in ["continuous_action", "tick_action"]:
        if not actions or not isinstance(actions, list) or len(actions) == 0:
            raise ValueError(f"Incomplete continuous_action specification: 'actions' must be a non-empty list. Got actions={actions}")
        for act in actions:
            if isinstance(act, dict):
                ActionSpecification(**act)

    # 5. Loot table
    elif spec_type in ["loot_table", "loot", "drop", "table", "loot_table_modification", "loot_table_override"] or "loot" in spec_type:
        if not target or not str(target).strip():
            raise ValueError(f"Incomplete loot_table specification: missing 'target' or 'path'. Got target={target}")
        if not item or not str(item).strip():
            raise ValueError(f"Incomplete loot_table specification: missing 'item'. Got item={item}")

    # 6. Advancement
    elif spec_type in ["advancement", "trigger"] or "advancement" in spec_type:
        if not path or not str(path).strip():
            raise ValueError(f"Incomplete advancement specification: missing 'path'. Got path={path}")
        if not criteria or not isinstance(criteria, dict) or len(criteria) == 0:
            raise ValueError(f"Incomplete advancement specification: 'criteria' must be a non-empty dictionary. Got criteria={criteria}")

    # 7. Recipe
    elif spec_type in ["recipe", "crafting", "crafting_shaped", "crafting_shapeless", "smelting", "blasting", "smoking", "campfire_cooking", "stonecutting"] or "recipe" in spec_type:
        if not result_item or not str(result_item).strip():
            raise ValueError(f"Incomplete recipe specification: missing 'result_item' or 'item'. Got result_item={result_item}")
        if "shaped" in recipe_type:
            if not pattern or not isinstance(pattern, list) or len(pattern) == 0:
                raise ValueError(f"Incomplete shaped recipe specification: 'pattern' must be a non-empty list. Got pattern={pattern}")
            if not key or not isinstance(key, dict) or len(key) == 0:
                raise ValueError(f"Incomplete shaped recipe specification: 'key' must be a non-empty dictionary. Got key={key}")
        elif any(t in recipe_type for t in ["shapeless", "smelt", "blast", "smoke", "campfire", "stonecut"]):
            if not ingredients or not isinstance(ingredients, list) or len(ingredients) == 0:
                raise ValueError(f"Incomplete recipe specification: 'ingredients' must be a non-empty list. Got ingredients={ingredients}")

    # 8. Predicate
    elif spec_type in ["predicate", "custom_predicate", "condition"] or "predicate" in spec_type:
        if not path or not str(path).strip():
            raise ValueError(f"Incomplete predicate specification: missing 'path'. Got path={path}")
        if not condition_type or not str(condition_type).strip():
            raise ValueError(f"Incomplete predicate specification: missing 'condition_type'. Got condition_type={condition_type}")
        norm_cond = str(condition_type).strip().lower()
        if not norm_cond.startswith("minecraft:"):
            norm_cond = f"minecraft:{norm_cond}"
        if norm_cond in ["minecraft:any_of", "minecraft:all_of"]:
            if not terms or not isinstance(terms, list) or len(terms) == 0:
                raise ValueError(f"Incomplete composite predicate specification: 'terms' must be a non-empty list for '{norm_cond}'. Got terms={terms}")
        elif norm_cond == "minecraft:inverted":
            if not term or not isinstance(term, dict) or len(term) == 0:
                raise ValueError(f"Incomplete inverted predicate specification: 'term' must be a non-empty dictionary for '{norm_cond}'. Got term={term}")
        elif norm_cond == "minecraft:random_chance":
            chance_val = condition_params.get("chance") if isinstance(condition_params, dict) else None
            if chance_val is None:
                raise ValueError(f"Incomplete random_chance predicate specification: missing 'chance' in condition_params. Got condition_params={condition_params}")

    # 9. Scoreboard objective
    elif spec_type in ["scoreboard_objective", "scoreboard", "scoreboard_objectives", "objective"]:
        obj_name = objective or path or target
        if not obj_name or not str(obj_name).strip():
            raise ValueError(
                f"Incomplete scoreboard mechanism specification: missing 'objective'. Got objective={objective}"
            )
        validate_objective_name(str(obj_name))

        if not criteria or not str(criteria).strip():
            raise ValueError(
                f"Incomplete scoreboard mechanism specification: missing 'criteria'. Got criteria={criteria}"
            )
        if isinstance(criteria, dict):
            raise ValueError(f"Scoreboard criteria must be a string, got dict: {criteria}")
        validate_criteria(str(criteria))

        if display_slot is not None and str(display_slot).strip():
            validate_display_slot(str(display_slot))

        if actions:
            if not isinstance(actions, list):
                raise ValueError(
                    f"Incomplete scoreboard mechanism specification: 'actions' must be a list. Got actions={actions}"
                )
            for act in actions:
                if isinstance(act, dict):
                    ActionSpecification(**act)
                elif isinstance(act, ActionSpecification):
                    pass
                else:
                    raise ValueError(f"Invalid action item in scoreboard mechanism: {type(act).__name__}")

    # 10. Property modification (Step 17.3)
    elif spec_type in ["property_modification", "modify_property"]:
        prop_mod = spec.property_modification if isinstance(spec, MechanismSpecification) else spec.get("property_modification")
        actions = spec.actions if isinstance(spec, MechanismSpecification) else spec.get("actions")
        if prop_mod is None and not actions:
            raise ValueError(
                "Incomplete property_modification specification: must provide 'property_modification' or 'actions'."
            )
        if actions:
            for act in actions:
                if isinstance(act, dict):
                    ActionSpecification(**act)

    else:
        raise ValueError(f"Unsupported mechanism specification type: '{spec_type}'")


class MinecraftDatapackSpec(BaseModel):
    """
    Structured semantic/datapack specification defining target version and planned content.
    Represents generation context decoupled from semantic property meaning.
    """
    model_config = ConfigDict(extra="allow")

    minecraft_version: str = Field(
        default="1.21.11",
        description="Target Minecraft Java Edition version"
    )
    requirements: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="High-level requirements / objectives"
    )
    mechanisms: List[MechanismSpecification] = Field(
        default_factory=list,
        description="Planned datapack mechanisms"
    )
    actions: List[ActionSpecification] = Field(
        default_factory=list,
        description="Planned actions / command specifications"
    )


