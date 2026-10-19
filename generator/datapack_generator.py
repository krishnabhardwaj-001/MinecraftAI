import hashlib
import json
import re
import shutil
import zipfile
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger("minecraft_ai.generator")

from ai.lifecycle_reconciler import DEFAULT_LIFECYCLE_RECONCILER
from ai.version_registry import VersionContext
from generator.loot_table_generator import LootTableGenerator
from generator.mechanisms import (
    AdvancementMechanismGenerator,
    FunctionMechanismGenerator,
    FunctionTagMechanismGenerator,
    InteractionMechanismGenerator,
    LootTableMechanismGenerator,
    PredicateMechanismGenerator,
    RecipeMechanismGenerator,
    StateMachineMechanismGenerator,
)
from generator.models import (
    ActionSpecification,
    AdvancementDefinition,
    DatapackManifest,
    DatapackResource,
    FunctionDefinition,
    FunctionTagDefinition,
    GenerationResult,
    InteractionSpecification,
    LootTableModification,
    MechanismSpecification,
    PredicateDefinition,
    RecipeDefinition,
    ScoreboardObjectiveDefinition,
)


def slugify(text: str, max_length: int = 60) -> str:
    """
    Convert text to a clean directory/file slug.

    If the resulting slug exceeds max_length, it is deterministically truncated
    to a readable prefix followed by an 8-character hex SHA-256 hash suffix.
    """
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower())
    cleaned = cleaned.strip("_")
    if not cleaned:
        return "datapack"

    if len(cleaned) <= max_length:
        return cleaned

    # Deterministic truncation: readable prefix up to (max_length - 9) + '_' + 8-char hex sha256
    hash_suffix = hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()[:8]
    prefix_len = max(1, max_length - len(hash_suffix) - 1)
    prefix = cleaned[:prefix_len].rstrip("_")
    if not prefix:
        prefix = cleaned[:prefix_len]
    return f"{prefix}_{hash_suffix}"


class DatapackGenerator:
    """
    Deterministic Datapack Generator for Minecraft Java 1.21.11.
    Supports modular mechanisms:
    - Loot table overrides / modifications
    - mcfunction generation
    - Function tags (tick, load, custom)
    - Advancements
    """

    def __init__(
        self,
        output_dir: Optional[Path] = None,
        version: str = "1.21.11",
        version_context: Optional[VersionContext] = None
    ):
        self.base_dir = Path(__file__).resolve().parent.parent
        self.output_dir = Path(output_dir) if output_dir else (self.base_dir / "generated")
        self.version_context = version_context or VersionContext.from_version(version)
        self.version = self.version_context.version_id
        self.loot_generator = LootTableGenerator(version=self.version)

        # Mechanism generators
        self.loot_mech = LootTableMechanismGenerator(version=self.version, loot_generator=self.loot_generator)
        self.function_mech = FunctionMechanismGenerator(version=self.version, version_context=self.version_context)
        self.tag_mech = FunctionTagMechanismGenerator(version=self.version, version_context=self.version_context)
        self.advancement_mech = AdvancementMechanismGenerator(version=self.version, version_context=self.version_context)
        self.recipe_mech = RecipeMechanismGenerator(version=self.version)
        self.predicate_mech = PredicateMechanismGenerator(version=self.version)
        self.state_machine_mech = StateMachineMechanismGenerator(version=self.version)
        self.interaction_mech = InteractionMechanismGenerator(version=self.version, version_context=self.version_context)


    def extract_loot_modifications(
        self,
        plan: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        understanding: Optional[Dict[str, Any]] = None
    ) -> List[LootTableModification]:
        """
        Extracts loot table modification specifications generically from
        planner, context, and understanding structures.
        Preserved for direct backwards compatibility.
        """
        modifications: List[LootTableModification] = []

        # 0. Check if plan directly specifies explicit modifications
        if plan and plan.get("modifications"):
            for raw_mod in plan["modifications"]:
                if isinstance(raw_mod, LootTableModification):
                    modifications.append(raw_mod)
                elif isinstance(raw_mod, dict):
                    modifications.append(LootTableModification(**raw_mod))
            if modifications:
                return modifications

        # 1. Inspect planner mechanisms
        implementation_plan = (
            plan.get("implementation_plan", []) if plan else []
        )

        # Check if plan steps provide explicit resources (loot table and/or item)
        plan_item = None
        plan_table = None
        if plan and "implementation_plan" in plan:
            for ip in plan["implementation_plan"]:
                for step in ip.get("steps", []):
                    for res in step.get("resources", []):
                        res_str = str(res).strip()
                        if res_str.endswith(".json") or "/" in res_str:
                            plan_table = res_str
                        elif ":" in res_str:
                            plan_item = res_str
                        elif not plan_item and res_str:
                            plan_item = res_str

        # Knowledge context shortcuts
        knowledge = context.get("knowledge", {}) if context else {}
        retrieved_loot_tables = knowledge.get("loot_tables", [])
        retrieved_entities = knowledge.get("entities", [])
        retrieved_items = knowledge.get("items", [])

        # Requirements from understanding or context
        requirements = []
        if understanding and "requirements" in understanding:
            requirements = understanding.get("requirements", [])
        elif context and "requirements" in context:
            requirements = context.get("requirements", [])

        # Check if plan has loot mechanisms or if context has loot tables + items
        has_loot_mechanism = False
        for plan_item_entry in implementation_plan:
            for mech in plan_item_entry.get("mechanisms", []):
                mech_type = str(mech.get("type", "")).lower()
                if any(
                    term in mech_type
                    for term in ["loot", "drop", "table"]
                ):
                    has_loot_mechanism = True
                    break

        # If planner didn't specify or wasn't passed, fall back to checking intent in requirements
        if not has_loot_mechanism and requirements:
            for req in requirements:
                intent = str(req.get("intent", "")).lower()
                if any(term in intent for term in ["drop", "loot"]):
                    has_loot_mechanism = True
                    break

        # If loot modification is appropriate:
        if has_loot_mechanism or (retrieved_loot_tables and retrieved_items) or (plan_table and plan_item):
            # Resolve target loot table
            loot_table_path = plan_table
            if not loot_table_path:
                if retrieved_loot_tables:
                    loot_table_path = retrieved_loot_tables[0].get("path")
                elif retrieved_entities:
                    loot_table_path = retrieved_entities[0].get("loot_table")

            # Resolve requested item
            item_id = plan_item
            if not item_id:
                if retrieved_items:
                    item_id = retrieved_items[0].get("id")

            # Resolve count (default 1)
            count = 1
            for req in requirements:
                for detail in req.get("details", []):
                    if isinstance(detail, dict):
                        d_name = str(detail.get("name", "")).lower()
                        d_val = detail.get("value")
                        if d_name in ["count", "amount", "quantity"]:
                            try:
                                count = int(d_val)
                            except (ValueError, TypeError) as e:
                                logger.debug("Could not parse count %s as integer: %s", d_val, e)
                        # Also check if item wasn't retrieved but is in details
                        if not item_id and d_name in ["item", "reward"]:
                            item_id = str(d_val)

            if loot_table_path and item_id:
                modifications.append(
                    LootTableModification(
                        loot_table_path=loot_table_path,
                        item=item_id,
                        count=count,
                        operation="add_pool"
                    )
                )

        return modifications

    def extract_mechanisms(
        self,
        plan: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        understanding: Optional[Dict[str, Any]] = None
    ) -> Dict[str, List[Any]]:
        """
        Generically extracts all mechanism specifications (loot tables,
        functions, function tags, advancements) from the planner, context,
        and understanding structures.
        """
        loot_modifications: List[LootTableModification] = []
        functions: List[FunctionDefinition] = []
        tags: List[FunctionTagDefinition] = []
        advancements: List[AdvancementDefinition] = []
        recipes: List[RecipeDefinition] = []
        predicates: List[PredicateDefinition] = []
        state_machines: List[MechanismSpecification] = []
        scoreboard_objectives: List[ScoreboardObjectiveDefinition] = []
        interactions: List[MechanismSpecification] = []

        # 0. Check for explicit specifications directly in plan
        if plan:
            raw_mods = plan.get("modifications") or plan.get("loot_modifications")
            if raw_mods:
                for raw in raw_mods:
                    if isinstance(raw, LootTableModification):
                        loot_modifications.append(raw)
                    elif isinstance(raw, dict):
                        loot_modifications.append(LootTableModification(**raw))

            if plan.get("functions"):
                for raw in plan["functions"]:
                    if isinstance(raw, FunctionDefinition):
                        functions.append(raw)
                    elif isinstance(raw, dict):
                        functions.append(FunctionDefinition(**raw))

            if plan.get("tags"):
                for raw in plan["tags"]:
                    if isinstance(raw, FunctionTagDefinition):
                        tags.append(raw)
                    elif isinstance(raw, dict):
                        tags.append(FunctionTagDefinition(**raw))

            if plan.get("advancements"):
                for raw in plan["advancements"]:
                    if isinstance(raw, AdvancementDefinition):
                        advancements.append(raw)
                    elif isinstance(raw, dict):
                        advancements.append(AdvancementDefinition(**raw))

            if plan.get("recipes"):
                for raw in plan["recipes"]:
                    if isinstance(raw, RecipeDefinition):
                        recipes.append(raw)
                    elif isinstance(raw, dict):
                        recipes.append(RecipeDefinition(**raw))

            if plan.get("predicates"):
                for raw in plan["predicates"]:
                    if isinstance(raw, PredicateDefinition):
                        predicates.append(raw)
                    elif isinstance(raw, dict):
                        predicates.append(PredicateDefinition(**raw))

            if plan.get("state_machines"):
                for raw in plan["state_machines"]:
                    if isinstance(raw, MechanismSpecification):
                        state_machines.append(raw)
                    elif isinstance(raw, dict):
                        state_machines.append(MechanismSpecification(**raw))

            if plan.get("interactions"):
                for raw in plan["interactions"]:
                    if isinstance(raw, MechanismSpecification):
                        interactions.append(raw)
                    elif isinstance(raw, InteractionSpecification):
                        interactions.append(MechanismSpecification(type="interaction", interaction=raw))
                    elif isinstance(raw, dict):
                        if raw.get("type") == "interaction" or "interaction" in raw:
                            interactions.append(MechanismSpecification(**raw))
                        else:
                            interactions.append(MechanismSpecification(type="interaction", interaction=InteractionSpecification(**raw)))

            raw_sb = plan.get("scoreboard_objectives") or plan.get("objectives") or plan.get("scoreboards")
            if raw_sb:
                for raw in raw_sb:
                    if isinstance(raw, ScoreboardObjectiveDefinition):
                        scoreboard_objectives.append(raw)
                    elif isinstance(raw, dict):
                        scoreboard_objectives.append(ScoreboardObjectiveDefinition(**raw))

            if loot_modifications or functions or tags or advancements or recipes or predicates or state_machines or scoreboard_objectives or interactions:
                return {
                    "loot_modifications": loot_modifications,
                    "functions": functions,
                    "tags": tags,
                    "advancements": advancements,
                    "recipes": recipes,
                    "predicates": predicates,
                    "state_machines": state_machines,
                    "scoreboard_objectives": scoreboard_objectives,
                    "interactions": interactions,
                }

        # 1. Direct consumption from structured MechanismSpecification in implementation_plan
        implementation_plan = (
            plan.get("implementation_plan", []) if plan else []
        )

        for ip in implementation_plan:
            for raw_mech in ip.get("mechanisms", []):
                spec = raw_mech if isinstance(raw_mech, MechanismSpecification) else None
                if spec is None and isinstance(raw_mech, dict):
                    has_structured_fields = any(
                        k in raw_mech for k in [
                            "target", "item", "commands", "actions", "values", "tag_name", "criteria", "rewards",
                            "result_item", "recipe_type", "ingredients", "pattern", "key",
                            "condition_type", "condition_params", "predicate_path",
                            "objective", "condition_predicate", "on_enter", "on_exit",
                            "property_modification", "implementation", "interaction"
                        ]
                    )
                    if has_structured_fields:
                        try:
                            spec = MechanismSpecification(**raw_mech)
                        except Exception:
                            spec = None

                if spec is not None:
                    m_type = str(spec.type).lower()
                    if m_type == "interaction" or spec.interaction is not None:
                        interactions.append(spec)
                    elif any(t in m_type for t in ["state_machine", "event_latch", "event_trigger"]):
                        state_machines.append(spec)
                    elif any(t in m_type for t in ["continuous_action", "tick_action"]):
                        parsed_acts = [a if isinstance(a, ActionSpecification) else ActionSpecification(**a) for a in (spec.actions or [])]
                        f_def = FunctionDefinition(
                            function_path="tick",
                            actions=parsed_acts,
                            namespace=spec.namespace or "minecraft_ai",
                            description="Continuous action loop"
                        )
                        functions.append(f_def)
                        tags.append(FunctionTagDefinition(tag_name="tick", values=[f"{spec.namespace or 'minecraft_ai'}:tick"]))
                    elif any(t in m_type for t in ["function_tag", "tick_tag", "load_tag", "tag"]) or "tag" in m_type:
                        if spec.values:
                            tags.append(spec.to_tag_definition())
                    elif any(t in m_type for t in ["function", "mcfunction", "command", "property_modification", "modify_property"]):
                        if spec.actions or spec.commands:
                            functions.append(spec.to_function_definition())
                    elif any(t in m_type for t in ["loot", "drop", "table"]):
                        if (spec.target or spec.path) and spec.item:
                            loot_modifications.append(spec.to_loot_modification())
                    elif any(t in m_type for t in ["advancement", "trigger"]):
                        if spec.criteria:
                            advancements.append(spec.to_advancement_definition())
                    elif any(t in m_type for t in ["recipe", "crafting", "crafting_shaped", "crafting_shapeless", "smelting", "blasting", "smoking", "campfire_cooking", "stonecutting"]) or "recipe" in m_type:
                        if spec.result_item or spec.item:
                            recipes.append(spec.to_recipe_definition())
                    elif any(t in m_type for t in ["predicate", "custom_predicate", "condition"]):
                        if spec.condition_type or spec.condition_params or spec.terms or spec.term or spec.path:
                            predicates.append(spec.to_predicate_definition())
                    elif any(t in m_type for t in ["scoreboard_objective", "scoreboard", "objective"]) or m_type == "scoreboard":
                        scoreboard_objectives.append(spec.to_scoreboard_objective_definition())
                        if spec.actions or spec.commands:
                            functions.append(spec.to_function_definition())

        if loot_modifications or functions or tags or advancements or recipes or predicates or state_machines or scoreboard_objectives or interactions:
            return {
                "loot_modifications": loot_modifications,
                "functions": functions,
                "tags": tags,
                "advancements": advancements,
                "recipes": recipes,
                "predicates": predicates,
                "state_machines": state_machines,
                "scoreboard_objectives": scoreboard_objectives,
                "interactions": interactions,
            }

        # 2. Fallback heuristic inspection for minimal or legacy plans
        has_loot_mech = False
        has_func_mech = False
        has_tick_tag_mech = False
        has_load_tag_mech = False
        has_adv_mech = False

        for ip in implementation_plan:
            for mech in ip.get("mechanisms", []):
                mech_type = str(mech.get("type", "")).lower()
                if any(t in mech_type for t in ["loot", "drop", "table"]):
                    has_loot_mech = True
                if any(t in mech_type for t in ["function", "mcfunction", "command", "tick", "load", "effect", "scoreboard", "property_modification", "modify_property", "attribute"]):
                    has_func_mech = True
                if "tick" in mech_type:
                    has_tick_tag_mech = True
                if "load" in mech_type or "init" in mech_type:
                    has_load_tag_mech = True
                if any(t in mech_type for t in ["advancement", "trigger"]):
                    has_adv_mech = True

        # Requirements from understanding or context
        requirements = []
        if understanding and "requirements" in understanding:
            requirements = understanding.get("requirements", [])
        elif context and "requirements" in context:
            requirements = context.get("requirements", [])

        # Fallback inspection on requirements if planner didn't specify mechanism
        if not (has_loot_mech or has_func_mech or has_adv_mech) and requirements:
            for req in requirements:
                intent = str(req.get("intent", "")).lower()
                desc = str(req.get("description", "")).lower()
                if any(t in intent or t in desc for t in ["drop", "loot"]):
                    has_loot_mech = True
                elif any(t in intent or t in desc for t in ["effect", "command", "give", "teleport", "speed", "title", "say"]):
                    has_func_mech = True
                    if any(t in desc or t in intent for t in ["every tick", "tick", "loop", "always", "constant"]):
                        has_tick_tag_mech = True
                elif any(t in intent or t in desc for t in ["advancement", "achievement"]):
                    has_adv_mech = True

        # Loot modifications extraction
        if has_loot_mech:
            loot_modifications = self.extract_loot_modifications(
                plan=plan,
                context=context,
                understanding=understanding
            )

        # Functions & Tags extraction
        if has_func_mech:
            extracted_commands: List[str] = []
            func_name = "main"

            # Check steps in implementation_plan
            for ip in implementation_plan:
                for step in ip.get("steps", []):
                    # Check for explicit commands in step
                    if "commands" in step and isinstance(step["commands"], list):
                        extracted_commands.extend([str(c) for c in step["commands"]])
                    elif "command" in step:
                        extracted_commands.append(str(step["command"]))
                    else:
                        action = str(step.get("action", "")).strip()
                        first_word = action.split()[0].lstrip("/").lower() if action else ""
                        known_command_roots = {
                            "effect", "give", "execute", "scoreboard", "title", "say", "tellraw",
                            "playsound", "particle", "attribute", "tag", "team", "teleport", "tp",
                            "weather", "time", "gamemode", "difficulty", "clear", "kill"
                        }
                        if first_word in known_command_roots:
                            extracted_commands.append(action.lstrip("/"))

            # If no commands extracted from steps, derive generically from requirements
            if not extracted_commands:
                for req in requirements:
                    intent = str(req.get("intent", "")).lower()
                    target = str(req.get("target", "@a"))
                    if "all player" in target.lower():
                        target = "@a"
                    elif "player" in target.lower() and not target.startswith("@"):
                        target = "@p"

                    details_dict = {}
                    for d in req.get("details", []):
                        if isinstance(d, dict):
                            details_dict[str(d.get("name", "")).lower()] = d.get("value")

                    if "effect" in intent or "effect" in details_dict or any("effect" in str(d.get("name", "")).lower() for d in req.get("details", [])):
                        effect_name = details_dict.get("effect") or details_dict.get("type") or "speed"
                        if not str(effect_name).startswith("minecraft:"):
                            effect_name = f"minecraft:{effect_name}"
                        duration = details_dict.get("duration", 10)
                        amplifier = details_dict.get("amplifier", details_dict.get("level", 1))
                        try:
                            amp_int = max(0, int(amplifier) - 1)
                        except (ValueError, TypeError):
                            amp_int = 0
                        extracted_commands.append(f"effect give {target} {effect_name} {duration} {amp_int} true")

            if extracted_commands:
                if has_tick_tag_mech:
                    func_name = "tick"
                elif has_load_tag_mech:
                    func_name = "load"

                default_ns = "minecraft_ai"
                functions.append(
                    FunctionDefinition(
                        function_path=func_name,
                        commands=extracted_commands,
                        namespace=default_ns,
                        description="Generated function"
                    )
                )

                if has_tick_tag_mech:
                    tags.append(
                        FunctionTagDefinition(
                            tag_name="tick",
                            values=[f"{default_ns}:{func_name}"],
                            namespace="minecraft"
                        )
                    )
                if has_load_tag_mech:
                    tags.append(
                        FunctionTagDefinition(
                            tag_name="load",
                            values=[f"{default_ns}:{func_name}"],
                            namespace="minecraft"
                        )
                    )

        # Advancements extraction
        if has_adv_mech:
            adv_path = "root"
            criteria = {
                "requirement": {
                    "trigger": "minecraft:tick"
                }
            }
            advancements.append(
                AdvancementDefinition(
                    advancement_path=adv_path,
                    criteria=criteria,
                    namespace="minecraft_ai"
                )
            )

        return {
            "loot_modifications": loot_modifications,
            "functions": functions,
            "tags": tags,
            "advancements": advancements,
            "recipes": recipes,
            "predicates": predicates,
            "state_machines": state_machines,
            "scoreboard_objectives": scoreboard_objectives,
        }

    def generate(
        self,
        plan: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        understanding: Optional[Dict[str, Any]] = None,
        modifications: Optional[List[LootTableModification]] = None,
        functions: Optional[List[FunctionDefinition]] = None,
        tags: Optional[List[FunctionTagDefinition]] = None,
        advancements: Optional[List[AdvancementDefinition]] = None,
        recipes: Optional[List[RecipeDefinition]] = None,
        predicates: Optional[List[PredicateDefinition]] = None,
        state_machines: Optional[List[MechanismSpecification]] = None,
        scoreboard_objectives: Optional[List[ScoreboardObjectiveDefinition]] = None,
        interactions: Optional[List[Union[MechanismSpecification, InteractionSpecification]]] = None,
        datapack_name: Optional[str] = None,
        description: Optional[str] = None,
        create_zip: bool = True,
        clean: bool = True
    ) -> GenerationResult:
        """
        Deterministically generates a complete Minecraft Java 1.21.11 datapack
        using the requested implementation mechanisms.
        """
        loot_mods: List[LootTableModification] = list(modifications) if modifications is not None else []
        funcs: List[FunctionDefinition] = list(functions) if functions is not None else []
        tag_defs: List[FunctionTagDefinition] = list(tags) if tags is not None else []
        adv_defs: List[AdvancementDefinition] = list(advancements) if advancements is not None else []
        rec_defs: List[RecipeDefinition] = list(recipes) if recipes is not None else []
        pred_defs: List[PredicateDefinition] = list(predicates) if predicates is not None else []
        sm_defs: List[MechanismSpecification] = list(state_machines) if state_machines is not None else []
        sb_defs: List[ScoreboardObjectiveDefinition] = list(scoreboard_objectives) if scoreboard_objectives is not None else []
        int_defs: List[Union[MechanismSpecification, InteractionSpecification]] = list(interactions) if interactions is not None else []

        # If no explicit mechanism parameters provided, extract generically
        if (
            modifications is None
            and functions is None
            and tags is None
            and advancements is None
            and recipes is None
            and predicates is None
            and state_machines is None
            and scoreboard_objectives is None
            and interactions is None
        ):
            extracted = self.extract_mechanisms(
                plan=plan,
                context=context,
                understanding=understanding
            )
            loot_mods = extracted["loot_modifications"]
            funcs = extracted["functions"]
            tag_defs = extracted["tags"]
            adv_defs = extracted["advancements"]
            rec_defs = extracted.get("recipes", [])
            pred_defs = extracted.get("predicates", [])
            sm_defs = extracted.get("state_machines", [])
            sb_defs = extracted.get("scoreboard_objectives", [])
            int_defs = extracted.get("interactions", [])

        if not (loot_mods or funcs or tag_defs or adv_defs or rec_defs or pred_defs or sm_defs or sb_defs or int_defs):
            raise ValueError(
                "No valid modifications or mechanisms could be determined from the plan and context."
            )

        # General Mechanism Consistency & Lifecycle Reconciliation
        if len(sm_defs) > 1:
            pred_info_map = {
                getattr(p, "predicate_path", getattr(p, "path", "")): {
                    "condition": getattr(p, "condition_type", ""),
                    **(getattr(p, "condition_params", None) or {})
                }
                for p in pred_defs
            }
            raw_sms = [sm.model_dump() if hasattr(sm, "model_dump") else dict(sm) for sm in sm_defs]
            reconciled_raw = DEFAULT_LIFECYCLE_RECONCILER.reconcile(raw_sms, pred_info_map)
            sm_defs = [
                MechanismSpecification(**m) if not isinstance(m, MechanismSpecification) else m
                for m in reconciled_raw
                if str(m.get("type", "")).strip().lower() in ("state_machine", "event_latch", "event_trigger")
            ]
            for m in reconciled_raw:
                if str(m.get("type", "")).strip().lower() == "scoreboard_objective":
                    obj_name = m.get("objective") or m.get("path")
                    if obj_name and not any(s.objective == obj_name for s in sb_defs):
                        sb_defs.append(ScoreboardObjectiveDefinition(objective=obj_name, criteria=m.get("criteria", "dummy")))


        # Resolve datapack name
        if not datapack_name:
            if understanding and understanding.get("understood_request"):
                datapack_name = slugify(understanding["understood_request"])
            elif plan and plan.get("summary"):
                datapack_name = slugify(plan["summary"])
            elif loot_mods:
                first_mod = loot_mods[0]
                table_stem = Path(first_mod.loot_table_path).stem
                item_stem = first_mod.item.split(":")[-1]
                datapack_name = f"{table_stem}_drop_{item_stem}"
            elif funcs:
                first_func = funcs[0]
                datapack_name = f"{first_func.function_path}_datapack"
            elif adv_defs:
                first_adv = adv_defs[0]
                datapack_name = f"{first_adv.advancement_path}_datapack"
            elif rec_defs:
                first_rec = rec_defs[0]
                datapack_name = f"{first_rec.recipe_path}_datapack"
            elif pred_defs:
                first_pred = pred_defs[0]
                datapack_name = f"{first_pred.predicate_path}_datapack"
            elif sm_defs:
                first_sm = sm_defs[0]
                datapack_name = f"{first_sm.objective or 'state_machine'}_datapack"
            elif sb_defs:
                first_sb = sb_defs[0]
                datapack_name = f"{first_sb.objective}_scoreboard_datapack"
            elif int_defs:
                first_int = int_defs[0]
                if isinstance(first_int, MechanismSpecification) and first_int.interaction:
                    int_name = first_int.interaction.name
                elif isinstance(first_int, InteractionSpecification):
                    int_name = first_int.name
                else:
                    int_name = "interaction"
                datapack_name = f"{slugify(int_name)}_interaction_datapack"
            else:
                datapack_name = "minecraft_datapack"

            datapack_name = slugify(datapack_name)


        # Resolve description
        if not description:
            if plan and plan.get("summary"):
                description = plan["summary"]
            elif understanding and understanding.get("understood_request"):
                description = understanding["understood_request"]
            else:
                description = "Generated by MinecraftAI"

        datapack_dir = self.output_dir / datapack_name
        if clean and datapack_dir.exists():
            shutil.rmtree(datapack_dir)
        datapack_dir.mkdir(parents=True, exist_ok=True)

        files_generated: List[str] = []

        # 1. Write pack.mcmeta (resolved from VersionContext / VersionMetadata)
        meta = self.version_context.metadata
        manifest = DatapackManifest(
            pack_format=meta.pack_format,
            min_format=meta.min_format if meta.supports_format_range else None,
            max_format=meta.max_format if meta.supports_format_range else None,
            description=description
        )

        pack_dict = {
            "pack_format": manifest.pack_format,
            "description": manifest.description
        }
        if manifest.min_format is not None:
            pack_dict["min_format"] = manifest.min_format
        if manifest.max_format is not None:
            pack_dict["max_format"] = manifest.max_format

        mcmeta_content = json.dumps(
            {"pack": pack_dict},
            indent=2,
            ensure_ascii=False
        ) + "\n"

        mcmeta_path = datapack_dir / "pack.mcmeta"
        with open(mcmeta_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(mcmeta_content)
        files_generated.append("pack.mcmeta")

        # 2. Collect and write all resources from mechanism generators
        resources: List[DatapackResource] = []

        # Loot table modifications
        for mod in loot_mods:
            resources.extend(self.loot_mech.generate(mod))

        # Functions
        for func in funcs:
            resources.extend(self.function_mech.generate(func))

        # Function Tags
        for tag in tag_defs:
            resources.extend(self.tag_mech.generate(tag))

        # Advancements
        for adv in adv_defs:
            resources.extend(self.advancement_mech.generate(adv))

        # Recipes
        for rec in rec_defs:
            resources.extend(self.recipe_mech.generate(rec))

        # Predicates
        for pred in pred_defs:
            resources.extend(self.predicate_mech.generate(pred))

        # State machines
        for sm in sm_defs:
            resources.extend(self.state_machine_mech.generate(sm))

        # Interactions
        for int_item in int_defs:
            resources.extend(self.interaction_mech.generate(int_item))

        # Consolidate scoreboard objectives and detect conflicts
        consolidated_sb: Dict[str, ScoreboardObjectiveDefinition] = {}
        for sb in sb_defs:
            name = sb.objective
            if name in consolidated_sb:
                existing = consolidated_sb[name]
                if existing.criteria != sb.criteria:
                    raise ValueError(
                        f"Conflicting criteria for scoreboard objective '{name}': "
                        f"'{existing.criteria}' vs '{sb.criteria}'"
                    )
                if existing.display_name != sb.display_name:
                    raise ValueError(
                        f"Conflicting display_name for scoreboard objective '{name}': "
                        f"'{existing.display_name}' vs '{sb.display_name}'"
                    )
                if existing.display_slot != sb.display_slot:
                    raise ValueError(
                        f"Conflicting display_slot for scoreboard objective '{name}': "
                        f"'{existing.display_slot}' vs '{sb.display_slot}'"
                    )
            else:
                consolidated_sb[name] = sb

        # Validate that state machine objectives do not conflict with declared objectives
        for sm in sm_defs:
            sm_obj = (sm.objective or sm.path or "event_state").strip()
            if sm_obj in consolidated_sb:
                existing = consolidated_sb[sm_obj]
                if existing.criteria != "dummy":
                    raise ValueError(
                        f"Conflicting criteria for state machine objective '{sm_obj}': "
                        f"state machine requires 'dummy', but objective defined with '{existing.criteria}'"
                    )

        # Generate resources for consolidated scoreboard objectives
        if consolidated_sb:
            sb_ns = (
                (sm_defs[0].namespace if sm_defs and sm_defs[0].namespace else None)
                or (funcs[0].namespace if funcs and funcs[0].namespace else None)
                or "minecraft_ai"
            )
            load_lines = ["# Generated by MinecraftAI - Scoreboard Initialization"]
            for obj_def in consolidated_sb.values():
                load_lines.extend(self.function_mech.synthesize_objective_command(obj_def))
            load_content = "\n".join(load_lines) + "\n"
            resources.append(
                DatapackResource(
                    relative_path=f"data/{sb_ns}/function/load.mcfunction",
                    content=load_content,
                    resource_type="function"
                )
            )
            load_tag_json = json.dumps({"values": [f"{sb_ns}:load"]}, indent=2) + "\n"
            resources.append(
                DatapackResource(
                    relative_path="data/minecraft/tags/function/load.json",
                    content=load_tag_json,
                    resource_type="function_tag"
                )
            )

        # Deterministically write all resource files with intelligent consolidation
        for res in resources:
            target_file = datapack_dir / res.relative_path
            target_file.parent.mkdir(parents=True, exist_ok=True)

            if target_file.exists():
                # Merge function tag JSON files (e.g. tick.json, load.json)
                if res.relative_path.endswith(".json") and "tags/function" in res.relative_path:
                    try:
                        existing_data = json.loads(target_file.read_text(encoding="utf-8"))
                        new_data = json.loads(res.content)
                        existing_vals = existing_data.get("values", [])
                        new_vals = new_data.get("values", [])
                        merged_vals = []
                        for v in existing_vals + new_vals:
                            if v not in merged_vals:
                                merged_vals.append(v)
                        merged_data = {"values": merged_vals}
                        if existing_data.get("replace") is True or new_data.get("replace") is True:
                            merged_data["replace"] = True
                        content_to_write = json.dumps(merged_data, indent=2, ensure_ascii=False) + "\n"
                        with open(target_file, "w", encoding="utf-8", newline="\n") as f:
                            f.write(content_to_write)
                    except Exception:
                        with open(target_file, "w", encoding="utf-8", newline="\n") as f:
                            f.write(res.content)

                # Merge .mcfunction files (append commands, preserve single header)
                elif res.relative_path.endswith(".mcfunction"):
                    try:
                        existing_text = target_file.read_text(encoding="utf-8")
                        if res.content.strip() == existing_text.strip():
                            # Identical function content at same path: keep one
                            continue

                        # Check if mergeable function (lifecycle functions, diagnostic functions, or property modification functions)
                        is_mergeable = (
                            res.relative_path.endswith("load.mcfunction")
                            or res.relative_path.endswith("tick.mcfunction")
                            or res.relative_path.endswith("debug.mcfunction")
                            or "/function/modify_" in res.relative_path
                        )
                        if not is_mergeable:
                            raise ValueError(
                                f"Conflicting function content for '{res.relative_path}': "
                                "multiple mechanisms defined differing content for the same function."
                            )

                        existing_lines = [l.strip() for l in existing_text.splitlines() if l.strip()]
                        existing_obj_adds = {}
                        existing_setdisplays = {}
                        for el in existing_lines:
                            m_obj = re.match(r"^scoreboard\s+objectives\s+add\s+([a-zA-Z0-9_.\+\-]+)\s+(\S+)(?:\s+(.*))?$", el)
                            if m_obj:
                                existing_obj_adds[m_obj.group(1)] = (m_obj.group(2), (m_obj.group(3) or "").strip(), el)
                            m_slot = re.match(r"^scoreboard\s+objectives\s+setdisplay\s+(\S+)\s+([a-zA-Z0-9_.\+\-]+)$", el)
                            if m_slot:
                                existing_setdisplays[m_slot.group(1)] = (m_slot.group(2), el)

                        new_lines = [
                            l for l in res.content.splitlines()
                            if l.strip() and not l.strip().startswith("# Generated by") and not l.strip().startswith("# Deterministic property modification")
                        ]
                        filtered_new_lines = []
                        for nl in new_lines:
                            nl_strip = nl.strip()
                            m_new_obj = re.match(r"^scoreboard\s+objectives\s+add\s+([a-zA-Z0-9_.\+\-]+)\s+(\S+)(?:\s+(.*))?$", nl_strip)
                            if m_new_obj:
                                obj_name = m_new_obj.group(1)
                                crit = m_new_obj.group(2)
                                disp = (m_new_obj.group(3) or "").strip()
                                if obj_name in existing_obj_adds:
                                    ex_crit, ex_disp, ex_cmd = existing_obj_adds[obj_name]
                                    if ex_crit != crit or (ex_disp and disp and ex_disp != disp):
                                        raise ValueError(
                                            f"Conflicting scoreboard objective definition for '{obj_name}': "
                                            f"'{ex_cmd}' vs '{nl_strip}'"
                                        )
                                    # Compatible definition: deduplicate (keep one)
                                    continue
                                else:
                                    existing_obj_adds[obj_name] = (crit, disp, nl_strip)
                                    filtered_new_lines.append(nl)
                                    continue

                            m_new_slot = re.match(r"^scoreboard\s+objectives\s+setdisplay\s+(\S+)\s+([a-zA-Z0-9_.\+\-]+)$", nl_strip)
                            if m_new_slot:
                                slot_name = m_new_slot.group(1)
                                tgt_obj = m_new_slot.group(2)
                                if slot_name in existing_setdisplays:
                                    ex_tgt, ex_cmd = existing_setdisplays[slot_name]
                                    if ex_tgt != tgt_obj:
                                        raise ValueError(
                                            f"Conflicting display slot '{slot_name}': "
                                            f"'{ex_cmd}' vs '{nl_strip}'"
                                        )
                                    continue
                                else:
                                    existing_setdisplays[slot_name] = (tgt_obj, nl_strip)
                                    filtered_new_lines.append(nl)
                                    continue

                            # Diagnostic commands deduplication in lifecycle and diagnostic functions
                            if nl_strip in existing_lines:
                                if nl_strip.startswith("scoreboard objectives setdisplay ") or \
                                   nl_strip.startswith("scoreboard players set #load_ran mcai_debug ") or \
                                   nl_strip.startswith("scoreboard players set #tick_count mcai_debug ") or \
                                   nl_strip.startswith("say [MinecraftAI] [LOAD OK]") or \
                                   res.relative_path.endswith("debug.mcfunction"):
                                    continue

                            filtered_new_lines.append(nl)

                        if filtered_new_lines:
                            if res.relative_path.endswith("debug.mcfunction"):
                                existing_lines_raw = existing_text.rstrip("\n").splitlines()
                                if existing_lines_raw and existing_lines_raw[-1].strip() == "say ========================================":
                                    merged_content = "\n".join(existing_lines_raw[:-1] + filtered_new_lines + [existing_lines_raw[-1]]) + "\n"
                                else:
                                    merged_content = existing_text.rstrip("\n") + "\n" + "\n".join(filtered_new_lines) + "\n"
                            else:
                                merged_content = existing_text.rstrip("\n") + "\n" + "\n".join(filtered_new_lines) + "\n"
                        else:
                            merged_content = existing_text
                        with open(target_file, "w", encoding="utf-8", newline="\n") as f:
                            f.write(merged_content)
                    except ValueError:
                        raise
                    except Exception:
                        with open(target_file, "w", encoding="utf-8", newline="\n") as f:
                            f.write(res.content)
                else:
                    with open(target_file, "w", encoding="utf-8", newline="\n") as f:
                        f.write(res.content)
            else:
                with open(target_file, "w", encoding="utf-8", newline="\n") as f:
                    f.write(res.content)

            if res.relative_path not in files_generated:
                files_generated.append(res.relative_path)

        # Post-generation function tag sanitization:
        # Prune any dangling function references that do not exist on disk,
        # because in Minecraft Java 1.21.11, even ONE missing reference causes
        # Minecraft's TagLoader to drop the ENTIRE tag.
        existing_functions = set()
        for func_file in datapack_dir.glob("data/*/function/**/*.mcfunction"):
            rel_parts = func_file.relative_to(datapack_dir / "data").parts
            fn_ns = rel_parts[0]
            fn_subpath = "/".join(rel_parts[2:])[:-11]  # remove .mcfunction
            existing_functions.add(f"{fn_ns}:{fn_subpath}")

        for tag_file in datapack_dir.glob("data/*/tags/function/**/*.json"):
            try:
                tag_data = json.loads(tag_file.read_text(encoding="utf-8"))
                original_vals = tag_data.get("values", [])
                cleaned_vals = []
                for val in original_vals:
                    val_id = val if isinstance(val, str) else (val.get("id") if isinstance(val, dict) else "")
                    is_required = True if isinstance(val, str) else val.get("required", True)
                    # Keep if subtag (#...) or optional or points to existing function
                    if val_id.startswith("#") or not is_required or val_id in existing_functions:
                        cleaned_vals.append(val)

                clean_tag_dict = {"values": cleaned_vals}
                if tag_data.get("replace") is True:
                    clean_tag_dict["replace"] = True

                tag_file.write_text(json.dumps(clean_tag_dict, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            except Exception as e:
                logger.debug("Failed sanitizing tag file %s: %s", tag_file, e)

        # 3. Create deterministic ZIP archive if requested
        zip_path: Optional[Path] = None
        if create_zip:
            zip_path = self.output_dir / f"{datapack_name}.zip"
            # Deterministic fixed timestamp for reproducible zip hashing
            fixed_time = (2026, 1, 1, 0, 0, 0)

            with zipfile.ZipFile(
                zip_path,
                "w",
                compression=zipfile.ZIP_DEFLATED
            ) as zf:
                # Sort files to ensure deterministic archive order
                for root, dirs, files in sorted(datapack_dir.walk()):
                    dirs.sort()
                    for filename in sorted(files):
                        file_abs = root / filename
                        file_rel = file_abs.relative_to(datapack_dir).as_posix()
                        with open(file_abs, "rb") as f:
                            data = f.read()

                        zinfo = zipfile.ZipInfo(
                            filename=file_rel,
                            date_time=fixed_time
                        )
                        zinfo.compress_type = zipfile.ZIP_DEFLATED
                        zf.writestr(zinfo, data)

        return GenerationResult(
            datapack_name=datapack_name,
            datapack_path=datapack_dir,
            zip_path=zip_path,
            files_generated=files_generated,
            status="success"
        )


def generate_datapack(
    plan: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
    understanding: Optional[Dict[str, Any]] = None,
    modifications: Optional[List[LootTableModification]] = None,
    functions: Optional[List[FunctionDefinition]] = None,
    tags: Optional[List[FunctionTagDefinition]] = None,
    advancements: Optional[List[AdvancementDefinition]] = None,
    recipes: Optional[List[RecipeDefinition]] = None,
    predicates: Optional[List[PredicateDefinition]] = None,
    state_machines: Optional[List[MechanismSpecification]] = None,
    scoreboard_objectives: Optional[List[ScoreboardObjectiveDefinition]] = None,
    interactions: Optional[List[Union[MechanismSpecification, InteractionSpecification]]] = None,
    output_dir: Optional[Path] = None,
    datapack_name: Optional[str] = None,
    description: Optional[str] = None,
    create_zip: bool = True,
    version: str = "1.21.11",
    version_context: Optional[VersionContext] = None
) -> GenerationResult:
    """
    Convenience function to generate a datapack deterministically.
    """
    generator = DatapackGenerator(output_dir=output_dir, version=version, version_context=version_context)
    return generator.generate(
        plan=plan,
        context=context,
        understanding=understanding,
        modifications=modifications,
        functions=functions,
        tags=tags,
        advancements=advancements,
        recipes=recipes,
        predicates=predicates,
        state_machines=state_machines,
        scoreboard_objectives=scoreboard_objectives,
        interactions=interactions,
        datapack_name=datapack_name,
        description=description,
        create_zip=create_zip
    )
