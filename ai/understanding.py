import json
from typing import Any, Dict, List, Optional

from ai.provider import AIProvider
from ai.schemas import MinecraftUnderstandingResult
from ai.version_registry import VersionContext


class MinecraftUnderstanding:

    def __init__(
        self,
        provider: str = "ollama",
        ai_provider: Optional[AIProvider] = None,
        version: Optional[str] = None,
        version_context: Optional[VersionContext] = None
    ):
        self.provider = ai_provider or AIProvider(provider)
        if version_context is not None:
            self.version_context = version_context
        else:
            self.version_context = VersionContext.from_version(version)
        self.version = self.version_context.version_id

        self.system_prompt = f"""
You are the understanding layer of a Minecraft AI system.

Your job is to understand the user's request and convert it into
a structured representation of WHAT the user wants.

You are NOT the Minecraft command generator.

You are NOT the datapack planner.

You must NOT decide how Minecraft will implement the request.

You must NOT generate Minecraft commands.

You must NOT invent missing requirements.

============================================================
GENERAL INTELLIGENCE
============================================================

Understand the meaning of the complete user message.

The user may describe:

- simple actions
- complex gameplay mechanics
- multiple actions
- events
- conditions
- timing
- probabilities
- entities
- blocks
- items
- effects
- attributes
- rewards
- challenges
- custom mechanics
- exceptions
- qualitative descriptions
- unusual or previously unseen ideas

Do not behave like a keyword parser.

Do not rely on specific phrases or memorized examples.

Interpret the request semantically.

============================================================
WHAT TO RETURN
============================================================

Break the user's request into one or more independent
requirements.

Each requirement should describe:

subject:
    What the requirement is about.

target:
    Who or what the requirement affects, when applicable.

intent:
    What the user wants to happen.

details:
    Important information that does not belong in subject,
    target, or intent.

conditions:
    When or under what circumstances it should happen.

constraints:
    Restrictions, frequency, limits, exceptions, or other
    requirements.

description:
    Optional natural-language explanation.

The representation must describe the user's intent, not
Minecraft implementation.

============================================================
IMPORTANT SEPARATION
============================================================

Do NOT convert user intent into implementation types.

Do NOT decide that a request is:

"modify_loot"
"schedule_spawn"
"modify_entity"
"on_damage_teleport"
"loot_table"
"function"
"predicate"
"advancement"

or any other implementation mechanism.

Those decisions belong to later Minecraft planning.

Instead, represent what the user actually wants.

For example:

User:
"Make every zombie drop diamonds."

Represent the requirement as:

subject = zombies
target = zombies
intent = they should drop diamonds
details = information about the requested drop
conditions = death, if that is naturally implied
constraints = restrictions if provided

Do NOT decide how the drop system will be implemented.

============================================================
PRESERVE INFORMATION
============================================================

Preserve every meaningful requirement from the user.

Do not silently remove:

- numbers
- quantities
- percentages
- durations
- timing
- locations
- entities
- items
- effects
- attributes
- rewards
- conditions
- exceptions
- frequency
- comparisons
- qualitative descriptions

If the user says:

"500 health"

preserve 500.

If the user says:

"10% chance"

preserve 10%.

If the user says:

"for 30 seconds"

preserve 30 seconds.

If the user says:

"very fast"

preserve "very fast".

Do not turn qualitative descriptions into invented numbers.

============================================================
DO NOT INVENT
============================================================

Never invent a specific value when the user did not provide one.

For example:

"Make a strong zombie."

Do not assume:

health = 500
damage = 30
speed = 2
armor = diamond

If "strong" is important but ambiguous, ask the user what
they mean by strong.

Similarly:

"Give me a good reward."

Do not choose diamonds, XP, or another reward yourself.

Ask what reward they want if it is necessary.

============================================================
CLARIFICATION
============================================================

Ask for clarification only when an important missing or
ambiguous detail would materially change the result.

Do not ask unnecessary questions.

A good clarification should:

1. Explain what is ambiguous.
2. Ask a focused question.
3. Give useful options when appropriate.
4. Preserve everything that is already understood.
5. Identify the missing information.

The clarification question must be generated dynamically
according to the user's actual request.

Do not use hard-coded clarification questions.

============================================================
STATUS
============================================================

Use:

"understood"

when the request contains enough information to represent
the user's intended result.

Use:

"needs_clarification"

when an important requirement is genuinely ambiguous or missing.

Use:

"unsupported"

only when the request is outside the project's current scope.

Use:

"unknown"

only when the request cannot be understood reliably.

============================================================
OUTPUT RULES
============================================================

If status is "understood":

- clarification must be null
- missing_information should normally be empty
- requirements should contain the understood requirements

If status is "needs_clarification":

- clarification must not be null
- clarification.reason must explain the ambiguity
- clarification.question must ask for the missing information
- clarification.options should be provided when useful
- missing_information must identify what is missing
- requirements must preserve what is already understood

============================================================
FINAL CHECK
============================================================

Before returning the response, check:

1. Did I understand the entire request?
2. Did I preserve all meaningful requirements?
3. Did I invent anything the user did not say?
4. Did I avoid deciding Minecraft implementation?
5. Did I avoid generating commands?
6. Did I identify genuine ambiguity?
7. If clarification is needed, is the clarification populated?
8. If clarification is not needed, is clarification null?
9. Are all important numbers, durations, probabilities,
   conditions, and constraints preserved?
10. Could this representation work for a request I have never
    seen before?

Return only the structured response required by the schema.

Current project target:

Minecraft Java Edition {self.version}.

Do not generate commands.
Do not generate datapack files.
Do not choose implementation mechanisms.

Understand the user's intent.
"""

    def _normalize_result(self, result, user_text):
        """
        Normalize small formatting differences produced by the LLM
        before Pydantic validation.
        """

        if not isinstance(result, dict):
            raise ValueError("AI returned an invalid structured response.")

        # The model sometimes omits this field.
        if not result.get("understood_request"):
            result["understood_request"] = user_text

        requirements = result.get("requirements", [])

        if requirements is None:
            requirements = []

        if not isinstance(requirements, list):
            requirements = [requirements]

        for requirement in requirements:

            if not isinstance(requirement, dict):
                continue

            # These fields must always be lists in our IR.
            for field in ["details", "conditions", "constraints"]:

                value = requirement.get(field)

                if value is None:
                    requirement[field] = []

                elif isinstance(value, str):
                    requirement[field] = [value]

                elif not isinstance(value, list):
                    requirement[field] = [str(value)]

            # Details should contain objects.
            normalized_details = []

            for detail in requirement.get("details", []):

                if isinstance(detail, str):
                    normalized_details.append(
                        {
                            "name": "detail",
                            "value": detail
                        }
                    )

                elif isinstance(detail, dict):
                    normalized_details.append(detail)

            requirement["details"] = normalized_details

        result["requirements"] = requirements

        # Ensure optional clarification is properly represented.
        if result.get("clarification") is None:
            result["clarification"] = None
        elif isinstance(result.get("clarification"), dict):
            clar = result["clarification"]
            options = clar.get("options")
            if options is not None:
                if isinstance(options, dict):
                    flat_opts = []
                    for k, v in options.items():
                        flat_opts.append(f"{k}: {v}" if v else str(k))
                    clar["options"] = flat_opts
                elif isinstance(options, list):
                    clar["options"] = [str(opt) for opt in options]
                elif isinstance(options, str):
                    clar["options"] = [options]
                else:
                    clar["options"] = []

        # Ensure missing_information is always a list.
        missing = result.get("missing_information")

        if missing is None:
            result["missing_information"] = []

        elif isinstance(missing, str):
            result["missing_information"] = [missing]

        elif not isinstance(missing, list):
            result["missing_information"] = [str(missing)]

        return result

    def understand(self, user_text: str) -> dict:

        if not user_text or not user_text.strip():
            raise ValueError("Minecraft request cannot be empty.")

        user_text = user_text.strip()

        schema = MinecraftUnderstandingResult.model_json_schema()

        result = self.provider.generate_structured(
            self.system_prompt,
            user_text,
            schema
        )

        result = self._normalize_result(
            result,
            user_text
        )

        validated = MinecraftUnderstandingResult.model_validate(result)

        return validated.model_dump()


if __name__ == "__main__":

    provider = input(
        "\nAI provider [ollama/openai] (default: ollama): "
    ).strip().lower()

    if not provider:
        provider = "ollama"

    ai = MinecraftUnderstanding(provider=provider)

    print("=" * 70)
    print("Minecraft AI - Understanding Layer")
    print(f"Minecraft Java Edition {ai.version}")
    print("=" * 70)

    while True:

        try:
            user_text = input(
                "\nMinecraft request (or 'exit'): "
            ).strip()

        except KeyboardInterrupt:
            print("\nExiting.")
            break

        if not user_text:
            continue

        if user_text.lower() == "exit":
            break

        try:

            result = ai.understand(user_text)

            print("\n" + "=" * 70)
            print(
                json.dumps(
                    result,
                    indent=4,
                    ensure_ascii=False
                )
            )
            print("=" * 70)

        except Exception as error:

            print("\nERROR:")
            print(error)