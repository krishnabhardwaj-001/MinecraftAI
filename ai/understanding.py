from typing import Optional

from pydantic import BaseModel, Field

from ai.provider import AIProvider


# ============================================================
# STRUCTURED MINECRAFT ACTION
# ============================================================

class MinecraftAction(BaseModel):

    type: str = Field(
        description=(
            "The Minecraft action to perform. "
            "Examples: effect, give, summon, scoreboard, "
            "execute, data, command, ability."
        )
    )

    target: Optional[str] = Field(
        default=None,
        description=(
            "Minecraft target selector such as "
            "@s, @a, @p, @r, or @e."
        )
    )

    effect: Optional[str] = None

    item: Optional[str] = None

    entity: Optional[str] = None

    amount: Optional[int] = None

    duration_seconds: Optional[int] = None

    level: Optional[int] = None

    multiplier: Optional[float] = None

    purpose: Optional[str] = None

    description: Optional[str] = None


# ============================================================
# COMPLETE REQUEST
# ============================================================

class MinecraftRequest(BaseModel):

    minecraft_version: str = "1.21.11"

    edition: str = "Java"

    understood_request: str

    actions: list[MinecraftAction]

    needs_clarification: bool = False

    clarification_question: Optional[str] = None


# ============================================================
# SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """
You are the natural-language understanding engine for a
Minecraft Java Edition 1.21.11 AI.

Your job is NOT to generate Minecraft commands.

Your job is to understand what the user wants and convert
their natural-language request into structured Minecraft
actions.

The user may use:

- slang
- abbreviations
- informal language
- incomplete sentences
- spelling mistakes
- conversational language
- multiple requests in one sentence
- references such as "it", "them", "that mob"
- quantities
- durations
- comparisons
- conditions

Understand the meaning rather than matching keywords.

Examples:

"make me faster"
means a speed effect.

"make me 10 times faster"
means a speed request with multiplier 10.

"yo give me a sword"
means give an item.

"spawn five zombies"
means summon five zombie entities.

"make everyone invisible for 30 seconds"
means an invisibility effect targeting @a.

"give me a sword and make me fast"
means TWO actions.

Do not invent Minecraft commands.

Do not output explanations inside actions.

If the request is ambiguous and you genuinely cannot
determine what the user means, set needs_clarification
to true and ask one concise clarification question.

Always assume:

Minecraft Java Edition 1.21.11

Default target:

@s

unless the user specifies another target.

Convert durations to seconds.

For example:

2 minutes = 120 seconds

Use Minecraft IDs when you know them.

Examples:

speed -> minecraft:speed
diamond sword -> minecraft:diamond_sword
zombie -> minecraft:zombie

Remember:

You are an UNDERSTANDING layer.

A different component will later convert your structured
actions into actual Minecraft commands.
"""


# ============================================================
# AI UNDERSTANDING ENGINE
# ============================================================

class MinecraftUnderstanding:

    def __init__(self, provider="ollama"):

        self.provider = AIProvider(
            provider=provider
        )

    def understand(self, user_text):

        if not user_text.strip():
            raise ValueError(
                "User request cannot be empty."
            )

        schema = MinecraftRequest.model_json_schema()

        result = self.provider.generate_structured(
            system_prompt=SYSTEM_PROMPT,

            user_prompt=user_text,

            schema=schema
        )

        return MinecraftRequest.model_validate(
            result
        )


# ============================================================
# TEST MODE
# ============================================================

def main():

    print("=" * 70)
    print("MINECRAFT AI - AI UNDERSTANDING ENGINE")
    print("Minecraft Java Edition 1.21.11")
    print("=" * 70)

    provider = input(
        "\nProvider (ollama/openai): "
    ).strip().lower()

    if provider not in ["ollama", "openai"]:

        print(
            "Invalid provider. "
            "Use 'ollama' or 'openai'."
        )

        return

    ai = MinecraftUnderstanding(
        provider=provider
    )

    while True:

        user_text = input(
            "\nMinecraft request (or 'exit'): "
        ).strip()

        if user_text.lower() == "exit":

            print("Exiting.")

            break

        if not user_text:

            continue

        try:

            result = ai.understand(
                user_text
            )

            print("\n" + "=" * 70)

            print(
                result.model_dump_json(
                    indent=4
                )
            )

            print("=" * 70)

        except Exception as error:

            print("\nERROR:")

            print(error)


if __name__ == "__main__":
    main()