import json
from typing import List

from generator.mechanisms.base import BaseMechanismGenerator
from generator.models import DatapackResource, FunctionTagDefinition


class FunctionTagMechanismGenerator(BaseMechanismGenerator):
    """
    Deterministic mechanism generator for Minecraft Java 1.21.11 function tags.
    Produces tag JSON files under 'data/<namespace>/tags/function/<tag_name>.json'
    (e.g., #minecraft:tick for continuous game-loop execution and #minecraft:load for initialization).
    """

    def __init__(self, version: str = "1.21.11"):
        self.version = version

    def generate(self, spec: FunctionTagDefinition) -> List[DatapackResource]:
        clean_tag = spec.tag_name.strip().replace("\\", "/").strip("/")
        if clean_tag.endswith(".json"):
            clean_tag = clean_tag[:-5]

        # Normalize values: ensure each function identifier is valid
        normalized_values: List[str] = []
        for val in spec.values:
            val_clean = val.strip()
            if not val_clean:
                continue
            if ":" not in val_clean:
                val_clean = f"{spec.namespace}:{val_clean}"
            normalized_values.append(val_clean)

        tag_dict = {
            "replace": bool(spec.replace),
            "values": normalized_values
        }

        content = json.dumps(tag_dict, indent=2, ensure_ascii=False) + "\n"
        namespace = spec.namespace or "minecraft"
        rel_path = f"data/{namespace}/tags/function/{clean_tag}.json"

        return [
            DatapackResource(
                relative_path=rel_path,
                content=content,
                resource_type="function_tag"
            )
        ]
