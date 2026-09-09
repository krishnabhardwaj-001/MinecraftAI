import json
from pathlib import Path

from minecraft_request_parser import parse_request


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

COMMANDS_FILE = (
    BASE_DIR
    / "knowledge"
    / "commands"
    / "java"
    / "1.21.11"
    / "commands.jsonl"
)


# ============================================================
# LOAD COMMAND KNOWLEDGE
# ============================================================

def load_command_knowledge():
    """
    Load the generated Minecraft 1.21.11 command syntax records.
    """

    records = []

    with open(COMMANDS_FILE, "r", encoding="utf-8") as file:

        for line in file:

            line = line.strip()

            if line:
                records.append(
                    json.loads(line)
                )

    return records


# ============================================================
# FIND COMMAND SYNTAX
# ============================================================

def get_command_syntax(command_name, knowledge):
    """
    Get every syntax record belonging to a command.
    """

    return [
        record
        for record in knowledge
        if record.get("command") == command_name
    ]


# ============================================================
# FIND SYNTAX CONTAINING ARGUMENT
# ============================================================

def find_syntax_records(
    command_name,
    knowledge,
    required_tokens=None
):
    """
    Find syntax records for a command.

    required_tokens:
        Tokens that should appear in the syntax.
    """

    records = get_command_syntax(
        command_name,
        knowledge
    )

    if not required_tokens:
        return records

    results = []

    for record in records:

        syntax = record.get(
            "syntax",
            ""
        )

        matches = True

        for token in required_tokens:

            if token not in syntax:
                matches = False
                break

        if matches:
            results.append(record)

    return results


# ============================================================
# EFFECT COMMAND
# ============================================================

def generate_effect(request):
    """
    Generate an /effect command.

    Example:
        make me faster

    Result:
        /effect give @s speed 30 0
    """

    target = request.get(
        "target",
        "@s"
    )

    effect = request.get(
        "effect"
    )

    duration = request.get(
        "duration_seconds",
        30
    )

    level = request.get(
        "level",
        1
    )

    if not effect:

        return {
            "success": False,
            "error": "No effect was detected."
        }

    # Minecraft uses amplifier 0 for level 1.
    amplifier = max(
        0,
        level - 1
    )

    command = (
        f"/effect give "
        f"{target} "
        f"{effect} "
        f"{duration} "
        f"{amplifier}"
    )

    return {
        "success": True,
        "action": "apply_effect",
        "command": command,
        "target": target,
        "effect": effect,
        "duration_seconds": duration,
        "level": level,
        "amplifier": amplifier
    }


# ============================================================
# GIVE COMMAND
# ============================================================

def generate_give(request):
    """
    Generate a /give command.

    Example:
        give me a diamond sword

    Result:
        /give @s diamond_sword 1
    """

    target = request.get(
        "target",
        "@s"
    )

    item = request.get(
        "item"
    )

    amount = request.get(
        "amount",
        1
    )

    if not item:

        return {
            "success": False,
            "error": "No item was detected."
        }

    command = (
        f"/give "
        f"{target} "
        f"{item} "
        f"{amount}"
    )

    return {
        "success": True,
        "action": "give_item",
        "command": command,
        "target": target,
        "item": item,
        "amount": amount
    }


# ============================================================
# SUMMON COMMAND
# ============================================================

def generate_summon(request):
    """
    Generate a /summon command.

    Example:
        spawn a zombie

    Result:
        /summon zombie
    """

    entity = request.get(
        "entity"
    )

    if not entity:

        return {
            "success": False,
            "error": "No entity was detected."
        }

    command = (
        f"/summon "
        f"{entity}"
    )

    return {
        "success": True,
        "action": "summon_entity",
        "command": command,
        "entity": entity
    }


# ============================================================
# SCOREBOARD
# ============================================================

def generate_scoreboard(request):
    """
    Scoreboard generation will be expanded later.

    For now we return a structured placeholder.
    """

    purpose = request.get(
        "purpose",
        "score_tracking"
    )

    return {
        "success": False,
        "action": "scoreboard",
        "purpose": purpose,
        "error": (
            "Scoreboard generation requires "
            "additional information such as "
            "objective name and operation."
        )
    }


# ============================================================
# COMMAND GENERATOR
# ============================================================

def generate_command(request, knowledge):
    """
    Convert a structured Minecraft request
    into a command.
    """

    action = request.get(
        "action"
    )

    if action == "apply_effect":

        return generate_effect(
            request
        )

    if action == "give_item":

        return generate_give(
            request
        )

    if action == "summon_entity":

        return generate_summon(
            request
        )

    if action == "scoreboard":

        return generate_scoreboard(
            request
        )

    return {
        "success": False,
        "error": (
            f"Unsupported action: {action}"
        )
    }


# ============================================================
# SYNTAX VERIFICATION
# ============================================================

def verify_command_family(
    generated_result,
    knowledge
):
    """
    Basic verification that the generated command
    belongs to a command family that exists in the
    Minecraft 1.21.11 command tree.
    """

    if not generated_result.get(
        "success",
        False
    ):
        return generated_result

    command = generated_result.get(
        "command",
        ""
    )

    if not command:
        return generated_result

    # Remove /
    command_without_slash = command[1:]

    command_name = command_without_slash.split(
        " ",
        1
    )[0]

    records = get_command_syntax(
        command_name,
        knowledge
    )

    if not records:

        generated_result["verified"] = False

        generated_result["verification_error"] = (
            f"/{command_name} was not found "
            "in the Minecraft 1.21.11 command tree."
        )

        return generated_result

    generated_result["verified"] = True

    generated_result["syntax_records_available"] = len(
        records
    )

    return generated_result


# ============================================================
# FULL PIPELINE
# ============================================================

def process_request(
    user_text,
    knowledge
):
    """
    Complete pipeline:

        Natural language
             ↓
        Request parser
             ↓
        Command generator
             ↓
        Basic verification
    """

    request = parse_request(
        user_text
    )

    generated = generate_command(
        request,
        knowledge
    )

    verified = verify_command_family(
        generated,
        knowledge
    )

    return {
        "request": request,
        "generation": verified
    }


# ============================================================
# DISPLAY
# ============================================================

def display_result(result):

    print("\n")
    print("=" * 70)
    print("MINECRAFT AI - COMMAND GENERATOR")
    print("=" * 70)

    print("\nSTRUCTURED REQUEST:")

    print(
        json.dumps(
            result["request"],
            indent=4
        )
    )

    print("\nGENERATION RESULT:")

    print(
        json.dumps(
            result["generation"],
            indent=4
        )
    )

    if result["generation"].get(
        "success",
        False
    ):

        print("\nGENERATED COMMAND:")

        print(
            result["generation"]["command"]
        )

    print("\n" + "=" * 70)


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("MINECRAFT AI - COMMAND GENERATOR")
    print("Minecraft Java Edition 1.21.11")
    print("=" * 70)

    print("\nLoading Minecraft command knowledge...")

    knowledge = load_command_knowledge()

    print(
        f"Loaded {len(knowledge)} syntax records."
    )

    while True:

        user_text = input(
            "\nEnter Minecraft request (or 'exit'): "
        ).strip()

        if user_text.lower() == "exit":

            print("Exiting.")
            break

        if not user_text:
            continue

        result = process_request(
            user_text,
            knowledge
        )

        display_result(
            result
        )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()