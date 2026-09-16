import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

from validator.models import ValidationCheck, ValidationIssue, ValidationResult


class DatapackValidator:
    """
    Deterministic validator for Minecraft Java Edition 1.21.11 datapacks.
    Validates directory and ZIP structures, JSON correctness, Minecraft 1.21+ path
    conventions, item IDs against 1.21.11 knowledge, and vanilla drop preservation.
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

        # Vanilla loot tables base directory
        self.vanilla_loot_dir = (
            self.base_dir
            / "knowledge"
            / "loot_tables"
            / "java"
            / self.version
            / "tables"
        )

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

        # Check for obsolete 1.20- plural 'loot_tables' directory
        if data_dir.exists():
            for ns_dir in data_dir.iterdir():
                if ns_dir.is_dir():
                    obsolete_loot = ns_dir / "loot_tables"
                    if obsolete_loot.exists():
                        errors.append(
                            ValidationIssue(
                                level="error",
                                code="OBSOLETE_PATH",
                                message=(
                                    f"Found legacy plural path '{obsolete_loot.relative_to(dir_path)}'. "
                                    f"Minecraft 1.21+ requires singular 'data/{ns_dir.name}/loot_table/'."
                                ),
                                file=str(obsolete_loot.relative_to(dir_path))
                            )
                        )
                        checks.append(
                            ValidationCheck(
                                name="1.21+ Singular Path Convention",
                                passed=False,
                                message="Found legacy plural 'loot_tables' directory",
                                file=str(obsolete_loot.relative_to(dir_path))
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
