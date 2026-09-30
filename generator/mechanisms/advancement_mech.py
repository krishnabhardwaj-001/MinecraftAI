import json
from typing import Any, Dict, List, Optional

from generator.mechanisms.base import BaseMechanismGenerator
from generator.models import AdvancementDefinition, DatapackResource


class AdvancementMechanismGenerator(BaseMechanismGenerator):
    """
    Deterministic mechanism generator for Minecraft Java 1.21.11 advancement JSON files.
    Produces advancements under 'data/<namespace>/advancement/<path>.json'
    for event triggers (e.g. player_killed_entity, tick, consume_item) and rewards.
    """

    def __init__(self, version: str = "1.21.11", version_context: Optional[Any] = None):
        self.version = version
        self.version_context = version_context

    def generate(self, spec: AdvancementDefinition) -> List[DatapackResource]:
        clean_path = spec.advancement_path.strip().replace("\\", "/").strip("/")
        if clean_path.endswith(".json"):
            clean_path = clean_path[:-5]

        adv_dict: Dict[str, Any] = {}

        if spec.display:
            adv_dict["display"] = spec.display

        adv_dict["criteria"] = spec.criteria or {
            "requirement": {
                "trigger": "minecraft:tick"
            }
        }

        if spec.rewards:
            adv_dict["rewards"] = spec.rewards

        content = json.dumps(adv_dict, indent=2, ensure_ascii=False) + "\n"
        namespace = spec.namespace or "minecraft"
        rel_path = f"data/{namespace}/advancement/{clean_path}.json"

        return [
            DatapackResource(
                relative_path=rel_path,
                content=content,
                resource_type="advancement"
            )
        ]
