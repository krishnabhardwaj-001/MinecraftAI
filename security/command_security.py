"""
security/command_security.py - Minecraft Command Security & Sandbox Verification.

Verifies that commands synthesized and processed by MinecraftAI remain strictly
within authorized Minecraft Java command boundaries, and prevents any OS-level
shell injection, command execution, or unauthorized administrative actions.
"""

import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set

# Administrative / operator commands that must not be executed or generated in datapacks
BLOCKED_ADMIN_COMMANDS: Set[str] = {
    "ban",
    "ban-ip",
    "banlist",
    "deop",
    "kick",
    "op",
    "pardon",
    "pardon-ip",
    "publish",
    "save-all",
    "save-off",
    "save-on",
    "setidletimeout",
    "stop",
    "whitelist",
}

# Fallback approved Minecraft Java command verbs (datapack safe)
DEFAULT_DATAPACK_COMMAND_VERBS: Set[str] = {
    "advancement",
    "attribute",
    "bossbar",
    "clear",
    "clone",
    "damage",
    "data",
    "datapack",
    "debug",
    "defaultgamemode",
    "dialog",
    "difficulty",
    "effect",
    "enchant",
    "execute",
    "experience",
    "fetchprofile",
    "fill",
    "fillbiome",
    "forceload",
    "function",
    "gamemode",
    "gamerule",
    "give",
    "help",
    "item",
    "jfr",
    "kill",
    "list",
    "locate",
    "loot",
    "me",
    "msg",
    "particle",
    "perf",
    "place",
    "playsound",
    "random",
    "recipe",
    "reload",
    "return",
    "ride",
    "rotate",
    "say",
    "schedule",
    "scoreboard",
    "seed",
    "setblock",
    "spawnpoint",
    "spectate",
    "spreadplayers",
    "stopsound",
    "stopwatch",
    "summon",
    "tag",
    "team",
    "teammsg",
    "teleport",
    "tellraw",
    "test",
    "tick",
    "time",
    "title",
    "tp",
    "transfer",
    "trigger",
    "version",
    "waypoint",
    "weather",
    "worldborder",
}

_ALLOWED_VERBS_CACHE: Dict[str, Set[str]] = {}


def load_allowed_command_verbs(version: Optional[str] = None) -> Set[str]:
    """
    Dynamically loads approved Minecraft command verbs from authoritative knowledge assets
    in knowledge/commands/java/{version}/commands.jsonl.
    Excludes server-administrative commands (ban, op, stop, etc.).
    """
    cache_key = version or "all"
    if cache_key in _ALLOWED_VERBS_CACHE:
        return _ALLOWED_VERBS_CACHE[cache_key]

    base_knowledge_dir = Path(__file__).resolve().parent.parent / "knowledge" / "commands" / "java"
    loaded_verbs: Set[str] = set()

    if base_knowledge_dir.exists():
        if version:
            target_files = [base_knowledge_dir / version / "commands.jsonl"]
        else:
            target_files = list(base_knowledge_dir.glob("*/commands.jsonl"))

        for tf in target_files:
            if tf.exists():
                try:
                    with open(tf, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                data = json.loads(line)
                                cmd = data.get("command")
                                if cmd and cmd.lower() not in BLOCKED_ADMIN_COMMANDS:
                                    loaded_verbs.add(cmd.lower())
                except Exception:
                    pass

    if not loaded_verbs:
        loaded_verbs = set(DEFAULT_DATAPACK_COMMAND_VERBS)

    _ALLOWED_VERBS_CACHE[cache_key] = loaded_verbs
    return loaded_verbs


# Initialized set of allowed command verbs for backwards compatibility
ALLOWED_COMMAND_VERBS: Set[str] = load_allowed_command_verbs()

# Dangerous shell execution patterns that must never appear in command structure
DANGEROUS_SHELL_PATTERNS = [
    re.compile(r"\b(?:cmd\.exe|powershell|bash|sh|zsh|wscript|cscript)\b", re.IGNORECASE),
    re.compile(r"[`$]\(.*\)", re.IGNORECASE),
    re.compile(r"[;&|`]", re.IGNORECASE),
    re.compile(r"\b(?:eval|exec|system|popen|subprocess)\b", re.IGNORECASE),
]


class CommandSecurityError(ValueError):
    """Raised when a command violates security rules or contains prohibited syntax."""
    pass


def _mask_command_for_security_check(cmd_body: str) -> str:
    """
    Extracts the structural part of a command for shell-injection pattern checks,
    masking JSON text components, NBT compounds, quoted strings, and free-text chat messages.
    """
    # 1. Check for free-text chat commands (say, me, teammsg)
    # Even when chained via execute ... run say
    m_chat = re.search(r'(?:^|\b(?:run)\s+)(say|me|teammsg)\s+(.*)$', cmd_body, re.IGNORECASE)
    if m_chat:
        prefix = cmd_body[:m_chat.start(2)]
        return prefix + '""'

    # 2. Mask JSON objects/arrays/NBT compounds {...} and quoted strings "...", '...'
    chars: List[str] = []
    i = 0
    n = len(cmd_body)
    while i < n:
        c = cmd_body[i]
        if c in ('"', "'"):
            q = c
            i += 1
            while i < n:
                if cmd_body[i] == '\\':
                    i += 2
                    continue
                if cmd_body[i] == q:
                    i += 1
                    break
                i += 1
            chars.append('""')
        elif c == '{':
            depth = 1
            i += 1
            while i < n and depth > 0:
                if cmd_body[i] in ('"', "'"):
                    q = cmd_body[i]
                    i += 1
                    while i < n:
                        if cmd_body[i] == '\\':
                            i += 2
                            continue
                        if cmd_body[i] == q:
                            i += 1
                            break
                        i += 1
                elif cmd_body[i] == '{':
                    depth += 1
                    i += 1
                elif cmd_body[i] == '}':
                    depth -= 1
                    i += 1
                else:
                    i += 1
            chars.append('{}')
        else:
            chars.append(c)
            i += 1

    return ''.join(chars)


def extract_command_verbs(cmd_body: str) -> List[str]:
    """
    Extracts the root command verb and any subcommand verbs chained via execute ... run <subcommand>.
    """
    tokens = cmd_body.split()
    if not tokens:
        return []

    verbs = [tokens[0].lower()]

    # If it's an execute command, find all subcommands following 'run'
    # e.g., 'execute as @a run give @s diamond' -> ['execute', 'give']
    i = 0
    while i < len(tokens):
        if tokens[i].lower() == "run" and i + 1 < len(tokens):
            verbs.append(tokens[i + 1].lower())
        i += 1

    return verbs


def validate_minecraft_command(
    command: str,
    allowed_verbs: Optional[Set[str]] = None,
    version: Optional[str] = None
) -> str:
    """
    Validates a single Minecraft command line.

    Enforces:
    - Non-empty line.
    - Comments (# ...) are accepted as safe documentation.
    - No dangerous shell injection or execution tokens in the command structure.
    - Root verb and all execute subcommand verbs are recognized Minecraft command verbs.
    """
    if not isinstance(command, str):
        raise CommandSecurityError("Command must be a string.")

    cleaned = command.strip()
    if not cleaned:
        return ""

    # Comments are safe
    if cleaned.startswith("#"):
        return cleaned

    # Strip optional leading slash if present
    cmd_body = cleaned[1:].strip() if cleaned.startswith("/") else cleaned

    # Check for shell execution patterns on command structure (ignoring JSON / strings / chat text)
    structural_cmd = _mask_command_for_security_check(cmd_body)
    for pat in DANGEROUS_SHELL_PATTERNS:
        if pat.search(structural_cmd):
            raise CommandSecurityError(f"Prohibited shell or injection pattern detected in command: '{command}'")

    # Determine allowed verbs
    effective_verbs = allowed_verbs or (load_allowed_command_verbs(version) if version else ALLOWED_COMMAND_VERBS)

    # Extract all command verbs (root verb + any verbs chained with 'run')
    verbs = extract_command_verbs(cmd_body)
    for verb in verbs:
        if verb not in effective_verbs:
            raise CommandSecurityError(
                f"Unauthorized or unverified command verb '{verb}'. Permitted verbs: {sorted(list(effective_verbs))}"
            )

    return cleaned


def validate_mcfunction_content(
    content: str,
    allowed_verbs: Optional[Set[str]] = None,
    version: Optional[str] = None
) -> List[str]:
    """
    Validates all lines of an .mcfunction file for command safety.
    """
    validated_lines: List[str] = []
    for line in content.splitlines():
        trimmed = line.strip()
        if trimmed:
            val = validate_minecraft_command(trimmed, allowed_verbs=allowed_verbs, version=version)
            validated_lines.append(val)
        else:
            validated_lines.append("")

    return validated_lines
