import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ai.provider import AIProvider
from ai.context import retrieve_minecraft_context
from generator.models import (
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



class PlannerResult(BaseModel):
    status: str
    minecraft_version: str
    summary: str
    implementation_plan: List[ImplementationPlan] = Field(default_factory=list)
    missing_knowledge: List[str] = Field(default_factory=list)
    clarifications: List[str] = Field(default_factory=list)


class MinecraftPlanner:
    def __init__(self, provider="ollama", version="1.21.11"):
        self.version = version
        self.ai = AIProvider(provider=provider)

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
22. For standard mob drop requests (e.g. 'Make every creeper drop diamonds'), default to adding the item drop to the mob loot table alongside default drops. Do not ask for clarification regarding keeping or replacing default drops unless the user explicitly mentions default drops.
23. For predicate requests, if the predicate condition type is available in retrieved knowledge (under 'predicates') or supported Minecraft conditions, populate the structured predicate mechanism with type 'predicate' and mark status as 'ready'.
24. For state-machine and event-trigger requests (e.g. 'only once when X starts', 'when X begins', 'on state change'):
    - Use mechanism type 'state_machine' with 'objective', 'condition_predicate', 'state_scope' ('global' for environmental/world events like weather/time, or 'player' for individual player events), and 'on_enter' structured actions.
    - The deterministic generator automatically handles safe scoreboard initialization in load.mcfunction (using persistent '#global' for global state or dynamic tick initialization for players) and sets up the tick transition and reset logic.
25. For player-targeted actions, specify 'target': '@a' (or '@p' / '@s'). The generator automatically enforces correct execution context chaining ('execute as @a at @s run ...').

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

    def _build_user_prompt(
        self,
        understanding: Dict[str, Any],
        context: Dict[str, Any]
    ) -> str:

        return f"""
Create an implementation plan for the following Minecraft request.

MINECRAFT:
{json.dumps(context.get("minecraft", {}), indent=2)}

USER REQUEST:
{context.get("user_request", "")}

UNDERSTANDING:
{json.dumps(understanding, indent=2)}

REQUIREMENTS:
{json.dumps(context.get("requirements", []), indent=2)}

RETRIEVED MINECRAFT KNOWLEDGE:
{json.dumps(context.get("knowledge", {}), indent=2)}

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
                    mech_dict["type"] = mech_type

                    # Helper to normalize action dictionaries
                    def _norm_action(act: Any) -> Dict[str, Any]:
                        if isinstance(act, dict):
                            ad = dict(act)
                            a_type = str(ad.get("action_type", "apply_effect")).strip().lower()
                            ad["action_type"] = a_type
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
                            if not ad.get("target"):
                                ad["target"] = "@a"
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

            normalized_plan.append({
                "requirement_index": requirement_index,
                "objective": str(objective),
                "mechanisms": normalized_mechanisms,
                "steps": normalized_steps,
                "constraints": normalized_constraints,
                "missing_knowledge": [
                    str(x) for x in plan_missing
                ]
            })

        result["implementation_plan"] = normalized_plan

        return result

    def plan(
        self,
        understanding: Dict[str, Any]
    ) -> Dict[str, Any]:

        if not isinstance(understanding, dict):
            raise ValueError(
                "Understanding must be a dictionary."
            )

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
    version="1.21.11"
) -> Dict[str, Any]:

    planner = MinecraftPlanner(
        provider=provider,
        version=version
    )

    return planner.plan(understanding)


def validate_plan_mechanisms(plan: Dict[str, Any]) -> None:
    """
    Validates all mechanism specifications in an implementation plan for completeness.
    Raises ValueError if any mechanism specification is incomplete.
    """
    for ip in plan.get("implementation_plan", []):
        for mech in ip.get("mechanisms", []):
            validate_mechanism_specification(mech)