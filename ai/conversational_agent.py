"""
ai/conversational_agent.py - Conversational Understanding & Prompt Completion Engine

Uses LLM-driven semantic reasoning across the entire message and conversational context.
Understands complete natural-language requests, reconciles follow-up adjustments without
losing previously agreed context, infers sensible defaults, explains assumptions in plain
English, and presents concrete proposals for user confirmation before generation.
"""
import json
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict

from ai.conversation import (
    AssumptionItem,
    ConversationSession,
    ProposedBehavior,
)
from ai.provider import AIProvider
from ai.version_registry import VersionContext, get_version_registry

logger = logging.getLogger(__name__)


class AgentTurnOutput(BaseModel):
    """Structured response schema returned by the conversational LLM."""
    model_config = ConfigDict(extra="allow")

    summary: str = Field(
        ...,
        description="Plain-English explanation of what the datapack will do in Minecraft"
    )
    trigger_condition: Optional[str] = Field(
        default=None,
        description="When the mechanic triggers (e.g. 'When a player kills a zombie', 'Continuously every tick')"
    )
    target_affected: Optional[str] = Field(
        default=None,
        description="Who or what is affected (e.g. 'The player', 'All zombies')"
    )
    mechanisms_involved: List[str] = Field(
        default_factory=list,
        description="Minecraft mechanisms involved (e.g. ['loot_table', 'function', 'attribute_modifier', 'recipe'])"
    )
    assumptions: List[AssumptionItem] = Field(
        default_factory=list,
        description="Assumptions or sensible defaults inferred by the AI with technical rationale"
    )
    open_choices: List[str] = Field(
        default_factory=list,
        description="Focused non-technical choices if multiple materially divergent paths exist"
    )
    status: str = Field(
        default="proposed",
        description="'proposed' (ready to confirm), 'needs_clarification' (materially divergent), 'confirmed', or 'unsupported'"
    )
    is_complete: bool = Field(
        default=True,
        description="True if enough details exist to build upon user confirmation; False if waiting on choices"
    )
    confirmation_prompt: str = Field(
        default="Does this proposed behavior match what you want, or would you like to make any adjustments?",
        description="Plain-English prompt asking the user to confirm or revise"
    )
    unsupported_reason: Optional[str] = Field(
        default=None,
        description="If status is 'unsupported', explanation of why Minecraft datapacks cannot perform this request"
    )
    raw_requirements: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Structured semantic requirements for downstream planning"
    )


class ConversationalUnderstandingEngine:
    """
    LLM-powered conversational understanding engine.
    Interprets entire requests, manages multi-turn dialogue, infers sensible defaults,
    and formulates plain-English proposals before generation.
    """

    def __init__(
        self,
        ai_provider: Optional[AIProvider] = None,
        provider_name: str = "ollama",
        version: str = "1.21.11"
    ):
        self.ai = ai_provider or AIProvider(provider=provider_name)
        self.version = version

    def _build_system_prompt(self, version: str) -> str:
        return f"""You are the Conversational Understanding Engine of MinecraftAI.
Target: Minecraft Java Edition {version}.

Your primary responsibility is to understand the user's natural-language request,
its context, intended outcome, implied constraints, and gameplay preferences.

CORE PRINCIPLES:
1. UNDERSTAND THE WHOLE MESSAGE:
   - Interpret the semantic meaning of the user's complete message.
   - Do NOT behave like a keyword matcher or regex classifier.
   - Understand the player's gameplay goal, context, and desired experience.

2. MULTI-TURN CONVERSATION & CONTEXT PRESERVATION:
   - When the user sends a follow-up message, evaluate it in the context of previous messages.
   - If the user modifies one aspect (e.g. "Actually make it drop gold instead of diamonds"),
     update that specific item while PRESERVING all other previously agreed requirements (e.g. zombie target, drop rate).
   - If the user confirms (e.g. "yes", "confirm", "looks good", "generate it"), set status to "confirmed".

3. INCOMPLETE REQUESTS & SENSIBLE DEFAULTS:
   - When a request is incomplete or vague (e.g. "make me faster" or "make a strong sword"), do NOT ask unnecessary questions.
   - Infer reasonable possibilities using Minecraft gameplay knowledge.
   - Propose sensible defaults (e.g. +50% movement speed attribute modifier, or Sharpness V with custom name).
   - Explicitly list your assumptions and explain your technical rationale in plain English.
   - Never silently treat an uncertain assumption as a confirmed requirement.

4. MATERIALLY DIVERGENT INTERPRETATIONS:
   - If a request has multiple materially divergent interpretations that cannot be defaulted
     (e.g. "make zombies drop something cool" could mean weapons, gems, or custom food),
     propose 2 to 4 focused, human-understandable choices in `open_choices` and set status to "needs_clarification".

5. UNSUPPORTED CAPABILITIES:
   - If a user asks for something fundamentally impossible with vanilla Minecraft datapacks
     (e.g. custom 3D entity models, client-side shaders, external audio streaming, modifying client UI/menus),
     set status to "unsupported" and explain the limitation politely in plain English in `unsupported_reason`.

6. OUTPUT CONTRACT:
   - Present the proposed behavior in clear, non-technical plain English.
   - Do NOT ask the user technical questions about commands, NBT, syntax, or predicates.
   - Ask the user to confirm or revise the proposal in `confirmation_prompt`.
   - Populate `raw_requirements` with structured semantic requirements for downstream planning.

Return ONLY a structured JSON response matching the required schema.
"""

    def process_turn(
        self,
        session: ConversationSession,
        user_message: str
    ) -> ProposedBehavior:
        """
        Processes a user message within the given conversation session,
        returning an updated ProposedBehavior.
        """
        user_clean = user_message.strip()
        session.add_user_message(user_clean)

        # 1. Quick check for explicit confirmation of an already complete and supported proposal
        if (
            session.current_proposal
            and session.current_proposal.is_complete
            and session.current_proposal.status != "unsupported"
            and not session.current_proposal.open_choices
        ):
            lower_msg = user_clean.lower().strip()
            confirm_starters = (
                "yes", "confirm", "looks good", "sounds good", "generate",
                "build it", "proceed", "go ahead", "perfect", "make it",
                "create it", "do it", "approved"
            )
            cleaned_lower = lower_msg.rstrip("!.,")
            is_confirm = any(cleaned_lower == s or cleaned_lower.startswith(f"{s},") or cleaned_lower.startswith(f"{s} ") for s in confirm_starters)
            is_negated = any(cleaned_lower.startswith(neg) for neg in ("no", "don't", "dont", "do not", "wait", "cancel", "stop", "change"))
            if is_confirm and not is_negated:
                confirmed_proposal = session.current_proposal.model_copy()
                confirmed_proposal.status = "confirmed"
                session.add_assistant_message(
                    content=f"Confirmed! Creating your datapack: {confirmed_proposal.summary}",
                    proposal=confirmed_proposal
                )
                session.confirm_proposal()
                return confirmed_proposal

        # 2. Build multi-turn prompt for the LLM
        history_text = session.get_formatted_history()
        target_version = session.minecraft_version or self.version

        user_prompt = f"""Target Minecraft Version: Java {target_version}

Conversation History:
{history_text}

Latest User Message:
"{user_clean}"

Analyze the complete request and conversational context. Formulate your plain-English proposal, assumptions, and structured requirements according to your system prompt instructions.
"""

        system_prompt = self._build_system_prompt(target_version)

        try:
            raw_response = self.ai.generate_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema=AgentTurnOutput.model_json_schema()
            )
            proposal = self._parse_agent_response(raw_response, user_clean)
        except Exception as e:
            logger.warning("Conversational LLM inference failed: %s. Formulating safe fallback proposal.", e)
            proposal = self._fallback_proposal(user_clean, target_version, error=str(e))

        # 3. Record turn in session
        session.add_assistant_message(
            content=proposal.summary,
            proposal=proposal
        )

        return proposal

    def _parse_agent_response(
        self,
        raw_response: Any,
        user_text: str
    ) -> ProposedBehavior:
        """Normalizes and validates the LLM structured output into a ProposedBehavior."""
        if isinstance(raw_response, str):
            try:
                raw_response = json.loads(raw_response)
            except Exception:
                raw_response = {"summary": raw_response}

        if not isinstance(raw_response, dict):
            raw_response = {"summary": str(raw_response)}

        summary = raw_response.get("summary") or f"Datapack for: {user_text}"
        trigger = raw_response.get("trigger_condition")
        target = raw_response.get("target_affected")
        mechs = raw_response.get("mechanisms_involved") or []
        if isinstance(mechs, str):
            mechs = [mechs]

        # Parse assumptions
        assumptions_list = []
        raw_assump = raw_response.get("assumptions") or []
        if isinstance(raw_assump, list):
            for a in raw_assump:
                if isinstance(a, dict):
                    desc = a.get("description", "")
                    rat = a.get("rationale", "")
                    def_app = a.get("default_applied", "")
                    if desc or def_app:
                        assumptions_list.append(
                            AssumptionItem(
                                description=desc or def_app,
                                rationale=rat or "Sensible Minecraft default",
                                default_applied=def_app or desc
                            )
                        )
                elif isinstance(a, str) and a.strip():
                    assumptions_list.append(
                        AssumptionItem(
                            description=a,
                            rationale="Inferred from gameplay context",
                            default_applied=a
                        )
                    )

        open_choices = raw_response.get("open_choices") or []
        if isinstance(open_choices, str):
            open_choices = [open_choices]

        status = raw_response.get("status", "proposed").lower()
        if open_choices and status != "confirmed":
            status = "needs_clarification"

        is_complete = bool(raw_response.get("is_complete", len(open_choices) == 0))
        confirm_prompt = raw_response.get(
            "confirmation_prompt",
            "Does this proposed behavior match what you want, or would you like to make any adjustments?"
        )
        unsupported_reason = raw_response.get("unsupported_reason")

        raw_reqs = raw_response.get("raw_requirements") or []
        if not raw_reqs:
            raw_reqs = [{
                "subject": target or "gameplay",
                "target": target,
                "intent": summary,
                "conditions": [trigger] if trigger else [],
                "constraints": []
            }]

        return ProposedBehavior(
            summary=summary,
            trigger_condition=trigger,
            target_affected=target,
            mechanisms_involved=mechs,
            assumptions=assumptions_list,
            open_choices=open_choices,
            status=status,
            is_complete=is_complete,
            confirmation_prompt=confirm_prompt,
            unsupported_reason=unsupported_reason,
            raw_requirements=raw_reqs
        )

    def _fallback_proposal(
        self,
        user_text: str,
        version: str,
        error: Optional[str] = None
    ) -> ProposedBehavior:
        """Safe fallback proposal if LLM call is interrupted."""
        return ProposedBehavior(
            summary=f"Create a custom datapack implementing: {user_text}",
            trigger_condition="As specified by user request",
            target_affected="Relevant Minecraft entities or players",
            mechanisms_involved=["function"],
            assumptions=[
                AssumptionItem(
                    description="Standard Minecraft behavior applied",
                    rationale=f"Inferred fallback for Java {version}",
                    default_applied="Default datapack execution"
                )
            ],
            open_choices=[],
            status="proposed",
            is_complete=True,
            confirmation_prompt="Does this match what you would like to generate?",
            raw_requirements=[{
                "subject": "gameplay",
                "intent": user_text,
                "conditions": [],
                "constraints": []
            }]
        )
