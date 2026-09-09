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


# ============================================================
# LOAD COMMANDS
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
# SEARCH COMMANDS
# ============================================================

def search_command(records, command_name):

    command_name = command_name.lower().strip()

    results = []

    for record in records:

        if record["command"].lower() == command_name:

            results.append(record)

    return results


# ============================================================
# DISPLAY RESULTS
# ============================================================

def display_results(results):

    if not results:

        print("No command found.")

        return

    print()
    print(f"Found {len(results)} syntax records.")
    print()

    for record in results:

        print(record["syntax"])

        for argument in record.get("arguments", []):

            parser = argument.get("parser")

            print(
                f"    <{argument['name']}>"
                f" -> {parser}"
            )

        print()


# ============================================================
# MAIN
# ============================================================

def main():

    print("Loading Minecraft Java Edition 1.21.11 commands...")

    records = load_commands()

    print(f"Loaded {len(records)} syntax records.")

    print()
    print("Minecraft Command Search")
    print("========================")
    print("Type a command such as: execute")
    print("Type 'exit' to quit.")
    print()

    while True:

        command_name = input("Command: ").strip()

        if command_name.lower() == "exit":
            break

        if command_name.startswith("/"):
            command_name = command_name[1:]

        results = search_command(
            records,
            command_name
        )

        display_results(results)


# ============================================================
# START PROGRAM
# ============================================================

if __name__ == "__main__":
    main()