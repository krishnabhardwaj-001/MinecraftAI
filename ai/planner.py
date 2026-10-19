import json
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ai.provider import AIProvider
from ai.context import retrieve_minecraft_context
from ai.semantic_models import PropertyModification
from ai.numeric_interpreter import NumericSemanticInterpreter, extract_property_modifications
from ai.property_registry import DEFAULT_PROPERTY_REGISTRY, PropertyCapabilityRegistry
from ai.clarification import (
    ClarificationRequirement,
    DEFAULT_CLARIFICATION_ENGINE,
    SemanticClarificationEngine,
)
from ai.implementation_mapper import ImplementationMapper
from knowledge_retriever import MinecraftKnowledgeRetriever
from generator.models import (
    ActionSpecification,
    MechanismSpecification,
    validate_mechanism_specification,
)



class Mechanism(MechanismSpecification):
    """
    Subclass of MechanismSpecification for backward compatibility with existing Planner usages.
    """
    pass


class PlanStep(BaseModel):
    id: str
    action: str
    depends_on: List[str] = Field(default_factory=list)
    resources: List[str] = Field(default_factory=list)


class ImplementationPlan(BaseModel):
    requirement_index: int
    objective: str
    mechanisms: List[MechanismSpecification] = Field(default_factory=list)
    steps: List[PlanStep] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    missing_knowledge: List[str] = Field(default_factory=list)
    clarifications: List[str] = Field(default_factory=list)
    clarification_requirements: List[ClarificationRequirement] = Field(default_factory=list)
    property_modification: Optional[PropertyModification] = Field(
        default=None,
        description="Structured semantic property modification"
    )



class PlannerResult(BaseModel):
    status: str
    minecraft_version: str
    summary: str
    implementation_plan: List[ImplementationPlan] = Field(default_factory=list)
    missing_knowledge: List[str] = Field(default_factory=list)
    clarifications: List[str] = Field(default_factory=list)
    clarification_requirements: List[ClarificationRequirement] = Field(default_factory=list)


class MinecraftPlanner:
    def __init__(
        self,
        provider="ollama",
        version="1.21.11",
        ai_provider=None,
        property_registry=None,
        clarification_engine=None,
    ):
        self.version = version
        self.ai = ai_provider or AIProvider(provider=provider)
        self.property_registry = property_registry or DEFAULT_PROPERTY_REGISTRY
        self.clarification_engine = clarification_engine or DEFAULT_CLARIFICATION_ENGINE
        self.implementation_mapper = ImplementationMapper(registry=self.property_registry)

    def _schema(self) -> Dict[str, Any]:
        return PlannerResult.model_json_schema()

    def _system_prompt(self) -> str:
        return f"""
You are the PLANNING ENGINE of an automatic Minecraft datapack maker.

Target:
- Minecraft Java Edition
- Version {self.version}

Your job is to convert the already-understood Minecraft request into a
machine-readable implementation plan.

IMPORTANT ARCHITECTURE:

USER REQUEST
    ↓
UNDERSTANDING
    ↓
YOU ARE HERE: PLANNER
    ↓
DATAPACK GENERATOR
    ↓
VALIDATOR

You are NOT the final command generator.

You must decide how the user's requirements can be implemented in Minecraft,
but you must NOT write the final datapack files or pretend that unverified
Minecraft syntax is valid.

You receive:
1. The original understood request.
2. Structured requirements.
3. Retrieved Minecraft knowledge.

Use the retrieved Minecraft knowledge as your primary Minecraft-specific
reference.

RULES:

1. Preserve the user's intent exactly.
2. Do not invent user requirements.
3. Do not invent probabilities, quantities, durations, targets, exceptions,
   or conditions that the user did not specify.
4. Do not silently change one requirement into another.
5. If something important is genuinely missing, put it in
   "clarifications".
6. If something cannot be determined because Minecraft knowledge is missing,
   put it in "missing_knowledge".
7. Do not ask unnecessary clarification questions.
8. If the request is sufficiently clear, produce a plan.
9. Populate structured parameters in "mechanisms" rather than vague prose.
10. You do NOT write raw Minecraft commands or command syntax strings. Instead, populate structured 'actions' inside mechanisms (specifying action_type, target, item, effect, duration, amplifier, objective, etc.). For effect actions, 'duration' may be an integer number of seconds (e.g. 30), 'infinite' for continuous/permanent effects, or omitted/null for default. The deterministic generator synthesizes the exact Minecraft commands.
11. Do not output complete raw JSON files; the deterministic generator creates the actual datapack files from your structured mechanism specifications.
12. Do not include testing actions. Testing belongs to the Validator.
13. Do not claim that a Minecraft mechanism is valid unless the supplied
    knowledge supports it.
14. Preserve all requirements separately.
15. Each implementation-plan entry must correspond to one requirement.
16. Use requirement_index to connect a plan to the original requirement.
17. If a requirement needs several mechanisms, include all of them.
18. Explain why each mechanism is appropriate in its "description".
19. Keep implementation details useful for the future Generator.
20. Do not turn general Minecraft concepts into fake commands.
21. Low-level JSON syntax details (like pool condition format) are handled by the generator; if the required entity and item knowledge is present, mark the plan as 'ready' rather than 'missing_knowledge'.
22. For standard mob drop requests (e.g. 'Make every creeper drop diamonds'), default to adding the item drop to the mob loot table alongside default drops, with a default drop count of 1 when the quantity is not specified. Do not ask for clarification regarding drop count or keeping/replacing default drops unless the user explicitly mentions them.
23. For predicate requests, if the predicate condition type is available in retrieved knowledge (under 'predicates') or supported Minecraft conditions, populate the structured predicate mechanism with type 'predicate' and mark status as 'ready'.
24. For state-machine and event-trigger requests (e.g. 'whenever it rains', 'only once when X starts', 'when X begins', 'on state change'):
    - Use mechanism type 'state_machine' with 'objective', 'condition_predicate', 'state_scope' ('global' for environmental/world events like weather/time, or 'player' for individual player events), and 'on_enter' structured actions. For event triggers like 'whenever it rains' or 'whenever night falls', default to executing once when the event begins (state_machine on_enter) using a global state latch, avoiding continuous tick spamming or unnecessary clarification.
    - The deterministic generator automatically handles safe scoreboard initialization in load.mcfunction (using persistent '#global' for global state or dynamic tick initialization for players) and sets up the tick transition and reset logic.
25. For player-targeted actions, specify 'target': '@a' (or '@p' / '@s'). The generator automatically enforces correct execution context chaining ('execute as @a at @s run ...').
26. For scoreboard objective requests (creating objectives, tracking player statistics, configuring display slots):
    - Use mechanism type 'scoreboard_objective' with 'objective' (1-16 chars, alphanumeric/underscore/dot/dash/plus), 'criteria' (e.g. 'dummy', 'deathCount', 'playerKillCount', 'totalKillCount', 'health', 'trigger', 'xp', 'level', 'food', 'air', 'armor', or valid statistic criteria from retrieved knowledge), optional 'display_name', and optional 'display_slot' ('sidebar', 'list', 'below_name', 'sidebar.team.<color>').
    - Objective creation belongs in one-time initialization ('load.mcfunction'), which the generator handles deterministically when 'scoreboard_objective' is specified.
27. For score actions (modifying, setting, adding, subtracting, resetting, or operating on scores):
    - Do NOT output raw 'scoreboard players ...' command strings.
    - Instead, populate structured action objects inside 'actions' (for functions/load) or 'on_enter' (for state machines):
      * Set score: {{"action_type": "set_score", "target": "<holder>", "objective": "<obj>", "score_value": <int>}}
      * Add score: {{"action_type": "add_score", "target": "<holder>", "objective": "<obj>", "score_value": <int >= 0>}}
      * Remove score: {{"action_type": "remove_score", "target": "<holder>", "objective": "<obj>", "score_value": <int >= 0>}}
      * Reset score: {{"action_type": "reset_score", "target": "<holder>", "objective": "<obj optional>"}}
      * Operation score: {{"action_type": "operation_score", "target": "<holder>", "objective": "<obj>", "operation": "<op>", "source_holder": "<source_holder>", "source_objective": "<source_obj>"}}
        Supported operations: '=', '+=', '-=', '*=', '/=', '%=', '<', '>', '><'.
      Holders can be entity selectors ('@a', '@p', '@s') or named fake players (e.g. '#global', '#state', '#timer').
28. For score conditions (conditional execution based on score values or comparisons):
    - Use structured conditions inside action 'conditions':
      * Score range condition: {{"type": "score", "holder": "<holder>", "objective": "<obj>", "range": "<range>"}} (range can be an exact integer e.g. "10", a closed interval e.g. "1..10", or a half-open interval e.g. "5..", "..0")
      * Score comparison condition: {{"type": "score_compare", "target": "<target_holder>", "target_objective": "<obj>", "operator": "<op>", "source": "<source_holder>", "source_objective": "<source_obj>"}}
        Supported comparison operators: '<', '<=', '=', '>=', '>'.
29. Lifecycle Separation (Load vs Tick vs State Machine):
    - 'load' (one-time setup): Use 'scoreboard_objective' mechanism for objective registration, display slot configuration, initial score values, and one-time setup.
    - 'tick' / 'continuous_action': Use 'continuous_action' or 'function' on tick for continuous repeated score updates (e.g. incrementing a counter every tick).
    - 'state_machine': Use 'state_machine' for transition/edge-triggered requests (e.g. 'only once when rain starts', 'when night begins'). The generator automatically coordinates safe load initialization, tick transition latches, on_enter execution, and falling edge reset logic.
30. Scoreboard Ambiguity & Clarification:
    - If a scoreboard request lacks essential information needed for implementation, do NOT invent arbitrary numbers, objectives, or operations. Set status to 'needs_clarification' and populate 'clarifications':
      * Objective purpose/criteria is unclear (e.g. 'Create a scoreboard.' -> ask what should be tracked or what criteria is intended).
      * Score value is missing when required (e.g. 'Give me points.' -> ask how many points and which score/objective).
      * Target is ambiguous (e.g. 'Add 10 points.' -> ask who receives the points).
      * Comparison operands are missing (e.g. 'Compare the score.' -> ask which score/objective and against what).
      * Operation is ambiguous (e.g. 'Change score A using score B.' -> ask which operation: set, add, subtract, multiply, divide, modulo, min, max, swap).
      * Temporal behavior is unclear (e.g. 'Give me points when it rains.' -> ask whether once when rain starts or repeatedly while raining).
31. Property Modification & Semantic Requests (Step 17.3):
    - For property modification requests (e.g. modifying speed, attack damage, health, or entity attributes):
      * Use mechanism type 'property_modification' with 'property_modification' carrying the structured semantic model, or populate 'actions' with action_type 'modify_property' and 'implementation' ('attribute', 'effect', 'scoreboard').
      * Preserve the semantic representation (property, operation, value kind, value magnitude). Do NOT generate command syntax or calculate effect amplifiers (e.g. '10 times faster' stays value=10, NOT amplifier=9).
      * If the target property is missing (e.g. 'make the zombie stronger') or value is missing/ambiguous, set status to 'needs_clarification' and populate 'clarifications'.

STRUCTURED MECHANISM SPECIFICATIONS:
Each entry in "mechanisms" should specify a "type" and its structured parameters:

1. Loot Table Mechanism:
   - "type": "loot_table"
   - "target": path from knowledge (e.g. "entities/creeper.json" or "entities/zombie.json")
   - "item": valid item ID from knowledge (e.g. "minecraft:diamond")
   - "count": integer drop count (e.g. 1)
   - "operation": "add_pool"

2. Function Mechanism:
   - "type": "function"
   - "namespace": datapack namespace (e.g. "minecraft_ai")
   - "path": function path without extension (e.g. "speed", "tick", "join")
   - "actions": list of structured action objects:
     * Apply effect: {{"action_type": "apply_effect", "target": "@a", "effect": "minecraft:speed", "duration": 30, "amplifier": 0}} (duration can be integer seconds like 30, "infinite" for permanent effects, or omitted/null for default)
     * Give item: {{"action_type": "give_item", "target": "@a", "item": "minecraft:diamond", "count": 1}}
     * Set score: {{"action_type": "set_score", "target": "#global", "objective": "state", "score_value": 0}}
     * Add score: {{"action_type": "add_score", "target": "@a", "objective": "points", "score_value": 10}}
     * Remove score: {{"action_type": "remove_score", "target": "@p", "objective": "points", "score_value": 5}}
     * Reset score: {{"action_type": "reset_score", "target": "@a", "objective": "temp"}}
     * Score operation: {{"action_type": "operation_score", "target": "@s", "objective": "score_a", "operation": "*=", "source_holder": "@s", "source_objective": "score_b"}}
     * Conditional execution with score checks:
       Inside any action, add "conditions":
       - Range check: [{{"type": "score", "holder": "@s", "objective": "points", "range": "10.."}}]
       - Compare check: [{{"type": "score_compare", "target": "@s", "target_objective": "score_a", "operator": ">", "source": "@s", "source_objective": "score_b"}}]

3. Function Tag Mechanism:
   - "type": "function_tag"
   - "namespace": "minecraft"
   - "tag_name": tag identifier (e.g. "tick" or "load")
   - "values": list of function IDs (e.g. ["minecraft_ai:tick"])

4. Advancement Mechanism:
   - "type": "advancement"
   - "namespace": "minecraft_ai"
   - "path": advancement path (e.g. "kill_zombie")
   - "criteria": criteria triggers and conditions (e.g. {{"killed_zombie": {{"trigger": "minecraft:player_killed_entity", "conditions": {{"entity": {{"type": "minecraft:zombie"}}}}}}}})
   - "rewards": optional rewards (e.g. {{"experience": 100, "function": "minecraft_ai:reward"}})

5. Recipe Mechanism:
   - "type": "recipe"
   - "recipe_type": "crafting_shaped", "crafting_shapeless", "smelting", "blasting", "smoking", or "stonecutting"
   - "path": recipe file name without extension (e.g. "diamond_from_dirt")
   - "result_item": valid item ID from knowledge (e.g. "minecraft:diamond")
   - "result_count": integer count (e.g. 1)
   - "ingredients": list of ingredient item IDs for shapeless/smelting (e.g. ["minecraft:dirt"])
   - "pattern": list of row strings for shaped (e.g. ["X", "#"])
   - "key": dictionary mapping characters to item IDs for shaped (e.g. {{"#": "minecraft:stick", "X": "minecraft:diamond"}})

6. Predicate Mechanism:
   - "type": "predicate"
   - "namespace": datapack namespace (e.g. "minecraft_ai")
   - "path": predicate file name without extension (e.g. "is_raining", "is_sneaking", "lucky_chance")
   - "condition_type": predicate condition ID (e.g. "minecraft:weather_check", "minecraft:time_check", "minecraft:random_chance", "minecraft:entity_properties", "minecraft:match_tool", "minecraft:all_of", "minecraft:any_of", "minecraft:inverted")
   - "condition_params": dictionary of condition-specific parameters:
     * for "minecraft:weather_check": {{"raining": true}} or {{"thundering": true}}
     * for "minecraft:time_check": {{"value": {{"min": 13000, "max": 24000}}}} (or integer value)
     * for "minecraft:random_chance": {{"chance": 0.5}}
     * for "minecraft:entity_properties": {{"entity": "this", "predicate": {{"flags": {{"is_sneaking": true}}}}}}
     * for "minecraft:match_tool": {{"predicate": {{"items": ["minecraft:diamond_sword"]}}}}
   - "terms": list of nested mechanism dictionaries for composite "minecraft:all_of" or "minecraft:any_of"
   - "term": single nested mechanism dictionary for "minecraft:inverted"

7. State Machine Mechanism (for edge-triggered requests like 'only once when X starts', 'when X begins'):
   - "type": "state_machine"
   - "namespace": datapack namespace (e.g. "minecraft_ai")
   - "objective": scoreboard objective name (e.g. "rain_state", "time_state")
   - "condition_predicate": predicate identifier (e.g. "minecraft_ai:is_raining")
   - "state_scope": "global" (for weather/time/environment) or "player" (for individual player events)
   - "on_enter": list of structured action objects to execute when condition starts (e.g. [{{"action_type": "give_item", "target": "@a", "item": "minecraft:diamond", "count": 1}}])

8. Continuous Action Mechanism (for continuous looping actions):
   - "type": "continuous_action"
   - "trigger": "tick"
   - "actions": list of structured action objects to execute continuously every tick

9. Scoreboard Objective Mechanism (for objective creation, display slot configuration, and initial setup in load):
   - "type": "scoreboard_objective"
   - "objective": objective name (1-16 chars, e.g. "deaths", "kills", "points")
   - "criteria": criteria string (e.g. "dummy", "deathCount", "playerKillCount", "totalKillCount", "health", "trigger", "level", "food", "air", "armor")
   - "display_name": optional display name string or text component (e.g. "Deaths")
   - "display_slot": optional display slot ("sidebar", "list", "below_name", "sidebar.team.<color>")
   - "actions": optional list of structured initial score actions to run during load (e.g. [{{"action_type": "set_score", "target": "#global", "objective": "points", "score_value": 0}}])

10. Property Modification Mechanism:
   - "type": "property_modification"
   - "target": target entity or selector (e.g. "@a", "zombie")
   - "property_modification": semantic property modification object
   - "implementation": structural Minecraft category ("effect", "attribute", "scoreboard")
   - "actions": optional list of structured actions with action_type "modify_property"

OUTPUT:

Return ONLY the structured JSON matching the supplied schema.

The top-level structure MUST contain:

status
minecraft_version
summary
implementation_plan
missing_knowledge
clarifications

Do not add unrelated top-level fields.

Allowed status values:

"ready"
"needs_clarification"
"missing_knowledge"
"unsupported"

Use "ready" when the plan can proceed using the available knowledge.

Use "needs_clarification" only when an important user decision is actually
required.

Use "missing_knowledge" when the request is understandable but the Minecraft
knowledge needed for implementation is unavailable.

Use "unsupported" only when the requested behavior cannot reasonably be
implemented by the current Minecraft datapack system.

Remember:
You are a planner, not a command hallucination engine.
"""

    @classmethod
    def _trim_knowledge(cls, knowledge: Dict[str, Any], max_items: int = 5) -> Dict[str, Any]:
        """Trims retrieved knowledge dictionaries to top entries to avoid context overflow."""
        if not isinstance(knowledge, dict):
            return {}
        trimmed = {}
        for k, v in knowledge.items():
            if isinstance(v, list):
                trimmed[k] = v[:max_items]
            elif isinstance(v, dict):
                trimmed[k] = {
                    sub_k: sub_v[:max_items] if isinstance(sub_v, list) else sub_v
                    for sub_k, sub_v in list(v.items())[:max_items]
                }
            else:
                trimmed[k] = v
        return trimmed

    def _build_user_prompt(
        self,
        understanding: Dict[str, Any],
        context: Dict[str, Any]
    ) -> str:
        knowledge_trimmed = self._trim_knowledge(context.get("knowledge", {}))
        return f"""
Create an implementation plan for the following Minecraft request.

MINECRAFT:
{json.dumps(context.get("minecraft", {}), separators=(',', ': '))}

USER REQUEST:
{context.get("user_request", "")}

UNDERSTANDING:
{json.dumps(understanding, separators=(',', ': '))}

REQUIREMENTS:
{json.dumps(context.get("requirements", []), separators=(',', ': '))}

RETRIEVED MINECRAFT KNOWLEDGE:
{json.dumps(knowledge_trimmed, separators=(',', ': '))}

Create one implementation_plan entry for each requirement.

Do not generate final commands.

Do not generate final datapack files.

Do not invent missing Minecraft syntax.

If the retrieved knowledge is insufficient for an implementation detail,
explicitly report that in missing_knowledge.

If the user's request itself is ambiguous in a way that requires a decision,
put the issue in clarifications.

Return only JSON matching the required schema.
"""

    def _normalize_result(
        self,
        result: Dict[str, Any],
        understanding: Dict[str, Any]
    ) -> Dict[str, Any]:

        if not isinstance(result, dict):
            raise ValueError("Planner returned an invalid response.")

        # ---------------------------------------------------------
        # Basic fields
        # ---------------------------------------------------------

        status = result.get("status")

        if not status:
            status = "ready"

        allowed_statuses = {
            "ready",
            "needs_clarification",
            "missing_knowledge",
            "unsupported"
        }

        if status not in allowed_statuses:
            status = "ready"

        result["status"] = status

        result["minecraft_version"] = result.get(
            "minecraft_version",
            self.version
        )

        if not result.get("summary"):
            result["summary"] = understanding.get(
                "understood_request",
                ""
            )

        # ---------------------------------------------------------
        # Missing knowledge
        # ---------------------------------------------------------

        missing = result.get("missing_knowledge", [])

        if missing is None:
            missing = []

        if isinstance(missing, str):
            missing = [missing]

        if not isinstance(missing, list):
            missing = [missing]

        normalized_missing = []

        for item in missing:
            if isinstance(item, str):
                normalized_missing.append(item)

            elif isinstance(item, dict):
                aspect = item.get("aspect")
                description = item.get("description")
                reason = item.get("reason")

                if description:
                    normalized_missing.append(str(description))
                elif reason:
                    normalized_missing.append(str(reason))
                elif aspect:
                    normalized_missing.append(str(aspect))
                else:
                    normalized_missing.append(
                        json.dumps(item, ensure_ascii=False)
                    )

            else:
                normalized_missing.append(str(item))

        result["missing_knowledge"] = normalized_missing
        # ---------------------------------------------------------
        # Clarifications
        # ---------------------------------------------------------

        clarifications = result.get("clarifications")

        # Some models call this "ambiguities".
        # We normalize the field name without changing the meaning.
        if clarifications is None:
            ambiguities = result.get("ambiguities", [])

            if isinstance(ambiguities, list):
                normalized_clarifications = []

                for item in ambiguities:
                    if isinstance(item, str):
                        normalized_clarifications.append(item)

                    elif isinstance(item, dict):
                        description = item.get("description")
                        question = item.get("question")

                        if question:
                            normalized_clarifications.append(
                                str(question)
                            )
                        elif description:
                            normalized_clarifications.append(
                                str(description)
                            )

                clarifications = normalized_clarifications
            else:
                clarifications = []

        if isinstance(clarifications, str):
            clarifications = [clarifications]

        if not isinstance(clarifications, list):
            clarifications = [clarifications]

        normalized_clarifications = []

        for item in clarifications:
            if isinstance(item, str):
                normalized_clarifications.append(item)

            elif isinstance(item, dict):
                question = item.get("question")
                description = item.get("description")
                reason = item.get("reason")

                if question:
                    normalized_clarifications.append(str(question))
                elif description:
                    normalized_clarifications.append(str(description))
                elif reason:
                    normalized_clarifications.append(str(reason))
                else:
                    normalized_clarifications.append(
                        json.dumps(item, ensure_ascii=False)
                    )

            else:
                normalized_clarifications.append(str(item))

        result["clarifications"] = normalized_clarifications
        if normalized_clarifications:
            result["status"] = "needs_clarification"

        # ---------------------------------------------------------
        # Implementation plan
        # ---------------------------------------------------------

        implementation_plan = result.get("implementation_plan")

        if implementation_plan is None:
            implementation_plan = []

        if not isinstance(implementation_plan, list):
            implementation_plan = [implementation_plan]

        normalized_plan = []

        for index, plan in enumerate(implementation_plan):

            if not isinstance(plan, dict):
                continue

            requirement_index = plan.get(
                "requirement_index",
                index
            )

            try:
                requirement_index = int(requirement_index)
            except (TypeError, ValueError):
                requirement_index = index

            objective = plan.get(
                "objective",
                ""
            )

            if not objective:
                requirements = understanding.get(
                    "requirements",
                    []
                )

                if (
                    isinstance(requirements, list)
                    and requirement_index < len(requirements)
                    and isinstance(
                        requirements[requirement_index],
                        dict
                    )
                ):
                    objective = requirements[
                        requirement_index
                    ].get(
                        "description",
                        requirements[
                            requirement_index
                        ].get(
                            "intent",
                            ""
                        )
                    )

            # -----------------------------------------------------
            # Mechanisms
            # -----------------------------------------------------

            mechanisms = plan.get(
                "mechanisms",
                []
            )

            if mechanisms is None:
                mechanisms = []

            if isinstance(mechanisms, dict):
                mechanisms = [mechanisms]

            normalized_mechanisms = []

            for mechanism in mechanisms:

                if isinstance(mechanism, str):
                    normalized_mechanisms.append({
                        "type": "function",
                        "description": mechanism,
                        "commands": [mechanism.lstrip("/")]
                    })

                elif isinstance(mechanism, dict):
                    mech_dict = dict(mechanism)
                    mech_type = str(mech_dict.get("type", "generic")).strip().lower()

                    # Clean up common type variations
                    if mech_type in ["loot_table_override", "loot_table_modification", "drop", "loot"]:
                        mech_type = "loot_table"
                    elif mech_type in ["mcfunction", "command", "function_command"]:
                        mech_type = "function"
                    elif mech_type in ["tag", "tick_tag", "load_tag"]:
                        mech_type = "function_tag"
                    elif mech_type in ["trigger"]:
                        mech_type = "advancement"
                    elif mech_type in ["crafting", "crafting_shaped", "crafting_shapeless", "smelting", "blasting", "smoking", "recipe_modification"]:
                        mech_type = "recipe"
                    elif mech_type in ["predicates", "custom_predicate", "predicate_condition"]:
                        mech_type = "predicate"
                    elif mech_type in ["state_machine", "event_latch", "event_trigger"]:
                        mech_type = "state_machine"
                    elif mech_type in ["continuous_action", "tick_action"]:
                        mech_type = "continuous_action"
                    elif mech_type in ["scoreboard", "scoreboard_objective", "objective", "scoreboards"]:
                        mech_type = "scoreboard_objective"
                    elif mech_type in ["property_modification", "modify_property"]:
                        mech_type = "property_modification"
                    mech_dict["type"] = mech_type

                    if mech_dict.get("property_modification"):
                        pm = mech_dict["property_modification"]
                        if isinstance(pm, PropertyModification):
                            mech_dict["property_modification"] = pm.model_dump()
                    if mech_dict.get("implementation"):
                        mech_dict["implementation"] = str(mech_dict["implementation"]).strip().lower()

                    # Helper to normalize action dictionaries
                    def _norm_action(act: Any) -> Dict[str, Any]:
                        if isinstance(act, dict):
                            ad = dict(act)
                            a_type = str(ad.get("action_type", "apply_effect")).strip().lower()

                            # Clean up action type variations
                            if a_type in ["score_set", "setscore"]:
                                a_type = "set_score"
                            elif a_type in ["score_add", "addscore"]:
                                a_type = "add_score"
                            elif a_type in ["score_remove", "removescore", "subtract_score"]:
                                a_type = "remove_score"
                            elif a_type in ["score_reset", "resetscore"]:
                                a_type = "reset_score"
                            elif a_type in ["score_operation", "operationscore", "score_op", "operation"]:
                                a_type = "operation_score"
                            elif a_type in ["modify_property", "property_modification"]:
                                a_type = "modify_property"
                            ad["action_type"] = a_type

                            if ad.get("property_modification"):
                                pm = ad["property_modification"]
                                if isinstance(pm, PropertyModification):
                                    ad["property_modification"] = pm.model_dump()
                            if ad.get("implementation"):
                                ad["implementation"] = str(ad["implementation"]).strip().lower()

                            if ad.get("item"):
                                iv = str(ad["item"]).strip()
                                if not iv.startswith("minecraft:") and ":" not in iv:
                                    iv = f"minecraft:{iv}"
                                ad["item"] = iv
                            if ad.get("effect"):
                                ev = str(ad["effect"]).strip()
                                if not ev.startswith("minecraft:") and ":" not in ev:
                                    ev = f"minecraft:{ev}"
                                ad["effect"] = ev

                            # Score action holder/target synchronization
                            is_score_action = a_type in [
                                "set_score", "add_score", "remove_score",
                                "reset_score", "operation_score"
                            ]
                            if is_score_action:
                                # sync score_holder and target
                                if not ad.get("target") and ad.get("score_holder"):
                                    ad["target"] = str(ad["score_holder"]).strip()
                                elif not ad.get("score_holder") and ad.get("target"):
                                    ad["score_holder"] = str(ad["target"]).strip()
                                elif not ad.get("target") and not ad.get("score_holder"):
                                    ad["target"] = "@s"
                                    ad["score_holder"] = "@s"

                                # Coerce score_value if string
                                if "score_value" in ad and ad["score_value"] is not None:
                                    sv = ad["score_value"]
                                    if isinstance(sv, str) and sv.strip().lstrip("-").isdigit():
                                        try:
                                            ad["score_value"] = int(sv.strip())
                                        except (ValueError, TypeError):
                                            pass

                                # Clean operation
                                if ad.get("operation"):
                                    ad["operation"] = str(ad["operation"]).strip()
                                if ad.get("source_holder"):
                                    ad["source_holder"] = str(ad["source_holder"]).strip()
                                if ad.get("source_objective"):
                                    ad["source_objective"] = str(ad["source_objective"]).strip()
                                if ad.get("objective"):
                                    ad["objective"] = str(ad["objective"]).strip()

                            else:
                                if not ad.get("target"):
                                    ad["target"] = "@a"

                            # Normalize conditions
                            raw_conds = ad.get("conditions")
                            if raw_conds is not None:
                                if isinstance(raw_conds, dict):
                                    raw_conds = [raw_conds]
                                if isinstance(raw_conds, list):
                                    norm_conds = []
                                    for c in raw_conds:
                                        if isinstance(c, dict):
                                            cd = dict(c)
                                            c_type = str(cd.get("type", "")).strip().lower()
                                            if c_type in ["score_compare", "compare_score"]:
                                                cd["type"] = "score_compare"
                                                if cd.get("operator"):
                                                    cd["operator"] = str(cd["operator"]).strip()
                                                if cd.get("target"):
                                                    cd["target"] = str(cd["target"]).strip()
                                                if cd.get("source"):
                                                    cd["source"] = str(cd["source"]).strip()
                                                if cd.get("target_objective"):
                                                    cd["target_objective"] = str(cd["target_objective"]).strip()
                                                if cd.get("source_objective"):
                                                    cd["source_objective"] = str(cd["source_objective"]).strip()
                                            elif c_type in ["score", "score_range"]:
                                                cd["type"] = "score"
                                                if cd.get("objective"):
                                                    cd["objective"] = str(cd["objective"]).strip()
                                                if cd.get("holder"):
                                                    cd["holder"] = str(cd["holder"]).strip()
                                                elif cd.get("target"):
                                                    cd["holder"] = str(cd["target"]).strip()
                                                if "range" in cd and cd["range"] is not None:
                                                    cd["range"] = str(cd["range"]).strip()
                                            norm_conds.append(cd)
                                    ad["conditions"] = norm_conds

                            return ad
                        elif isinstance(act, str):
                            return {
                                "action_type": "raw_command",
                                "raw_command": act.lstrip("/")
                            }
                        return {}

                    # Normalize structured actions
                    raw_actions = mech_dict.get("actions")
                    if raw_actions is not None:
                        if isinstance(raw_actions, dict):
                            raw_actions = [raw_actions]
                        if isinstance(raw_actions, list):
                            mech_dict["actions"] = [_norm_action(a) for a in raw_actions if _norm_action(a)]

                    raw_on_enter = mech_dict.get("on_enter")
                    if raw_on_enter is not None:
                        if isinstance(raw_on_enter, dict):
                            raw_on_enter = [raw_on_enter]
                        if isinstance(raw_on_enter, list):
                            mech_dict["on_enter"] = [_norm_action(a) for a in raw_on_enter if _norm_action(a)]

                    raw_on_exit = mech_dict.get("on_exit")
                    if raw_on_exit is not None:
                        if isinstance(raw_on_exit, dict):
                            raw_on_exit = [raw_on_exit]
                        if isinstance(raw_on_exit, list):
                            mech_dict["on_exit"] = [_norm_action(a) for a in raw_on_exit if _norm_action(a)]

                    # Normalize state_machine condition_predicate
                    raw_sm_pred = mech_dict.get("condition_predicate") or mech_dict.get("predicate")
                    if raw_sm_pred and isinstance(raw_sm_pred, str):
                        raw_sm_pred = raw_sm_pred.strip()
                        if not raw_sm_pred.startswith("minecraft:") and not raw_sm_pred.startswith("minecraft_ai:") and ":" not in raw_sm_pred:
                            raw_sm_pred = f"minecraft_ai:{raw_sm_pred}"
                        mech_dict["condition_predicate"] = raw_sm_pred

                    # Normalize predicate condition_type
                    raw_cond_type = mech_dict.get("condition_type")
                    if raw_cond_type and isinstance(raw_cond_type, str):
                        raw_cond_type = raw_cond_type.strip()
                        if not raw_cond_type.startswith("minecraft:") and ":" not in raw_cond_type:
                            raw_cond_type = f"minecraft:{raw_cond_type}"
                        mech_dict["condition_type"] = raw_cond_type

                    # Normalize commands (strip leading slash, ensure list of strings)
                    raw_cmds = mech_dict.get("commands")
                    if raw_cmds is not None:
                        if isinstance(raw_cmds, str):
                            raw_cmds = [raw_cmds]
                        if isinstance(raw_cmds, list):
                            clean_cmds = []
                            for c in raw_cmds:
                                c_str = str(c).strip()
                                if c_str.startswith("/"):
                                    c_str = c_str[1:]
                                if c_str:
                                    clean_cmds.append(c_str)
                            mech_dict["commands"] = clean_cmds

                    # Normalize item identifier (prefix minecraft: if bare item name)
                    raw_item = mech_dict.get("item")
                    if raw_item and isinstance(raw_item, str):
                        raw_item = raw_item.strip()
                        if not raw_item.startswith("minecraft:") and ":" not in raw_item:
                            raw_item = f"minecraft:{raw_item}"
                        mech_dict["item"] = raw_item

                    # Normalize count (coerce to int if int-like string)
                    raw_count = mech_dict.get("count")
                    if raw_count is not None and not isinstance(raw_count, dict):
                        try:
                            mech_dict["count"] = int(raw_count)
                        except (ValueError, TypeError):
                            pass

                    # Normalize values for function tags
                    raw_vals = mech_dict.get("values")
                    if raw_vals is not None:
                        if isinstance(raw_vals, str):
                            raw_vals = [raw_vals]
                        if isinstance(raw_vals, list):
                            mech_dict["values"] = [str(v).strip() for v in raw_vals if str(v).strip()]

                    # Normalize recipe result_item and ingredients
                    raw_res_item = mech_dict.get("result_item") or mech_dict.get("item")
                    if raw_res_item and isinstance(raw_res_item, str):
                        raw_res_item = raw_res_item.strip()
                        if not raw_res_item.startswith("minecraft:") and ":" not in raw_res_item:
                            raw_res_item = f"minecraft:{raw_res_item}"
                        mech_dict["result_item"] = raw_res_item

                    raw_ingredients = mech_dict.get("ingredients")
                    if raw_ingredients is not None:
                        if isinstance(raw_ingredients, str):
                            raw_ingredients = [raw_ingredients]
                        if isinstance(raw_ingredients, list):
                            clean_ings = []
                            for ing in raw_ingredients:
                                ing_str = str(ing).strip()
                                if ing_str and not ing_str.startswith("#") and not ing_str.startswith("minecraft:") and ":" not in ing_str:
                                    ing_str = f"minecraft:{ing_str}"
                                if ing_str:
                                    clean_ings.append(ing_str)
                            mech_dict["ingredients"] = clean_ings

                    raw_key = mech_dict.get("key")
                    if raw_key and isinstance(raw_key, dict):
                        clean_key = {}
                        for sym, k_val in raw_key.items():
                            k_str = str(k_val).strip()
                            if k_str and not k_str.startswith("#") and not k_str.startswith("minecraft:") and ":" not in k_str:
                                k_str = f"minecraft:{k_str}"
                            clean_key[str(sym)] = k_str
                        mech_dict["key"] = clean_key

                    # Normalize scoreboard_objective fields
                    if mech_type == "scoreboard_objective":
                        raw_obj = mech_dict.get("objective") or mech_dict.get("path") or mech_dict.get("target") or mech_dict.get("name")
                        if raw_obj:
                            mech_dict["objective"] = str(raw_obj).strip()
                        raw_crit = mech_dict.get("criteria")
                        if not raw_crit or not str(raw_crit).strip():
                            mech_dict["criteria"] = "dummy"
                        else:
                            mech_dict["criteria"] = str(raw_crit).strip()
                        if mech_dict.get("display_slot"):
                            mech_dict["display_slot"] = str(mech_dict["display_slot"]).strip().lower()

                    # Create and validate MechanismSpecification
                    try:
                        spec = MechanismSpecification(**mech_dict)
                        normalized_mechanisms.append(spec.model_dump(exclude_unset=False))
                    except Exception:
                        normalized_mechanisms.append(mech_dict)

            # -----------------------------------------------------
            # Steps
            # -----------------------------------------------------

            steps = plan.get(
                "steps",
                []
            )

            if steps is None:
                steps = []

            if isinstance(steps, dict):
                steps = [steps]

            normalized_steps = []

            for step_index, step in enumerate(steps):

                if isinstance(step, str):
                    normalized_steps.append({
                        "id": f"step_{step_index + 1}",
                        "action": step,
                        "depends_on": [],
                        "resources": []
                    })

                elif isinstance(step, dict):

                    step_id = step.get(
                        "id",
                        f"step_{step_index + 1}"
                    )

                    action = step.get(
                        "action",
                        ""
                    )

                    depends_on = step.get(
                        "depends_on",
                        []
                    )

                    resources = step.get(
                        "resources",
                        []
                    )

                    if isinstance(depends_on, str):
                        depends_on = [depends_on]

                    if not isinstance(depends_on, list):
                        depends_on = [str(depends_on)]

                    if isinstance(resources, str):
                        resources = [resources]

                    if not isinstance(resources, list):
                        resources = [str(resources)]

                    normalized_steps.append({
                        "id": str(step_id),
                        "action": str(action),
                        "depends_on": [
                            str(x) for x in depends_on
                        ],
                        "resources": [
                            str(x) for x in resources
                        ]
                    })

            # -----------------------------------------------------
            # Constraints
            # -----------------------------------------------------

            constraints = plan.get(
                "constraints",
                []
            )

            if constraints is None:
                constraints = []

            if isinstance(constraints, str):
                constraints = [constraints]

            if not isinstance(constraints, list):
                constraints = [str(constraints)]

            normalized_constraints = []

            for constraint in constraints:

                if isinstance(constraint, str):
                    normalized_constraints.append(
                        constraint
                    )

                elif isinstance(constraint, dict):
                    description = constraint.get(
                        "description"
                    )

                    if description:
                        normalized_constraints.append(
                            str(description)
                        )

            # -----------------------------------------------------
            # Plan-level missing knowledge
            # -----------------------------------------------------

            plan_missing = plan.get(
                "missing_knowledge",
                []
            )

            if plan_missing is None:
                plan_missing = []

            if isinstance(plan_missing, str):
                plan_missing = [plan_missing]

            if not isinstance(plan_missing, list):
                plan_missing = [str(plan_missing)]

            plan_entry = {
                "requirement_index": requirement_index,
                "objective": str(objective),
                "mechanisms": normalized_mechanisms,
                "steps": normalized_steps,
                "constraints": normalized_constraints,
                "missing_knowledge": [
                    str(x) for x in plan_missing
                ]
            }
            if plan.get("property_modification"):
                pm = plan["property_modification"]
                if isinstance(pm, dict):
                    plan_entry["property_modification"] = pm
                elif isinstance(pm, PropertyModification):
                    plan_entry["property_modification"] = pm.model_dump()
            if plan.get("clarifications"):
                plan_entry["clarifications"] = plan["clarifications"]
            if plan.get("clarification_requirements"):
                plan_entry["clarification_requirements"] = plan["clarification_requirements"]

            normalized_plan.append(plan_entry)

        result["implementation_plan"] = normalized_plan

        if "clarification_requirements" not in result:
            result["clarification_requirements"] = []

        return result

    def plan_property_modification(
        self,
        mod: PropertyModification,
        requirement_index: int = 0,
        default_target: Optional[str] = None,
    ) -> ImplementationPlan:
        """
        Converts a PropertyModification semantic contract into a structured ImplementationPlan
        preserving all semantic details without command generation or amplifier calculations.
        Delegates clarification analysis and question generation to SemanticClarificationEngine.
        """
        extra_meta = getattr(mod, "extra_metadata", None) or {}
        raw_target = (
            (extra_meta.get("target") if isinstance(extra_meta, dict) else None)
            or default_target
            or "@a"
        )
        if raw_target in ("player", "me", "my"):
            target = "@a"
        else:
            target = raw_target

        explicit_step_id = (
            extra_meta.get("step_id")
            or extra_meta.get("action_id")
            if isinstance(extra_meta, dict) else None
        )
        step_id = explicit_step_id or f"step_{requirement_index}"

        # 1. Delegate clarification analysis to the clarification engine
        clarification_req = self.clarification_engine.analyze_modification(
            mod, registry=self.property_registry
        )

        if clarification_req is not None:
            is_unknown = (
                clarification_req.metadata.get("unknown", False)
                or clarification_req.metadata.get("issue_type") == "unknown_property"
            )
            missing_know = [mod.property] if (is_unknown and mod.property) else []
            return ImplementationPlan(
                requirement_index=requirement_index,
                objective=f"Modify {mod.property or 'property'} for {target} ({clarification_req.reason})",
                mechanisms=[
                    MechanismSpecification(
                        type="property_modification",
                        target=target,
                        property_modification=mod,
                        implementation=None,
                        description=f"Unresolved semantic modification: {clarification_req.reason}",
                    )
                ],
                property_modification=mod,
                constraints=[],
                missing_knowledge=missing_know,
                clarifications=[clarification_req.question],
                clarification_requirements=[clarification_req],
            )

        # 2. Delegate deterministic implementation mapping to ImplementationMapper
        mapping = self.implementation_mapper.map_modification(
            mod,
            default_target=target,
            registry=self.property_registry,
            step_id=step_id,
        )

        if mapping.status != "ready":
            return ImplementationPlan(
                requirement_index=requirement_index,
                objective=f"Modify {mod.property or 'property'} for {mapping.target} ({mapping.reason})",
                mechanisms=[
                    MechanismSpecification(
                        type="property_modification",
                        target=mapping.target,
                        property_modification=mod,
                        implementation=None,
                        description=f"Unresolved semantic modification: {mapping.reason}",
                    )
                ],
                property_modification=mod,
                constraints=[],
                missing_knowledge=mapping.missing_knowledge,
                clarifications=[mapping.reason] if mapping.reason else [],
                clarification_requirements=[],
            )

        is_qualitative = mod.value is not None and getattr(mod.value, "kind", None) == "qualitative"
        obj_action = mod.operation if mod.operation else (f"qualitative ({mod.value.value})" if is_qualitative else "modify")
        return ImplementationPlan(
            requirement_index=requirement_index,
            objective=f"Apply {obj_action} {mod.property} on {mapping.target}",
            mechanisms=[mapping.mechanism_spec],
            steps=[PlanStep(id=f"step_{requirement_index}", action=f"modify_{mod.property}")],
            constraints=[],
            missing_knowledge=[],
            property_modification=mod,
            clarifications=[],
            clarification_requirements=[],
        )

    def plan(
        self,
        understanding: Dict[str, Any],
        property_modifications: Optional[List[PropertyModification]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:

        if not isinstance(understanding, dict):
            raise ValueError(
                "Understanding must be a dictionary."
            )

        # Early exit if understanding already halted at clarification
        if understanding.get("status") == "needs_clarification":
            clar_text = ""
            if isinstance(understanding.get("clarification"), dict):
                clar_text = understanding["clarification"].get("question", "")
            elif isinstance(understanding.get("clarification"), str):
                clar_text = understanding["clarification"]
            clars = understanding.get("clarifications") or ([clar_text] if clar_text else ["Clarification requested."])
            if isinstance(clars, str):
                clars = [clars]
            return {
                "status": "needs_clarification",
                "minecraft_version": self.version,
                "summary": understanding.get("understood_request", ""),
                "implementation_plan": [],
                "missing_knowledge": [],
                "clarifications": [str(c) for c in clars],
            }

        # Step 17.3: Check for semantic property modifications
        mods: List[PropertyModification] = []
        if property_modifications:
            mods = list(property_modifications)
        elif "property_modifications" in understanding and understanding["property_modifications"]:
            for item in understanding["property_modifications"]:
                if isinstance(item, PropertyModification):
                    mods.append(item)
                elif isinstance(item, dict):
                    mods.append(PropertyModification(**item))
        else:
            # Check requirements
            for req in understanding.get("requirements", []):
                if isinstance(req, dict):
                    if "property_modification" in req and req["property_modification"]:
                        pm = req["property_modification"]
                        if isinstance(pm, PropertyModification):
                            mods.append(pm)
                        elif isinstance(pm, dict):
                            mods.append(PropertyModification(**pm))
                    elif req.get("intent") in ("modify_property", "property_modification") or "property" in req:
                        try:
                            val_obj = None
                            if "value" in req and req["value"] is not None:
                                val_kind = req.get("value_kind", "absolute")
                                val_obj = SemanticNumericValue(kind=val_kind, value=req["value"])
                            extra = {}
                            if "target" in req and req["target"]:
                                extra["target"] = req["target"]
                            mods.append(
                                PropertyModification(
                                    property=req.get("property"),
                                    operation=req.get("operation"),
                                    value=val_obj,
                                    missing=req.get("missing", []),
                                    extra_metadata=extra
                                )
                            )
                        except Exception:
                            pass

            # If still not found, check if understood_request contains property modifications
            if not mods:
                req_text = understanding.get("understood_request", "")
                if req_text:
                    try:
                        extracted = extract_property_modifications(req_text)
                        # Filter out any incomplete heuristic extractions that have no operation and no value
                        valid_extracted = [
                            m for m in extracted
                            if m.operation is not None or m.value is not None or m.extra_metadata.get("ambiguous")
                        ]
                        if valid_extracted:
                            # Check if existing requirements already define broader gameplay
                            has_structured_reqs = any(
                                isinstance(r, dict) and r.get("intent") and r.get("intent") not in ("modify_property", "property_modification")
                                for r in understanding.get("requirements", [])
                            )
                            # If existing structured requirements exist, only adopt complete modifications
                            if has_structured_reqs:
                                complete_extracted = [
                                    m for m in valid_extracted
                                    if not m.missing and m.operation is not None and m.value is not None
                                ]
                                if complete_extracted:
                                    mods.extend(complete_extracted)
                            else:
                                mods.extend(valid_extracted)
                    except Exception:
                        pass

        if mods:
            req_text = understanding.get("understood_request", "")
            other_requirements: List[str] = []
            if req_text:
                try:
                    compound_res = NumericSemanticInterpreter().interpret_compound(req_text)
                    other_requirements = compound_res.get("other_requirements", [])
                except Exception:
                    pass

            retriever = MinecraftKnowledgeRetriever(version=self.version)
            plans: List[ImplementationPlan] = []
            clarifications: List[str] = []
            structured_clarifications: List[ClarificationRequirement] = []
            status = "ready"

            for idx, mod in enumerate(mods):
                ip = self.plan_property_modification(mod, requirement_index=idx)
                plans.append(ip)

                if ip.clarification_requirements or ip.clarifications:
                    status = "needs_clarification"
                    for cr in ip.clarification_requirements:
                        if cr not in structured_clarifications:
                            structured_clarifications.append(cr)
                        if cr.question not in clarifications:
                            clarifications.append(cr.question)
                    for c in ip.clarifications:
                        if c not in clarifications:
                            clarifications.append(c)

            # Handle non-property requirements from compound requests generically via Minecraft knowledge
            for other_idx, other_req in enumerate(other_requirements, start=len(plans)):
                clean_req = other_req.strip().lower()
                other_actions: List[ActionSpecification] = []
                missing_knowledge_items: List[str] = []

                # Query generic Minecraft knowledge for relevant items, entities, commands
                retrieval = retriever.search(clean_req)
                items = retrieval.get("items", [])
                entities = retrieval.get("entities", [])

                # Determine target if mentioned
                req_target = "@a"
                if "me" in clean_req or "player" in clean_req or "@a" in clean_req:
                    req_target = "@a"

                # 1. Check for summon / spawn entity intent
                if re.search(r"\b(?:summon|spawn|create)\b", clean_req):
                    if entities:
                        top_entity = entities[0]["id"]
                        other_actions.append(
                            ActionSpecification(
                                action_type="summon_entity",
                                target=req_target,
                                entity=top_entity,
                            )
                        )
                    else:
                        missing_knowledge_items.append(f"entity for '{other_req}'")

                # 2. Check for give / grant item intent (or items retrieved)
                elif re.search(r"\b(?:give|get|grant|receive|drop|take|holding)\b", clean_req) or items:
                    if items:
                        top_item = items[0]["id"]
                        count = 1
                        m_count = re.search(r"\b(\d+)\b", clean_req)
                        if m_count:
                            try:
                                count = max(1, int(m_count.group(1)))
                            except (ValueError, TypeError):
                                count = 1
                        other_actions.append(
                            ActionSpecification(
                                action_type="give_item",
                                target=req_target,
                                item=top_item,
                                count=count,
                            )
                        )
                    else:
                        missing_knowledge_items.append(f"item for '{other_req}'")

                # 3. Fallback: if entities matched
                elif entities:
                    other_actions.append(
                        ActionSpecification(
                            action_type="summon_entity",
                            target=req_target,
                            entity=entities[0]["id"],
                        )
                    )

                mech = MechanismSpecification(
                    type="function",
                    path=f"action_{other_idx}",
                    actions=other_actions,
                    description=f"Requirement: {other_req}"
                ) if other_actions else None

                plans.append(
                    ImplementationPlan(
                        requirement_index=other_idx,
                        objective=other_req,
                        mechanisms=[mech] if mech else [],
                        steps=[PlanStep(id=f"step_{other_idx}", action=other_req)],
                        missing_knowledge=missing_knowledge_items,
                    )
                )

            result = {
                "status": status,
                "minecraft_version": self.version,
                "summary": understanding.get("understood_request", "Property modification plan"),
                "implementation_plan": [p.model_dump() for p in plans],
                "missing_knowledge": [],
                "clarifications": clarifications,
                "clarification_requirements": [cr.model_dump() for cr in structured_clarifications],
            }
            validated = PlannerResult.model_validate(result)
            return validated.model_dump()

        if context is None:
            context = retrieve_minecraft_context(
                understanding,
                version=self.version,
                max_results=10
            )

        system_prompt = self._system_prompt()

        user_prompt = self._build_user_prompt(
            understanding,
            context
        )

        raw_result = self.ai.generate_structured(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema=self._schema()
        )

        normalized = self._normalize_result(
            raw_result,
            understanding
        )

        # ---------------------------------------------------------
        # Final Pydantic validation
        # ---------------------------------------------------------

        validated = PlannerResult.model_validate(
            normalized
        )

        return validated.model_dump()


def create_plan(
    understanding: Dict[str, Any],
    provider="ollama",
    version="1.21.11",
    ai_provider=None,
    property_modifications=None,
    property_registry=None,
    clarification_engine=None,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:

    planner = MinecraftPlanner(
        provider=provider,
        version=version,
        ai_provider=ai_provider,
        property_registry=property_registry,
        clarification_engine=clarification_engine,
    )

    return planner.plan(understanding, property_modifications=property_modifications, context=context)


def validate_plan_mechanisms(plan: Dict[str, Any]) -> None:
    """
    Validates all mechanism specifications in an implementation plan for completeness.
    Raises ValueError if any mechanism specification is incomplete.
    """
    for ip in plan.get("implementation_plan", []):
        for mech in ip.get("mechanisms", []):
            validate_mechanism_specification(mech)
