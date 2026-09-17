import json
from typing import Any, Dict, List, Optional, Union

from generator.mechanisms.base import BaseMechanismGenerator
from generator.models import DatapackResource, PredicateDefinition


class PredicateMechanismGenerator(BaseMechanismGenerator):
    """
    Deterministic mechanism generator for Minecraft Java 1.21.11 predicate JSON files.
    Produces predicates under 'data/<namespace>/predicate/<name>.json'.
    Strictly complies with 1.21+ singular 'predicate/' path convention.
    """

    def __init__(self, version: str = "1.21.11"):
        self.version = version

    def _normalize_id(self, raw_id: str) -> str:
        clean = str(raw_id).strip()
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

    def _normalize_condition_type(self, raw_type: str) -> str:
        clean = str(raw_type).strip().lower()
        if not clean:
            return "minecraft:weather_check"
        if not clean.startswith("minecraft:"):
            return f"minecraft:{clean}"
        return clean

    def _build_condition(
        self,
        condition_type: str,
        params: Optional[Dict[str, Any]] = None,
        terms: Optional[List[Dict[str, Any]]] = None,
        term: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Recursively builds a clean, validated Minecraft predicate condition dictionary.
        """
        c_type = self._normalize_condition_type(condition_type)
        p = params or {}

        # 1. Composite AND / OR conditions
        if c_type in ("minecraft:any_of", "minecraft:all_of"):
            sub_terms = terms or p.get("terms", [])
            built_terms = []
            for t in sub_terms:
                if isinstance(t, dict):
                    t_type = t.get("condition", "minecraft:weather_check")
                    t_params = {k: v for k, v in t.items() if k not in ("condition", "terms", "term")}
                    t_terms = t.get("terms")
                    t_term = t.get("term")
                    built_terms.append(self._build_condition(t_type, t_params, t_terms, t_term))
            return {
                "condition": c_type,
                "terms": built_terms
            }

        # 2. Inverted NOT condition
        if c_type == "minecraft:inverted":
            sub_term = term or p.get("term", {})
            if isinstance(sub_term, dict):
                t_type = sub_term.get("condition", "minecraft:weather_check")
                t_params = {k: v for k, v in sub_term.items() if k not in ("condition", "terms", "term")}
                t_terms = sub_term.get("terms")
                t_term = sub_term.get("term")
                built_term = self._build_condition(t_type, t_params, t_terms, t_term)
            else:
                built_term = {"condition": "minecraft:weather_check", "raining": True}
            return {
                "condition": c_type,
                "term": built_term
            }

        # 3. Weather check
        if c_type == "minecraft:weather_check":
            cond: Dict[str, Any] = {"condition": c_type}
            if "raining" in p:
                cond["raining"] = bool(p["raining"])
            if "thundering" in p:
                cond["thundering"] = bool(p["thundering"])
            if "raining" not in cond and "thundering" not in cond:
                cond["raining"] = True
            return cond

        # 4. Time check
        if c_type == "minecraft:time_check":
            val = p.get("value", {"min": 13000, "max": 24000})
            cond = {
                "condition": c_type,
                "value": val
            }
            if "period" in p:
                cond["period"] = int(p["period"])
            return cond

        # 5. Random chance
        if c_type == "minecraft:random_chance":
            chance_val = float(p.get("chance", 0.5))
            return {
                "condition": c_type,
                "chance": max(0.0, min(1.0, chance_val))
            }

        # 6. Random chance with enchanted bonus
        if c_type == "minecraft:random_chance_with_enchanted_bonus":
            ench = self._normalize_id(p.get("enchantment", "minecraft:looting"))
            return {
                "condition": c_type,
                "unenchanted_chance": float(p.get("unenchanted_chance", 0.1)),
                "enchanted_chance": p.get("enchanted_chance", 0.2),
                "enchantment": ench
            }

        # 7. Match tool
        if c_type == "minecraft:match_tool":
            pred = p.get("predicate", {})
            clean_pred: Dict[str, Any] = {}
            if "items" in pred:
                items_val = pred["items"]
                if isinstance(items_val, list):
                    clean_pred["items"] = [self._normalize_id(i) for i in items_val]
                elif isinstance(items_val, str):
                    clean_pred["items"] = self._normalize_id(items_val)
            if "count" in pred:
                clean_pred["count"] = pred["count"]
            if "predicates" in pred:
                clean_pred["predicates"] = pred["predicates"]
            # Fallback if top-level has items
            if not clean_pred and "items" in p:
                items_val = p["items"]
                if isinstance(items_val, list):
                    clean_pred["items"] = [self._normalize_id(i) for i in items_val]
                else:
                    clean_pred["items"] = self._normalize_id(items_val)
            return {
                "condition": c_type,
                "predicate": clean_pred
            }

        # 8. Entity properties
        if c_type == "minecraft:entity_properties":
            entity_target = p.get("entity", "this")
            pred = p.get("predicate", {})
            clean_pred = dict(pred)
            if "type" in clean_pred:
                clean_pred["type"] = self._normalize_id(clean_pred["type"])
            # If top-level flags specified
            if "flags" in p and "flags" not in clean_pred:
                clean_pred["flags"] = p["flags"]
            return {
                "condition": c_type,
                "entity": entity_target,
                "predicate": clean_pred
            }

        # 9. Location check
        if c_type == "minecraft:location_check":
            pred = p.get("predicate", {})
            clean_pred = dict(pred)
            if "biomes" in clean_pred:
                biomes_val = clean_pred["biomes"]
                if isinstance(biomes_val, list):
                    clean_pred["biomes"] = [self._normalize_id(b) for b in biomes_val]
                else:
                    clean_pred["biomes"] = self._normalize_id(biomes_val)
            if "dimension" in clean_pred:
                clean_pred["dimension"] = self._normalize_id(clean_pred["dimension"])
            cond = {
                "condition": c_type,
                "predicate": clean_pred
            }
            if "offset" in p:
                cond["offset"] = p["offset"]
            return cond

        # 10. Entity scores
        if c_type == "minecraft:entity_scores":
            entity_target = p.get("entity", "this")
            scores = p.get("scores", {})
            return {
                "condition": c_type,
                "entity": entity_target,
                "scores": scores
            }

        # 11. Reference
        if c_type == "minecraft:reference":
            ref_name = p.get("name") or p.get("predicate") or "minecraft_ai:custom"
            return {
                "condition": c_type,
                "name": self._normalize_id(ref_name)
            }

        # 12. General fallback for any other valid condition
        cond = {"condition": c_type}
        for k, v in p.items():
            if k != "condition":
                cond[k] = v
        return cond

    def generate(self, spec: PredicateDefinition) -> List[DatapackResource]:
        clean_path = spec.predicate_path.strip().replace("\\", "/").strip("/")
        if clean_path.endswith(".json"):
            clean_path = clean_path[:-5]

        namespace = spec.namespace or "minecraft_ai"

        # Build condition dictionary
        predicate_dict = self._build_condition(
            condition_type=spec.condition_type,
            params=spec.condition_params,
            terms=spec.terms,
            term=spec.term
        )

        # Deterministic serialization with sort_keys=True
        content = json.dumps(predicate_dict, indent=2, sort_keys=True) + "\n"

        rel_path = f"data/{namespace}/predicate/{clean_path}.json"

        return [
            DatapackResource(
                relative_path=rel_path,
                content=content,
                resource_type="predicate"
            )
        ]
