import json

from ai.understanding import MinecraftUnderstanding
from ai.planner import create_plan


def main():
    user_text = "Make every zombie drop diamonds."

    # ---------------------------------------------------------
    # UNDERSTANDING
    # ---------------------------------------------------------

    understanding_ai = MinecraftUnderstanding(
        provider="ollama"
    )

    understanding = understanding_ai.understand(
        user_text
    )

    print("=" * 70)
    print("UNDERSTANDING")
    print("=" * 70)

    print(
        json.dumps(
            understanding,
            indent=2,
            ensure_ascii=False
        )
    )

    # ---------------------------------------------------------
    # PLANNER
    # ---------------------------------------------------------

    result = create_plan(
        understanding,
        provider="ollama",
        version="1.21.11"
    )

    print()
    print("=" * 70)
    print("PLANNER RESULT")
    print("=" * 70)

    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()