import json
from pathlib import Path


# ============================================================
# CONFIGURATION
# ============================================================

VERSION = "1.21.11"

BASE_DIR = Path(__file__).parent

COMMANDS_FILE = (
    BASE_DIR
    / "knowledge"
    / "commands"
    / "java"
    / VERSION
    / "commands.jsonl"
)

SEMANTIC_FILE = (
    BASE_DIR
    / "knowledge"
    / "descriptions"
    / "semantic_commands.json"
)


# ============================================================
# LOAD SYNTAX KNOWLEDGE
# ============================================================

def load_syntax_knowledge():

    records = []

    with open(COMMANDS_FILE, "r", encoding="utf-8") as f:

        for line in f:

            line = line.strip()

            if line:
                records.append(json.loads(line))

    return records


# ============================================================
# LOAD SEMANTIC KNOWLEDGE
# ============================================================

def load_semantic_knowledge():

    with open(
        SEMANTIC_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        data = json.load(f)

    return {
        command["command"]: command
        for command in data["commands"]
    }


# ============================================================
# SEARCH SYNTAX
# ============================================================

def search_syntax(records, command):

    command = command.lower().strip()

    return [
        record
        for record in records
        if record["command"].lower() == command
    ]


# ============================================================
# SEARCH SEMANTIC KNOWLEDGE
# ============================================================

def search_semantic(semantic_data, command):

    command = command.lower().strip()

    return semantic_data.get(command)


# ============================================================
# DISPLAY KNOWLEDGE
# ============================================================

def display_knowledge(
    syntax_results,
    semantic_result
):

    print()
    print("=" * 60)
    print("MINECRAFT KNOWLEDGE")
    print("=" * 60)

    # --------------------------------------------------------
    # Semantic information
    # --------------------------------------------------------

    if semantic_result:

        print()
        print("DESCRIPTION:")
        print(semantic_result.get("description", "N/A"))

        purposes = semantic_result.get("purpose", [])

        if purposes:

            print()
            print("PURPOSE:")

            for purpose in purposes:

                print(f"  - {purpose}")

        subcommands = semantic_result.get(
            "important_subcommands",
            []
        )

        if subcommands:

            print()
            print("IMPORTANT SUBCOMMANDS:")

            print(
                "  "
                + ", ".join(subcommands)
            )

    else:

        print()
        print("No semantic information found.")

    # --------------------------------------------------------
    # Syntax information
    # --------------------------------------------------------

    print()
    print(
        f"SYNTAX RECORDS: {len(syntax_results)}"
    )

    if syntax_results:

        print()

        for record in syntax_results:

            print(
                "  "
                + record["syntax"]
            )

    print()
    print("=" * 60)
    print()


# ============================================================
# MAIN
# ============================================================

def main():

    print("Loading Minecraft knowledge...")

    syntax_records = load_syntax_knowledge()

    semantic_data = load_semantic_knowledge()

    print(
        f"Loaded {len(syntax_records)} syntax records."
    )

    print(
        f"Loaded {len(semantic_data)} semantic commands."
    )

    print()
    print("Minecraft Knowledge Retriever")
    print("=============================")
    print()
    print("Try:")
    print("  execute")
    print("  scoreboard")
    print("  summon")
    print("  give")
    print("  effect")
    print()
    print("Type 'exit' to quit.")
    print()

    while True:

        command = input("Command: ").strip()

        if command.lower() == "exit":
            break

        if command.startswith("/"):
            command = command[1:]

        if not command:
            continue

        syntax_results = search_syntax(
            syntax_records,
            command
        )

        semantic_result = search_semantic(
            semantic_data,
            command
        )

        display_knowledge(
            syntax_results,
            semantic_result
        )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()