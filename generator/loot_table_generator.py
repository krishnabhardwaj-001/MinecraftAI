import copy
import json
from pathlib import Path
from typing import Any, Dict, Optional

from generator.models import LootTableModification


class LootTableGenerator:
    """
    Deterministic Minecraft Java Edition loot-table generator and modifier.
    Preserves original Minecraft loot tables while applying structured modifications.
    """

    def __init__(self, version: str = "1.21.11"):
        self.version = version
        self.base_dir = Path(__file__).resolve().parent.parent
        self.source_loot_dir = (
            self.base_dir
            / "knowledge"
            / "loot_tables"
            / "java"
            / self.version
            / "tables"
        )

    def _normalize_path(self, loot_table_path: str) -> str:
        clean = loot_table_path.strip().replace("\\", "/")
        if clean.startswith("/"):
            clean = clean[1:]
        if clean.startswith("minecraft:"):
            clean = clean[len("minecraft:"):]
        elif clean.startswith("minecraft/"):
            clean = clean[len("minecraft/"):]
        if not clean.endswith(".json"):
            clean += ".json"
        return clean

    def _normalize_item_id(self, item_id: str) -> str:
        clean = item_id.strip().lower()
        if not clean.startswith("minecraft:"):
            clean = f"minecraft:{clean}"
        return clean

    def load_source_loot_table(
        self,
        loot_table_path: str
    ) -> Optional[Dict[str, Any]]:
        clean_path = self._normalize_path(loot_table_path)
        file_path = self.source_loot_dir / clean_path

        if not file_path.exists():
            return None

        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def modify_loot_table(
        self,
        modification: LootTableModification
    ) -> Dict[str, Any]:
        """
        Modifies a source loot table deterministically according to the modification spec.
        Preserves all existing pools, entries, conditions, functions, and random_sequence.
        """
        source = self.load_source_loot_table(modification.loot_table_path)

        if source is not None:
            table = copy.deepcopy(source)
        else:
            # Fallback to a generic entity loot table if source is not in knowledge base
            table = {
                "type": "minecraft:entity",
                "pools": []
            }

        pools = table.setdefault("pools", [])
        item_id = self._normalize_item_id(modification.item)

        # Build entry
        entry: Dict[str, Any] = {
            "type": "minecraft:item",
            "name": item_id
        }

        # Apply functions (e.g. set_count)
        if modification.functions:
            entry["functions"] = copy.deepcopy(modification.functions)
        elif isinstance(modification.count, int) and modification.count > 1:
            entry["functions"] = [
                {
                    "function": "minecraft:set_count",
                    "count": float(modification.count),
                    "add": False
                }
            ]
        elif isinstance(modification.count, dict):
            entry["functions"] = [
                {
                    "function": "minecraft:set_count",
                    "count": copy.deepcopy(modification.count),
                    "add": False
                }
            ]

        # Build new pool
        new_pool: Dict[str, Any] = {
            "rolls": float(modification.rolls),
            "entries": [entry]
        }

        if modification.conditions:
            new_pool["conditions"] = copy.deepcopy(modification.conditions)

        # Apply operation
        if modification.operation == "replace_all":
            table["pools"] = [new_pool]
        else:
            # Default: 'add_pool' preserves existing pools and appends new pool
            pools.append(new_pool)

        return table

    def serialize_loot_table(self, table: Dict[str, Any]) -> str:
        """
        Serialize table to a deterministic, formatted JSON string.
        """
        return json.dumps(table, indent=2, ensure_ascii=False) + "\n"
