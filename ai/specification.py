"""
ai/specification.py - Implementation-Neutral Specification Bridge

Validates confirmed conversational proposals against Minecraft Java datapack capabilities
and transforms them into structured, implementation-neutral specifications for the
downstream planner and deterministic generator.
"""
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field, ConfigDict

from ai.conversation import ProposedBehavior, ConversationSession


# Keywords and concepts that cannot be implemented by vanilla Minecraft datapacks
UNSUPPORTED_DATAPACK_CONCEPTS = [
    ("custom 3d model", "Vanilla datapacks cannot add custom 3D entity or block models without resource packs or client mods."),
    ("custom sound file", "Datapacks cannot bundle new audio files; custom sounds require a client-side resource pack."),
    ("custom texture", "Datapacks cannot bundle PNG texture assets; custom textures require a resource pack."),
    ("client shader", "Datapacks cannot alter client GPU shaders."),
    ("custom gui", "Datapacks cannot create completely custom client GUI menus or windows outside chat menus and containers."),
    ("external http", "Minecraft datapacks run sandboxed inside the Minecraft server and cannot make external HTTP requests or network calls."),
    ("play mp3", "Datapacks cannot stream or play external MP3 files."),
]


class ValidationReport(BaseModel):
    """Result of validating a proposed behavior against Minecraft capabilities."""
    model_config = ConfigDict(extra="allow")

    is_supported: bool
    unsupported_reason: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)


class ConfirmedGameplaySpecification(BaseModel):
    """
    Implementation-neutral gameplay specification ready for downstream compilation.
    Free of raw commands, filepaths, or internal mechanisms.
    """
    model_config = ConfigDict(extra="allow")

    summary: str
    target_version: str = "1.21.11"
    requirements: List[Dict[str, Any]] = Field(default_factory=list)
    trigger_condition: Optional[str] = None
    target_affected: Optional[str] = None
    mechanisms_involved: List[str] = Field(default_factory=list)
    assumptions_applied: List[Dict[str, str]] = Field(default_factory=list)


class SpecificationBridge:
    """
    Bridges confirmed conversational dialogue to the downstream deterministic pipeline.
    Validates capabilities and produces structured specifications.
    """

    def validate_capabilities(self, proposal: ProposedBehavior) -> ValidationReport:
        """
        Validates whether the requested behavior is technically possible with
        vanilla Minecraft Java datapacks.
        """
        combined_text = f"{proposal.summary} {proposal.trigger_condition or ''} {proposal.target_affected or ''}".lower()

        # Check for explicitly unsupported concepts
        for concept, explanation in UNSUPPORTED_DATAPACK_CONCEPTS:
            if concept in combined_text:
                return ValidationReport(
                    is_supported=False,
                    unsupported_reason=explanation
                )

        if proposal.status == "unsupported":
            return ValidationReport(
                is_supported=False,
                unsupported_reason=proposal.unsupported_reason or "Requested behavior is outside Minecraft datapack capabilities."
            )

        return ValidationReport(is_supported=True)

    def convert_to_understanding_result(
        self,
        proposal: ProposedBehavior,
        version: str = "1.21.11"
    ) -> Dict[str, Any]:
        """
        Converts a confirmed ProposedBehavior into a dictionary compatible with
        the downstream MinecraftUnderstandingResult schema used by ai/context.py and ai/planner.py.
        """
        validation = self.validate_capabilities(proposal)
        if not validation.is_supported:
            return {
                "status": "unsupported",
                "minecraft_version": version,
                "edition": "Java",
                "understood_request": proposal.summary,
                "requirements": [],
                "clarification": {
                    "reason": validation.unsupported_reason or "Unsupported request",
                    "question": "This request cannot be fulfilled by a vanilla datapack. Would you like to adjust your request?",
                    "options": []
                },
                "missing_information": ["unsupported_capability"]
            }

        # Synthesize structured requirements from raw_requirements and assumptions
        reqs = list(proposal.raw_requirements)
        if not reqs:
            reqs = [{
                "subject": proposal.target_affected or "gameplay",
                "target": proposal.target_affected,
                "intent": proposal.summary,
                "conditions": [proposal.trigger_condition] if proposal.trigger_condition else [],
                "constraints": []
            }]

        # Inject assumptions: associate with specific requirements or preserve as global context
        global_assumptions = []

        if proposal.assumptions and reqs:
            if len(reqs) == 1:
                # Single requirement: unambiguous, attach all assumptions to reqs[0]
                details = reqs[0].get("details", [])
                for a in proposal.assumptions:
                    details.append({
                        "name": a.description,
                        "value": a.default_applied,
                        "description": a.rationale
                    })
                reqs[0]["details"] = details
            else:
                # Multi-requirement: associate by explicit reference or unambiguous semantic match
                for a in proposal.assumptions:
                    matched_idx: Optional[int] = None

                    # 1. Prefer explicit requirement index reference
                    if (
                        a.target_requirement_index is not None
                        and isinstance(a.target_requirement_index, int)
                        and 0 <= a.target_requirement_index < len(reqs)
                    ):
                        matched_idx = a.target_requirement_index
                    else:
                        # 2. Semantic matching (only if match is UNAMBIGUOUS)
                        matching_indices = []
                        target_sub = (a.target_subject or "").strip().lower()
                        desc_text = f"{a.description} {a.default_applied}".lower()

                        for idx, req in enumerate(reqs):
                            req_sub = str(req.get("subject") or "").strip().lower()
                            req_target = str(req.get("target") or "").strip().lower()
                            req_intent = str(req.get("intent") or "").strip().lower()

                            # Match on explicit target_subject if specified
                            if target_sub and (target_sub == req_sub or target_sub == req_target or target_sub in req_intent):
                                matching_indices.append(idx)
                                continue

                            # Semantic keyword check (min 3 chars to prevent false substring positives)
                            sub_match = bool(req_sub and len(req_sub) >= 3 and req_sub in desc_text)
                            target_match = bool(req_target and len(req_target) >= 3 and req_target in desc_text)
                            if sub_match or target_match:
                                matching_indices.append(idx)

                        if len(matching_indices) == 1:
                            matched_idx = matching_indices[0]

                    # 3. Attach if unambiguously matched; otherwise preserve as global context
                    if matched_idx is not None:
                        details = reqs[matched_idx].get("details", [])
                        details.append({
                            "name": a.description,
                            "value": a.default_applied,
                            "description": a.rationale
                        })
                        reqs[matched_idx]["details"] = details
                    else:
                        # Ambiguous or unmatched: preserve as global context without corrupting individual requirements
                        global_assumptions.append({
                            "name": a.description,
                            "value": a.default_applied,
                            "description": a.rationale,
                            "scope": "global"
                        })

        result = {
            "status": "understood",
            "minecraft_version": version,
            "edition": "Java",
            "understood_request": proposal.summary,
            "requirements": reqs,
            "clarification": None,
            "missing_information": []
        }
        if global_assumptions:
            result["assumptions"] = global_assumptions

        return result

    def convert_session_to_specification(
        self,
        session: ConversationSession
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Converts a confirmed conversation session into a downstream-compatible dictionary.
        Returns: (success: bool, result_dict: Optional[Dict], error_message: Optional[str])
        """
        if not session.is_confirmed() or not session.current_proposal:
            return False, None, "Session has not been confirmed by the user."

        validation = self.validate_capabilities(session.current_proposal)
        if not validation.is_supported:
            return False, None, validation.unsupported_reason

        understanding_dict = self.convert_to_understanding_result(
            proposal=session.current_proposal,
            version=session.minecraft_version
        )
        return True, understanding_dict, None
