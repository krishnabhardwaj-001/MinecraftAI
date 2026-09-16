import json
from typing import Any, Dict, List

from generator.mechanisms.base import BaseMechanismGenerator
from generator.models import DatapackResource, RecipeDefinition


class RecipeMechanismGenerator(BaseMechanismGenerator):
    """
    Deterministic mechanism generator for Minecraft Java 1.21.11 recipe JSON files.
    Produces recipes under 'data/<namespace>/recipe/<name>.json'.
    Strictly complies with 1.21+ singular 'recipe/' path and 'result.id' syntax.
    """

    def __init__(self, version: str = "1.21.11"):
        self.version = version

    def _normalize_item_id(self, item_id: str) -> str:
        clean = item_id.strip()
        if not clean:
            return clean
        if clean.startswith("#"):
            tag_name = clean[1:].strip()
            if ":" not in tag_name:
                return f"#minecraft:{tag_name}"
            return f"#{tag_name}"
        if ":" not in clean:
            return f"minecraft:{clean}"
        return clean

    def generate(self, spec: RecipeDefinition) -> List[DatapackResource]:
        clean_path = spec.recipe_path.strip().replace("\\", "/").strip("/")
        if clean_path.endswith(".json"):
            clean_path = clean_path[:-5]

        # Normalize recipe type
        raw_type = str(spec.recipe_type).strip().lower()
        if raw_type in ["crafting_shaped", "shaped"]:
            rec_type = "minecraft:crafting_shaped"
        elif raw_type in ["crafting_shapeless", "shapeless", "crafting"]:
            rec_type = "minecraft:crafting_shapeless"
        elif raw_type in ["smelting", "smelt"]:
            rec_type = "minecraft:smelting"
        elif raw_type in ["blasting", "blast"]:
            rec_type = "minecraft:blasting"
        elif raw_type in ["smoking", "smoke"]:
            rec_type = "minecraft:smoking"
        elif raw_type in ["campfire_cooking", "campfire"]:
            rec_type = "minecraft:campfire_cooking"
        elif raw_type in ["stonecutting", "stonecut"]:
            rec_type = "minecraft:stonecutting"
        else:
            rec_type = raw_type if ":" in raw_type else f"minecraft:{raw_type}"

        # Normalize result item
        result_id = self._normalize_item_id(spec.result_item)
        result_count = spec.result_count if spec.result_count is not None and spec.result_count > 0 else 1

        # Normalize ingredients
        raw_ingredients = spec.ingredients or []
        if isinstance(raw_ingredients, str):
            raw_ingredients = [raw_ingredients]
        normalized_ingredients = [
            self._normalize_item_id(ing) for ing in raw_ingredients if str(ing).strip()
        ]

        recipe_dict: Dict[str, Any] = {
            "type": rec_type
        }

        if spec.category:
            recipe_dict["category"] = spec.category

        if spec.group:
            recipe_dict["group"] = spec.group

        # 1. Shaped crafting
        if rec_type == "minecraft:crafting_shaped":
            normalized_key: Dict[str, str] = {}
            for sym, item in spec.key.items():
                normalized_key[sym] = self._normalize_item_id(item)

            recipe_dict["key"] = normalized_key
            recipe_dict["pattern"] = spec.pattern
            recipe_dict["result"] = {
                "count": result_count,
                "id": result_id
            }

        # 2. Cooking (smelting, blasting, smoking, campfire_cooking)
        elif rec_type in [
            "minecraft:smelting",
            "minecraft:blasting",
            "minecraft:smoking",
            "minecraft:campfire_cooking"
        ]:
            primary_ingredient = (
                normalized_ingredients[0] if normalized_ingredients else "minecraft:stone"
            )
            recipe_dict["cookingtime"] = int(spec.cooking_time if spec.cooking_time is not None else 200)
            recipe_dict["experience"] = float(spec.experience if spec.experience is not None else 0.0)
            recipe_dict["ingredient"] = primary_ingredient
            recipe_dict["result"] = {
                "id": result_id
            }
            if result_count > 1:
                recipe_dict["result"]["count"] = result_count

        # 3. Stonecutting
        elif rec_type == "minecraft:stonecutting":
            primary_ingredient = (
                normalized_ingredients[0] if normalized_ingredients else "minecraft:stone"
            )
            recipe_dict["ingredient"] = primary_ingredient
            recipe_dict["result"] = {
                "count": result_count,
                "id": result_id
            }

        # 4. Default: Shapeless crafting
        else:
            recipe_dict["ingredients"] = (
                normalized_ingredients if normalized_ingredients else ["minecraft:stick"]
            )
            recipe_dict["result"] = {
                "count": result_count,
                "id": result_id
            }

        content = json.dumps(recipe_dict, indent=2, ensure_ascii=False) + "\n"
        namespace = spec.namespace or "minecraft"
        rel_path = f"data/{namespace}/recipe/{clean_path}.json"

        return [
            DatapackResource(
                relative_path=rel_path,
                content=content,
                resource_type="recipe"
            )
        ]
