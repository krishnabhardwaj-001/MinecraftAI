import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from qa.models import QACategory, QAFinding, QASeverity


class StaticSemanticAnalyzer:
    """
    Deterministic static semantic analyzer for Minecraft Java 1.21.11 datapacks.
    Inspects:
    1. File completeness and orphaned resources
    2. Cross-file reference integrity (functions, tags, predicates, objectives)
    3. Execution context semantics (@a, @s, as, at)
    4. State machine temporal logic and initialization ordering
    """

    def __init__(self, version: str = "1.21.11"):
        self.version = version

    def analyze(
        self,
        datapack_dir: Path,
        plan: Optional[Dict[str, Any]] = None,
        understanding: Optional[Dict[str, Any]] = None
    ) -> List[QAFinding]:
        """
        Runs complete static semantic analysis over the datapack directory.
        Returns a list of QAFinding items.
        """
        datapack_dir = Path(datapack_dir)
        if not datapack_dir.exists():
            return [
                QAFinding(
                    id="FIND-FILE-000",
                    severity=QASeverity.ERROR,
                    category=QACategory.FILE_COMPLETENESS,
                    file=str(datapack_dir),
                    problem="Datapack directory does not exist.",
                    explanation=f"Expected datapack directory at '{datapack_dir}' was not found.",
                    expected_behavior="Datapack directory must exist on filesystem before review.",
                    repair_required="Regenerate datapack files."
                )
            ]

        findings: List[QAFinding] = []

        # 1. Collect all generated resources
        resources = self._collect_resources(datapack_dir)

        # 2. Check file completeness & plan correspondence
        findings.extend(self._check_file_completeness(datapack_dir, resources, plan))

        # 3. Check cross-file references & symbol resolution
        findings.extend(self._check_reference_integrity(datapack_dir, resources))

        # 4. Check command execution context & semantics
        findings.extend(self._check_execution_context(datapack_dir, resources))

        # 5. Check state machine temporal logic & ordering
        findings.extend(self._check_state_machine_logic(datapack_dir, resources))

        return findings

    # -------------------------------------------------------------------------
    # Resource Collection
    # -------------------------------------------------------------------------
    def _collect_resources(self, root: Path) -> Dict[str, Any]:
        """
        Discovers and indexes all datapack resources by type and resource location.
        """
        data_dir = root / "data"
        res: Dict[str, Any] = {
            "functions": {},       # "ns:path" -> Path
            "tags": {},            # "ns:path" -> {"type": "function", "values": [...], "path": Path}
            "predicates": {},      # "ns:path" -> Path
            "recipes": {},         # "ns:path" -> Path
            "loot_tables": {},     # "ns:path" -> Path
            "advancements": {},    # "ns:path" -> Path
            "objectives_added": set(),  # Set of objective names added via scoreboard objectives add
            "objectives_used": set(),   # Set of objective names referenced
            "all_files": []
        }

        if not data_dir.exists():
            return res

        for p in data_dir.rglob("*"):
            if p.is_file():
                rel = p.relative_to(root)
                res["all_files"].append(str(rel).replace("\\", "/"))
                parts = p.relative_to(data_dir).parts
                if len(parts) >= 3:
                    ns = parts[0]
                    category = parts[1]
                    subpath = "/".join(parts[2:])

                    if category == "function" and p.suffix == ".mcfunction":
                        fn_id = f"{ns}:{subpath[:-11]}"
                        res["functions"][fn_id] = p
                    elif category == "predicate" and p.suffix == ".json":
                        pred_id = f"{ns}:{subpath[:-5]}"
                        res["predicates"][pred_id] = p
                    elif category == "recipe" and p.suffix == ".json":
                        rec_id = f"{ns}:{subpath[:-5]}"
                        res["recipes"][rec_id] = p
                    elif category == "tags" and len(parts) >= 4:
                        tag_cat = parts[2]
                        tag_subpath = "/".join(parts[3:])[:-5]
                        tag_id = f"{ns}:{tag_subpath}"
                        try:
                            with open(p, "r", encoding="utf-8") as f:
                                tag_data = json.load(f)
                            res["tags"][tag_id] = {
                                "type": tag_cat,
                                "values": tag_data.get("values", []),
                                "path": p
                            }
                        except Exception:
                            pass

        # Parse functions for scoreboard objective declarations and usages
        for fn_id, fn_path in res["functions"].items():
            try:
                with open(fn_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line_clean = line.strip()
                        if not line_clean or line_clean.startswith("#"):
                            continue
                        # Detect objective creation: scoreboard objectives add <obj> ...
                        m_add = re.search(r"\bscoreboard\s+objectives\s+add\s+([a-zA-Z0-9_\-\.]+)", line_clean)
                        if m_add:
                            res["objectives_added"].add(m_add.group(1))
                        # Detect objective usage: score <target> <obj> matches ... or scoreboard players set/add <target> <obj>
                        m_score = re.search(r"\bscore\s+\S+\s+([a-zA-Z0-9_\-\.]+)\s+matches\b", line_clean)
                        if m_score:
                            res["objectives_used"].add(m_score.group(1))
                        m_set = re.search(r"\bscoreboard\s+players\s+(?:set|add|remove|get|reset)\s+\S+\s+([a-zA-Z0-9_\-\.]+)", line_clean)
                        if m_set:
                            res["objectives_used"].add(m_set.group(1))
            except Exception:
                pass

        return res

    # -------------------------------------------------------------------------
    # 1. File Completeness & Plan Correspondence
    # -------------------------------------------------------------------------
    def _check_file_completeness(
        self,
        root: Path,
        resources: Dict[str, Any],
        plan: Optional[Dict[str, Any]]
    ) -> List[QAFinding]:
        findings: List[QAFinding] = []

        # Check pack.mcmeta exists
        mcmeta_path = root / "pack.mcmeta"
        if not mcmeta_path.exists():
            findings.append(
                QAFinding(
                    id="FIND-FILE-MCMETA",
                    severity=QASeverity.ERROR,
                    category=QACategory.FILE_COMPLETENESS,
                    file="pack.mcmeta",
                    problem="Required 'pack.mcmeta' is missing.",
                    explanation="Every Minecraft datapack requires pack.mcmeta in the root directory.",
                    expected_behavior="pack.mcmeta must be present with pack_format: 94.",
                    repair_required="Generate pack.mcmeta with pack_format: 94."
                )
            )

        # If plan specifies mechanisms, verify corresponding files exist
        if plan and "implementation_plan" in plan:
            for ip in plan["implementation_plan"]:
                for mech in ip.get("mechanisms", []):
                    m_type = mech.get("type") if isinstance(mech, dict) else getattr(mech, "type", None)
                    m_path = mech.get("path") if isinstance(mech, dict) else getattr(mech, "path", None)
                    m_ns = (mech.get("namespace") if isinstance(mech, dict) else getattr(mech, "namespace", None)) or "minecraft_ai"

                    if m_type == "function" and m_path:
                        expected_id = f"{m_ns}:{m_path}"
                        if expected_id not in resources["functions"]:
                            findings.append(
                                QAFinding(
                                    id=f"FIND-FILE-MISSING-FN-{m_path}",
                                    severity=QASeverity.ERROR,
                                    category=QACategory.FILE_COMPLETENESS,
                                    file=f"data/{m_ns}/function/{m_path}.mcfunction",
                                    problem=f"Planned function '{expected_id}' was not generated.",
                                    explanation=f"The implementation plan specified function '{m_path}', but no file was found.",
                                    expected_behavior=f"Function file data/{m_ns}/function/{m_path}.mcfunction must exist.",
                                    repair_required="Regenerate missing function mechanism."
                                )
                            )
                    elif m_type == "predicate" and m_path:
                        expected_id = f"{m_ns}:{m_path}"
                        if expected_id not in resources["predicates"]:
                            findings.append(
                                QAFinding(
                                    id=f"FIND-FILE-MISSING-PRED-{m_path}",
                                    severity=QASeverity.ERROR,
                                    category=QACategory.FILE_COMPLETENESS,
                                    file=f"data/{m_ns}/predicate/{m_path}.json",
                                    problem=f"Planned predicate '{expected_id}' was not generated.",
                                    explanation=f"The implementation plan specified predicate '{m_path}', but no file was found.",
                                    expected_behavior=f"Predicate file data/{m_ns}/predicate/{m_path}.json must exist.",
                                    repair_required="Regenerate missing predicate mechanism."
                                )
                            )

        # Detect dead/orphaned predicates
        # If a predicate exists, it should be referenced by at least one function or tag
        for pred_id, pred_path in resources["predicates"].items():
            referenced = False
            # Check functions for "predicate <pred_id>" or "predicate <short_id>"
            for fn_id, fn_p in resources["functions"].items():
                try:
                    with open(fn_p, "r", encoding="utf-8") as f:
                        content = f.read()
                        if f"predicate {pred_id}" in content:
                            referenced = True
                            break
                        # Also check if namespace is minecraft_ai and called without ns
                        short_name = pred_id.split(":")[-1]
                        if f"predicate {short_name}" in content:
                            referenced = True
                            break
                except Exception:
                    pass

            if not referenced:
                rel_path = str(pred_path.relative_to(root)).replace("\\", "/")
                findings.append(
                    QAFinding(
                        id=f"FIND-DEAD-PRED-{pred_id.replace(':', '_')}",
                        severity=QASeverity.WARNING,
                        category=QACategory.DEAD_LOGIC,
                        file=rel_path,
                        line_or_reference=pred_id,
                        problem=f"Predicate '{pred_id}' is generated but never referenced in any function.",
                        explanation="Datapack defines a custom predicate that is not attached to any tick, load, or custom function execution path.",
                        expected_behavior=f"Predicate '{pred_id}' should be evaluated by an 'if predicate' check in an active function.",
                        repair_required="Connect predicate to tick function execution or remove if unused."
                    )
                )

        return findings

    # -------------------------------------------------------------------------
    # 2. Cross-File Reference Integrity
    # -------------------------------------------------------------------------
    def _check_reference_integrity(
        self,
        root: Path,
        resources: Dict[str, Any]
    ) -> List[QAFinding]:
        findings: List[QAFinding] = []

        # Check tag values point to valid functions
        for tag_id, tag_info in resources["tags"].items():
            if tag_info.get("type") == "function":
                tag_path_rel = str(tag_info["path"].relative_to(root)).replace("\\", "/")
                for val in tag_info.get("values", []):
                    # val e.g. "minecraft_ai:tick"
                    if not val.startswith("#") and val not in resources["functions"]:
                        findings.append(
                            QAFinding(
                                id=f"FIND-REF-TAG-MISSING-FN-{val.replace(':', '_')}",
                                severity=QASeverity.ERROR,
                                category=QACategory.REFERENCE_INTEGRITY,
                                file=tag_path_rel,
                                line_or_reference=val,
                                problem=f"Function tag references non-existent function '{val}'.",
                                explanation=f"Tag '{tag_id}' includes '{val}' in values, but no corresponding .mcfunction file was generated.",
                                expected_behavior=f"Target function '{val}' must exist under data/{val.replace(':', '/function/')}.mcfunction.",
                                repair_required="Generate target function or remove invalid entry from tag values."
                            )
                        )

        # Check function-to-function and function-to-predicate calls
        for fn_id, fn_p in resources["functions"].items():
            rel_fn = str(fn_p.relative_to(root)).replace("\\", "/")
            try:
                with open(fn_p, "r", encoding="utf-8") as f:
                    for line_idx, line in enumerate(f, 1):
                        line_clean = line.strip()
                        if not line_clean or line_clean.startswith("#"):
                            continue

                        # Check "function <target>"
                        for m_fn in re.finditer(r"\bfunction\s+([a-zA-Z0-9_\-\.\/:]+)", line_clean):
                            target_fn = m_fn.group(1)
                            # Ignore macro functions with $ or tags starting with #
                            if "$" in target_fn or target_fn.startswith("#"):
                                continue
                            if ":" not in target_fn:
                                target_fn = f"minecraft:{target_fn}"
                            if target_fn not in resources["functions"]:
                                findings.append(
                                    QAFinding(
                                        id=f"FIND-REF-MISSING-FN-CALL-{line_idx}",
                                        severity=QASeverity.ERROR,
                                        category=QACategory.REFERENCE_INTEGRITY,
                                        file=rel_fn,
                                        line_or_reference=f"Line {line_idx}: {line_clean}",
                                        problem=f"Call to non-existent function '{target_fn}'.",
                                        explanation=f"Function '{fn_id}' executes 'function {target_fn}', but '{target_fn}' does not exist.",
                                        expected_behavior="Every called function must exist in the datapack.",
                                        repair_required="Generate the missing function or correct the function identifier."
                                    )
                                )

                        # Check "if/unless predicate <pred_id>"
                        for m_pred in re.finditer(r"\b(?:if|unless)\s+predicate\s+([a-zA-Z0-9_\-\.\/:]+)", line_clean):
                            target_pred = m_pred.group(1)
                            if ":" not in target_pred:
                                target_pred = f"minecraft:{target_pred}"
                            # Allow vanilla predicates if namespace is minecraft (some are vanilla)
                            # But if namespace is custom (minecraft_ai or similar), must exist
                            if not target_pred.startswith("minecraft:"):
                                if target_pred not in resources["predicates"]:
                                    findings.append(
                                        QAFinding(
                                            id=f"FIND-REF-MISSING-PRED-CALL-{line_idx}",
                                            severity=QASeverity.ERROR,
                                            category=QACategory.REFERENCE_INTEGRITY,
                                            file=rel_fn,
                                            line_or_reference=f"Line {line_idx}: {line_clean}",
                                            problem=f"Check against non-existent predicate '{target_pred}'.",
                                            explanation=f"Command checks 'predicate {target_pred}', but no predicate file was found.",
                                            expected_behavior=f"Predicate '{target_pred}' must exist at data/{target_pred.replace(':', '/predicate/')}.json.",
                                            repair_required="Generate the referenced predicate or fix the predicate identifier."
                                        )
                                    )
            except Exception:
                pass

        # Check scoreboard objective declaration integrity
        # Any objective used in tick or custom functions must be added somewhere (normally in load.mcfunction)
        undeclared = resources["objectives_used"] - resources["objectives_added"]
        if undeclared:
            for obj in undeclared:
                findings.append(
                    QAFinding(
                        id=f"FIND-REF-UNDECLARED-OBJ-{obj}",
                        severity=QASeverity.ERROR,
                        category=QACategory.INITIALIZATION,
                        file="data/minecraft_ai/function/load.mcfunction",
                        line_or_reference=obj,
                        problem=f"Scoreboard objective '{obj}' is referenced but never initialized via 'scoreboard objectives add'.",
                        explanation=(
                            f"The datapack uses scoreboard objective '{obj}' in commands, but no function "
                            f"(such as load.mcfunction) creates the objective using 'scoreboard objectives add {obj} dummy'."
                        ),
                        expected_behavior=f"Declare 'scoreboard objectives add {obj} dummy' in a #minecraft:load function.",
                        repair_required=f"Add 'scoreboard objectives add {obj} dummy' to load function."
                    )
                )

        return findings

    # -------------------------------------------------------------------------
    # 3. Execution Context Analysis
    # -------------------------------------------------------------------------
    def _check_execution_context(
        self,
        root: Path,
        resources: Dict[str, Any]
    ) -> List[QAFinding]:
        findings: List[QAFinding] = []

        # Find which functions are load functions
        load_fn_ids: Set[str] = set()
        load_tag = resources["tags"].get("minecraft:load")
        if load_tag:
            load_fn_ids.update(load_tag.get("values", []))

        for fn_id, fn_p in resources["functions"].items():
            rel_fn = str(fn_p.relative_to(root)).replace("\\", "/")
            is_load_fn = fn_id in load_fn_ids or "load" in fn_p.stem.lower()

            try:
                with open(fn_p, "r", encoding="utf-8") as f:
                    for line_idx, line in enumerate(f, 1):
                        line_clean = line.strip()
                        if not line_clean or line_clean.startswith("#"):
                            continue

                        # Check A: Player selector mutating state in load function
                        if is_load_fn:
                            # e.g. scoreboard players set @a ... or tag @a add ...
                            m_load_sel = re.search(r"\b(?:scoreboard\s+players\s+(?:set|add|remove|reset)|tag)\s+(@[apr]|@e\[type=player\])\b", line_clean)
                            if m_load_sel:
                                sel = m_load_sel.group(1)
                                findings.append(
                                    QAFinding(
                                        id=f"FIND-CTX-LOAD-EMPTY-SEL-{line_idx}",
                                        severity=QASeverity.ERROR,
                                        category=QACategory.EXECUTION_CONTEXT,
                                        file=rel_fn,
                                        line_or_reference=f"Line {line_idx}: {line_clean}",
                                        problem=f"Command mutates state on player selector '{sel}' during #minecraft:load execution.",
                                        explanation=(
                                            f"The load function runs during world load/startup before players connect. "
                                            f"Selector '{sel}' matches 0 players, so the score/tag is never initialized. "
                                            f"When players join later, their score remains unset (null), causing downstream 'matches 0' checks to fail."
                                        ),
                                        expected_behavior=(
                                            "Use a persistent dummy score holder (e.g. '#global') in load functions for global state, "
                                            "or dynamically initialize joining players in the tick function using "
                                            "'execute as @a unless score @s <obj> matches 0..1 run scoreboard players set @s <obj> 0'."
                                        ),
                                        evidence="ani.class (ServerFunctionManager.load()) executes before net.minecraft.server.players.PlayerList.placeNewPlayer()",
                                        repair_required="Change player selector in load to '#global' persistent holder or initialize dynamically on tick."
                                    )
                                )

                        # Check B: Command requiring entity context (@s) without preceding 'as'
                        # Commands like give @s, clear @s, effect give @s, etc.
                        entity_cmds = ["give @s", "clear @s", "effect give @s", "effect clear @s", "xp add @s", "tag @s"]
                        for e_cmd in entity_cmds:
                            if e_cmd in line_clean:
                                # Check if line contains "as @" before the entity command
                                # Valid: "execute as @a run give @s ..." or "execute if ... as @a ... run give @s ..."
                                as_match = re.search(r"\bas\s+(@[a-z0-9_\[\]=]+)\b.*?\b" + re.escape(e_cmd), line_clean)
                                if not as_match:
                                    findings.append(
                                        QAFinding(
                                            id=f"FIND-CTX-MISSING-AS-{line_idx}",
                                            severity=QASeverity.ERROR,
                                            category=QACategory.EXECUTION_CONTEXT,
                                            file=rel_fn,
                                            line_or_reference=f"Line {line_idx}: {line_clean}",
                                            problem=f"Command targets '@s' without establishing an entity execution context via 'as <selector>'.",
                                            explanation=(
                                                f"The command invokes '{e_cmd}', but in a function called by a function tag or console, "
                                                f"@s is undefined unless explicitly set with 'execute as <target>'."
                                            ),
                                            expected_behavior="Prepend 'execute as @a' or 'as <entity>' before '@s' commands.",
                                            repair_required="Add 'as @a at @s' to command execution context."
                                        )
                                    )

                        # Check C: Spatial command after 'as @a' without 'at @s'
                        # Commands like summon ... ~ ~ ~, setblock ~ ~ ~, particle ... ~ ~ ~
                        spatial_cmds = [r"\bsetblock\s+~", r"\bsummon\s+\S+\s+~", r"\bparticle\s+\S+\s+~"]
                        for s_pat in spatial_cmds:
                            if re.search(s_pat, line_clean):
                                if "as @" in line_clean and "at @" not in line_clean:
                                    findings.append(
                                        QAFinding(
                                            id=f"FIND-CTX-MISSING-AT-{line_idx}",
                                            severity=QASeverity.WARNING,
                                            category=QACategory.EXECUTION_CONTEXT,
                                            file=rel_fn,
                                            line_or_reference=f"Line {line_idx}: {line_clean}",
                                            problem="Spatial command uses relative coordinates '~' after 'as <selector>' without 'at @s'.",
                                            explanation=(
                                                "'execute as @a' changes the executing entity, but leaves the execution coordinates at "
                                                "world spawn or the caller's position. Commands using relative tildes '~' will execute at spawn, not the player."
                                            ),
                                            expected_behavior="Include 'at @s' when changing execution context for spatial commands: 'execute as @a at @s run ...'.",
                                            repair_required="Add 'at @s' after 'as @a'."
                                        )
                                    )
            except Exception:
                pass

        return findings

    # -------------------------------------------------------------------------
    # 4. State Machine Temporal Logic & Ordering
    # -------------------------------------------------------------------------
    def _check_state_machine_logic(
        self,
        root: Path,
        resources: Dict[str, Any]
    ) -> List[QAFinding]:
        findings: List[QAFinding] = []

        # Analyze tick functions for state machine anti-patterns
        tick_fn_ids: Set[str] = set()
        tick_tag = resources["tags"].get("minecraft:tick")
        if tick_tag:
            tick_fn_ids.update(tick_tag.get("values", []))

        for fn_id in tick_fn_ids:
            fn_p = resources["functions"].get(fn_id)
            if not fn_p or not fn_p.exists():
                continue

            rel_fn = str(fn_p.relative_to(root)).replace("\\", "/")
            try:
                with open(fn_p, "r", encoding="utf-8") as f:
                    lines = [l.strip() for l in f.readlines() if l.strip() and not l.strip().startswith("#")]

                # Anti-Pattern 1: Per-player state machine for environmental predicate
                # e.g. execute as @a if score @s rain_state matches 0 if predicate minecraft_ai:is_raining
                for line_idx, line in enumerate(lines, 1):
                    # Check if checking environmental predicate (weather, time) inside as @a per-player score
                    if "as @a" in line and "if score @s" in line:
                        # Check if any predicate checked on this line is an environmental predicate
                        m_pred = re.search(r"if\s+predicate\s+([a-zA-Z0-9_:\.]+)", line)
                        if m_pred:
                            pred_name = m_pred.group(1).lower()
                            if any(k in pred_name for k in ["rain", "weather", "night", "day", "time", "storm"]):
                                findings.append(
                                    QAFinding(
                                        id=f"FIND-SM-PER-PLAYER-ENV-{line_idx}",
                                        severity=QASeverity.ERROR,
                                        category=QACategory.STATE_MACHINE,
                                        file=rel_fn,
                                        line_or_reference=f"Line {line_idx}: {line}",
                                        problem="Environmental condition is tracked using per-player scoreboard state (@s).",
                                        explanation=(
                                            f"Weather/time conditions are global dimension states. Iterating per-player (@a/@s) "
                                            f"leads to state desynchronization when players join or disconnect during the event. "
                                            f"Global environmental state machines must use a persistent global score holder (e.g. '#global')."
                                        ),
                                        expected_behavior=(
                                            "Store global event state on '#global <obj>' and target players using: "
                                            "'execute if score #global <obj> matches 0 if predicate <pred> as @a at @s run <action>'."
                                        ),
                                        evidence="D018 (MinecraftAI Architecture Decision: Global vs Per-Player State Machines)",
                                        repair_required="Convert per-player environmental state to #global state holder."
                                    )
                                )

                # Anti-Pattern 2: Command Ordering Race Condition
                # If state is set to 1 before checking if state matches 0 on the same tick
                state_set_line = None
                action_check_line = None
                target_obj = None

                for idx, line in enumerate(lines):
                    m_check = re.search(r"if\s+score\s+(\S+)\s+(\S+)\s+matches\s+0", line)
                    if m_check:
                        holder = m_check.group(1)
                        obj = m_check.group(2)
                        action_check_line = (idx, holder, obj)

                    m_set = re.search(r"scoreboard\s+players\s+set\s+(\S+)\s+(\S+)\s+1", line)
                    if m_set:
                        holder = m_set.group(1)
                        obj = m_set.group(2)
                        state_set_line = (idx, holder, obj)

                if action_check_line and state_set_line:
                    # If both operate on same holder and obj
                    if action_check_line[1] == state_set_line[1] and action_check_line[2] == state_set_line[2]:
                        if state_set_line[0] < action_check_line[0]:
                            findings.append(
                                QAFinding(
                                    id="FIND-SM-ORDERING-INVERSION",
                                    severity=QASeverity.ERROR,
                                    category=QACategory.TIMING,
                                    file=rel_fn,
                                    line_or_reference=f"Line {state_set_line[0]+1} precedes Line {action_check_line[0]+1}",
                                    problem="State variable is mutated to 1 before the conditional action checking 'matches 0' is executed.",
                                    explanation=(
                                        f"Commands in .mcfunction execute sequentially in the same tick. "
                                        f"Because '{state_set_line[1]} {state_set_line[2]}' is set to 1 on line {state_set_line[0]+1}, "
                                        f"subsequent check on line {action_check_line[0]+1} will always evaluate to false, "
                                        f"completely preventing the action from ever triggering."
                                    ),
                                    expected_behavior="The conditional action checking 'matches 0' must execute BEFORE setting state to 1.",
                                    repair_required="Reorder commands: perform action check first, then update state."
                                )
                            )

                # Anti-Pattern 3: Missing Reset Condition in Stateful Transition
                # If there is a command setting score to 1, but no command setting it back to 0
                has_set_1 = any(re.search(r"scoreboard\s+players\s+set\s+\S+\s+\S+\s+1", l) for l in lines)
                has_reset_0 = any(re.search(r"scoreboard\s+players\s+set\s+\S+\s+\S+\s+0", l) for l in lines)

                if has_set_1 and not has_reset_0:
                    findings.append(
                        QAFinding(
                            id="FIND-SM-MISSING-RESET",
                            severity=QASeverity.ERROR,
                            category=QACategory.STATE_MACHINE,
                            file=rel_fn,
                            problem="State machine transitions to active state (1) but has no reset transition back to (0).",
                            explanation=(
                                "A state machine was created to handle an event, but there is no command resetting the score to 0 "
                                "when the condition ceases (e.g. 'execute unless predicate ... run scoreboard players set ... 0'). "
                                "This causes the event to permanently remain in state 1 and never trigger again on subsequent events."
                            ),
                            expected_behavior="Add reset command: 'execute unless predicate <pred> run scoreboard players set <holder> <obj> 0'.",
                            repair_required="Add reset command to tick function."
                        )
                    )

            except Exception:
                pass

        return findings
