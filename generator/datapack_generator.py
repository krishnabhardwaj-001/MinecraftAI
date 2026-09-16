import json
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from generator.loot_table_generator import LootTableGenerator
from generator.mechanisms import (
    AdvancementMechanismGenerator,
    FunctionMechanismGenerator,
    FunctionTagMechanismGenerator,
    LootTableMechanismGenerator,
    RecipeMechanismGenerator,
)
from generator.models import (
    AdvancementDefinition,
    DatapackManifest,
    DatapackResource,
    FunctionDefinition,
    FunctionTagDefinition,
    GenerationResult,
    LootTableModification,
    MechanismSpecification,
    RecipeDefinition,
)


def slugify(text: str) -> str:
    """
    Convert text to a clean directory/file slug.
    """
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower())
    cleaned = cleaned.strip("_")
    return cleaned or "datapack"


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
        version: str = "1.21.11"
    ):
        self.base_dir = Path(__file__).resolve().parent.parent
        self.output_dir = output_dir or (self.base_dir / "generated")
        self.version = version
        self.loot_generator = LootTableGenerator(version=version)

        # Mechanism generators
        self.loot_mech = LootTableMechanismGenerator(loot_generator=self.loot_generator)
        self.function_mech = FunctionMechanismGenerator()
        self.tag_mech = FunctionTagMechanismGenerator()
        self.advancement_mech = AdvancementMechanismGenerator()
        self.recipe_mech = RecipeMechanismGenerator(version=version)

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
                            except (ValueError, TypeError):
                                pass
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

        # 0. Check for explicit specifications directly in plan
        if plan:
            if plan.get("modifications"):
                for raw in plan["modifications"]:
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

            if loot_modifications or functions or tags or advancements or recipes:
                return {
                    "loot_modifications": loot_modifications,
                    "functions": functions,
                    "tags": tags,
                    "advancements": advancements,
                    "recipes": recipes
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
                            "target", "item", "commands", "values", "tag_name", "criteria", "rewards",
                            "result_item", "recipe_type", "ingredients", "pattern", "key"
                        ]
                    )
                    if has_structured_fields:
                        try:
                            spec = MechanismSpecification(**raw_mech)
                        except Exception:
                            spec = None

                if spec is not None:
                    m_type = str(spec.type).lower()
                    if any(t in m_type for t in ["function_tag", "tick_tag", "load_tag", "tag"]) or "tag" in m_type:
                        if spec.values:
                            tags.append(spec.to_tag_definition())
                    elif any(t in m_type for t in ["function", "mcfunction", "command"]):
                        if spec.commands:
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

        if loot_modifications or functions or tags or advancements or recipes:
            return {
                "loot_modifications": loot_modifications,
                "functions": functions,
                "tags": tags,
                "advancements": advancements,
                "recipes": recipes
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
                if any(t in mech_type for t in ["function", "mcfunction", "command", "tick", "load", "effect", "scoreboard"]):
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
            "recipes": recipes
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

        # If no explicit mechanism parameters provided, extract generically
        if (
            modifications is None
            and functions is None
            and tags is None
            and advancements is None
            and recipes is None
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

        if not (loot_mods or funcs or tag_defs or adv_defs or rec_defs):
            raise ValueError(
                "No valid modifications or mechanisms could be determined from the plan and context."
            )

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
            else:
                datapack_name = "minecraft_datapack"

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

        # 1. Write pack.mcmeta (Minecraft Java 1.21.11 major pack format 94)
        manifest = DatapackManifest(
            pack_format=94,
            min_format=[94, 0],
            max_format=[94, 1],  # Minecraft Java 1.21.11 data pack version 94.1
            description=description
        )

        pack_dict = {
            "pack_format": manifest.pack_format,
            "min_format": manifest.min_format,
            "max_format": manifest.max_format,
            "description": manifest.description
        }

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

        # Deterministically write all resource files
        for res in resources:
            target_file = datapack_dir / res.relative_path
            target_file.parent.mkdir(parents=True, exist_ok=True)
            with open(target_file, "w", encoding="utf-8", newline="\n") as f:
                f.write(res.content)
            files_generated.append(res.relative_path)

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
    output_dir: Optional[Path] = None,
    datapack_name: Optional[str] = None,
    description: Optional[str] = None,
    create_zip: bool = True
) -> GenerationResult:
    """
    Convenience function to generate a datapack deterministically.
    """
    generator = DatapackGenerator(output_dir=output_dir)
    return generator.generate(
        plan=plan,
        context=context,
        understanding=understanding,
        modifications=modifications,
        functions=functions,
        tags=tags,
        advancements=advancements,
        recipes=recipes,
        datapack_name=datapack_name,
        description=description,
        create_zip=create_zip
    )

