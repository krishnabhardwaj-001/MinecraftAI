from ai.understanding import MinecraftUnderstanding
from ai.context import retrieve_minecraft_context


def main():

    user_request = (
        "Make every zombie drop diamonds."
    )

    understanding_ai = MinecraftUnderstanding()

    understanding = (
        understanding_ai.understand(
            user_request
        )
    )

    context = retrieve_minecraft_context(
        understanding
    )

    print()
    print("=" * 70)
    print("UNDERSTANDING")
    print("=" * 70)

    print(understanding)

    print()
    print("=" * 70)
    print("MINECRAFT CONTEXT")
    print("=" * 70)

    print(context)


if __name__ == "__main__":
    main()