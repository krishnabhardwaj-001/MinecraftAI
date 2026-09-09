import re
import json
from pathlib import Path


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

SEMANTIC_FILE = (
    BASE_DIR
    / "knowledge"
    / "descriptions"
    / "semantic_commands.json"
)


# ============================================================
# LOAD KNOWLEDGE
# ============================================================

def load_command_knowledge():
    knowledge = []

    with open(COMMANDS_FILE, "r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()

            if line:
                knowledge.append(json.loads(line))

    return knowledge


def load_semantic_knowledge():
    """
    Load semantic knowledge and normalize it into a list of records.
    Supports both:
      1. A JSON list of command records
      2. A JSON object containing command records
    """

    with open(SEMANTIC_FILE, "r", encoding="utf-8") as file:
        data = json.load(file)

    # Case 1:
    # [
    #   {"command": "execute", ...},
    #   {"command": "give", ...}
    # ]
    if isinstance(data, list):
        return data

    # Case 2:
    # {
    #   "execute": {...},
    #   "give": {...}
    # }
    if isinstance(data, dict):

        normalized = []

        for command_name, command_data in data.items():

            if isinstance(command_data, dict):

                # If command name is not already present,
                # add it from the dictionary key.
                if "command" not in command_data:
                    command_data["command"] = command_name

                normalized.append(command_data)

        return normalized

    raise ValueError(
        "semantic_commands.json must contain a JSON list or object."
    )


# ============================================================
# INTENT DEFINITIONS
# ============================================================

INTENTS = {

    "effect": {
        "keywords": [
            "faster",
            "fast",
            "speed",
            "slow",
            "slowness",
            "strength",
            "stronger",
            "weak",
            "jump",
            "jump higher",
            "regeneration",
            "heal",
            "healing",
            "poison",
            "invisible",
            "invisibility",
            "night vision",
            "fire resistance",
            "water breathing",
            "haste",
            "effect",
            "buff",
            "debuff"
        ],
        "commands": ["effect"]
    },

    "give": {
        "keywords": [
            "give",
            "get",
            "receive",
            "obtain",
            "item",
            "items",
            "sword",
            "pickaxe",
            "axe",
            "shovel",
            "bow",
            "armor",
            "diamond",
            "netherite",
            "food"
        ],
        "commands": ["give"]
    },

    "summon": {
        "keywords": [
            "spawn",
            "summon",
            "create mob",
            "create entity",
            "mob",
            "zombie",
            "skeleton",
            "creeper",
            "villager",
            "iron golem",
            "wither",
            "ender dragon",
            "entity"
        ],
        "commands": ["summon"]
    },

    "scoreboard": {
        "keywords": [
            "score",
            "scores",
            "scoreboard",
            "timer",
            "countdown",
            "counter",
            "cooldown",
            "points",
            "objective",
            "track",
            "count"
        ],
        "commands": ["scoreboard"]
    },

    "execute": {
        "keywords": [
            "execute",
            "run command",
            "run",
            "at player",
            "as player",
            "at",
            "as",
            "if",
            "unless",
            "condition",
            "when",
            "where",
            "position",
            "location"
        ],
        "commands": ["execute"]
    },

    "data": {
        "keywords": [
            "data",
            "nbt",
            "modify data",
            "change data",
            "read data",
            "entity data",
            "block data",
            "tag"
        ],
        "commands": ["data"]
    }
}


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_text(text):
    """
    Convert user text into a simple normalized form.
    """

    text = text.lower()

    # Replace punctuation with spaces
    text = re.sub(r"[^a-z0-9_ ]", " ", text)

    # Remove repeated spaces
    text = re.sub(r"\s+", " ", text).strip()

    return text


# ============================================================
# INTENT DETECTION
# ============================================================

def detect_intents(text):
    """
    Detect possible Minecraft concepts from natural language.
    """

    text = normalize_text(text)

    detected = []

    for intent_name, intent_data in INTENTS.items():

        score = 0
        matched_keywords = []

        for keyword in intent_data["keywords"]:

            keyword = keyword.lower()

            if keyword in text:
                score += 1
                matched_keywords.append(keyword)

        if score > 0:
            detected.append({
                "intent": intent_name,
                "score": score,
                "matched_keywords": matched_keywords,
                "commands": intent_data["commands"]
            })

    # Highest scoring intents first
    detected.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    return detected


# ============================================================
# COMMAND SEARCH
# ============================================================

def search_command(command_name, command_knowledge):
    """
    Return all syntax records for a particular command.
    """

    results = []

    for record in command_knowledge:

        if record.get("command") == command_name:
            results.append(record)

    return results


# ============================================================
# SEMANTIC SEARCH
# ============================================================

def search_semantic(command_name, semantic_knowledge):
    """
    Find semantic information for a command.
    """

    for record in semantic_knowledge:

        if record.get("command") == command_name:
            return record

    return None


# ============================================================
# BUILD RESULT
# ============================================================

def build_result(user_text, detected_intents, command_knowledge, semantic_knowledge):
    """
    Convert detected intents into a structured AI-friendly result.
    """

    result = {
        "user_request": user_text,
        "normalized_request": normalize_text(user_text),
        "detected_intents": [],
        "candidate_commands": []
    }

    seen_commands = set()

    for intent in detected_intents:

        intent_result = {
            "intent": intent["intent"],
            "score": intent["score"],
            "matched_keywords": intent["matched_keywords"],
            "commands": []
        }

        for command_name in intent["commands"]:

            if command_name in seen_commands:
                continue

            seen_commands.add(command_name)

            semantic = search_semantic(
                command_name,
                semantic_knowledge
            )

            syntax = search_command(
                command_name,
                command_knowledge
            )

            command_result = {
                "command": command_name,
                "semantic": semantic,
                "syntax_count": len(syntax),
                "syntax_examples": syntax[:5]
            }

            intent_result["commands"].append(command_result)

            result["candidate_commands"].append(command_result)

        result["detected_intents"].append(intent_result)

    return result


# ============================================================
# DISPLAY RESULT
# ============================================================

def display_result(result):

    print("\n" + "=" * 70)
    print("MINECRAFT AI - INTENT ANALYSIS")
    print("=" * 70)

    print("\nUser request:")
    print(result["user_request"])

    print("\nNormalized:")
    print(result["normalized_request"])

    print("\nDetected intents:")

    if not result["detected_intents"]:
        print("  No known Minecraft intent detected.")
        return

    for intent in result["detected_intents"]:

        print(
            f"\n  Intent: {intent['intent']}"
        )

        print(
            f"  Score: {intent['score']}"
        )

        print(
            f"  Matched keywords: "
            f"{', '.join(intent['matched_keywords'])}"
        )

        for command in intent["commands"]:

            print(
                f"\n    Command: /{command['command']}"
            )

            print(
                f"    Syntax records: "
                f"{command['syntax_count']}"
            )

            semantic = command["semantic"]

            if semantic:

                print(
                    f"    Description: "
                    f"{semantic.get('description', 'N/A')}"
                )

                purposes = semantic.get(
                    "purposes",
                    []
                )

                if purposes:

                    print("    Purposes:")

                    for purpose in purposes:
                        print(
                            f"      - {purpose}"
                        )

            print("    Example syntax:")

            for syntax in command["syntax_examples"]:

                print(
                    f"      /{syntax['syntax']}"
                )

    print("\n" + "=" * 70)


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("MINECRAFT AI - NATURAL LANGUAGE UNDERSTANDING")
    print("Minecraft Java Edition 1.21.11")
    print("=" * 70)

    # Load knowledge
    command_knowledge = load_command_knowledge()
    semantic_knowledge = load_semantic_knowledge()

    print(
        f"\nLoaded {len(command_knowledge)} command syntax records."
    )

    # Interactive loop
    while True:

        print("\nEnter a Minecraft request.")
        print("Type 'exit' to stop.")

        user_text = input("\n> ").strip()

        if user_text.lower() == "exit":
            print("\nExiting.")
            break

        if not user_text:
            continue

        # Detect intent
        detected_intents = detect_intents(user_text)

        # Build structured result
        result = build_result(
            user_text,
            detected_intents,
            command_knowledge,
            semantic_knowledge
        )

        # Display result
        display_result(result)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()