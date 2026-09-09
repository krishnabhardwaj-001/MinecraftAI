import re
import json


# ============================================================
# EFFECT DETECTION
# ============================================================

EFFECT_ALIASES = {
    "speed": [
        "speed",
        "faster",
        "fast",
        "run faster",
        "move faster"
    ],

    "slowness": [
        "slow",
        "slower",
        "slowness"
    ],

    "strength": [
        "strength",
        "strong",
        "stronger"
    ],

    "jump_boost": [
        "jump",
        "jump higher",
        "higher jump"
    ],

    "regeneration": [
        "regeneration",
        "regenerate",
        "regen",
        "heal",
        "healing"
    ],

    "invisibility": [
        "invisible",
        "invisibility"
    ],

    "night_vision": [
        "night vision",
        "see in dark",
        "see better in dark"
    ],

    "fire_resistance": [
        "fire resistance",
        "resistant to fire",
        "immune to fire"
    ],

    "water_breathing": [
        "water breathing",
        "breathe underwater",
        "underwater breathing"
    ],

    "haste": [
        "haste",
        "mine faster",
        "mining faster"
    ]
}


# ============================================================
# ITEM DETECTION
# ============================================================

ITEM_ALIASES = {
    "diamond_sword": [
        "diamond sword"
    ],

    "netherite_sword": [
        "netherite sword"
    ],

    "diamond_pickaxe": [
        "diamond pickaxe"
    ],

    "netherite_pickaxe": [
        "netherite pickaxe"
    ],

    "diamond_axe": [
        "diamond axe"
    ],

    "netherite_axe": [
        "netherite axe"
    ],

    "bow": [
        "bow"
    ],

    "crossbow": [
        "crossbow"
    ],

    "shield": [
        "shield"
    ],

    "elytra": [
        "elytra"
    ],

    "diamond": [
        "diamond"
    ],

    "netherite_ingot": [
        "netherite ingot"
    ]
}


# ============================================================
# ENTITY DETECTION
# ============================================================

ENTITY_ALIASES = {
    "zombie": [
        "zombie"
    ],

    "skeleton": [
        "skeleton"
    ],

    "creeper": [
        "creeper"
    ],

    "villager": [
        "villager"
    ],

    "iron_golem": [
        "iron golem",
        "iron_golem"
    ],

    "wither": [
        "wither"
    ],

    "ender_dragon": [
        "ender dragon",
        "ender_dragon"
    ],

    "cow": [
        "cow"
    ],

    "pig": [
        "pig"
    ],

    "chicken": [
        "chicken"
    ]
}


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_text(text):
    text = text.lower()

    text = re.sub(
        r"[^a-z0-9_ ]",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ============================================================
# FIND ALIAS
# ============================================================

def find_alias(text, aliases):
    """
    Search for the best matching alias.
    """

    matches = []

    for canonical_name, phrases in aliases.items():

        for phrase in phrases:

            if phrase in text:

                matches.append(
                    (
                        len(phrase),
                        canonical_name
                    )
                )

    if not matches:
        return None

    # Prefer longest phrase.
    matches.sort(
        key=lambda item: item[0],
        reverse=True
    )

    return matches[0][1]


# ============================================================
# TARGET DETECTION
# ============================================================

def detect_target(text):
    """
    Determine who the command should affect.
    """

    if (
        "everyone" in text
        or "all players" in text
        or "every player" in text
    ):
        return "@a"

    if (
        "nearest player" in text
        or "nearest" in text
    ):
        return "@p"

    if (
        "random player" in text
        or "random" in text
    ):
        return "@r"

    if (
        "all entities" in text
        or "every entity" in text
    ):
        return "@e"

    # "me", "myself", "my player"
    if (
        "me" in text
        or "myself" in text
        or "my player" in text
    ):
        return "@s"

    # Default target
    return "@s"


# ============================================================
# EFFECT LEVEL
# ============================================================

def detect_effect_level(text):
    """
    Convert simple phrases into Minecraft amplifier levels.

    Minecraft effect amplifier:
        level 1 -> amplifier 0
        level 2 -> amplifier 1
        level 3 -> amplifier 2
    """

    patterns = [
        (r"level\s+(\d+)", 1),
        (r"lvl\s+(\d+)", 1),
        (r"(\d+)\s+times\s+strong", 1),
        (r"(\d+)\s+strong", 1)
    ]

    for pattern, offset in patterns:

        match = re.search(
            pattern,
            text
        )

        if match:

            level = int(
                match.group(1)
            )

            if level < 1:
                level = 1

            return level

    # Default level
    return 1


# ============================================================
# DURATION
# ============================================================

def detect_duration(text):
    """
    Detect simple duration phrases.

    Examples:
        10 seconds
        30 seconds
        1 minute
        2 minutes
    """

    seconds_match = re.search(
        r"(\d+)\s*seconds?",
        text
    )

    if seconds_match:

        return int(
            seconds_match.group(1)
        )

    minutes_match = re.search(
        r"(\d+)\s*minutes?",
        text
    )

    if minutes_match:

        return int(
            minutes_match.group(1)
        ) * 60

    # Default Minecraft effect duration
    return 30


# ============================================================
# ACTION DETECTION
# ============================================================

def detect_action(text):

    # Effect
    if (
        find_alias(
            text,
            EFFECT_ALIASES
        )
        is not None
    ):
        return "apply_effect"

    # Give item
    if (
        find_alias(
            text,
            ITEM_ALIASES
        )
        is not None
        and
        (
            "give" in text
            or "get" in text
            or "receive" in text
            or "obtain" in text
        )
    ):
        return "give_item"

    # Summon entity
    if (
        find_alias(
            text,
            ENTITY_ALIASES
        )
        is not None
        and
        (
            "spawn" in text
            or "summon" in text
            or "create" in text
        )
    ):
        return "summon_entity"

    # Explicit command request
    if "execute" in text:
        return "execute"

    if "scoreboard" in text:
        return "scoreboard"

    if "cooldown" in text:
        return "scoreboard"

    if "timer" in text:
        return "scoreboard"

    if "data" in text or "nbt" in text:
        return "data"

    return "unknown"


# ============================================================
# BUILD EFFECT REQUEST
# ============================================================

def build_effect_request(text):

    effect = find_alias(
        text,
        EFFECT_ALIASES
    )

    target = detect_target(text)

    level = detect_effect_level(text)

    duration = detect_duration(text)

    return {
        "action": "apply_effect",
        "target": target,
        "effect": effect,
        "level": level,
        "duration_seconds": duration
    }


# ============================================================
# BUILD ITEM REQUEST
# ============================================================

def build_item_request(text):

    item = find_alias(
        text,
        ITEM_ALIASES
    )

    target = detect_target(text)

    return {
        "action": "give_item",
        "target": target,
        "item": item,
        "amount": 1
    }


# ============================================================
# BUILD SUMMON REQUEST
# ============================================================

def build_summon_request(text):

    entity = find_alias(
        text,
        ENTITY_ALIASES
    )

    target = detect_target(text)

    return {
        "action": "summon_entity",
        "entity": entity,
        "reference_target": target
    }


# ============================================================
# BUILD SCOREBOARD REQUEST
# ============================================================

def build_scoreboard_request(text):

    if "cooldown" in text:

        purpose = "cooldown"

    elif "timer" in text:

        purpose = "timer"

    elif "countdown" in text:

        purpose = "countdown"

    elif "points" in text:

        purpose = "points"

    else:

        purpose = "score_tracking"

    return {
        "action": "scoreboard",
        "purpose": purpose
    }


# ============================================================
# BUILD REQUEST
# ============================================================

def parse_request(user_text):

    text = normalize_text(
        user_text
    )

    action = detect_action(
        text
    )

    result = {
        "minecraft_version": "1.21.11",
        "edition": "Java",
        "user_request": user_text,
        "normalized_request": text,
        "action": action
    }

    # --------------------------------------------------------
    # EFFECT
    # --------------------------------------------------------

    if action == "apply_effect":

        result.update(
            build_effect_request(
                text
            )
        )

    # --------------------------------------------------------
    # ITEM
    # --------------------------------------------------------

    elif action == "give_item":

        result.update(
            build_item_request(
                text
            )
        )

    # --------------------------------------------------------
    # SUMMON
    # --------------------------------------------------------

    elif action == "summon_entity":

        result.update(
            build_summon_request(
                text
            )
        )

    # --------------------------------------------------------
    # SCOREBOARD
    # --------------------------------------------------------

    elif action == "scoreboard":

        result.update(
            build_scoreboard_request(
                text
            )
        )

    # --------------------------------------------------------
    # UNKNOWN
    # --------------------------------------------------------

    else:

        result["message"] = (
            "The request was not specific enough "
            "for the current parser."
        )

    return result


# ============================================================
# DISPLAY
# ============================================================

def display_result(result):

    print("\n")
    print("=" * 70)
    print("MINECRAFT AI - REQUEST PARSER")
    print("=" * 70)

    print(
        json.dumps(
            result,
            indent=4
        )
    )

    print("=" * 70)


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("MINECRAFT AI - STRUCTURED REQUEST PARSER")
    print("Minecraft Java Edition 1.21.11")
    print("=" * 70)

    while True:

        user_text = input(
            "\nEnter Minecraft request (or 'exit'): "
        ).strip()

        if user_text.lower() == "exit":

            print("Exiting.")
            break

        if not user_text:
            continue

        result = parse_request(
            user_text
        )

        display_result(
            result
        )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()