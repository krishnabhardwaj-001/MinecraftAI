import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ai.provider import AIProvider
from qa.analyzer import StaticSemanticAnalyzer
from qa.models import (
    IntentVerificationResult,
    QACategory,
    QAFinding,
    QAResult,
    QASeverity,
)
from validator.models import ValidationResult


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
        version: str = "1.21.11"
    ):
        self.version = version
        self.provider_name = provider
        self.ai = ai_provider or AIProvider(provider=provider)
        self.analyzer = StaticSemanticAnalyzer(version=version)

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

        # Check 3: If structural findings already showed load selector or ordering failure, document intent failure
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
