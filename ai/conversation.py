"""
ai/conversation.py - Conversational State & Turn Manager

Maintains multi-turn conversation sessions for natural-language datapack creation.
Tracks message histories, evolving behavioral proposals, plain-English assumptions,
sensible defaults, and user confirmation status.
"""
import threading
import time
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict


class ConversationMessage(BaseModel):
    """A single message in the conversation history."""
    model_config = ConfigDict(extra="allow")

    role: str = Field(..., description="'user', 'assistant', or 'system'")
    content: str = Field(..., description="Message text")
    timestamp: float = Field(default_factory=time.time)


class AssumptionItem(BaseModel):
    """An assumption made by the AI when details are incomplete, with its rationale."""
    model_config = ConfigDict(extra="allow")

    description: str = Field(..., description="Plain-English explanation of the assumed behavior")
    rationale: str = Field(..., description="Why this assumption or sensible default was chosen")
    default_applied: str = Field(..., description="The concrete default value or behavior applied")
    target_requirement_index: Optional[int] = Field(
        default=None,
        description="Explicit 0-based index of the requirement this assumption modifies, if known"
    )
    target_subject: Optional[str] = Field(
        default=None,
        description="Specific entity, item, or mechanism subject this assumption targets (e.g. 'zombie', 'skeleton')"
    )


class ProposedBehavior(BaseModel):
    """
    A concrete plain-English proposal of what the Minecraft datapack will do,
    presented to the user for review and confirmation before code generation.
    """
    model_config = ConfigDict(extra="allow")

    summary: str = Field(
        ...,
        description="Clear plain-English summary of what the player will experience in-game"
    )
    trigger_condition: Optional[str] = Field(
        default=None,
        description="When or how the behavior activates (e.g. 'When a zombie dies', 'Continuously while in the world')"
    )
    target_affected: Optional[str] = Field(
        default=None,
        description="Who or what is affected (e.g. 'The player executing the command', 'All creepers in the world')"
    )
    mechanisms_involved: List[str] = Field(
        default_factory=list,
        description="High-level Minecraft gameplay mechanisms involved (e.g. 'entity_loot', 'attribute', 'function')"
    )
    assumptions: List[AssumptionItem] = Field(
        default_factory=list,
        description="Assumptions or sensible defaults inferred by the AI with technical rationale"
    )
    open_choices: List[str] = Field(
        default_factory=list,
        description="Focused non-technical choices presented if multiple materially divergent paths exist"
    )
    status: str = Field(
        default="proposed",
        description="'proposed', 'needs_clarification', 'confirmed', or 'unsupported'"
    )
    is_complete: bool = Field(
        default=True,
        description="True if enough details exist to build upon user confirmation; False if waiting on choices"
    )
    confirmation_prompt: str = Field(
        default="Does this proposed behavior match what you want, or would you like to make any adjustments?",
        description="Plain-English question asking the user to confirm or revise"
    )
    unsupported_reason: Optional[str] = Field(
        default=None,
        description="If status is 'unsupported', plain-English explanation of why the request is beyond Minecraft capabilities"
    )
    raw_requirements: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Structured semantic requirements extracted for downstream planner"
    )


class ConversationTurn(BaseModel):
    """A complete interaction turn in the dialogue."""
    model_config = ConfigDict(extra="allow")

    turn_index: int
    user_message: str
    assistant_response: str
    proposed_behavior: ProposedBehavior
    created_at: float = Field(default_factory=time.time)


class ConversationSession(BaseModel):
    """A multi-turn conversation session tracking user interactions and evolving proposals."""
    model_config = ConfigDict(extra="allow")

    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    minecraft_version: str = Field(default="1.21.11")
    max_turns: int = Field(default=10, description="Maximum number of conversational turns to preserve in active history")
    total_turns: int = Field(default=0, description="Total lifetime turns recorded in this session")
    messages: List[ConversationMessage] = Field(default_factory=list)
    turns: List[ConversationTurn] = Field(default_factory=list)
    current_proposal: Optional[ProposedBehavior] = None
    confirmed_specification: Optional[Dict[str, Any]] = None
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    def trim_history(self) -> None:
        """
        Enforces a bounded conversation history by trimming complete conversational turns.
        Preserves:
        1. Turn 0 (Initial user goal / overarching request).
        2. The most recent (max_turns - 1) turns (active sliding window).
        3. Never mutates current_proposal, confirmed_specification, assumptions, or open_choices.
        4. Rebuilds messages to remain 100% consistent with the retained turns.
        """
        if len(self.turns) <= self.max_turns:
            return

        # Keep initial turn (index 0) + most recent (max_turns - 1) turns
        recent_count = max(1, self.max_turns - 1)
        initial_turn = self.turns[0]
        recent_turns = self.turns[-recent_count:]
        self.turns = [initial_turn] + recent_turns

        # Re-synchronize messages strictly to match the retained turns
        new_messages: List[ConversationMessage] = []
        for turn in self.turns:
            new_messages.append(ConversationMessage(role="user", content=turn.user_message))
            new_messages.append(ConversationMessage(role="assistant", content=turn.assistant_response))

        self.messages = new_messages

    def add_user_message(self, content: str) -> ConversationMessage:
        """Appends a user message to the session history and invalidates stale confirmations."""
        msg = ConversationMessage(role="user", content=content)
        self.messages.append(msg)
        # Requirement 5: Any new user message edits or continues dialogue, invalidating previous confirmation
        if self.confirmed_specification is not None:
            self.confirmed_specification = None
        if self.current_proposal and self.current_proposal.status == "confirmed":
            self.current_proposal.status = "proposed"
        self.updated_at = time.time()
        return msg

    def add_assistant_message(
        self,
        content: str,
        proposal: Optional[ProposedBehavior] = None
    ) -> ConversationMessage:
        """Appends an assistant message and updates the active proposal."""
        msg = ConversationMessage(role="assistant", content=content)
        self.messages.append(msg)
        if proposal is not None:
            self.current_proposal = proposal
            if proposal.status != "confirmed":
                self.confirmed_specification = None
            self.total_turns += 1
            turn = ConversationTurn(
                turn_index=self.total_turns,
                user_message=self.get_latest_user_message_text(),
                assistant_response=content,
                proposed_behavior=proposal
            )
            self.turns.append(turn)
            self.trim_history()
        self.updated_at = time.time()
        return msg

    def get_latest_user_message_text(self) -> str:
        """Returns the text of the most recent user message."""
        for msg in reversed(self.messages):
            if msg.role == "user":
                return msg.content
        return ""

    def confirm_proposal(self) -> Optional[Dict[str, Any]]:
        """Marks the active proposal as confirmed and locks the specification for compilation."""
        if not self.current_proposal or not self.current_proposal.is_complete:
            return None
        if self.current_proposal.status == "unsupported":
            return None
        if self.current_proposal.open_choices:
            return None

        self.current_proposal.status = "confirmed"
        self.confirmed_specification = {
            "summary": self.current_proposal.summary,
            "trigger_condition": self.current_proposal.trigger_condition,
            "target_affected": self.current_proposal.target_affected,
            "mechanisms_involved": self.current_proposal.mechanisms_involved,
            "assumptions": [a.model_dump() for a in self.current_proposal.assumptions],
            "raw_requirements": self.current_proposal.raw_requirements,
            "minecraft_version": self.minecraft_version,
            "confirmed_at": time.time(),
        }
        self.updated_at = time.time()
        return self.confirmed_specification

    def is_confirmed(self) -> bool:
        """Checks whether the user has confirmed the proposed behavior."""
        return bool(
            self.confirmed_specification is not None
            and self.current_proposal
            and self.current_proposal.status == "confirmed"
            and self.current_proposal.is_complete
            and not self.current_proposal.open_choices
        )

    def get_formatted_history(self) -> str:
        """
        Formats the conversation history for context injection into LLM prompts.
        Bounded by the retained turns and clearly annotates preserved baseline if older turns were trimmed.
        """
        lines = []
        has_pruned_turns = False
        if len(self.turns) > 1 and self.turns[1].turn_index > 2:
            has_pruned_turns = True

        for i, turn in enumerate(self.turns):
            if i == 0:
                lines.append(f"User [Initial Goal]: {turn.user_message}")
                lines.append(f"Assistant: {turn.assistant_response}")
                if has_pruned_turns:
                    baseline = self.current_proposal.summary if self.current_proposal else "Dialogue established"
                    lines.append(f"[Note: Intermediate turns compacted. Current agreed baseline: '{baseline}']")
            else:
                lines.append(f"User: {turn.user_message}")
                lines.append(f"Assistant: {turn.assistant_response}")

        if not self.turns:
            for msg in self.messages:
                speaker = "User" if msg.role == "user" else "Assistant"
                lines.append(f"{speaker}: {msg.content}")

        return "\n".join(lines)


class ConversationSessionManager:
    """Thread-safe in-memory session manager with automatic TTL expiration."""

    def __init__(self, ttl_seconds: int = 3600):
        self._sessions: Dict[str, ConversationSession] = {}
        self._lock = threading.Lock()
        self._ttl_seconds = ttl_seconds

    def create_session(self, version: str = "1.21.11", session_id: Optional[str] = None) -> ConversationSession:
        sid = session_id or str(uuid.uuid4())
        session = ConversationSession(session_id=sid, minecraft_version=version)
        with self._lock:
            self._sessions[sid] = session
        return session

    def get_session(self, session_id: str) -> Optional[ConversationSession]:
        with self._lock:
            session = self._sessions.get(session_id)
            if session and (time.time() - session.updated_at > self._ttl_seconds):
                del self._sessions[session_id]
                return None
            return session

    def get_or_create(self, session_id: Optional[str] = None, version: str = "1.21.11") -> ConversationSession:
        if session_id:
            existing = self.get_session(session_id)
            if existing:
                return existing
        return self.create_session(version=version, session_id=session_id)

    def cleanup_expired(self) -> int:
        now = time.time()
        expired = []
        with self._lock:
            for sid, s in self._sessions.items():
                if now - s.updated_at > self._ttl_seconds:
                    expired.append(sid)
            for sid in expired:
                del self._sessions[sid]
        return len(expired)

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            return bool(self._sessions.pop(session_id, None))


# Default global manager instance
DEFAULT_CONVERSATION_MANAGER = ConversationSessionManager()
