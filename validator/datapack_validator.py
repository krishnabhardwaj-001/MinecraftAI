import json
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

from validator.models import ValidationCheck, ValidationIssue, ValidationResult


class DatapackValidator:
    """
    Deterministic static validator for Minecraft Java Edition 1.21.11 datapacks.
    Validates directory and ZIP structures, JSON correctness, Minecraft 1.21+ singular path
    conventions, item IDs against 1.21.11 knowledge, entity IDs, recipe/predicate schemas,
    and vanilla drop preservation.

    LIMITATIONS:
    The DatapackValidator operates as a static, offline validator. It verifies that files,
    paths, schemas, and identifiers comply with Minecraft 1.21.11 specifications, but it CANNOT
    simulate runtime game-loop physics (such as the 20-tick linear ramp of rainLevel in
    ServerLevel.tick()), player connection lifecycles, or runtime command execution results.
    Runtime state-machine correctness (e.g. edge-triggered events, scoreboard state holders)
    must be verified against Minecraft runtime semantics and architectural patterns.
    """

    EXPECTED_PACK_FORMAT = 94

    def __init__(
        self,
        version: str = "1.21.11",
        expected_pack_format: int = EXPECTED_PACK_FORMAT
    ):
        self.version = version
        self.expected_pack_format = expected_pack_format
        self.base_dir = Path(__file__).resolve().parent.parent

        # Load valid item IDs from knowledge
        self.valid_items = self._load_valid_items()

        # Load valid command roots from knowledge
        self.valid_commands = self._load_valid_commands()

        # Load valid entity IDs from knowledge
        self.valid_entities = self._load_valid_entities()

        # Vanilla loot tables base directory
        self.vanilla_loot_dir = (
            self.base_dir
            / "knowledge"
            / "loot_tables"
            / "java"
            / self.version
            / "tables"
        )

    def _load_valid_commands(self) -> Set[str]:
        """
        Loads all valid Minecraft command root names for 1.21.11 from knowledge assets.
        """
        commands_path = (
            self.base_dir
            / "knowledge"
            / "commands"
            / "java"
            / self.version
            / "commands.jsonl"
        )
        commands: Set[str] = set()
        if commands_path.exists():
            try:
                with open(commands_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            entry = json.loads(line)
                            cmd = entry.get("command")
                            if cmd:
                                commands.add(cmd.lower())
            except Exception:
                pass

        if not commands:
            commands = {
                "advancement", "attribute", "ban", "ban-ip", "banlist", "bossbar",
                "clear", "clone", "damage", "data", "datapack", "debug", "defaultgamemode",
                "deop", "difficulty", "effect", "enchant", "execute", "experience", "fill",
                "fillbiome", "forceload", "function", "gamemode", "gamerule", "give",
                "help", "item", "jfr", "kick", "kill", "list", "locate", "loot", "me",
                "msg", "op", "pardon", "pardon-ip", "particle", "perf", "place", "playsound",
                "publish", "recipe", "reload", "return", "ride", "say", "schedule", "scoreboard",
                "seed", "setblock", "setidletimeout", "setworldspawn", "spawnpoint", "spectate",
                "spreadplayers", "stop", "stopsound", "summon", "tag", "team", "teammsg",
                "teleport", "tell", "tellraw", "tick", "time", "title", "tm", "tp", "trigger",
                "w", "weather", "whitelist", "worldborder", "xp"
            }
        return commands

    def _load_valid_items(self) -> Set[str]:
        """
        Loads all valid Minecraft item IDs for 1.21.11 from knowledge assets.
        """
        items_path = (
            self.base_dir
            / "knowledge"
            / "items"
            / "java"
            / self.version
            / "items.json"
        )

        if not items_path.exists():
            # Fallback to generated reports
            items_path = self.base_dir / "generated" / "reports" / "items.json"

        if not items_path.exists():
            return set()

        try:
            with open(items_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, list):
                return {item["id"].lower() for item in data if "id" in item}
            elif isinstance(data, dict):
                return {k.lower() for k in data.keys()}
        except Exception:
            pass

        return set()

    def _load_valid_entities(self) -> Set[str]:
        """
        Loads all valid Minecraft entity IDs for 1.21.11 from knowledge assets.
        """
        entities_path = (
            self.base_dir
            / "knowledge"
            / "entities"
            / "java"
            / self.version
            / "entities.json"
        )

        if not entities_path.exists():
            return set()

        try:
            with open(entities_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, list):
                return {item["id"].lower() for item in data if "id" in item}
            elif isinstance(data, dict):
                return {k.lower() for k in data.keys()}
        except Exception:
            pass

        return set()

    def validate(self, path: Union[str, Path]) -> ValidationResult:
        """
        Validates a datapack directory or ZIP file.
        """
        target = Path(path).resolve()

        if not target.exists():
            return ValidationResult(
                status="invalid",
                target_path=str(target),
                is_zip=False,
                errors=[
                    ValidationIssue(
                        level="error",
                        code="TARGET_NOT_FOUND",
                        message=f"Target path does not exist: {target}"
                    )
                ],
                checks=[
                    ValidationCheck(
                        name="Target Path Existence",
                        passed=False,
                        message=f"Path not found: {target}"
                    )
                ]
            )

        if target.is_file() or target.suffix.lower() == ".zip":
            return self._validate_zip(target)
        elif target.is_dir():
            return self._validate_directory(target, is_zip=False)
        else:
            return ValidationResult(
                status="invalid",
                target_path=str(target),
                is_zip=False,
                errors=[
                    ValidationIssue(
                        level="error",
                        code="INVALID_TARGET_TYPE",
                        message=f"Target must be a directory or ZIP file: {target}"
                    )
                ],
                checks=[
                    ValidationCheck(
                        name="Target Type Check",
                        passed=False,
                        message="Not a directory or ZIP file"
                    )
                ]
            )

    def _validate_zip(self, zip_path: Path) -> ValidationResult:
        """
        Validates a ZIP file safely: checks archive integrity, blocks path traversal,
        and runs full structural validation on extracted content.
        """
        checks: List[ValidationCheck] = []
        errors: List[ValidationIssue] = []

        # 1. Integrity check
        try:
            zf = zipfile.ZipFile(zip_path, "r")
        except zipfile.BadZipFile as e:
            return ValidationResult(
                status="invalid",
                target_path=str(zip_path),
                is_zip=True,
                errors=[
                    ValidationIssue(
                        level="error",
                        code="CORRUPT_ZIP",
                        message=f"Archive is corrupt or not a valid ZIP file: {e}"
                    )
                ],
                checks=[
                    ValidationCheck(
                        name="ZIP Integrity Check",
                        passed=False,
                        message=f"Bad ZIP file: {e}"
                    )
                ]
            )

        checks.append(
            ValidationCheck(
                name="ZIP Integrity Check",
                passed=True,
                message="ZIP archive opened successfully"
            )
        )

        with zf:
            # 2. Path safety check (guard against zip slip / path traversal)
            unsafe_paths: List[str] = []
            for name in zf.namelist():
                # Check for directory traversal or absolute paths
                if ".." in name or name.startswith("/") or name.startswith("\\"):
                    unsafe_paths.append(name)
                elif ":" in name and not name.startswith("minecraft:"):
                    # Check for drive letters (e.g. C:)
                    parts = name.split(":")
                    if len(parts[0]) == 1 and parts[0].isalpha():
                        unsafe_paths.append(name)

            if unsafe_paths:
                for bad_path in unsafe_paths:
                    errors.append(
                        ValidationIssue(
                            level="error",
                            code="UNSAFE_PATH",
                            message=f"Unsafe path detected in ZIP archive: '{bad_path}'",
                            file=bad_path
                        )
                    )
                return ValidationResult(
                    status="invalid",
                    target_path=str(zip_path),
                    is_zip=True,
                    errors=errors,
                    checks=checks + [
                        ValidationCheck(
                            name="ZIP Path Safety Check",
                            passed=False,
                            message=f"Detected {len(unsafe_paths)} unsafe path(s)"
                        )
                    ]
                )

            checks.append(
                ValidationCheck(
                    name="ZIP Path Safety Check",
                    passed=True,
                    message="All paths in archive are safe relative paths"
                )
            )

            # 3. Extract to temporary directory and run directory validation
            with tempfile.TemporaryDirectory(prefix="mc_dp_val_") as temp_dir:
                temp_path = Path(temp_dir)
                zf.extractall(temp_path)

                # Find datapack root inside zip (could be root or inside single top directory)
                extracted_root = temp_path
                if not (temp_path / "pack.mcmeta").exists():
                    subdirs = [p for p in temp_path.iterdir() if p.is_dir()]
                    if len(subdirs) == 1 and (subdirs[0] / "pack.mcmeta").exists():
                        extracted_root = subdirs[0]

                res = self._validate_directory(
                    extracted_root,
                    is_zip=True,
                    original_path=str(zip_path)
                )

                # Prepend zip checks to result
                res.checks = checks + res.checks
                return res

    def _validate_directory(
        self,
        dir_path: Path,
        is_zip: bool = False,
        original_path: Optional[str] = None
    ) -> ValidationResult:
        """
        Validates all aspects of a datapack directory.
        """
        target_display = original_path if (is_zip and original_path) else str(dir_path)
        errors: List[ValidationIssue] = []
        warnings: List[ValidationIssue] = []
        checks: List[ValidationCheck] = []

        # ---------------------------------------------------------
        # 1. Structural Requirements
        # ---------------------------------------------------------
        mcmeta_path = dir_path / "pack.mcmeta"
        if not mcmeta_path.exists():
            errors.append(
                ValidationIssue(
                    level="error",
                    code="MISSING_MCMETA",
                    message="Required 'pack.mcmeta' file is missing from datapack root.",
                    file="pack.mcmeta"
                )
            )
            checks.append(
                ValidationCheck(
                    name="pack.mcmeta Existence",
                    passed=False,
                    message="pack.mcmeta is missing",
                    file="pack.mcmeta"
                )
            )
        else:
            checks.append(
                ValidationCheck(
                    name="pack.mcmeta Existence",
                    passed=True,
                    message="pack.mcmeta found in root",
                    file="pack.mcmeta"
                )
            )

        data_dir = dir_path / "data"
        if not data_dir.exists() or not data_dir.is_dir():
            errors.append(
                ValidationIssue(
                    level="error",
                    code="MISSING_DATA_DIR",
                    message="Required 'data/' directory is missing from datapack root.",
                    file="data/"
                )
            )
            checks.append(
                ValidationCheck(
                    name="data/ Directory Existence",
                    passed=False,
                    message="data/ directory is missing",
                    file="data/"
                )
            )
        else:
            checks.append(
                ValidationCheck(
                    name="data/ Directory Existence",
                    passed=True,
                    message="data/ directory found",
                    file="data/"
                )
            )

        # Check for obsolete 1.20- plural directories ('loot_tables', 'functions', 'tags/functions', 'advancements')
        if data_dir.exists():
            for ns_dir in data_dir.iterdir():
                if ns_dir.is_dir():
                    obsolete_paths = [
                        (ns_dir / "loot_tables", f"data/{ns_dir.name}/loot_table/"),
                        (ns_dir / "functions", f"data/{ns_dir.name}/function/"),
                        (ns_dir / "tags" / "functions", f"data/{ns_dir.name}/tags/function/"),
                        (ns_dir / "advancements", f"data/{ns_dir.name}/advancement/"),
                        (ns_dir / "recipes", f"data/{ns_dir.name}/recipe/"),
                        (ns_dir / "predicates", f"data/{ns_dir.name}/predicate/"),
                    ]
                    for obsolete_path, required_singular in obsolete_paths:
                        if obsolete_path.exists():
                            rel_obs = str(obsolete_path.relative_to(dir_path))
                            errors.append(
                                ValidationIssue(
                                    level="error",
                                    code="OBSOLETE_PATH",
                                    message=(
                                        f"Found legacy plural path '{rel_obs}'. "
                                        f"Minecraft 1.21+ requires singular '{required_singular}'."
                                    ),
                                    file=rel_obs
                                )
                            )
                            checks.append(
                                ValidationCheck(
                                    name="1.21+ Singular Path Convention",
                                    passed=False,
                                    message=f"Found legacy plural directory: {rel_obs}",
                                    file=rel_obs
                                )
                            )

        # ---------------------------------------------------------
        # 2. pack.mcmeta Validation
        # ---------------------------------------------------------
        if mcmeta_path.exists():
            mcmeta_data = None
            try:
                with open(mcmeta_path, "r", encoding="utf-8") as f:
                    mcmeta_data = json.load(f)
                checks.append(
                    ValidationCheck(
                        name="pack.mcmeta JSON Syntax",
                        passed=True,
                        message="pack.mcmeta is valid JSON",
                        file="pack.mcmeta"
                    )
                )
            except Exception as e:
                errors.append(
                    ValidationIssue(
                        level="error",
                        code="INVALID_JSON",
                        message=f"pack.mcmeta contains invalid JSON: {e}",
                        file="pack.mcmeta"
                    )
                )
                checks.append(
                    ValidationCheck(
                        name="pack.mcmeta JSON Syntax",
                        passed=False,
                        message=f"JSON parse error: {e}",
                        file="pack.mcmeta"
                    )
                )

            if isinstance(mcmeta_data, dict):
                pack_section = mcmeta_data.get("pack")
                if not isinstance(pack_section, dict):
                    errors.append(
                        ValidationIssue(
                            level="error",
                            code="MALFORMED_MCMETA",
                            message="pack.mcmeta missing 'pack' dictionary.",
                            file="pack.mcmeta"
                        )
                    )
                else:
                    # Check pack_format
                    pack_format = pack_section.get("pack_format")
                    min_format = pack_section.get("min_format")
                    max_format = pack_section.get("max_format")

                    format_valid = False
                    format_detail = ""

                    def format_matches(val, expected: int) -> bool:
                        if isinstance(val, int):
                            return val == expected
                        if isinstance(val, (list, tuple)) and len(val) >= 1:
                            try:
                                return int(val[0]) == expected
                            except (ValueError, TypeError):
                                return False
                        return False

                    if format_matches(pack_format, self.expected_pack_format):
                        format_valid = True
                        format_detail = f"pack_format: {pack_format}"
                    elif format_matches(max_format, self.expected_pack_format):
                        format_valid = True
                        format_detail = f"max_format: {max_format}"
                    elif format_matches(min_format, self.expected_pack_format):
                        format_valid = True
                        format_detail = f"min_format: {min_format}"
                    elif pack_format is not None:
                        format_detail = f"pack_format: {pack_format}"
                    elif max_format is not None:
                        format_detail = f"max_format: {max_format}"

                    if format_valid:
                        checks.append(
                            ValidationCheck(
                                name="Pack Format Compatibility",
                                passed=True,
                                message=f"Pack format compatible with Java {self.version} ({format_detail})",
                                file="pack.mcmeta"
                            )
                        )
                    else:
                        errors.append(
                            ValidationIssue(
                                level="error",
                                code="INVALID_PACK_FORMAT",
                                message=(
                                    f"Expected pack format {self.expected_pack_format} for Minecraft Java "
                                    f"{self.version}, got {format_detail or 'missing format'}."
                                ),
                                file="pack.mcmeta"
                            )
                        )
                        checks.append(
                            ValidationCheck(
                                name="Pack Format Compatibility",
                                passed=False,
                                message=f"Incompatible format: {format_detail or 'None'}",
                                file="pack.mcmeta"
                            )
                        )

                    # Check description
                    desc = pack_section.get("description")
                    if desc is None:
                        warnings.append(
                            ValidationIssue(
                                level="warning",
                                code="MISSING_DESCRIPTION",
                                message="pack.mcmeta is missing a 'description' field.",
                                file="pack.mcmeta"
                            )
                        )

        # ---------------------------------------------------------
        # 3. JSON Parsing & File Structure Validation
        # ---------------------------------------------------------
        json_files = list(dir_path.rglob("*.json"))
        parsed_json_cache: Dict[Path, Any] = {}

        for json_file in json_files:
            rel_file = json_file.relative_to(dir_path).as_posix()
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    content = json.load(f)
                parsed_json_cache[json_file] = content
            except Exception as e:
                errors.append(
                    ValidationIssue(
                        level="error",
                        code="INVALID_JSON",
                        message=f"Invalid JSON syntax: {e}",
                        file=rel_file
                    )
                )
                checks.append(
                    ValidationCheck(
                        name="JSON Syntax Validation",
                        passed=False,
                        message=f"Parse error in {rel_file}: {e}",
                        file=rel_file
                    )
                )

        if not any(err.code == "INVALID_JSON" for err in errors):
            checks.append(
                ValidationCheck(
                    name="JSON Syntax Validation",
                    passed=True,
                    message=f"All {len(json_files)} JSON file(s) parsed successfully"
                )
            )

        # ---------------------------------------------------------
        # 4. Loot Table Semantic & Identifier Validation
        # ---------------------------------------------------------
        loot_table_files = [
            f for f in json_files
            if "loot_table" in f.parts and f.name != "pack.mcmeta"
        ]

        for loot_file in loot_table_files:
            rel_path = loot_file.relative_to(dir_path).as_posix()
            table_data = parsed_json_cache.get(loot_file)

            if not isinstance(table_data, dict):
                errors.append(
                    ValidationIssue(
                        level="error",
                        code="MALFORMED_LOOT_TABLE",
                        message="Loot table root must be a JSON object.",
                        file=rel_path
                    )
                )
                continue

            # Validate pools
            pools = table_data.get("pools")
            if pools is not None and not isinstance(pools, list):
                errors.append(
                    ValidationIssue(
                        level="error",
                        code="MALFORMED_LOOT_TABLE",
                        message="Loot table 'pools' must be a list.",
                        file=rel_path
                    )
                )
                continue

            if pools:
                for pool_idx, pool in enumerate(pools):
                    if not isinstance(pool, dict):
                        errors.append(
                            ValidationIssue(
                                level="error",
                                code="MALFORMED_LOOT_TABLE",
                                message=f"Pool at index {pool_idx} must be an object.",
                                file=rel_path
                            )
                        )
                        continue

                    # Validate rolls
                    if "rolls" not in pool:
                        errors.append(
                            ValidationIssue(
                                level="error",
                                code="MALFORMED_LOOT_TABLE",
                                message=f"Pool at index {pool_idx} missing required 'rolls' field.",
                                file=rel_path
                            )
                        )

                    # Validate entries
                    entries = pool.get("entries")
                    if entries is None or not isinstance(entries, list):
                        errors.append(
                            ValidationIssue(
                                level="error",
                                code="MALFORMED_LOOT_TABLE",
                                message=f"Pool at index {pool_idx} missing or invalid 'entries' list.",
                                file=rel_path
                            )
                        )
                        continue

                    if len(entries) == 0:
                        warnings.append(
                            ValidationIssue(
                                level="warning",
                                code="EMPTY_POOL_ENTRIES",
                                message=f"Pool at index {pool_idx} has empty 'entries' list.",
                                file=rel_path
                            )
                        )

                    for entry_idx, entry in enumerate(entries):
                        if not isinstance(entry, dict):
                            errors.append(
                                ValidationIssue(
                                    level="error",
                                    code="MALFORMED_LOOT_TABLE",
                                    message=f"Entry {entry_idx} in pool {pool_idx} must be an object.",
                                    file=rel_path
                                )
                            )
                            continue

                        entry_type = entry.get("type")
                        if not entry_type:
                            errors.append(
                                ValidationIssue(
                                    level="error",
                                    code="MALFORMED_LOOT_TABLE",
                                    message=f"Entry {entry_idx} in pool {pool_idx} missing required 'type'.",
                                    file=rel_path
                                )
                            )

                        # Item ID validation
                        if entry_type == "minecraft:item":
                            item_name = entry.get("name")
                            if not item_name or not isinstance(item_name, str):
                                errors.append(
                                    ValidationIssue(
                                        level="error",
                                        code="MALFORMED_LOOT_TABLE",
                                        message=f"Item entry {entry_idx} in pool {pool_idx} missing item 'name'.",
                                        file=rel_path
                                    )
                                )
                            else:
                                normalized_name = (
                                    item_name.lower()
                                    if item_name.startswith("minecraft:")
                                    else f"minecraft:{item_name.lower()}"
                                )

                                # Check against 1.21.11 knowledge base
                                if self.valid_items and normalized_name not in self.valid_items:
                                    errors.append(
                                        ValidationIssue(
                                            level="error",
                                            code="INVALID_ITEM_ID",
                                            message=(
                                                f"Item ID '{item_name}' is not a recognized Minecraft {self.version} item."
                                            ),
                                            file=rel_path
                                        )
                                    )

            # -----------------------------------------------------
            # 5. Vanilla Source Preservation Verification
            # -----------------------------------------------------
            # Extract relative loot table path: data/minecraft/loot_table/entities/creeper.json -> entities/creeper.json
            try:
                parts = loot_file.parts
                lt_idx = parts.index("loot_table")
                sub_parts = parts[lt_idx + 1:]
                clean_rel_lt = Path(*sub_parts).as_posix()

                vanilla_file = self.vanilla_loot_dir / clean_rel_lt
                if vanilla_file.exists():
                    with open(vanilla_file, "r", encoding="utf-8") as vf:
                        vanilla_data = json.load(vf)

                    vanilla_pools = vanilla_data.get("pools", [])
                    current_pools = table_data.get("pools", [])

                    # Verify that all vanilla pools are preserved in the current table
                    preserved = True
                    for v_pool in vanilla_pools:
                        v_entries = v_pool.get("entries", [])
                        v_entry_names = {
                            e.get("name") for e in v_entries if isinstance(e, dict) and e.get("name")
                        }

                        # Check if this set of entry names exists in some current pool
                        found_match = False
                        for c_pool in current_pools:
                            c_entries = c_pool.get("entries", [])
                            c_entry_names = {
                                e.get("name") for e in c_entries if isinstance(e, dict) and e.get("name")
                            }
                            if v_entry_names.issubset(c_entry_names):
                                found_match = True
                                break

                        if not found_match:
                            preserved = False
                            break

                    if preserved:
                        checks.append(
                            ValidationCheck(
                                name=f"Vanilla Preservation ({clean_rel_lt})",
                                passed=True,
                                message="All original vanilla pools/drops are preserved.",
                                file=rel_path
                            )
                        )
                    else:
                        warnings.append(
                            ValidationIssue(
                                level="warning",
                                code="PRESERVATION_FAILURE",
                                message=(
                                    f"Modified loot table '{clean_rel_lt}' does not appear to preserve "
                                    f"all original vanilla drops."
                                ),
                                file=rel_path
                            )
                        )
            except ValueError:
                pass

        if loot_table_files:
            loot_checks_passed = not any(
                err.code in ["MALFORMED_LOOT_TABLE", "INVALID_ITEM_ID"]
                for err in errors
            )
            checks.append(
                ValidationCheck(
                    name="Loot Table Structure & Identifier Check",
                    passed=loot_checks_passed,
                    message=f"Validated {len(loot_table_files)} loot table file(s)"
                )
            )

        # ---------------------------------------------------------
        # 6. Function (.mcfunction) Validation
        # ---------------------------------------------------------
        function_files = list(dir_path.rglob("*.mcfunction"))
        func_errors = 0

        for func_file in function_files:
            rel_path = func_file.relative_to(dir_path).as_posix()
            try:
                with open(func_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                for line_idx, raw_line in enumerate(lines, start=1):
                    line = raw_line.strip()
                    if not line or line.startswith("#"):
                        continue

                    # Commands in mcfunction files MUST NOT have leading slash
                    if line.startswith("/"):
                        errors.append(
                            ValidationIssue(
                                level="error",
                                code="LEADING_SLASH_IN_FUNCTION",
                                message=(
                                    f"Command at line {line_idx} must not start with '/': '{line}'"
                                ),
                                file=rel_path
                            )
                        )
                        func_errors += 1

                    # Command root check
                    first_token = line.lstrip("/").split()[0].lower() if line.lstrip("/").split() else ""
                    if self.valid_commands and first_token and first_token not in self.valid_commands:
                        warnings.append(
                            ValidationIssue(
                                level="warning",
                                code="UNKNOWN_COMMAND",
                                message=(
                                    f"Command root '{first_token}' at line {line_idx} is not a known Minecraft command."
                                ),
                                file=rel_path
                            )
                        )

                    # Check for empty player selectors on load
                    is_load_fn = (
                        func_file.name == "load.mcfunction" or
                        func_file.stem == "load"
                    )
                    if is_load_fn:
                        load_selector_match = re.search(
                            r"\bscoreboard\s+players\s+(?:set|add|remove|reset|enable)\s+(@[apres])\b",
                            line,
                            re.IGNORECASE
                        ) or re.search(
                            r"\btag\s+(@[apres])\s+(?:add|remove)\b",
                            line,
                            re.IGNORECASE
                        )
                        if load_selector_match:
                            selector_used = load_selector_match.group(1)
                            warnings.append(
                                ValidationIssue(
                                    level="warning",
                                    code="EMPTY_SELECTOR_ON_LOAD",
                                    message=(
                                        f"Command at line {line_idx} modifies score/tag on '{selector_used}' inside a load function. "
                                        f"#minecraft:load executes during world startup when no players are connected, "
                                        f"so '{selector_used}' will match 0 entities. Use a global state holder (e.g. '#global') "
                                        f"or initialize player scores dynamically in the tick loop."
                                    ),
                                    file=rel_path
                                )
                            )
            except Exception as e:
                errors.append(
                    ValidationIssue(
                        level="error",
                        code="FUNCTION_READ_ERROR",
                        message=f"Error reading mcfunction file: {e}",
                        file=rel_path
                    )
                )
                func_errors += 1

        if function_files:
            checks.append(
                ValidationCheck(
                    name="Function Syntax Check",
                    passed=(func_errors == 0),
                    message=f"Validated {len(function_files)} mcfunction file(s)"
                )
            )

        # ---------------------------------------------------------
        # 7. Function Tag Validation (data/<ns>/tags/function/*.json)
        # ---------------------------------------------------------
        tag_files = [
            f for f in json_files
            if "tags" in f.parts and "function" in f.parts and f.name != "pack.mcmeta"
        ]
        tag_errors = 0

        for tag_file in tag_files:
            rel_path = tag_file.relative_to(dir_path).as_posix()
            tag_data = parsed_json_cache.get(tag_file)

            if not isinstance(tag_data, dict):
                errors.append(
                    ValidationIssue(
                        level="error",
                        code="MALFORMED_TAG",
                        message="Function tag root must be a JSON object.",
                        file=rel_path
                    )
                )
                tag_errors += 1
                continue

            # Validate 'replace' field if present (boolean required; 'replace': false is valid syntax)
            if "replace" in tag_data:
                if not isinstance(tag_data["replace"], bool):
                    errors.append(
                        ValidationIssue(
                            level="error",
                            code="MALFORMED_TAG",
                            message="Field 'replace' in function tag must be a boolean.",
                            file=rel_path
                        )
                    )
                    tag_errors += 1

            # Check for game-loop tags ('tick.json', 'load.json') placed outside 'minecraft' namespace
            if tag_file.name in ["tick.json", "load.json"]:
                rel_parts = tag_file.relative_to(dir_path).parts
                if len(rel_parts) >= 2 and rel_parts[1] != "minecraft":
                    tag_ns = rel_parts[1]
                    warnings.append(
                        ValidationIssue(
                            level="warning",
                            code="MISPLACED_GAME_LOOP_TAG",
                            message=(
                                f"Function tag '{tag_file.name}' is under namespace '{tag_ns}' ('{rel_path}'). "
                                f"Minecraft Java 1.21.11 only triggers #minecraft:tick and #minecraft:load automatically. "
                                f"Game loop functions should be registered under 'data/minecraft/tags/function/'."
                            ),
                            file=rel_path
                        )
                    )

            values = tag_data.get("values")
            if values is None or not isinstance(values, list):
                errors.append(
                    ValidationIssue(
                        level="error",
                        code="MALFORMED_TAG",
                        message="Function tag missing required 'values' list.",
                        file=rel_path
                    )
                )
                tag_errors += 1
            else:
                for idx, val in enumerate(values):
                    if not isinstance(val, str) and not (isinstance(val, dict) and "id" in val):
                        errors.append(
                            ValidationIssue(
                                level="error",
                                code="MALFORMED_TAG",
                                message=f"Tag value at index {idx} must be a string or object with 'id'.",
                                file=rel_path
                            )
                        )
                        tag_errors += 1
                    else:
                        val_id = val if isinstance(val, str) else str(val.get("id", ""))
                        is_required = True if isinstance(val, str) else val.get("required", True)
                        # Check target existence for non-optional, direct function references
                        if is_required and not val_id.startswith("#"):
                            if ":" in val_id:
                                v_ns, v_path = val_id.split(":", 1)
                            else:
                                v_ns, v_path = "minecraft", val_id
                            target_fn = dir_path / "data" / v_ns / "function" / f"{v_path}.mcfunction"
                            if not target_fn.exists():
                                errors.append(
                                    ValidationIssue(
                                        level="error",
                                        code="MISSING_TAG_REFERENCE",
                                        message=(
                                            f"Function tag references non-existent function '{val_id}'. "
                                            f"In Minecraft Java 1.21.11, a missing reference causes TagLoader to drop the entire tag (all-or-nothing behavior)."
                                        ),
                                        file=rel_path
                                    )
                                )
                                tag_errors += 1

        if tag_files:
            checks.append(
                ValidationCheck(
                    name="Function Tag Validation",
                    passed=(tag_errors == 0),
                    message=f"Validated {len(tag_files)} function tag file(s)"
                )
            )

        # ---------------------------------------------------------
        # 8. Advancement Validation (data/<ns>/advancement/*.json)
        # ---------------------------------------------------------
        advancement_files = [
            f for f in json_files
            if "advancement" in f.parts and f.name != "pack.mcmeta"
        ]
        adv_errors = 0

        for adv_file in advancement_files:
            rel_path = adv_file.relative_to(dir_path).as_posix()
            adv_data = parsed_json_cache.get(adv_file)

            if not isinstance(adv_data, dict):
                errors.append(
                    ValidationIssue(
                        level="error",
                        code="MALFORMED_ADVANCEMENT",
                        message="Advancement root must be a JSON object.",
                        file=rel_path
                    )
                )
                adv_errors += 1
                continue

            criteria = adv_data.get("criteria")
            if criteria is None or not isinstance(criteria, dict) or len(criteria) == 0:
                errors.append(
                    ValidationIssue(
                        level="error",
                        code="MALFORMED_ADVANCEMENT",
                        message="Advancement missing required non-empty 'criteria' object.",
                        file=rel_path
                    )
                )
                adv_errors += 1

        if advancement_files:
            checks.append(
                ValidationCheck(
                    name="Advancement Validation",
                    passed=(adv_errors == 0),
                    message=f"Validated {len(advancement_files)} advancement file(s)"
                )
            )

        # ---------------------------------------------------------
        # 9. Recipe Validation (data/<ns>/recipe/*.json)
        # ---------------------------------------------------------
        recipe_files = [
            f for f in json_files
            if "recipe" in f.parts and f.name != "pack.mcmeta"
        ]
        recipe_errors = 0

        for rec_file in recipe_files:
            rel_path = rec_file.relative_to(dir_path).as_posix()
            rec_data = parsed_json_cache.get(rec_file)

            if not isinstance(rec_data, dict):
                errors.append(
                    ValidationIssue(
                        level="error",
                        code="MALFORMED_RECIPE",
                        message="Recipe root must be a JSON object.",
                        file=rel_path
                    )
                )
                recipe_errors += 1
                continue

            rec_type = rec_data.get("type")
            if not rec_type or not isinstance(rec_type, str):
                errors.append(
                    ValidationIssue(
                        level="error",
                        code="MALFORMED_RECIPE",
                        message="Recipe missing required 'type' field.",
                        file=rel_path
                    )
                )
                recipe_errors += 1
                continue

            # Validate result object (1.21+ result structure: {"id": "...", "count": ...})
            result = rec_data.get("result")
            if result is None:
                errors.append(
                    ValidationIssue(
                        level="error",
                        code="MALFORMED_RECIPE",
                        message="Recipe missing required 'result' field.",
                        file=rel_path
                    )
                )
                recipe_errors += 1
            elif isinstance(result, str):
                res_id = result.lower() if result.startswith("minecraft:") else f"minecraft:{result.lower()}"
                if self.valid_items and res_id not in self.valid_items:
                    errors.append(
                        ValidationIssue(
                            level="error",
                            code="INVALID_ITEM_ID",
                            message=f"Recipe result item ID '{result}' is not a recognized Minecraft {self.version} item.",
                            file=rel_path
                        )
                    )
                    recipe_errors += 1
            elif isinstance(result, dict):
                res_id = result.get("id") or result.get("item")
                if not res_id:
                    errors.append(
                        ValidationIssue(
                            level="error",
                            code="MALFORMED_RECIPE",
                            message="Recipe result object missing required 'id' field.",
                            file=rel_path
                        )
                    )
                    recipe_errors += 1
                else:
                    norm_id = res_id.lower() if res_id.startswith("minecraft:") else f"minecraft:{res_id.lower()}"
                    if self.valid_items and norm_id not in self.valid_items:
                        errors.append(
                            ValidationIssue(
                                level="error",
                                code="INVALID_ITEM_ID",
                                message=f"Recipe result item ID '{res_id}' is not a recognized Minecraft {self.version} item.",
                                file=rel_path
                            )
                        )
                        recipe_errors += 1

            # Validate ingredients for shapeless
            if "shapeless" in rec_type:
                ings = rec_data.get("ingredients")
                if ings is None or not isinstance(ings, list) or len(ings) == 0:
                    errors.append(
                        ValidationIssue(
                            level="error",
                            code="MALFORMED_RECIPE",
                            message="Shapeless recipe missing required non-empty 'ingredients' list.",
                            file=rel_path
                        )
                    )
                    recipe_errors += 1
                else:
                    for ing in ings:
                        ing_str = ing if isinstance(ing, str) else (ing.get("item") or ing.get("id") if isinstance(ing, dict) else None)
                        if ing_str and not ing_str.startswith("#"):
                            norm_ing = ing_str.lower() if ing_str.startswith("minecraft:") else f"minecraft:{ing_str.lower()}"
                            if self.valid_items and norm_ing not in self.valid_items:
                                errors.append(
                                    ValidationIssue(
                                        level="error",
                                        code="INVALID_ITEM_ID",
                                        message=f"Ingredient item ID '{ing_str}' is not a recognized Minecraft {self.version} item.",
                                        file=rel_path
                                    )
                                )
                                recipe_errors += 1

            # Validate pattern & key for shaped
            elif "shaped" in rec_type:
                pattern = rec_data.get("pattern")
                key = rec_data.get("key")
                if pattern is None or not isinstance(pattern, list) or len(pattern) == 0:
                    errors.append(
                        ValidationIssue(
                            level="error",
                            code="MALFORMED_RECIPE",
                            message="Shaped recipe missing required non-empty 'pattern' list.",
                            file=rel_path
                        )
                    )
                    recipe_errors += 1
                if key is None or not isinstance(key, dict) or len(key) == 0:
                    errors.append(
                        ValidationIssue(
                            level="error",
                            code="MALFORMED_RECIPE",
                            message="Shaped recipe missing required non-empty 'key' mapping.",
                            file=rel_path
                        )
                    )
                    recipe_errors += 1
                elif pattern and isinstance(pattern, list) and isinstance(key, dict):
                    for row in pattern:
                        for char in str(row):
                            if char != " " and char not in key:
                                errors.append(
                                    ValidationIssue(
                                        level="error",
                                        code="MALFORMED_RECIPE",
                                        message=f"Pattern symbol '{char}' is not defined in recipe 'key'.",
                                        file=rel_path
                                    )
                                )
                                recipe_errors += 1
                    for sym, k_val in key.items():
                        k_str = k_val if isinstance(k_val, str) else (k_val.get("item") or k_val.get("id") if isinstance(k_val, dict) else None)
                        if k_str and not k_str.startswith("#"):
                            norm_k = k_str.lower() if k_str.startswith("minecraft:") else f"minecraft:{k_str.lower()}"
                            if self.valid_items and norm_k not in self.valid_items:
                                errors.append(
                                    ValidationIssue(
                                        level="error",
                                        code="INVALID_ITEM_ID",
                                        message=f"Key item ID '{k_str}' for symbol '{sym}' is not a recognized Minecraft {self.version} item.",
                                        file=rel_path
                                    )
                                )
                                recipe_errors += 1

            # Validate cooking / single ingredient
            elif any(t in rec_type for t in ["smelting", "blasting", "smoking", "campfire_cooking", "stonecutting"]):
                ing = rec_data.get("ingredient")
                if not ing:
                    errors.append(
                        ValidationIssue(
                            level="error",
                            code="MALFORMED_RECIPE",
                            message=f"Recipe type '{rec_type}' missing required 'ingredient' field.",
                            file=rel_path
                        )
                    )
                    recipe_errors += 1
                else:
                    ing_str = ing if isinstance(ing, str) else (ing.get("item") or ing.get("id") if isinstance(ing, dict) else None)
                    if ing_str and not ing_str.startswith("#"):
                        norm_ing = ing_str.lower() if ing_str.startswith("minecraft:") else f"minecraft:{ing_str.lower()}"
                        if self.valid_items and norm_ing not in self.valid_items:
                            errors.append(
                                ValidationIssue(
                                    level="error",
                                    code="INVALID_ITEM_ID",
                                    message=f"Ingredient item ID '{ing_str}' is not a recognized Minecraft {self.version} item.",
                                    file=rel_path
                                )
                            )
                            recipe_errors += 1

        if recipe_files:
            checks.append(
                ValidationCheck(
                    name="Recipe Structure & Identifier Check",
                    passed=(recipe_errors == 0),
                    message=f"Validated {len(recipe_files)} recipe file(s)"
                )
            )

        # ---------------------------------------------------------
        # 10. Predicate Validation
        # ---------------------------------------------------------
        VALID_CONDITION_TYPES = {
            "minecraft:all_of",
            "minecraft:any_of",
            "minecraft:inverted",
            "minecraft:weather_check",
            "minecraft:time_check",
            "minecraft:random_chance",
            "minecraft:random_chance_with_enchanted_bonus",
            "minecraft:entity_properties",
            "minecraft:killed_by_player",
            "minecraft:entity_scores",
            "minecraft:block_state_property",
            "minecraft:match_tool",
            "minecraft:table_bonus",
            "minecraft:survives_explosion",
            "minecraft:damage_source_properties",
            "minecraft:location_check",
            "minecraft:reference",
            "minecraft:value_check",
            "minecraft:enchantment_active_check",
        }

        predicate_files = list(dir_path.glob("data/*/predicate/**/*.json"))
        predicate_errors = 0

        def _validate_predicate_condition(cond: Any, rel_path: str) -> int:
            err_count = 0
            if not isinstance(cond, dict):
                errors.append(
                    ValidationIssue(
                        level="error",
                        code="MALFORMED_PREDICATE",
                        message="Predicate condition must be a JSON object.",
                        file=rel_path
                    )
                )
                return 1

            c_type = cond.get("condition")
            if not c_type or not isinstance(c_type, str):
                errors.append(
                    ValidationIssue(
                        level="error",
                        code="MALFORMED_PREDICATE",
                        message="Predicate condition object missing required 'condition' identifier.",
                        file=rel_path
                    )
                )
                return 1

            norm_cond = c_type.lower() if c_type.startswith("minecraft:") else f"minecraft:{c_type.lower()}"
            if norm_cond not in VALID_CONDITION_TYPES:
                errors.append(
                    ValidationIssue(
                        level="error",
                        code="UNSUPPORTED_PREDICATE_TYPE",
                        message=f"Unsupported predicate condition type '{c_type}'.",
                        file=rel_path
                    )
                )
                return 1

            # Check composite terms
            if norm_cond in ("minecraft:all_of", "minecraft:any_of"):
                terms = cond.get("terms")
                if terms is None or not isinstance(terms, list) or len(terms) == 0:
                    errors.append(
                        ValidationIssue(
                            level="error",
                            code="MALFORMED_PREDICATE",
                            message=f"Predicate composite '{norm_cond}' requires non-empty 'terms' list.",
                            file=rel_path
                        )
                    )
                    err_count += 1
                else:
                    for t in terms:
                        err_count += _validate_predicate_condition(t, rel_path)

            elif norm_cond == "minecraft:inverted":
                term = cond.get("term")
                if term is None or not isinstance(term, dict):
                    errors.append(
                        ValidationIssue(
                            level="error",
                            code="MALFORMED_PREDICATE",
                            message="Predicate 'minecraft:inverted' requires a 'term' condition object.",
                            file=rel_path
                        )
                    )
                    err_count += 1
                else:
                    err_count += _validate_predicate_condition(term, rel_path)

            elif norm_cond == "minecraft:random_chance":
                chance = cond.get("chance")
                if chance is None or not isinstance(chance, (int, float)) or not (0.0 <= float(chance) <= 1.0):
                    errors.append(
                        ValidationIssue(
                            level="error",
                            code="INVALID_PREDICATE_PARAM",
                            message=f"Predicate 'random_chance' requires 'chance' float between 0.0 and 1.0, got '{chance}'.",
                            file=rel_path
                        )
                    )
                    err_count += 1

            elif norm_cond == "minecraft:weather_check":
                raining = cond.get("raining")
                thundering = cond.get("thundering")
                if raining is None and thundering is None:
                    errors.append(
                        ValidationIssue(
                            level="error",
                            code="INVALID_PREDICATE_PARAM",
                            message="Predicate 'weather_check' requires at least one of 'raining' or 'thundering'.",
                            file=rel_path
                        )
                    )
                    err_count += 1
                if raining is not None and not isinstance(raining, bool):
                    errors.append(
                        ValidationIssue(
                            level="error",
                            code="INVALID_PREDICATE_PARAM",
                            message="Predicate 'weather_check' field 'raining' must be a boolean.",
                            file=rel_path
                        )
                    )
                    err_count += 1
                if thundering is not None and not isinstance(thundering, bool):
                    errors.append(
                        ValidationIssue(
                            level="error",
                            code="INVALID_PREDICATE_PARAM",
                            message="Predicate 'weather_check' field 'thundering' must be a boolean.",
                            file=rel_path
                        )
                    )
                    err_count += 1

            elif norm_cond == "minecraft:match_tool":
                predicate_obj = cond.get("predicate")
                if not isinstance(predicate_obj, dict):
                    errors.append(
                        ValidationIssue(
                            level="error",
                            code="MALFORMED_PREDICATE",
                            message="Predicate 'match_tool' requires a 'predicate' object.",
                            file=rel_path
                        )
                    )
                    err_count += 1
                else:
                    items = predicate_obj.get("items")
                    if items:
                        items_list = [items] if isinstance(items, str) else (items if isinstance(items, list) else [])
                        for itm in items_list:
                            if isinstance(itm, str) and not itm.startswith("#"):
                                norm_item = itm.lower() if itm.startswith("minecraft:") else f"minecraft:{itm.lower()}"
                                if self.valid_items and norm_item not in self.valid_items:
                                    errors.append(
                                        ValidationIssue(
                                            level="error",
                                            code="INVALID_ITEM_ID",
                                            message=f"Item ID '{itm}' in predicate is not a recognized Minecraft {self.version} item.",
                                            file=rel_path
                                        )
                                    )
                                    err_count += 1

            elif norm_cond == "minecraft:entity_properties":
                pred_obj = cond.get("predicate")
                if pred_obj and isinstance(pred_obj, dict):
                    etype = pred_obj.get("type")
                    if etype and isinstance(etype, str) and not etype.startswith("#"):
                        norm_ent = etype.lower() if etype.startswith("minecraft:") else f"minecraft:{etype.lower()}"
                        if self.valid_entities and norm_ent not in self.valid_entities:
                            errors.append(
                                ValidationIssue(
                                    level="error",
                                    code="INVALID_ENTITY_ID",
                                    message=f"Entity type '{etype}' in predicate is not a recognized Minecraft {self.version} entity.",
                                    file=rel_path
                                )
                            )
                            err_count += 1

            return err_count

        for pred_path in predicate_files:
            rel_path = str(pred_path.relative_to(dir_path))
            try:
                with open(pred_path, "r", encoding="utf-8") as f:
                    pred_data = json.load(f)
            except Exception as e:
                errors.append(
                    ValidationIssue(
                        level="error",
                        code="INVALID_JSON",
                        message=f"Predicate file contains invalid JSON: {e}",
                        file=rel_path
                    )
                )
                predicate_errors += 1
                continue

            if isinstance(pred_data, list):
                if len(pred_data) == 0:
                    errors.append(
                        ValidationIssue(
                            level="error",
                            code="MALFORMED_PREDICATE",
                            message="Predicate condition list cannot be empty.",
                            file=rel_path
                        )
                    )
                    predicate_errors += 1
                else:
                    for cond in pred_data:
                        predicate_errors += _validate_predicate_condition(cond, rel_path)
            elif isinstance(pred_data, dict):
                predicate_errors += _validate_predicate_condition(pred_data, rel_path)
            else:
                errors.append(
                    ValidationIssue(
                        level="error",
                        code="MALFORMED_PREDICATE",
                        message="Predicate file root must be a JSON object or array.",
                        file=rel_path
                    )
                )
                predicate_errors += 1

        if predicate_files:
            checks.append(
                ValidationCheck(
                    name="Predicate Structure & Identifier Check",
                    passed=(predicate_errors == 0),
                    message=f"Validated {len(predicate_files)} predicate file(s)"
                )
            )

        status = "valid" if len(errors) == 0 else "invalid"

        return ValidationResult(
            status=status,
            target_path=target_display,
            is_zip=is_zip,
            errors=errors,
            warnings=warnings,
            checks=checks
        )


def validate_datapack(
    path: Union[str, Path],
    version: str = "1.21.11",
    expected_pack_format: int = 94
) -> ValidationResult:
    """
    Convenience function to validate a datapack directory or ZIP archive.
    """
    validator = DatapackValidator(
        version=version,
        expected_pack_format=expected_pack_format
    )
    return validator.validate(path)
