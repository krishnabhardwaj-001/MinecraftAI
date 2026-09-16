import json
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from ai.provider import AIProvider
from ai.context import retrieve_minecraft_context


class Mechanism(BaseModel):
    type: str
    description: str


class PlanStep(BaseModel):
    id: str
    action: str
    depends_on: List[str] = Field(default_factory=list)
    resources: List[str] = Field(default_factory=list)


class ImplementationPlan(BaseModel):
    requirement_index: int
    objective: str
    mechanisms: List[Mechanism] = Field(default_factory=list)
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
9. Do not output final Minecraft commands.
10. Do not output complete JSON loot tables.
11. Do not create datapack files.
12. Do not include testing actions. Testing belongs to the Validator.
13. Do not claim that a Minecraft mechanism is valid unless the supplied
    knowledge supports it.
14. Preserve all requirements separately.
15. Each implementation-plan entry must correspond to one requirement.
16. Use requirement_index to connect a plan to the original requirement.
17. If a requirement needs several mechanisms, include all of them.
18. Explain why each mechanism is appropriate.
19. Keep implementation details useful for the future Generator.
20. Do not turn general Minecraft concepts into fake commands.

PLANNING VS GENERATION:

Planning example:

User:
"Make every zombie drop diamonds."

Good planning:
- identify zombie death/loot behavior
- identify the appropriate loot-system mechanism
- identify the relevant Minecraft resource
- identify that the existing zombie loot behavior must be preserved if
  replacing/modifying it
- identify any Minecraft knowledge required to construct the final resource

Bad planning:
- writing the actual /loot command
- inventing JSON syntax
- writing a complete loot table
- inventing file contents

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
                        "type": "minecraft_mechanism",
                        "description": mechanism
                    })

                elif isinstance(mechanism, dict):
                    mechanism_type = mechanism.get(
                        "type",
                        "minecraft_mechanism"
                    )

                    description = mechanism.get(
                        "description",
                        ""
                    )

                    normalized_mechanisms.append({
                        "type": str(mechanism_type),
                        "description": str(description)
                    })

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