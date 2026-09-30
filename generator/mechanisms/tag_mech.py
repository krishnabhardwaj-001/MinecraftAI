import json
from typing import Any, List, Optional

from generator.mechanisms.base import BaseMechanismGenerator
from generator.models import DatapackResource, FunctionTagDefinition


class FunctionTagMechanismGenerator(BaseMechanismGenerator):
    """
    Deterministic mechanism generator for Minecraft Java 1.21.11 function tags.
    Produces tag JSON files under 'data/<namespace>/tags/function/<tag_name>.json'
    (e.g., #minecraft:tick for continuous game-loop execution and #minecraft:load for initialization).
    """

    def __init__(self, version: str = "1.21.11", version_context: Optional[Any] = None):
        self.version = version
        self.version_context = version_context

    def generate(self, spec: FunctionTagDefinition) -> List[DatapackResource]:
        clean_tag = spec.tag_name.strip().replace("\\", "/").strip("/")
        if clean_tag.endswith(".json"):
            clean_tag = clean_tag[:-5]

        # In Minecraft Java 1.21.11, standard game-loop tags ('tick', 'load') must reside
        # under the 'minecraft' namespace (data/minecraft/tags/function/{tick,load}.json).
        if clean_tag in ["tick", "load"]:
            tag_namespace = "minecraft"
            fallback_val_ns = (
                spec.namespace if spec.namespace and spec.namespace != "minecraft" else "minecraft_ai"
            )
        else:
            tag_namespace = spec.namespace or "minecraft"
            fallback_val_ns = spec.namespace or "minecraft_ai"

        # Normalize values: ensure each function identifier is valid
        normalized_values: List[str] = []
        for val in spec.values:
            val_clean = val.strip()
            if not val_clean:
                continue
            if ":" not in val_clean and not val_clean.startswith("#"):
                val_clean = f"{fallback_val_ns}:{val_clean}"
            normalized_values.append(val_clean)

        # Standard canonical tag format: omit 'replace' when false (Mojang default).
        # Only include 'replace': true when explicitly requested.
        tag_dict: dict = {
            "values": normalized_values
        }
        if spec.replace:
            tag_dict["replace"] = True

        content = json.dumps(tag_dict, indent=2, ensure_ascii=False) + "\n"
        rel_path = f"data/{tag_namespace}/tags/function/{clean_tag}.json"

        return [
            DatapackResource(
                relative_path=rel_path,
                content=content,
                resource_type="function_tag"
            )
        ]
