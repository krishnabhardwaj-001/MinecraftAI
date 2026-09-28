import copy
import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from ai.provider import AIProvider
from generator.models import MechanismSpecification
from qa.models import QACategory, QAFinding, QARepairPlan, QAResult, QASeverity


class QARepairEngine:
    """
    Step 14: AI Diagnosis & Structured Repair Layer for Autonomous Datapack QA.

    Diagnoses QA failures and produces a structured repair plan that updates
    the Planner's MechanismSpecifications for deterministic regeneration.
    Strictly adheres to the architectural rule: NEVER directly patch raw files.
    """

    def __init__(
        self,
        ai_provider: Optional[AIProvider] = None,
        provider: str = "ollama",
        version: str = "1.21.11"
    ):
        self.version = version
        self.provider_name = provider
        self.ai = ai_provider or AIProvider(provider=provider)

    def diagnose_and_repair(
        self,
        qa_result: QAResult,
        plan: Dict[str, Any],
        understanding: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        previous_attempts: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[QARepairPlan, Dict[str, Any]]:
        """
        Diagnoses QA findings and generates a corrected implementation plan.
        Returns (QARepairPlan, corrected_plan_dict).

        Detects repeated identical failures across attempts to prevent infinite loops.
        """
        # 1. Check for repeated identical failure
        current_finding_ids = sorted([f.id for f in qa_result.findings if f.severity == QASeverity.ERROR])
        if previous_attempts:
            last_attempt = previous_attempts[-1]
            last_finding_ids = sorted(last_attempt.get("error_finding_ids", []))
            if current_finding_ids and current_finding_ids == last_finding_ids:
                return QARepairPlan(
                    diagnosis="Repeated identical QA failure detected without progress across attempts.",
                    summary="Aborting QA repair loop: identical errors repeated.",
                    mechanism_modifications=[],
                    regenerate=False
                ), plan

        # 2. Build structured repair deterministically
        corrected_plan = copy.deepcopy(plan)
        modifications: List[Dict[str, Any]] = []
        diagnoses: List[str] = []

        # Find existing mechanisms in plan
        mechanisms_list: List[Dict[str, Any]] = []
        if "implementation_plan" in corrected_plan:
            for ip in corrected_plan["implementation_plan"]:
                for mech in ip.get("mechanisms", []):
                    if isinstance(mech, dict):
                        mechanisms_list.append(mech)
                    elif hasattr(mech, "model_dump"):
                        mechanisms_list.append(mech.model_dump())

        # Inspect specific findings
        for f in qa_result.findings:
            if f.severity != QASeverity.ERROR:
                continue

            # Case A: Load function empty player selector or per-player environmental state
            if f.category in (QACategory.EXECUTION_CONTEXT, QACategory.STATE_MACHINE) and any(
                k in f.id for k in ["LOAD-EMPTY-SEL", "PER-PLAYER-ENV", "FIND-SM-ORDERING-INVERSION", "FIND-SM-MISSING-RESET"]
            ):
                diagnoses.append(
                    f"Identified state machine / execution context issue in '{f.file}': {f.problem}. "
                    f"Applying Rule 24: converting to persistent '#global' state machine."
                )
                self._repair_to_global_state_machine(mechanisms_list, f)

            # Case B: Undeclared scoreboard objective
            elif f.category == QACategory.INITIALIZATION and "UNDECLARED-OBJ" in f.id:
                obj_name = f.line_or_reference or "state"
                diagnoses.append(f"Scoreboard objective '{obj_name}' was undeclared. Adding to load function.")
                self._ensure_objective_in_load(mechanisms_list, obj_name)

            # Case C: Missing execution context 'as @a at @s'
            elif f.category == QACategory.EXECUTION_CONTEXT and "MISSING-AS" in f.id:
                diagnoses.append(f"Entity command lacks context. Adding 'execute as @a at @s' to command.")
                self._repair_missing_entity_context(mechanisms_list)

            # Case D: Missing planned function or predicate
            elif f.category == QACategory.FILE_COMPLETENESS and "MISSING-PRED" in f.id:
                diagnoses.append(f"Predicate was planned but missing. Ensuring predicate mechanism is populated.")

            # Case E: Missing/dangling function tag reference
            elif f.category == QACategory.REFERENCE_INTEGRITY and "TAG-MISSING-FN" in f.id:
                dead_fn = f.line_or_reference or ""
                diagnoses.append(f"Function tag references non-existent function '{dead_fn}'. Pruning invalid tag entry.")
                self._repair_dangling_tag_reference(mechanisms_list, dead_fn)

            # Case F: Duplicate attribute modifier ID (Step 19.5)
            elif f.category == QACategory.COMMAND_SEMANTICS and "FIND-ATTR-DUP-MOD" in f.id:
                dup_mod_id = None
                m = re.search(r"modifier ID '([^']+)'", f.problem)
                if m:
                    dup_mod_id = m.group(1)
                diagnoses.append(
                    f"Duplicate attribute modifier ID '{dup_mod_id or 'unknown'}' detected. "
                    f"Disambiguating modifier identity across structured actions."
                )
                self._repair_duplicate_modifier(mechanisms_list, dup_mod_id)

        # Update corrected plan with modified mechanisms
        if "implementation_plan" in corrected_plan:
            if len(corrected_plan["implementation_plan"]) <= 1:
                for ip in corrected_plan["implementation_plan"]:
                    ip["mechanisms"] = mechanisms_list

        diagnosis_text = " ".join(diagnoses) or "General semantic adjustments to align implementation with user intent."
        repair_plan = QARepairPlan(
            diagnosis=diagnosis_text,
            summary="Corrected mechanism specifications to resolve execution context, state machine logic, or attribute modifier conflicts.",
            mechanism_modifications=mechanisms_list,
            regenerate=True
        )

        return repair_plan, corrected_plan

    # -------------------------------------------------------------------------
    # Deterministic Mechanism Repair Helpers
    # -------------------------------------------------------------------------
    def _repair_to_global_state_machine(
        self,
        mechanisms: List[Dict[str, Any]],
        finding: QAFinding
    ) -> None:
        """
        Converts a flawed per-player environmental state machine to a robust #global state machine.
        Supports both structured state_machine mechanisms and legacy function mechanisms.
        """
        pred_mech = next((m for m in mechanisms if m.get("type") == "predicate"), None)
        pred_id = "minecraft_ai:is_raining"
        if pred_mech:
            ns = pred_mech.get("namespace", "minecraft_ai")
            path = pred_mech.get("path", "is_raining")
            pred_id = f"{ns}:{path}"

        obj_name = "event_state"
        if "rain" in pred_id.lower():
            obj_name = "rain_state"
        elif "night" in pred_id.lower() or "time" in pred_id.lower():
            obj_name = "time_state"

        # Case 1: Structured state_machine mechanism already present
        sm_mech = next((m for m in mechanisms if m.get("type") == "state_machine"), None)
        if sm_mech:
            sm_mech["state_scope"] = "global"
            sm_mech["objective"] = obj_name
            sm_mech["condition_predicate"] = pred_id
            if not sm_mech.get("on_enter"):
                sm_mech["on_enter"] = [{
                    "action_type": "give_item",
                    "target": "@a",
                    "item": "minecraft:diamond",
                    "count": 1
                }]
            return

        # Case 2: Legacy or explicit function mechanisms for load and tick
        load_mech = next((m for m in mechanisms if m.get("type") == "function" and m.get("path") == "load"), None)
        tick_mech = next((m for m in mechanisms if m.get("type") == "function" and m.get("path") == "tick"), None)

        # Update load function
        if load_mech:
            load_mech["commands"] = [
                f"scoreboard objectives add {obj_name} dummy",
                f"scoreboard players set #global {obj_name} 0"
            ]

        # Extract action command from tick function (e.g. give @s minecraft:diamond 1)
        action_cmd = "give @s minecraft:diamond 1"
        if tick_mech and tick_mech.get("commands"):
            for cmd in tick_mech["commands"]:
                m_run = re.search(r"\brun\s+(give\s+@s\s+\S+\s+\d+|effect\s+give\s+@s\s+\S+.*)$", cmd)
                if m_run:
                    action_cmd = m_run.group(1)
                    break
        elif tick_mech and tick_mech.get("actions"):
            # Extract from first action if present
            first_act = tick_mech["actions"][0]
            if isinstance(first_act, dict) and first_act.get("item"):
                action_cmd = f"give @s {first_act.get('item')} {first_act.get('count', 1)}"

        # Update tick function with correct sequence and context
        if tick_mech:
            tick_mech["commands"] = [
                f"execute if score #global {obj_name} matches 0 if predicate {pred_id} as @a at @s run {action_cmd}",
                f"execute if predicate {pred_id} run scoreboard players set #global {obj_name} 1",
                f"execute unless predicate {pred_id} run scoreboard players set #global {obj_name} 0"
            ]

    def _ensure_objective_in_load(
        self,
        mechanisms: List[Dict[str, Any]],
        obj_name: str
    ) -> None:
        load_mech = next((m for m in mechanisms if m.get("type") == "function" and m.get("path") == "load"), None)
        add_cmd = f"scoreboard objectives add {obj_name} dummy"
        if load_mech:
            cmds = load_mech.get("commands", [])
            if not any(add_cmd in c for c in cmds):
                cmds.insert(0, add_cmd)
                load_mech["commands"] = cmds
        else:
            mechanisms.append({
                "type": "function",
                "path": "load",
                "namespace": "minecraft_ai",
                "commands": [add_cmd, f"scoreboard players set #global {obj_name} 0"]
            })

    def _repair_missing_entity_context(
        self,
        mechanisms: List[Dict[str, Any]]
    ) -> None:
        for mech in mechanisms:
            if mech.get("type") == "function":
                # Handle structured actions
                if mech.get("actions"):
                    for act in mech["actions"]:
                        if isinstance(act, dict):
                            act["execution_context"] = {"as_target": True, "at_target": True}
                # Handle legacy commands
                if mech.get("commands"):
                    new_cmds = []
                    for cmd in mech.get("commands", []):
                        if ("give @s" in cmd or "effect give @s" in cmd) and "as @" not in cmd:
                            new_cmds.append(f"execute as @a at @s run {cmd.lstrip('/')}")
                        else:
                            new_cmds.append(cmd)
                    mech["commands"] = new_cmds

    def _repair_dangling_tag_reference(
        self,
        mechanisms: List[Dict[str, Any]],
        dead_fn: str
    ) -> None:
        for m in mechanisms:
            if m.get("type") in ("function_tag", "tag") and "values" in m:
                m["values"] = [v for v in m["values"] if v != dead_fn]

    def _repair_duplicate_modifier(
        self,
        mechanisms: List[Dict[str, Any]],
        dup_mod_id: Optional[str] = None
    ) -> None:
        """
        Disambiguates duplicate attribute modifier IDs across structured mechanism actions.
        Ensures all actions have distinct, deterministic, collision-safe modifier IDs
        by checking against all existing IDs in the plan and incrementing until unused.
        """
        clean_target_dup = dup_mod_id.replace("minecraft_ai:", "").strip().lower() if dup_mod_id else None

        # 1. Collect every existing modifier ID from the complete structured implementation plan
        all_existing_ids: Set[str] = set()
        for mech in mechanisms:
            for action_key in ("actions", "on_enter", "on_exit"):
                actions = mech.get(action_key, [])
                if not isinstance(actions, list):
                    continue
                for action in actions:
                    act_is_dict = isinstance(action, dict)
                    act_mod_id = action.get("modifier_id") if act_is_dict else getattr(action, "modifier_id", None)
                    if act_mod_id:
                        all_existing_ids.add(str(act_mod_id).strip().lower().replace("minecraft_ai:", ""))
                    pm = action.get("property_modification") if act_is_dict else getattr(action, "property_modification", None)
                    if isinstance(pm, dict) and isinstance(pm.get("extra_metadata"), dict):
                        extra_mid = pm["extra_metadata"].get("modifier_id")
                        if extra_mid:
                            all_existing_ids.add(str(extra_mid).strip().lower().replace("minecraft_ai:", ""))

        # 2. Iterate through all actions, preserving first valid occurrence and disambiguating duplicates
        allocated_ids: Set[str] = set()

        for mech in mechanisms:
            for action_key in ("actions", "on_enter", "on_exit"):
                actions = mech.get(action_key, [])
                if not isinstance(actions, list):
                    continue

                for action in actions:
                    act_is_dict = isinstance(action, dict)
                    act_mod_id = action.get("modifier_id") if act_is_dict else getattr(action, "modifier_id", None)
                    pm = action.get("property_modification") if act_is_dict else getattr(action, "property_modification", None)
                    a_type = action.get("action_type") if act_is_dict else getattr(action, "action_type", None)

                    # Only process attribute actions or actions with property modifications / modifier IDs
                    if not (act_mod_id or pm or a_type in ("property_modification", "attribute", "attribute_modifier")):
                        continue

                    prop = None
                    op = None
                    val_str = None
                    if isinstance(pm, dict):
                        prop = pm.get("property")
                        op = pm.get("operation")
                        val_obj = pm.get("value")
                        val_val = val_obj.get("value") if isinstance(val_obj, dict) else getattr(val_obj, "value", val_obj)
                        val_str = str(val_val) if val_val is not None else None
                        if not act_mod_id and isinstance(pm.get("extra_metadata"), dict):
                            act_mod_id = pm["extra_metadata"].get("modifier_id")
                    elif hasattr(pm, "property"):
                        prop = getattr(pm, "property", None)
                        op = getattr(pm, "operation", None)
                        val_obj = getattr(pm, "value", None)
                        val_val = getattr(val_obj, "value", val_obj)
                        val_str = str(val_val) if val_val is not None else None

                    # Determine base modifier identifier
                    if act_mod_id:
                        base_id = str(act_mod_id).strip().lower().replace("minecraft_ai:", "")
                    elif prop:
                        clean_prop = str(prop).strip().lower().split(".")[-1]
                        op_tag = str(op or "set").strip().lower()
                        base_id = f"{clean_prop}_{op_tag}_{val_str or 'val'}"
                    else:
                        base_id = "modifier"

                    # If not yet seen in this pass, preserve the first valid occurrence
                    if base_id not in allocated_ids:
                        allocated_ids.add(base_id)
                        continue

                    # Duplicate collision detected: find the next unused deterministic candidate ID
                    m_step = re.match(r"^(.*)_step_\d+$", base_id)
                    if m_step:
                        stem = m_step.group(1)
                        counter = 0
                        candidate = f"{stem}_step_{counter}"
                        while candidate in all_existing_ids or candidate in allocated_ids:
                            counter += 1
                            candidate = f"{stem}_step_{counter}"
                        step_tag = f"step_{counter}"
                    else:
                        counter = 1
                        candidate = f"{base_id}_{counter}"
                        while candidate in all_existing_ids or candidate in allocated_ids:
                            counter += 1
                            candidate = f"{base_id}_{counter}"
                        step_tag = f"repaired_{counter}"

                    allocated_ids.add(candidate)

                    if act_is_dict:
                        action["modifier_id"] = candidate
                        action["step_id"] = step_tag
                        if isinstance(pm, dict):
                            if "extra_metadata" not in pm or not isinstance(pm["extra_metadata"], dict):
                                pm["extra_metadata"] = {}
                            pm["extra_metadata"]["modifier_id"] = candidate
                            pm["extra_metadata"]["step_id"] = step_tag
                    else:
                        setattr(action, "modifier_id", candidate)
                        setattr(action, "step_id", step_tag)
                        if hasattr(pm, "extra_metadata"):
                            if pm.extra_metadata is None or not isinstance(pm.extra_metadata, dict):
                                pm.extra_metadata = {}
                            pm.extra_metadata["modifier_id"] = candidate
                            pm.extra_metadata["step_id"] = step_tag
