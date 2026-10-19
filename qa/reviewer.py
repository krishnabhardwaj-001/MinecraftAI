import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ai.provider import AIProvider
from ai.version_registry import VersionContext
from qa.analyzer import StaticSemanticAnalyzer
from qa.models import (
    IntentVerificationResult,
    QACategory,
    QAFinding,
    QAResult,
    QASeverity,
)
from validator.models import ValidationResult
from ai.semantic_models import PropertyModification, SemanticValue
from ai.property_registry import DEFAULT_PROPERTY_REGISTRY
from ai.implementation_mapper import ImplementationMapper


class AutonomousQAReviewer:
    """
    Step 14: Autonomous QA Reviewer for Minecraft Java Edition 1.21.11 Datapacks.

    Performs an independent, human-like QA and intent verification pass over the
    COMPLETE generated datapack:
    1. Static semantic & cross-file reference analysis (StaticSemanticAnalyzer)
    2. Execution context and state-machine temporal logic review
    3. User intent verification comparing command logic to the original request
    4. Optional LLM-assisted edge-case review
    """

    def __init__(
        self,
        ai_provider: Optional[AIProvider] = None,
        provider: str = "ollama",
        version: Optional[str] = None,
        version_context: Optional[VersionContext] = None
    ):
        if version_context is not None:
            self.version_context = version_context
        else:
            self.version_context = VersionContext.from_version(version)
        self.version = self.version_context.version_id
        self.provider_name = provider
        self._ai_provider = ai_provider
        self.analyzer = StaticSemanticAnalyzer(version_context=self.version_context)

    @property
    def ai(self) -> AIProvider:
        if self._ai_provider is None:
            self._ai_provider = AIProvider(provider=self.provider_name)
        return self._ai_provider

    @ai.setter
    def ai(self, val: AIProvider):
        self._ai_provider = val

    def review(
        self,
        datapack_dir: Path,
        original_request: str,
        understanding: Optional[Dict[str, Any]] = None,
        plan: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        val_result: Optional[ValidationResult] = None
    ) -> QAResult:
        """
        Executes complete QA review over the generated datapack directory.
        """
        datapack_dir = Path(datapack_dir)

        # 1. Run deterministic static semantic analyzer
        findings = self.analyzer.analyze(
            datapack_dir=datapack_dir,
            plan=plan,
            understanding=understanding
        )

        # 2. Collect all file contents for intent and command review
        all_files_content = self._read_all_files(datapack_dir)

        # 3. Perform intent verification
        intent_result = self._verify_intent(
            original_request=original_request,
            understanding=understanding,
            plan=plan,
            all_files_content=all_files_content,
            findings=findings
        )

        # If intent verification found critical mismatches, add them as QAFindings
        if not intent_result.matches_intent:
            for missing in intent_result.missing_aspects:
                findings.append(
                    QAFinding(
                        id=f"FIND-INTENT-MISSING-{len(findings)+1}",
                        severity=QASeverity.ERROR,
                        category=QACategory.INTENT_MISMATCH,
                        problem=f"Requested requirement not satisfied: {missing}",
                        explanation=intent_result.reasoning,
                        expected_behavior=f"The datapack must fulfill '{missing}'.",
                        repair_required="Update implementation plan to include missing requirement."
                    )
                )
            for unwanted in intent_result.unwanted_aspects:
                findings.append(
                    QAFinding(
                        id=f"FIND-INTENT-UNWANTED-{len(findings)+1}",
                        severity=QASeverity.ERROR,
                        category=QACategory.INTENT_MISMATCH,
                        problem=f"Unwanted/counter-productive behavior detected: {unwanted}",
                        explanation=intent_result.reasoning,
                        expected_behavior="Remove or restrict unwanted behavior.",
                        repair_required="Correct command conditions or rate limits."
                    )
                )

        # 4. Formulate final status
        error_count = sum(1 for f in findings if f.severity == QASeverity.ERROR)
        warn_count = sum(1 for f in findings if f.severity == QASeverity.WARNING)

        if error_count > 0 or not intent_result.matches_intent:
            status = "failed"
            summary = (
                f"QA Review FAILED: {error_count} error(s), {warn_count} warning(s). "
                f"Intent match: {intent_result.matches_intent}."
            )
        elif warn_count > 0:
            status = "warning"
            summary = f"QA Review PASSED with {warn_count} warning(s). Intent verified."
        else:
            status = "passed"
            summary = "QA Review PASSED cleanly. All semantic, reference, and intent checks verified."

        return QAResult(
            status=status,
            summary=summary,
            findings=findings,
            intent_verification=intent_result,
            static_semantic_verification="failed" if error_count > 0 else "passed",
            runtime_verification="not_available"
        )

    # -------------------------------------------------------------------------
    # Intent Verification
    # -------------------------------------------------------------------------
    def _verify_intent(
        self,
        original_request: str,
        understanding: Optional[Dict[str, Any]],
        plan: Optional[Dict[str, Any]],
        all_files_content: Dict[str, str],
        findings: List[QAFinding]
    ) -> IntentVerificationResult:
        """
        Compares the generated implementation against the original user intent.
        Evaluates:
        - "once when X starts" vs continuous execution
        - requested items present in give commands or loot tables
        - requested entities targeted
        """
        request_lower = original_request.lower()
        missing_aspects: List[str] = []
        unwanted_aspects: List[str] = []
        reasoning_parts: List[str] = []

        all_commands: List[str] = []
        for file_path, content in all_files_content.items():
            if file_path.endswith(".mcfunction"):
                for line in content.splitlines():
                    line_c = line.strip()
                    if line_c and not line_c.startswith("#"):
                        all_commands.append(line_c)

        combined_commands = " \n ".join(all_commands)
        combined_all_content = " \n ".join(all_files_content.values())

        # Check 1: "once" / "when ... starts" vs continuous execution
        is_once_request = any(k in request_lower for k in ["once", "when it starts", "when the rain starts", "on start", "only once"])
        if is_once_request:
            # Must have a state latch (scoreboard matches 0, set to 1)
            has_state_latch = (
                re.search(r"if\s+score\s+\S+\s+\S+\s+matches\s+0", combined_commands) is not None
                and re.search(r"scoreboard\s+players\s+set\s+\S+\s+\S+\s+1", combined_commands) is not None
            )
            if not has_state_latch:
                unwanted_aspects.append("Continuous execution instead of triggering only once when event starts")
                reasoning_parts.append(
                    "User requested action 'only once when event starts', but commands lack a transition state latch, "
                    "which would cause the action to trigger repeatedly every tick while the condition is active."
                )
            else:
                reasoning_parts.append("Verified transition state machine latch for 'once when starts' requirement.")

        # Check 2: Item presence from understanding
        if understanding and "requirements" in understanding:
            for req in understanding["requirements"]:
                for detail in req.get("details", []):
                    if detail.get("name") == "item":
                        expected_item = detail.get("value", "").lower()
                        # Verify that expected_item appears in commands or loot tables
                        if expected_item and expected_item not in combined_all_content.lower():
                            missing_aspects.append(f"Requested item '{expected_item}' not found in any generated resource")
                            reasoning_parts.append(
                                f"User requested item '{expected_item}', but this item was not found in generated commands or loot tables."
                            )

        # Check 3: Property modification intent verification (Step 19.4 & Step 19 remediation)
        requested_mods: List[Any] = []

        def _to_property_mod(item: Any) -> Optional[PropertyModification]:
            if isinstance(item, PropertyModification):
                return item
            if isinstance(item, dict) and item.get("property"):
                val_raw = item.get("value")
                val_obj = None
                if isinstance(val_raw, SemanticValue):
                    val_obj = val_raw
                elif isinstance(val_raw, dict):
                    try:
                        val_obj = SemanticValue(**val_raw)
                    except Exception:
                        pass
                elif isinstance(val_raw, (int, float)):
                    try:
                        val_obj = SemanticValue(kind=item.get("value_kind", "absolute"), value=val_raw)
                    except Exception:
                        pass
                try:
                    target_cand = item.get("target")
                    if not target_cand and isinstance(item.get("extra_metadata"), dict):
                        target_cand = item["extra_metadata"].get("target")
                    return PropertyModification(
                        property=item.get("property"),
                        operation=item.get("operation"),
                        value=val_obj,
                        target=target_cand or "@a",
                        missing=item.get("missing", []),
                        extra_metadata=item.get("extra_metadata", {})
                    )
                except Exception:
                    pass
            return None

        # 1. Collect from plan
        if plan and isinstance(plan, dict) and "implementation_plan" in plan:
            for ip in plan.get("implementation_plan", []):
                if isinstance(ip, dict):
                    pm = ip.get("property_modification")
                    pmod = _to_property_mod(pm)
                    if pmod and not any(getattr(m, "property", None) == pmod.property for m in requested_mods):
                        requested_mods.append(pmod)
                    for mech in (ip.get("mechanisms") or []):
                        if isinstance(mech, dict):
                            for action in (mech.get("actions") or []):
                                act_pm = action.get("property_modification") if isinstance(action, dict) else getattr(action, "property_modification", None)
                                pmod = _to_property_mod(act_pm)
                                if pmod and not any(getattr(m, "property", None) == pmod.property for m in requested_mods):
                                    requested_mods.append(pmod)

        # 2. Collect from understanding
        if understanding and isinstance(understanding, dict):
            for pm in understanding.get("property_modifications", []):
                pmod = _to_property_mod(pm)
                if pmod and not any(getattr(m, "property", None) == pmod.property for m in requested_mods):
                    requested_mods.append(pmod)

            for req in understanding.get("requirements", []):
                if isinstance(req, dict):
                    pm = req.get("property_modification")
                    pmod = _to_property_mod(pm)
                    if pmod and not any(getattr(m, "property", None) == pmod.property for m in requested_mods):
                        requested_mods.append(pmod)
                    elif req.get("property"):
                        prop_name = str(req["property"]).strip().lower()
                        if not any(getattr(m, "property", None) == prop_name for m in requested_mods):
                            try:
                                from ai.numeric_interpreter import extract_property_modifications
                                ems = extract_property_modifications(original_request)
                                for em in ems:
                                    if em.property and em.property.strip().lower() == prop_name:
                                        requested_mods.append(em)
                                        break
                            except Exception:
                                pass

        # 3. Fallback to NLP extraction if still empty
        if not requested_mods:
            req_text = (understanding.get("understood_request") if understanding and isinstance(understanding, dict) else "") or original_request
            if req_text:
                try:
                    from ai.numeric_interpreter import extract_property_modifications
                    extracted = extract_property_modifications(req_text)
                    for em in extracted:
                        if em.property and not any(getattr(m, "property", None) == em.property for m in requested_mods):
                            requested_mods.append(em)
                except Exception:
                    pass

        # 4. Verify each requested property modification against structured plan and generated commands
        if requested_mods:
            for pmod in requested_mods:
                ok, reason = self._verify_property_modification(pmod, plan, all_commands)
                if not ok:
                    missing_aspects.append(f"Requested property modification '{pmod.property}' failed verification: {reason}")
                    reasoning_parts.append(
                        f"Property modification intent mismatch for '{pmod.property}': {reason}"
                    )
                else:
                    reasoning_parts.append(reason)

        # Check 4: If structural findings already showed load selector or ordering failure, document intent failure
        critical_findings = [f for f in findings if f.category in (QACategory.EXECUTION_CONTEXT, QACategory.STATE_MACHINE) and f.severity == QASeverity.ERROR]
        if critical_findings:
            reasoning_parts.append(
                f"Execution and state machine failures prevent the datapack from fulfilling user intent: "
                f"{'; '.join(f.problem for f in critical_findings)}"
            )

        matches_intent = len(missing_aspects) == 0 and len(unwanted_aspects) == 0 and len(critical_findings) == 0
        confidence = 1.0 if matches_intent else 0.2

        if matches_intent and not reasoning_parts:
            reasoning_parts.append("Implementation matches all requested requirements and constraints.")

        return IntentVerificationResult(
            matches_intent=matches_intent,
            confidence=confidence,
            reasoning=" ".join(reasoning_parts),
            missing_aspects=missing_aspects,
            unwanted_aspects=unwanted_aspects
        )

    def _verify_property_modification(
        self,
        mod: PropertyModification,
        plan: Optional[Dict[str, Any]],
        all_commands: List[str]
    ) -> tuple[bool, str]:
        """
        Verifies that a structured PropertyModification is correctly and accurately
        implemented in the generated commands and plan, matching property, operation,
        value_kind, numeric value, target, and Minecraft mechanism.
        """
        prop_name = str(getattr(mod, "property", "")).strip().lower()
        if not prop_name:
            return False, "Missing property identifier in modification specification."

        # 1. Look up property capabilities
        cap = DEFAULT_PROPERTY_REGISTRY.lookup(prop_name)
        if not cap:
            return False, f"Property '{prop_name}' is not recognized in property capability registry."

        # 2. Map structured PropertyModification to Minecraft mechanism
        target = getattr(mod, "target", None) or (mod.extra_metadata.get("target") if getattr(mod, "extra_metadata", None) and isinstance(mod.extra_metadata, dict) else None) or "@a"
        mapper = ImplementationMapper(registry=DEFAULT_PROPERTY_REGISTRY)
        mapped = mapper.map_modification(mod, default_target=target)
        if mapped.status != "ready":
            return False, f"Property modification for '{prop_name}' could not be resolved to Minecraft mechanism: {mapped.reason or mapped.status}"

        # 3. If structured plan is provided, verify alignment of plan actions/specifications
        if plan and isinstance(plan, dict) and "implementation_plan" in plan:
            for ip in plan.get("implementation_plan", []):
                if isinstance(ip, dict):
                    plan_pm = ip.get("property_modification")
                    if isinstance(plan_pm, dict):
                        p_name = plan_pm.get("property")
                        if p_name and str(p_name).strip().lower() == prop_name:
                            p_op = plan_pm.get("operation")
                            if p_op and mod.operation and p_op != mod.operation:
                                return False, f"Plan specifies operation '{p_op}', but intent requested '{mod.operation}'."
                            p_val = plan_pm.get("value")
                            p_kind = p_val.get("kind") if isinstance(p_val, dict) else getattr(p_val, "kind", None)
                            m_kind = mod.value.kind if mod.value else None
                            if p_kind and m_kind and p_kind != m_kind:
                                return False, f"Plan specifies value kind '{p_kind}', but intent requested '{m_kind}'."
                            p_v = p_val.get("value") if isinstance(p_val, dict) else getattr(p_val, "value", None)
                            m_v = mod.value.value if mod.value else None
                            if p_v is not None and m_v is not None:
                                try:
                                    if abs(float(p_v) - float(m_v)) > 1e-4:
                                        return False, f"Plan specifies value {p_v}, but intent requested {m_v}."
                                except (ValueError, TypeError):
                                    pass

                    for mech in ip.get("mechanisms", []):
                        if isinstance(mech, dict):
                            for action in mech.get("actions", []):
                                act_pm = action.get("property_modification") if isinstance(action, dict) else getattr(action, "property_modification", None)
                                if act_pm:
                                    a_name = act_pm.get("property") if isinstance(act_pm, dict) else getattr(act_pm, "property", None)
                                    if a_name and str(a_name).strip().lower() == prop_name:
                                        a_op = act_pm.get("operation") if isinstance(act_pm, dict) else getattr(act_pm, "operation", None)
                                        if a_op and mod.operation and a_op != mod.operation:
                                            return False, f"Plan action specifies operation '{a_op}', but intent requested '{mod.operation}'."
                                        a_val = act_pm.get("value") if isinstance(act_pm, dict) else getattr(act_pm, "value", None)
                                        a_kind = a_val.get("kind") if isinstance(a_val, dict) else getattr(a_val, "kind", None)
                                        m_kind = mod.value.kind if mod.value else None
                                        if a_kind and m_kind and a_kind != m_kind:
                                            return False, f"Plan action specifies value kind '{a_kind}', but intent requested '{m_kind}'."
                                        a_v = a_val.get("value") if isinstance(a_val, dict) else getattr(a_val, "value", None)
                                        m_v = mod.value.value if mod.value else None
                                        if a_v is not None and m_v is not None:
                                            try:
                                                if abs(float(a_v) - float(m_v)) > 1e-4:
                                                    return False, f"Plan action specifies value {a_v}, but intent requested {m_v}."
                                            except (ValueError, TypeError):
                                                pass

        # 4. Verify generated commands
        mech_type = mapped.mechanism_type
        expected_target = mapped.target
        op = mod.operation
        val_obj = mod.value
        val_kind = getattr(val_obj, "kind", None) if val_obj else None
        val_num = getattr(val_obj, "value", None) if val_obj else None

        if mech_type == "attribute":
            if op == "set" and val_kind == "absolute":
                expected_subcmd = "base_set"
                expected_mod_type = None
                expected_amount = float(val_num)
            elif op == "add" and val_kind == "relative":
                expected_subcmd = "modifier_add"
                expected_mod_type = "add_value"
                expected_amount = float(val_num)
            elif op == "subtract" and val_kind == "relative":
                expected_subcmd = "modifier_add"
                expected_mod_type = "add_value"
                expected_amount = -float(val_num)
            elif op == "add" and val_kind == "percentage":
                expected_subcmd = "modifier_add"
                expected_mod_type = "add_multiplied_base"
                expected_amount = float(val_num) / 100.0
            elif op == "subtract" and val_kind == "percentage":
                expected_subcmd = "modifier_add"
                expected_mod_type = "add_multiplied_base"
                expected_amount = -float(val_num) / 100.0
            elif op == "multiply" and val_kind == "multiplier":
                expected_subcmd = "modifier_add"
                expected_mod_type = "add_multiplied_total"
                expected_amount = float(val_num) - 1.0
            elif op == "divide" and val_kind == "multiplier":
                expected_subcmd = "modifier_add"
                expected_mod_type = "add_multiplied_total"
                expected_amount = (1.0 / float(val_num)) - 1.0
            else:
                return False, f"Unsupported semantic combination for attribute: operation='{op}', value_kind='{val_kind}'."

            minecraft_id = mapped.minecraft_identifier or f"minecraft:generic.{prop_name}"
            clean_ident = minecraft_id.lower()
            short_ident = clean_ident.split(":")[-1]
            base_name = short_ident.split(".")[-1]

            mismatches: List[str] = []
            found_any_for_attr = False

            for cmd in all_commands:
                cmd_lower = cmd.lower()
                if "attribute" not in cmd_lower:
                    continue
                if not (clean_ident in cmd_lower or short_ident in cmd_lower or f" {base_name} " in cmd_lower or f":{base_name} " in cmd_lower or f".{base_name} " in cmd_lower):
                    continue

                found_any_for_attr = True

                # Parse target
                cmd_target = None
                m_exec = re.search(r"execute\s+as\s+(\S+)", cmd, re.IGNORECASE)
                if m_exec:
                    cmd_target = m_exec.group(1)
                else:
                    m_attr_target = re.search(r"attribute\s+(\S+)", cmd, re.IGNORECASE)
                    if m_attr_target:
                        cmd_target = m_attr_target.group(1)

                target_match = False
                if cmd_target:
                    if cmd_target == expected_target:
                        target_match = True
                    elif expected_target == "@a" and cmd_target in ("@a", "@p"):
                        target_match = True
                    elif expected_target == "@s" and cmd_target in ("@s", "@a"):
                        target_match = True

                # Check base set
                m_base = re.search(r"base\s+set\s+(-?\d+(?:\.\d+)?)", cmd, re.IGNORECASE)
                if m_base:
                    found_amount = float(m_base.group(1))
                    if expected_subcmd == "base_set":
                        if abs(found_amount - expected_amount) < 1e-4:
                            if target_match:
                                return True, f"Verified generated implementation for property '{prop_name}' (base set {expected_amount}) targeting '{cmd_target}'."
                            else:
                                mismatches.append(f"Target mismatch: found '{cmd_target}', expected '{expected_target}'")
                        else:
                            mismatches.append(f"Amount mismatch for base set: found {found_amount}, expected {expected_amount}")
                    else:
                        mismatches.append(f"Operation mismatch: found 'base set {found_amount}', expected {expected_subcmd} ({expected_mod_type} {expected_amount})")
                    continue

                # Check modifier add
                m_mod = re.search(r"modifier\s+add\s+(\S+)\s+(-?\d+(?:\.\d+)?)\s+(add_value|add_multiplied_base|add_multiplied_total)", cmd, re.IGNORECASE)
                if m_mod:
                    found_mod_id = m_mod.group(1)
                    found_amount = float(m_mod.group(2))
                    found_mod_type = m_mod.group(3).lower()
                    if expected_subcmd == "modifier_add":
                        if found_mod_type == expected_mod_type:
                            if abs(found_amount - expected_amount) < 1e-4:
                                if target_match:
                                    return True, f"Verified generated implementation for property '{prop_name}' ({expected_mod_type} {expected_amount}) targeting '{cmd_target}'."
                                else:
                                    mismatches.append(f"Target mismatch: found '{cmd_target}', expected '{expected_target}'")
                            else:
                                mismatches.append(f"Amount mismatch: found {found_amount}, expected {expected_amount} for '{expected_mod_type}'")
                        else:
                            mismatches.append(f"Modifier type mismatch: found '{found_mod_type}', expected '{expected_mod_type}'")
                    else:
                        mismatches.append(f"Subcommand mismatch: found modifier add ({found_mod_type} {found_amount}), expected {expected_subcmd} ({expected_amount})")
                    continue

            if found_any_for_attr:
                return False, f"Command found for property '{prop_name}', but semantic mismatch: {'; '.join(mismatches)}"
            return False, f"Requested property modification '{prop_name}' not implemented in generated datapack."

        elif mech_type == "effect":
            eff_id = mapped.minecraft_identifier or f"minecraft:{prop_name}"
            clean_eff = eff_id.lower()
            short_eff = clean_eff.split(":")[-1]
            for cmd in all_commands:
                cmd_lower = cmd.lower()
                if "effect give" in cmd_lower and (clean_eff in cmd_lower or short_eff in cmd_lower):
                    return True, f"Verified generated implementation for property '{prop_name}' (effect {short_eff})."
            return False, f"Requested effect for property '{prop_name}' not found in generated commands."

        elif mech_type == "scoreboard":
            for cmd in all_commands:
                cmd_lower = cmd.lower()
                if "scoreboard" in cmd_lower and prop_name in cmd_lower:
                    return True, f"Verified generated implementation for property '{prop_name}' (scoreboard)."
            return False, f"Requested scoreboard mechanism for property '{prop_name}' not found in generated commands."

        return False, f"Unsupported mechanism '{mech_type}' for property '{prop_name}'."


    def _read_all_files(self, root: Path) -> Dict[str, str]:
        contents: Dict[str, str] = {}
        for p in root.rglob("*"):
            if p.is_file():
                rel = str(p.relative_to(root)).replace("\\", "/")
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        contents[rel] = f.read()
                except Exception:
                    pass
        return contents
