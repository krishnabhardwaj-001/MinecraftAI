from typing import List, Optional

from generator.loot_table_generator import LootTableGenerator
from generator.mechanisms.base import BaseMechanismGenerator
from generator.models import DatapackResource, LootTableModification


class LootTableMechanismGenerator(BaseMechanismGenerator):
    """
    Deterministic mechanism generator for Minecraft Java 1.21.11 loot tables.
    Uses LootTableGenerator to produce modified vanilla loot table JSON files
    under 'data/minecraft/loot_table/'.
    """

    def __init__(
        self,
        version: str = "1.21.11",
        loot_generator: Optional[LootTableGenerator] = None
    ):
        self.version = version
        self.loot_generator = loot_generator or LootTableGenerator(version=version)

    def generate(self, spec: LootTableModification) -> List[DatapackResource]:
        modified_table = self.loot_generator.modify_loot_table(spec)
        clean_rel = self.loot_generator._normalize_path(spec.loot_table_path)
        content = self.loot_generator.serialize_loot_table(modified_table)

        rel_path = f"data/minecraft/loot_table/{clean_rel}"
        return [
            DatapackResource(
                relative_path=rel_path,
                content=content,
                resource_type="loot_table"
            )
        ]
