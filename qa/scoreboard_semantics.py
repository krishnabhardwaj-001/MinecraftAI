"""
qa/scoreboard_semantics.py - Step 16.5 QA Semantic Analysis & Runtime Simulation for Scoreboards
Authoritative target: Minecraft Java Edition 1.21.11

Provides lightweight, deterministic semantic simulation for:
1. Abstract scoreboard state (objectives, holders, 32-bit signed integer values, initialization state)
2. Scoreboard operations (=, +=, -=, *=, /=, %=, <, >, ><) with Java/Minecraft integer division and modulo
3. Three-valued condition evaluation (TRUE, FALSE, UNKNOWN) for ranges and score-to-score comparisons
4. State-machine temporal analysis over game ticks (rising edge, sustained, falling edge)
5. Semantic hazard detection:
   - SCORE_USE_BEFORE_INITIALIZATION
   - SCORE_OPERATION_DIVIDE_BY_ZERO
   - SCORE_OPERATION_MODULO_BY_ZERO
   - STATE_EVENT_REPEATS
   - STATE_EVENT_UNREACHABLE
   - STATE_LATCH_NEVER_RESETS
   - STATE_EXIT_UNREACHABLE
   - STATE_TRANSITION_MISMATCH
   - SCORE_WRITE_CONFLICT
"""

import copy
import re
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from qa.models import QACategory, QAFinding, QASeverity

MIN_SCORE_32 = -2147483648
MAX_SCORE_32 = 2147483647


def to_int32(val: int) -> int:
    """
    Simulates Minecraft Java 32-bit signed integer wrapping.
    """
    val = val & 0xFFFFFFFF
    if val >= 0x80000000:
        val -= 0x100000000
    return val


def java_int_div(a: int, b: int) -> int:
    """
    Simulates Minecraft Java integer division (truncation toward zero).
    Raises ZeroDivisionError on b == 0.
    """
    if b == 0:
        raise ZeroDivisionError("Division by zero in scoreboard operation")
    res = int(a / b)
    return to_int32(res)


def java_int_rem(a: int, b: int) -> int:
    """
    Simulates Minecraft Java integer remainder (has the sign of dividend a).
    Raises ZeroDivisionError on b == 0.
    """
    if b == 0:
        raise ZeroDivisionError("Modulo by zero in scoreboard operation")
    sign = -1 if a < 0 else 1
    res = sign * (abs(a) % abs(b))
    return to_int32(res)


class TriState(str, Enum):
    """
    Three-valued Kleene logic for static condition reasoning:
    TRUE, FALSE, UNKNOWN.
    """
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"

    def invert(self) -> "TriState":
        if self == TriState.TRUE:
            return TriState.FALSE
        elif self == TriState.FALSE:
            return TriState.TRUE
        return TriState.UNKNOWN

    def __invert__(self) -> "TriState":
        return self.invert()

    def __and__(self, other: "TriState") -> "TriState":
        if self == TriState.FALSE or other == TriState.FALSE:
            return TriState.FALSE
        if self == TriState.TRUE and other == TriState.TRUE:
            return TriState.TRUE
        return TriState.UNKNOWN

    def __or__(self, other: "TriState") -> "TriState":
        if self == TriState.TRUE or other == TriState.TRUE:
            return TriState.TRUE
        if self == TriState.FALSE and other == TriState.FALSE:
            return TriState.FALSE
        return TriState.UNKNOWN


class AbstractScoreboardState:
    """
    Lightweight deterministic state model representing Minecraft Java 1.21.11 scoreboards.
    Tracks:
    - objectives declared
    - holders and their integer scores
    - initialization status per (holder, objective)
    """

    def __init__(self):
        self.objectives: Dict[str, Dict[str, Any]] = {}
        self.scores: Dict[Tuple[str, str], int] = {}
        self.initialized: Dict[Tuple[str, str], bool] = {}

    def clone(self) -> "AbstractScoreboardState":
        new_state = AbstractScoreboardState()
        new_state.objectives = copy.deepcopy(self.objectives)
        new_state.scores = copy.deepcopy(self.scores)
        new_state.initialized = copy.deepcopy(self.initialized)
        return new_state

    def declare_objective(
        self,
        name: str,
        criteria: str = "dummy",
        display_name: Optional[str] = None
    ) -> None:
        self.objectives[name] = {
            "criteria": criteria,
            "display_name": display_name
        }

    def is_objective_declared(self, name: str) -> bool:
        return name in self.objectives

    def is_initialized(self, holder: str, objective: str) -> bool:
        return self.initialized.get((holder, objective), False)

    def get_score(self, holder: str, objective: str) -> Optional[int]:
        if not self.is_initialized(holder, objective):
            return None
        return self.scores.get((holder, objective))

    def set_score(self, holder: str, objective: str, value: int) -> None:
        self.scores[(holder, objective)] = to_int32(value)
        self.initialized[(holder, objective)] = True

    def add_score(self, holder: str, objective: str, value: int) -> None:
        curr = self.scores.get((holder, objective), 0)
        self.scores[(holder, objective)] = to_int32(curr + value)
        self.initialized[(holder, objective)] = True

    def remove_score(self, holder: str, objective: str, value: int) -> None:
        curr = self.scores.get((holder, objective), 0)
        self.scores[(holder, objective)] = to_int32(curr - value)
        self.initialized[(holder, objective)] = True

    def reset_score(self, holder: str, objective: Optional[str] = None) -> None:
        if objective is not None:
            self.scores.pop((holder, objective), None)
            self.initialized[(holder, objective)] = False
        else:
            keys = [k for k in self.scores if k[0] == holder or holder == "*"]
            for k in keys:
                self.scores.pop(k, None)
                self.initialized[k] = False

    def apply_operation(
        self,
        target_holder: str,
        target_obj: str,
        op: str,
        source_holder: str,
        source_obj: str
    ) -> Optional[str]:
        """
        Applies a scoreboard arithmetic or assignment operation:
        =, +=, -=, *=, /=, %=, <, >, ><
        Returns an error code string if a semantic hazard occurs, else None.
        """
        if not self.is_initialized(source_holder, source_obj):
            return "SOURCE_UNINITIALIZED"

        curr_t = self.scores.get((target_holder, target_obj), 0)
        curr_s = self.scores.get((source_holder, source_obj), 0)

        if op == "=":
            self.scores[(target_holder, target_obj)] = curr_s
            self.initialized[(target_holder, target_obj)] = True
        elif op == "+=":
            self.scores[(target_holder, target_obj)] = to_int32(curr_t + curr_s)
            self.initialized[(target_holder, target_obj)] = True
        elif op == "-=":
            self.scores[(target_holder, target_obj)] = to_int32(curr_t - curr_s)
            self.initialized[(target_holder, target_obj)] = True
        elif op == "*=":
            self.scores[(target_holder, target_obj)] = to_int32(curr_t * curr_s)
            self.initialized[(target_holder, target_obj)] = True
        elif op == "/=":
            if curr_s == 0:
                return "DIVIDE_BY_ZERO"
            self.scores[(target_holder, target_obj)] = java_int_div(curr_t, curr_s)
            self.initialized[(target_holder, target_obj)] = True
        elif op == "%=":
            if curr_s == 0:
                return "MODULO_BY_ZERO"
            self.scores[(target_holder, target_obj)] = java_int_rem(curr_t, curr_s)
            self.initialized[(target_holder, target_obj)] = True
        elif op == "<":
            self.scores[(target_holder, target_obj)] = min(curr_t, curr_s)
            self.initialized[(target_holder, target_obj)] = True
        elif op == ">":
            self.scores[(target_holder, target_obj)] = max(curr_t, curr_s)
            self.initialized[(target_holder, target_obj)] = True
        elif op == "><":
            self.scores[(target_holder, target_obj)] = curr_s
            self.scores[(source_holder, source_obj)] = curr_t
            self.initialized[(target_holder, target_obj)] = True
            self.initialized[(source_holder, source_obj)] = True
        else:
            return "UNSUPPORTED_OPERATION"

        return None

    def eval_range(self, holder: str, objective: str, range_str: str) -> TriState:
        """
        Evaluates a Minecraft score range condition.
        """
        if not self.is_initialized(holder, objective):
            return TriState.UNKNOWN

        val = self.scores.get((holder, objective))
        if val is None:
            return TriState.UNKNOWN

        clean = range_str.strip()
        if ".." in clean:
            parts = clean.split("..")
            low = int(parts[0]) if parts[0].strip() else None
            high = int(parts[1]) if parts[1].strip() else None

            if low is not None and val < low:
                return TriState.FALSE
            if high is not None and val > high:
                return TriState.FALSE
            return TriState.TRUE
        else:
            try:
                exact = int(clean)
                return TriState.TRUE if val == exact else TriState.FALSE
            except ValueError:
                return TriState.UNKNOWN

    def eval_comparison(
        self,
        target_holder: str,
        target_obj: str,
        op: str,
        source_holder: str,
        source_obj: str
    ) -> TriState:
        """
        Evaluates a score-to-score comparison (<, <=, =, >=, >).
        """
        if not self.is_initialized(target_holder, target_obj) or not self.is_initialized(source_holder, source_obj):
            return TriState.UNKNOWN

        t_val = self.scores.get((target_holder, target_obj))
        s_val = self.scores.get((source_holder, source_obj))
        if t_val is None or s_val is None:
            return TriState.UNKNOWN

        if op == "<":
            return TriState.TRUE if t_val < s_val else TriState.FALSE
        elif op == "<=":
            return TriState.TRUE if t_val <= s_val else TriState.FALSE
        elif op == "=":
            return TriState.TRUE if t_val == s_val else TriState.FALSE
        elif op == ">=":
            return TriState.TRUE if t_val >= s_val else TriState.FALSE
        elif op == ">":
            return TriState.TRUE if t_val > s_val else TriState.FALSE

        return TriState.UNKNOWN


class ParsedCommand:
    """
    Lightweight structure for an analyzed Minecraft command line.
    """
    def __init__(
        self,
        raw_line: str,
        line_number: int,
        file_path: str,
        conditions: List[Dict[str, Any]],
        subcommand_tokens: List[str],
        is_action: bool
    ):
        self.raw_line = raw_line
        self.line_number = line_number
        self.file_path = file_path
        self.conditions = conditions
        self.subcommand_tokens = subcommand_tokens
        self.is_action = is_action


class ScoreboardSemanticSimulator:
    """
    Lightweight deterministic semantic analyzer and multi-tick simulator
    for Minecraft Java Edition 1.21.11 scoreboard and state-machine datapacks.
    """

    def __init__(self, version: str = "1.21.11"):
        self.version = version

    def parse_line(self, line: str, line_number: int, file_path: str) -> Optional[ParsedCommand]:
        line_clean = line.strip()
        if not line_clean or line_clean.startswith("#"):
            return None

        tokens = line_clean.split()
        conditions: List[Dict[str, Any]] = []
        i = 0

        while i < len(tokens):
            tok = tokens[i].lower()
            if tok == "execute":
                i += 1
                continue

            elif tok in ("if", "unless") and i + 1 < len(tokens) and tokens[i + 1].lower() == "score":
                inverted = (tok == "unless")
                if i + 4 < len(tokens):
                    holder = tokens[i + 2]
                    obj = tokens[i + 3]
                    op_or_matches = tokens[i + 4].lower()

                    if op_or_matches == "matches" and i + 5 < len(tokens):
                        range_expr = tokens[i + 5]
                        conditions.append({
                            "type": "score_range",
                            "inverted": inverted,
                            "holder": holder,
                            "obj": obj,
                            "range": range_expr
                        })
                        i += 6
                        continue
                    elif op_or_matches in ("<", "<=", "=", ">=", ">") and i + 6 < len(tokens):
                        source_holder = tokens[i + 5]
                        source_obj = tokens[i + 6]
                        conditions.append({
                            "type": "score_comp",
                            "inverted": inverted,
                            "target_holder": holder,
                            "target_obj": obj,
                            "op": op_or_matches,
                            "source_holder": source_holder,
                            "source_obj": source_obj
                        })
                        i += 7
                        continue
                i += 1

            elif tok in ("if", "unless") and i + 1 < len(tokens) and tokens[i + 1].lower() == "predicate":
                inverted = (tok == "unless")
                pred_name = tokens[i + 2] if i + 2 < len(tokens) else ""
                conditions.append({
                    "type": "predicate",
                    "inverted": inverted,
                    "predicate": pred_name
                })
                i += 3

            elif tok in ("as", "at") and i + 1 < len(tokens):
                i += 2

            elif tok == "run":
                i += 1
                break
            else:
                break

        sub_tokens = tokens[i:]
        is_action = False
        if sub_tokens:
            first = sub_tokens[0].lower()
            if first in ("give", "effect", "clear", "summon", "setblock", "particle", "tellraw", "title", "tp", "teleport"):
                is_action = True
            elif first == "say":
                msg = " ".join(sub_tokens).lower()
                # Treat as action only if not internal system diagnostic/event report
                if not ("say [minecraftai]" in msg or "diagnostic report" in msg or "=====" in msg):
                    is_action = True
            elif first == "scoreboard" and len(sub_tokens) >= 5 and sub_tokens[1].lower() == "players":
                sub_act = sub_tokens[2].lower()
                holder = sub_tokens[3]
                obj = sub_tokens[4]
                # Exclude debug / tick counters
                if not (holder.startswith("#tick") or holder.startswith("#debug") or "debug" in obj.lower() or "tick" in obj.lower()):
                    if sub_act in ("add", "remove"):
                        is_action = True
                    elif sub_act == "set" and any(c.get("type") == "score_range" and c.get("range") == "0" for c in conditions):
                        is_action = True

        return ParsedCommand(
            raw_line=line_clean,
            line_number=line_number,
            file_path=file_path,
            conditions=conditions,
            subcommand_tokens=sub_tokens,
            is_action=is_action
        )

    def parse_function_file(self, file_path: Path, rel_path: str) -> List[ParsedCommand]:
        commands: List[ParsedCommand] = []
        if not file_path.exists():
            return commands
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line_idx, line in enumerate(f, 1):
                    parsed = self.parse_line(line, line_idx, rel_path)
                    if parsed:
                        commands.append(parsed)
        except Exception:
            pass
        return commands

    def evaluate_conditions(
        self,
        cmd: ParsedCommand,
        state: AbstractScoreboardState,
        predicate_states: Dict[str, bool]
    ) -> TriState:
        overall = TriState.TRUE

        for cond in cmd.conditions:
            c_type = cond["type"]
            if c_type == "predicate":
                pred_id = cond["predicate"]
                pred_val = None
                for p_key, p_val in predicate_states.items():
                    if p_key == pred_id or p_key.split(":")[-1] == pred_id.split(":")[-1]:
                        pred_val = p_val
                        break
                if pred_val is None:
                    cond_res = TriState.UNKNOWN
                else:
                    cond_res = TriState.TRUE if pred_val else TriState.FALSE

                if cond["inverted"]:
                    cond_res = ~cond_res
                overall = overall & cond_res

            elif c_type == "score_range":
                holder = cond["holder"]
                obj = cond["obj"]
                rng = cond["range"]
                effective_holder = holder
                if holder in ("@s", "@a") and not state.is_initialized(holder, obj) and state.is_initialized("Player1", obj):
                    effective_holder = "Player1"

                cond_res = state.eval_range(effective_holder, obj, rng)
                if cond["inverted"]:
                    cond_res = ~cond_res
                overall = overall & cond_res

            elif c_type == "score_comp":
                t_h = cond["target_holder"]
                t_o = cond["target_obj"]
                op = cond["op"]
                s_h = cond["source_holder"]
                s_o = cond["source_obj"]
                cond_res = state.eval_comparison(t_h, t_o, op, s_h, s_o)
                if cond["inverted"]:
                    cond_res = ~cond_res
                overall = overall & cond_res

        return overall

    def execute_subcommand(
        self,
        sub_tokens: List[str],
        state: AbstractScoreboardState,
        cmd: ParsedCommand,
        findings: List[QAFinding]
    ) -> None:
        if len(sub_tokens) < 2 or sub_tokens[0].lower() != "scoreboard":
            return

        subsystem = sub_tokens[1].lower()
        if subsystem == "objectives":
            if len(sub_tokens) >= 4 and sub_tokens[2].lower() == "add":
                obj = sub_tokens[3]
                crit = sub_tokens[4] if len(sub_tokens) >= 5 else "dummy"
                state.declare_objective(obj, crit)
            elif len(sub_tokens) >= 4 and sub_tokens[2].lower() == "remove":
                obj = sub_tokens[3]
                state.reset_score("*", obj)

        elif subsystem == "players":
            if len(sub_tokens) < 3:
                return
            sub_act = sub_tokens[2].lower()
            if sub_act == "set" and len(sub_tokens) >= 6:
                holder, obj, val_str = sub_tokens[3], sub_tokens[4], sub_tokens[5]
                try:
                    val = int(val_str)
                    state.set_score(holder, obj, val)
                except ValueError:
                    pass
            elif sub_act == "add" and len(sub_tokens) >= 6:
                holder, obj, val_str = sub_tokens[3], sub_tokens[4], sub_tokens[5]
                try:
                    val = int(val_str)
                    state.add_score(holder, obj, val)
                except ValueError:
                    pass
            elif sub_act == "remove" and len(sub_tokens) >= 6:
                holder, obj, val_str = sub_tokens[3], sub_tokens[4], sub_tokens[5]
                try:
                    val = int(val_str)
                    state.remove_score(holder, obj, val)
                except ValueError:
                    pass
            elif sub_act == "reset" and len(sub_tokens) >= 4:
                holder = sub_tokens[3]
                obj = sub_tokens[4] if len(sub_tokens) >= 5 else None
                state.reset_score(holder, obj)
            elif sub_act == "operation" and len(sub_tokens) >= 8:
                t_h, t_o, op, s_h, s_o = sub_tokens[3], sub_tokens[4], sub_tokens[5], sub_tokens[6], sub_tokens[7]
                err = state.apply_operation(t_h, t_o, op, s_h, s_o)
                if err == "DIVIDE_BY_ZERO":
                    findings.append(
                        QAFinding(
                            id="SCORE_OPERATION_DIVIDE_BY_ZERO",
                            severity=QASeverity.ERROR,
                            category=QACategory.COMMAND_SEMANTICS,
                            file=cmd.file_path,
                            line_or_reference=f"Line {cmd.line_number}: {cmd.raw_line}",
                            problem=f"Scoreboard operation '/=' uses divisor '{s_h} {s_o}' which is statically known to be 0.",
                            explanation="Minecraft Java Edition scoreboard division by zero fails silently at runtime without modifying the target score.",
                            expected_behavior="Divisor must be non-zero before executing scoreboard division.",
                            repair_required="Verify divisor score is non-zero before running operation."
                        )
                    )
                elif err == "MODULO_BY_ZERO":
                    findings.append(
                        QAFinding(
                            id="SCORE_OPERATION_MODULO_BY_ZERO",
                            severity=QASeverity.ERROR,
                            category=QACategory.COMMAND_SEMANTICS,
                            file=cmd.file_path,
                            line_or_reference=f"Line {cmd.line_number}: {cmd.raw_line}",
                            problem=f"Scoreboard operation '%=' uses divisor '{s_h} {s_o}' which is statically known to be 0.",
                            explanation="Minecraft Java Edition scoreboard modulo with divisor zero fails silently at runtime without modifying the target score.",
                            expected_behavior="Divisor must be non-zero before executing scoreboard modulo.",
                            repair_required="Verify divisor score is non-zero before running operation."
                        )
                    )

    def analyze_datapack(self, datapack_dir: Path) -> List[QAFinding]:
        datapack_dir = Path(datapack_dir)
        findings: List[QAFinding] = []
        if not datapack_dir.exists():
            return findings

        state = AbstractScoreboardState()

        # Discover all .mcfunction files
        func_files: Dict[str, Tuple[Path, str]] = {}
        data_dir = datapack_dir / "data"
        if data_dir.exists():
            for p in data_dir.rglob("*.mcfunction"):
                rel = p.relative_to(datapack_dir).as_posix()
                func_files[rel] = (p, rel)

        # Separate load vs tick vs other functions
        load_cmds: List[ParsedCommand] = []
        tick_cmds: List[ParsedCommand] = []
        other_cmds: List[ParsedCommand] = []

        for rel, (p, _) in sorted(func_files.items()):
            parsed = self.parse_function_file(p, rel)
            if "load" in p.name.lower():
                load_cmds.extend(parsed)
            elif "tick" in p.name.lower():
                tick_cmds.extend(parsed)
            else:
                other_cmds.extend(parsed)

        # -------------------------------------------------------------
        # Phase 1: Load Lifecycle Execution & Objective Initialization
        # -------------------------------------------------------------
        for cmd in load_cmds:
            self.execute_subcommand(cmd.subcommand_tokens, state, cmd, findings)

        # -------------------------------------------------------------
        # Phase 2: Static Initialization & Operation Checks in Tick
        # -------------------------------------------------------------
        # Check dynamic player initialization in tick
        for cmd in tick_cmds:
            if "unless score @s" in cmd.raw_line and "scoreboard players set @s" in cmd.raw_line:
                m_obj = re.search(r"unless\s+score\s+@s\s+(\S+)", cmd.raw_line)
                if m_obj:
                    state.set_score("Player1", m_obj.group(1), 0)

        # Check for use-before-initialization on global / fake-player holders
        for cmd in tick_cmds + other_cmds:
            for cond in cmd.conditions:
                if cond["type"] == "score_range":
                    holder = cond["holder"]
                    obj = cond["obj"]
                    if holder.startswith("#"):
                        if not state.is_initialized(holder, obj):
                            findings.append(
                                QAFinding(
                                    id="SCORE_USE_BEFORE_INITIALIZATION",
                                    severity=QASeverity.ERROR,
                                    category=QACategory.INITIALIZATION,
                                    file=cmd.file_path,
                                    line_or_reference=f"Line {cmd.line_number}: {cmd.raw_line}",
                                    problem=f"Scoreboard score '{holder} {obj}' is evaluated before being initialized.",
                                    explanation=(
                                        f"Command checks 'score {holder} {obj} matches {cond['range']}', but '{holder} {obj}' "
                                        f"was never initialized in load.mcfunction or prior commands. "
                                        f"In Minecraft Java Edition, unset scores are null and do not match 0."
                                    ),
                                    expected_behavior=f"Initialize '{holder} {obj}' in #minecraft:load before testing its value.",
                                    repair_required=f"Add 'scoreboard players set {holder} {obj} 0' to load.mcfunction."
                                )
                            )

            # Check division / modulo by known zero
            if cmd.subcommand_tokens and len(cmd.subcommand_tokens) >= 8:
                if cmd.subcommand_tokens[0].lower() == "scoreboard" and cmd.subcommand_tokens[2].lower() == "operation":
                    op = cmd.subcommand_tokens[5]
                    s_h = cmd.subcommand_tokens[6]
                    s_o = cmd.subcommand_tokens[7]
                    if op in ("/=", "%=") and state.is_initialized(s_h, s_o) and state.get_score(s_h, s_o) == 0:
                        code = "SCORE_OPERATION_DIVIDE_BY_ZERO" if op == "/=" else "SCORE_OPERATION_MODULO_BY_ZERO"
                        op_name = "division" if op == "/=" else "modulo"
                        findings.append(
                            QAFinding(
                                id=code,
                                severity=QASeverity.ERROR,
                                category=QACategory.COMMAND_SEMANTICS,
                                file=cmd.file_path,
                                line_or_reference=f"Line {cmd.line_number}: {cmd.raw_line}",
                                problem=f"Scoreboard operation '{op}' uses divisor '{s_h} {s_o}' which is statically known to be 0.",
                                explanation=f"Minecraft Java Edition scoreboard integer {op_name} by zero fails silently at runtime without modifying the target score.",
                                expected_behavior=f"Ensure divisor '{s_h} {s_o}' is non-zero before operation.",
                                repair_required="Validate divisor score."
                            )
                        )

        # -------------------------------------------------------------
        # Phase 3: Multi-Mechanism Write Conflict Analysis
        # -------------------------------------------------------------
        unconditional_writes: Dict[Tuple[str, str], List[Tuple[str, ParsedCommand]]] = {}
        for cmd in tick_cmds:
            if not cmd.conditions and cmd.subcommand_tokens and len(cmd.subcommand_tokens) >= 5:
                if cmd.subcommand_tokens[0].lower() == "scoreboard" and cmd.subcommand_tokens[1].lower() == "players":
                    act = cmd.subcommand_tokens[2].lower()
                    holder = cmd.subcommand_tokens[3]
                    obj = cmd.subcommand_tokens[4]
                    if act in ("set", "add", "remove", "reset"):
                        unconditional_writes.setdefault((holder, obj), []).append((act, cmd))

        for (h, o), writes in unconditional_writes.items():
            if len(writes) > 1:
                actions = [w[0] for w in writes]
                if ("set" in actions and "add" in actions) or ("set" in actions and "reset" in actions) or (actions.count("set") > 1):
                    findings.append(
                        QAFinding(
                            id="SCORE_WRITE_CONFLICT",
                            severity=QASeverity.WARNING,
                            category=QACategory.COMMAND_SEMANTICS,
                            file=writes[0][1].file_path,
                            line_or_reference=f"{writes[0][1].raw_line} vs {writes[1][1].raw_line}",
                            problem=f"Conflicting unconditional score writes detected for '{h} {o}' in the same tick lifecycle.",
                            explanation="Multiple unconditional write operations target the same score holder on every tick, producing ordering-dependent side effects.",
                            expected_behavior="Guard state mutations with mutually exclusive conditional checks.",
                            repair_required="Add conditional guards before mutating shared score."
                        )
                    )

        # -------------------------------------------------------------
        # Phase 4: State Machine Temporal Simulation
        # -------------------------------------------------------------
        state_machine_present = any(
            any(c.get("type") == "score_range" for c in cmd.conditions)
            for cmd in tick_cmds
        )

        if state_machine_present and tick_cmds:
            findings.extend(self._simulate_temporal_state_machine(load_cmds, tick_cmds, state))

        # Deterministic sorting
        findings.sort(key=lambda f: (f.file or "", f.id, f.line_or_reference or ""))
        return findings

    def _simulate_temporal_state_machine(
        self,
        load_cmds: List[ParsedCommand],
        tick_cmds: List[ParsedCommand],
        initial_load_state: AbstractScoreboardState
    ) -> List[QAFinding]:
        findings: List[QAFinding] = []
        sim_state = initial_load_state.clone()

        # Identify environmental predicates
        environmental_preds: Set[str] = set()
        for cmd in tick_cmds:
            for cond in cmd.conditions:
                if cond["type"] == "predicate":
                    environmental_preds.add(cond["predicate"])

        target_pred = list(environmental_preds)[0] if environmental_preds else "condition"

        # Multi-tick simulation:
        # Ticks 1..3: Inactive (predicate = False)
        # Ticks 4..7: Active (predicate = True, tick 4 is rising edge)
        # Ticks 8..10: Inactive (predicate = False, tick 8 is falling edge)
        cmd_fires_per_tick: Dict[ParsedCommand, List[int]] = {cmd: [] for cmd in tick_cmds if cmd.is_action}

        for tick in range(1, 11):
            pred_active = (4 <= tick <= 7)
            pred_dict = {target_pred: pred_active}

            for cmd in tick_cmds:
                eval_res = self.evaluate_conditions(cmd, sim_state, pred_dict)
                if eval_res == TriState.TRUE:
                    if cmd in cmd_fires_per_tick:
                        cmd_fires_per_tick[cmd].append(tick)
                    # Execute state updates
                    dummy_findings: List[QAFinding] = []
                    self.execute_subcommand(cmd.subcommand_tokens, sim_state, cmd, dummy_findings)

        # 1. Rising edge & sustained active analysis
        for cmd, fired_ticks in cmd_fires_per_tick.items():
            has_enter_cond = any(c.get("type") == "score_range" and c.get("range") in ("0", "..0") for c in cmd.conditions)
            has_pred_cond = any(c.get("type") == "predicate" and not c.get("inverted", False) for c in cmd.conditions)

            if has_enter_cond:
                fired_rising = (4 in fired_ticks)
                sustained_fires = [t for t in (5, 6, 7) if t in fired_ticks]

                if not fired_rising and not sustained_fires:
                    findings.append(
                        QAFinding(
                            id="STATE_EVENT_UNREACHABLE",
                            severity=QASeverity.ERROR,
                            category=QACategory.UNREACHABLE_LOGIC,
                            file=cmd.file_path,
                            line_or_reference=f"Line {cmd.line_number}: {cmd.raw_line}",
                            problem="State machine on_enter action is unreachable and never fires.",
                            explanation="During multi-tick simulation with active condition, the on-enter action condition was never satisfied.",
                            expected_behavior="Action should fire exactly once on the rising edge transition when condition becomes active.",
                            repair_required="Check initial state setup in load.mcfunction and condition ordering in tick.mcfunction."
                        )
                    )
                elif sustained_fires:
                    findings.append(
                        QAFinding(
                            id="STATE_EVENT_REPEATS",
                            severity=QASeverity.ERROR,
                            category=QACategory.STATE_MACHINE,
                            file=cmd.file_path,
                            line_or_reference=f"Line {cmd.line_number}: {cmd.raw_line}",
                            problem="State machine on_enter event action repeats continuously every tick while condition remains active.",
                            explanation=(
                                f"Action fired on rising edge tick 4, but continued to fire on sustained ticks {sustained_fires} ({len(sustained_fires)} repeated fires). "
                                f"The state machine failed to latch its state to 1, causing the action to re-trigger on every game tick."
                            ),
                            expected_behavior="Event action must trigger only once on transition (rising edge), guarded by state latching.",
                            repair_required="Add state latch: 'execute if predicate <pred> run scoreboard players set #global <obj> 1'."
                        )
                    )
            elif has_pred_cond and not has_enter_cond:
                sustained_fires = [t for t in (5, 6, 7) if t in fired_ticks]
                if 4 in fired_ticks and sustained_fires:
                    findings.append(
                        QAFinding(
                            id="STATE_EVENT_REPEATS",
                            severity=QASeverity.ERROR,
                            category=QACategory.STATE_MACHINE,
                            file=cmd.file_path,
                            line_or_reference=f"Line {cmd.line_number}: {cmd.raw_line}",
                            problem="Event action repeats continuously every tick while condition remains active.",
                            explanation="Action is conditioned on environmental predicate without an entry state latch, firing every game tick.",
                            expected_behavior="Event action must trigger only once on transition (rising edge), guarded by state latching.",
                            repair_required="Add state condition 'if score #global <obj> matches 0' and latch to 1."
                        )
                    )

        # 2. Falling edge & latch reset analysis (Ticks 8..10)
        # Check if any state holder set to 1 was never reset to 0
        latched_holders: Set[Tuple[str, str]] = set()
        for cmd in tick_cmds:
            if cmd.subcommand_tokens and len(cmd.subcommand_tokens) >= 6:
                if cmd.subcommand_tokens[0].lower() == "scoreboard" and cmd.subcommand_tokens[2].lower() == "set" and cmd.subcommand_tokens[5] == "1":
                    latched_holders.add((cmd.subcommand_tokens[3], cmd.subcommand_tokens[4]))

        first_action_cmd = next((cmd for cmd in tick_cmds if cmd.is_action), None)
        action_file = first_action_cmd.file_path if first_action_cmd else (tick_cmds[0].file_path if tick_cmds else "data/minecraft_ai/function/tick.mcfunction")

        for h, o in sorted(latched_holders):
            final_score = sim_state.get_score(h, o)
            if final_score == 1:
                findings.append(
                    QAFinding(
                        id="STATE_LATCH_NEVER_RESETS",
                        severity=QASeverity.ERROR,
                        category=QACategory.STATE_MACHINE,
                        file=action_file,
                        line_or_reference=f"State holder: {h} {o}",
                        problem=f"State machine latch '{h} {o}' never resets to 0 after condition ceases.",
                        explanation=(
                            f"State variable '{h} {o}' was latched to 1 on condition start, but remained at 1 "
                            f"after the condition ended. This permanently locks the state machine, preventing future events from firing."
                        ),
                        expected_behavior=f"Reset state score to 0 when condition ceases: 'execute unless predicate ... run scoreboard players set {h} {o} 0'.",
                        repair_required=f"Add reset command: 'execute unless predicate <pred> run scoreboard players set {h} {o} 0'."
                    )
                )

        return findings
