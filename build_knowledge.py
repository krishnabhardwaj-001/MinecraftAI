import json
from pathlib import Path


# ============================================================
# CONFIGURATION
# ============================================================

VERSION = "1.21.11"
EDITION = "Java"

BASE_DIR = Path(__file__).parent

COMMANDS_FILE = (
    BASE_DIR
    / "knowledge"
    / "commands"
    / "java"
    / VERSION
    / "commands.jsonl"
)

OUTPUT_FILE = (
    BASE_DIR
    / "knowledge"
    / "descriptions"
    / "commands.json"
)


# ============================================================
# LOAD COMMAND TREE DATA
# ============================================================

def load_commands():

    records = []

    with open(COMMANDS_FILE, "r", encoding="utf-8") as f:

        for line in f:

            line = line.strip()

            if line:
                records.append(json.loads(line))

    return records


# ============================================================
# GROUP SYNTAX BY COMMAND
# ============================================================

def build_command_index(records):

    commands = {}

    for record in records:

        name = record["command"]

        if name not in commands:

            commands[name] = {
                "command": name,
                "version": VERSION,
                "edition": EDITION,
                "syntax": [],
                "arguments": []
            }

        # ----------------------------------------------------
        # Add syntax
        # ----------------------------------------------------

        syntax = record.get("syntax")

        if syntax and syntax not in commands[name]["syntax"]:

            commands[name]["syntax"].append(syntax)

        # ----------------------------------------------------
        # Add arguments
        # ----------------------------------------------------

        for argument in record.get("arguments", []):

            argument_copy = {
                "name": argument.get("name"),
                "parser": argument.get("parser")
            }

            if "properties" in argument:

                argument_copy["properties"] = argument["properties"]

            # Avoid duplicate arguments

            if argument_copy not in commands[name]["arguments"]:

                commands[name]["arguments"].append(
                    argument_copy
                )

    return commands


# ============================================================
# MAIN
# ============================================================

def main():

    print("Loading Minecraft command knowledge...")

    records = load_commands()

    print(
        f"Loaded {len(records)} syntax records."
    )

    print("Building command index...")

    commands = build_command_index(records)

    print(
        f"Found {len(commands)} unique commands."
    )

    # --------------------------------------------------------
    # Create output directory
    # --------------------------------------------------------

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    # --------------------------------------------------------
    # Save JSON
    # --------------------------------------------------------

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            list(commands.values()),
            f,
            indent=2,
            ensure_ascii=False
        )

    print()
    print("==========================================")
    print("Knowledge index created successfully")
    print("==========================================")
    print()
    print(f"Output: {OUTPUT_FILE}")
    print(f"Commands: {len(commands)}")


if __name__ == "__main__":
    main()