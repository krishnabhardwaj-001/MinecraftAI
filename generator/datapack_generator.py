import json
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from generator.loot_table_generator import LootTableGenerator
from generator.models import DatapackManifest, GenerationResult, LootTableModification


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

    def extract_loot_modifications(
        self,
        plan: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        understanding: Optional[Dict[str, Any]] = None
    ) -> List[LootTableModification]:
        """
        Extracts loot table modification specifications generically from
        planner, context, and understanding structures.
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

    def generate(
        self,
        plan: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        understanding: Optional[Dict[str, Any]] = None,
        modifications: Optional[List[LootTableModification]] = None,
        datapack_name: Optional[str] = None,
        description: Optional[str] = None,
        create_zip: bool = True
    ) -> GenerationResult:
        """
        Deterministically generates a complete Minecraft Java 1.21.11 datapack.
        """
        # Resolve modifications
        if modifications is None:
            modifications = self.extract_loot_modifications(
                plan=plan,
                context=context,
                understanding=understanding
            )

        if not modifications:
            raise ValueError(
                "No valid modifications could be determined from the plan and context."
            )

        # Resolve datapack name
        if not datapack_name:
            if understanding and understanding.get("understood_request"):
                datapack_name = slugify(understanding["understood_request"])
            elif plan and plan.get("summary"):
                datapack_name = slugify(plan["summary"])
            elif modifications:
                first_mod = modifications[0]
                table_stem = Path(first_mod.loot_table_path).stem
                item_stem = first_mod.item.split(":")[-1]
                datapack_name = f"{table_stem}_drop_{item_stem}"
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
        datapack_dir.mkdir(parents=True, exist_ok=True)

        files_generated: List[str] = []

        # 1. Write pack.mcmeta
        manifest = DatapackManifest(
            pack_format=94,  # Minecraft Java 1.21.11 pack format
            description=description
        )

        mcmeta_content = json.dumps(
            {
                "pack": {
                    "pack_format": manifest.pack_format,
                    "description": manifest.description
                }
            },
            indent=2,
            ensure_ascii=False
        ) + "\n"

        mcmeta_path = datapack_dir / "pack.mcmeta"
        with open(mcmeta_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(mcmeta_content)
        files_generated.append("pack.mcmeta")

        # 2. Write loot tables under data/minecraft/loot_table/ (1.21+ convention)
        data_dir = datapack_dir / "data" / "minecraft" / "loot_table"

        for mod in modifications:
            modified_table = self.loot_generator.modify_loot_table(mod)
            clean_rel = self.loot_generator._normalize_path(mod.loot_table_path)

            target_file = data_dir / clean_rel
            target_file.parent.mkdir(parents=True, exist_ok=True)

            content = self.loot_generator.serialize_loot_table(modified_table)
            with open(target_file, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)

            rel_datapack_path = f"data/minecraft/loot_table/{clean_rel}"
            files_generated.append(rel_datapack_path)

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
        datapack_name=datapack_name,
        description=description,
        create_zip=create_zip
    )
