from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, ConfigDict


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


class FunctionDefinition(BaseModel):
    """
    Specification for a Minecraft .mcfunction resource.
    """
    model_config = ConfigDict(extra="allow")

    function_path: str = Field(
        ...,
        description="Relative function path without .mcfunction extension (e.g. 'main' or 'tick')"
    )
    commands: List[str] = Field(
        default_factory=list,
        description="List of Minecraft commands to execute in this function"
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

    # Function parameters
    commands: Optional[List[str]] = Field(
        default_factory=list,
        description="List of Minecraft commands for function resources"
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

    # Advancement parameters
    criteria: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Criteria and triggers for the advancement"
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
        f_path = self.path or self.target or "main"
        return FunctionDefinition(
            function_path=f_path,
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

    def to_advancement_definition(self) -> AdvancementDefinition:
        a_path = self.path or self.target or "root"
        return AdvancementDefinition(
            advancement_path=a_path,
            criteria=self.criteria or {},
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


def validate_mechanism_specification(spec: Union[MechanismSpecification, Dict[str, Any]]) -> None:
    """
    Strictly validates a mechanism specification for completeness.
    Raises ValueError if required parameters are missing or invalid.
    """
    if isinstance(spec, dict):
        spec_type = str(spec.get("type", "")).lower()
        target = spec.get("target") or spec.get("path")
        item = spec.get("item")
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
    elif isinstance(spec, MechanismSpecification):
        spec_type = str(spec.type).lower()
        target = spec.target or spec.path
        item = spec.item
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
    else:
        raise ValueError(f"Expected MechanismSpecification or dict, got {type(spec)}")

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
        if not commands or not isinstance(commands, list) or len(commands) == 0:
            raise ValueError(f"Incomplete function specification: 'commands' must be a non-empty list. Got commands={commands}")

    # 3. Loot table
    elif spec_type in ["loot_table", "loot", "drop", "table", "loot_table_modification", "loot_table_override"] or "loot" in spec_type:
        if not target or not str(target).strip():
            raise ValueError(f"Incomplete loot_table specification: missing 'target' or 'path'. Got target={target}")
        if not item or not str(item).strip():
            raise ValueError(f"Incomplete loot_table specification: missing 'item'. Got item={item}")

    # 4. Advancement
    elif spec_type in ["advancement", "trigger"] or "advancement" in spec_type:
        if not path or not str(path).strip():
            raise ValueError(f"Incomplete advancement specification: missing 'path'. Got path={path}")
        if not criteria or not isinstance(criteria, dict) or len(criteria) == 0:
            raise ValueError(f"Incomplete advancement specification: 'criteria' must be a non-empty dictionary. Got criteria={criteria}")

    # 5. Recipe
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

    else:
        raise ValueError(f"Unsupported mechanism specification type: '{spec_type}'")

