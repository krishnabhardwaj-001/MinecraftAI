"""
ai/lifecycle_reconciler.py - General Mechanism Consistency & Lifecycle Reconciliation Layer

Analyzes structured mechanisms and requirements upstream of deterministic datapack generation:
1. Detects whether multiple mechanisms belong to the same logical lifecycle (e.g. trigger + reset).
2. Detects contradictory state mutations on shared scoreboard objectives.
3. Reconciles related mechanisms into a single coherent state model (with on_enter and on_exit).
4. Preserves independent state machines for genuinely independent lifecycles by disambiguating state variables.
5. Completely general-purpose: zero request-specific or keyword-based rules.
"""
import copy
import hashlib
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


def format_safe_objective_name(
    base: str,
    suffix: Optional[str] = None,
    used_objectives: Optional[Set[str]] = None,
    max_length: int = 16
) -> str:
    """
    Format and disambiguate a Minecraft scoreboard objective name.
    Strictly guarantees:
    1. Valid characters matching ^[a-zA-Z0-9_]+$
    2. Length <= max_length (default 16 chars for Minecraft Java 1.21.11)
    3. Uniqueness against used_objectives
    4. Deterministic disambiguation that avoids collisions even when
       two long candidates share the same prefix.
    """
    used = used_objectives if used_objectives is not None else set()
    clean_base = re.sub(r"[^a-zA-Z0-9_]+", "", (base or "").strip().lower()).strip("_") or "obj"
    clean_suffix = re.sub(r"[^a-zA-Z0-9_]+", "", (suffix or "").strip().lower()).strip("_") if suffix else ""

    if clean_suffix:
        full_name = f"{clean_base}_{clean_suffix}"
        # If full name exceeds max_length, try readable combination of base + suffix
        if len(full_name) > max_length:
            s_budget = min(len(clean_suffix), 8)
            b_budget = max(1, max_length - 1 - s_budget)
            short_cand = f"{clean_base[:b_budget].rstrip('_')}_{clean_suffix[:s_budget].rstrip('_')}"
            if len(short_cand) <= max_length and short_cand not in used:
                return short_cand
    else:
        full_name = clean_base

    # If full name is already short enough and unused, use it directly
    if len(full_name) <= max_length and full_name not in used:
        return full_name

    # If full name fits within max_length but collides, try simple numerical suffix if space permits
    if len(full_name) <= max_length - 2:
        for idx in range(2, 10):
            cand = f"{full_name}_{idx}"
            if len(cand) <= max_length and cand not in used:
                return cand

    # Long name or collision: use readable prefix + deterministic hash of the full disambiguated text.
    # Hash length: 4 hex characters. Prefix budget: max_length - 1 - 4 = 11 characters.
    hash_seed = full_name
    h = hashlib.sha256(hash_seed.encode("utf-8")).hexdigest()[:4]
    prefix_budget = max(1, max_length - 5)
    prefix = clean_base[:prefix_budget].rstrip("_") or "obj"
    candidate = f"{prefix}_{h}"

    if candidate not in used and len(candidate) <= max_length:
        return candidate

    # In case of hash collision or repeated requests, incorporate counter deterministically
    for idx in range(2, 1000):
        h_idx = hashlib.sha256(f"{hash_seed}_{idx}".encode("utf-8")).hexdigest()[:4]
        candidate = f"{prefix}_{h_idx}"
        if candidate not in used and len(candidate) <= max_length:
            return candidate

    return candidate[:max_length]



def are_predicates_complementary(
    pred1_id: str,
    pred2_id: str,
    predicates_info: Optional[Dict[str, Dict[str, Any]]] = None
) -> bool:
    """
    Determines if two predicates are logically complementary (one is true iff the other is false).
    Inspects predicate JSON definitions when available (e.g. inverted conditions or opposing parameters).
    """
    if not pred1_id or not pred2_id:
        return False

    clean1 = pred1_id.strip()
    clean2 = pred2_id.strip()

    # Exact same predicate is identical, not complementary
    if clean1 == clean2 or clean1.split(":")[-1] == clean2.split(":")[-1]:
        return False

    if not predicates_info:
        return False

    def _get_pred_data(pid: str) -> Optional[Dict[str, Any]]:
        # Match full ID or stem
        stem = pid.split(":")[-1]
        for k, v in predicates_info.items():
            if k == pid or k.split(":")[-1] == stem:
                return v
        return None

    p1_data = _get_pred_data(clean1)
    p2_data = _get_pred_data(clean2)

    if not p1_data or not p2_data:
        return False

    # Check 1: One predicate is explicitly "minecraft:inverted" wrapping the other
    if p1_data.get("condition") == "minecraft:inverted":
        term = p1_data.get("term", {})
        if term == p2_data or term.get("term") == p2_data:
            return True

    if p2_data.get("condition") == "minecraft:inverted":
        term = p2_data.get("term", {})
        if term == p1_data or term.get("term") == p1_data:
            return True

    # Check 2: Same condition type with opposing boolean parameters (e.g. weather_check raining: true vs false)
    c1_type = p1_data.get("condition")
    c2_type = p2_data.get("condition")
    if c1_type and c1_type == c2_type:
        # Check all boolean keys
        bool_keys = [k for k in p1_data if isinstance(p1_data[k], bool) and k in p2_data and isinstance(p2_data[k], bool)]
        if bool_keys and all(p1_data[k] != p2_data[k] for k in bool_keys):
            return True

    return False


def is_explicit_latch_reset_action(action: Dict[str, Any], objective: str) -> bool:
    """
    Checks if an action is an explicit score-reset to 0 on the state machine objective.
    (e.g. set_score #global <obj> 0 or reset_score).
    """
    if not isinstance(action, dict):
        return False

    a_type = str(action.get("action_type", "")).strip().lower()
    act_obj = str(action.get("objective", "")).strip()
    target = str(action.get("target", "") or action.get("score_holder", "")).strip()

    if act_obj and act_obj != objective:
        return False

    if a_type == "set_score" and action.get("score_value") == 0:
        return True
    if a_type == "reset_score":
        return True

    return False


class MechanismLifecycleReconciler:
    """
    Reconciles composed mechanism specifications to maintain state consistency,
    prevent contradictory tick writes, and unify shared lifecycles.
    """

    def reconcile(
        self,
        mechanisms: List[Dict[str, Any]],
        predicates_info: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Takes a list of raw mechanism specification dictionaries and produces a
        reconciled list where shared lifecycles are unified and state collisions resolved.
        """
        if not mechanisms:
            return []

        # Separate mechanisms by type
        state_machines: List[Dict[str, Any]] = []
        other_mechanisms: List[Dict[str, Any]] = []

        for m in mechanisms:
            if not isinstance(m, dict):
                other_mechanisms.append(m)
                continue
            m_type = str(m.get("type", "")).strip().lower()
            if m_type in ("state_machine", "event_latch", "event_trigger"):
                state_machines.append(copy.deepcopy(m))
            else:
                other_mechanisms.append(copy.deepcopy(m))

        if len(state_machines) <= 1:
            return mechanisms

        reconciled_sms = self._reconcile_state_machines(state_machines, predicates_info)

        # Ensure all objectives in reconciled state machines are registered
        self._ensure_scoreboard_objectives_registered(reconciled_sms, other_mechanisms)

        return other_mechanisms + reconciled_sms

    def _reconcile_state_machines(
        self,
        sms: List[Dict[str, Any]],
        predicates_info: Optional[Dict[str, Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Unifies state machines belonging to the same lifecycle and disambiguates
        state machines belonging to independent lifecycles.
        """
        merged_sms: List[Dict[str, Any]] = []
        used_objectives: Set[str] = set()

        # Group state machines by candidate objective
        obj_groups: Dict[str, List[Dict[str, Any]]] = {}
        for sm in sms:
            obj = str(sm.get("objective") or sm.get("path") or "event_state").strip()
            obj_groups.setdefault(obj, []).append(sm)

        for obj, group in obj_groups.items():
            if len(group) == 1:
                sm = group[0]
                safe_obj = format_safe_objective_name(obj, used_objectives=used_objectives)
                sm["objective"] = safe_obj
                merged_sms.append(sm)
                used_objectives.add(safe_obj)
                continue

            # Multiple state machines target the same objective.
            # Analyze relationships: Are they part of the same lifecycle or independent?
            unified = self._unify_group(obj, group, predicates_info, used_objectives)
            for u in unified:
                u_obj = format_safe_objective_name(str(u.get("objective") or obj), used_objectives=used_objectives)
                u["objective"] = u_obj
                used_objectives.add(u_obj)
                merged_sms.append(u)

        return merged_sms

    def _unify_group(
        self,
        objective: str,
        group: List[Dict[str, Any]],
        predicates_info: Optional[Dict[str, Dict[str, Any]]] = None,
        used_objectives: Optional[Set[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Examines a set of state machines that share an objective.
        Unifies complementary/redundant phases into a single state machine.
        Retains genuinely independent state machines as separate entries with disambiguated objectives.
        """
        # Find primary trigger machine (the one with non-trivial on_enter gameplay actions)
        primary: Optional[Dict[str, Any]] = None
        secondary_candidates: List[Dict[str, Any]] = []

        for sm in group:
            on_enter = sm.get("on_enter", [])
            has_gameplay_actions = any(not is_explicit_latch_reset_action(a, objective) for a in on_enter)

            if has_gameplay_actions and primary is None:
                primary = sm
            else:
                secondary_candidates.append(sm)

        if primary is None:
            primary = secondary_candidates.pop(0)

        primary_safe_obj = format_safe_objective_name(objective, used_objectives=used_objectives)
        primary["objective"] = primary_safe_obj

        primary_pred = str(primary.get("condition_predicate") or "").strip()
        primary_enter: List[Dict[str, Any]] = list(primary.get("on_enter", []))
        primary_exit: List[Dict[str, Any]] = list(primary.get("on_exit", []))

        independent_sms: List[Dict[str, Any]] = []

        for sec in secondary_candidates:
            sec_pred = str(sec.get("condition_predicate") or "").strip()
            sec_enter: List[Dict[str, Any]] = sec.get("on_enter", [])
            sec_exit: List[Dict[str, Any]] = sec.get("on_exit", [])

            # Check if sec is purely a reset / falling-edge handler of the primary lifecycle.
            # Crucial: sec_enter MUST be non-empty. An empty on_enter list does not qualify as a reset machine.
            is_reset_machine = bool(sec_enter) and all(is_explicit_latch_reset_action(a, objective) for a in sec_enter)
            is_complementary = are_predicates_complementary(primary_pred, sec_pred, predicates_info)
            is_same_predicate = (primary_pred and sec_pred and (primary_pred == sec_pred or primary_pred.split(":")[-1] == sec_pred.split(":")[-1]))

            if is_same_predicate:
                # Same predicate & same objective: merge actions
                for a in sec_enter:
                    if not is_explicit_latch_reset_action(a, objective):
                        primary_enter.append(a)
                primary_exit.extend(sec_exit)
                logger.info("Unified redundant state machine with identical predicate into primary lifecycle.")

            elif is_complementary or (is_reset_machine and sec_pred):
                # sec represents the reset / falling-edge phase of the primary lifecycle!
                # In Minecraft, the primary state machine's falling edge ('unless predicate primary_pred')
                # automatically handles returning to state 0.
                # Any legitimate gameplay exit actions (non-reset actions) in sec_enter belong in on_exit!
                for a in sec_enter:
                    if not is_explicit_latch_reset_action(a, objective):
                        primary_exit.append(a)
                primary_exit.extend(sec_exit)
                logger.info("Unified complementary reset state machine into primary on_exit lifecycle.")

            else:
                # Genuinely independent lifecycle that happened to use the same objective!
                # Keep as separate state machine, but disambiguate objective safely (<= 16 chars).
                pred_stem = sec_pred.split(":")[-1] if sec_pred else "secondary"
                sec_safe_obj = format_safe_objective_name(
                    objective, suffix=pred_stem, used_objectives=used_objectives
                )
                sec["objective"] = sec_safe_obj
                independent_sms.append(sec)
                logger.info("Disambiguated independent state machine to objective '%s'.", sec["objective"])

        primary["on_enter"] = primary_enter
        primary["on_exit"] = primary_exit

        return [primary] + independent_sms

    def _ensure_scoreboard_objectives_registered(
        self,
        sms: List[Dict[str, Any]],
        other_mechanisms: List[Dict[str, Any]]
    ) -> None:
        """
        Ensures that every scoreboard objective used by reconciled state machines
        has a corresponding 'scoreboard_objective' registration in load.
        """
        registered_objs: Set[str] = set()
        for m in other_mechanisms:
            m_type = str(m.get("type", "")).strip().lower()
            if m_type == "scoreboard_objective":
                obj = str(m.get("objective") or m.get("path") or "").strip()
                if obj:
                    registered_objs.add(obj)

        for sm in sms:
            obj = str(sm.get("objective") or "").strip()
            if obj and obj not in registered_objs:
                other_mechanisms.append({
                    "type": "scoreboard_objective",
                    "objective": obj,
                    "criteria": "dummy",
                    "display_name": f"{obj} state"
                })
                registered_objs.add(obj)


# Global default instance
DEFAULT_LIFECYCLE_RECONCILER = MechanismLifecycleReconciler()


def reconcile_plan_mechanisms(
    plan: Dict[str, Any],
    predicates_info: Optional[Dict[str, Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Applies lifecycle reconciliation to all mechanisms across all implementation entries in a plan.
    """
    if not isinstance(plan, dict):
        return plan

    ip_list = plan.get("implementation_plan", [])
    if not ip_list or not isinstance(ip_list, list):
        return plan

    # Gather all mechanisms across all entries
    all_mechs: List[Dict[str, Any]] = []
    for ip in ip_list:
        mechs = ip.get("mechanisms", [])
        if isinstance(mechs, list):
            for m in mechs:
                if isinstance(m, dict):
                    all_mechs.append(m)

    reconciled = DEFAULT_LIFECYCLE_RECONCILER.reconcile(all_mechs, predicates_info)

    # Re-assign reconciled mechanisms to implementation_plan
    # If unified, assign to the primary entry and clear redundant entries
    if ip_list:
        ip_list[0]["mechanisms"] = reconciled
        for ip in ip_list[1:]:
            ip["mechanisms"] = []

    return plan
