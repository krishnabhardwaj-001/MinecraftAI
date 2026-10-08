"""
security/command_security.py - Minecraft Command Security & Sandbox Verification.

Verifies that commands synthesized and processed by MinecraftAI remain strictly
within authorized Minecraft Java command boundaries, and prevents any OS-level
shell injection, command execution, or unauthorized administrative actions.
"""

import re
from typing import List, Optional, Set


# Approved Minecraft Java command root verbs generated and supported by the pipeline
ALLOWED_COMMAND_VERBS: Set[str] = {
    "scoreboard",
    "tellraw",
    "give",
    "clear",
    "effect",
    "attribute",
    "execute",
    "function",
    "tag",
    "say",
    "summon",
    "tp",
    "teleport",
    "weather",
    "time",
    "playsound",
    "particle",
    "datapack",
    "reload",
}

# Dangerous shell execution patterns that must never appear in command synthesis
DANGEROUS_SHELL_PATTERNS = [
    re.compile(r"\b(?:cmd\.exe|powershell|bash|sh|zsh|wscript|cscript)\b", re.IGNORECASE),
    re.compile(r"[`$]\(.*\)", re.IGNORECASE),
    re.compile(r"[;&|`]", re.IGNORECASE),
    re.compile(r"\b(?:eval|exec|system|popen|subprocess)\b", re.IGNORECASE),
]


class CommandSecurityError(ValueError):
    """Raised when a command violates security rules or contains prohibited syntax."""
    pass


def validate_minecraft_command(command: str) -> str:
    """
    Validates a single Minecraft command line.

    Enforces:
    - Non-empty line.
    - Comments (# ...) are accepted as safe documentation.
    - No dangerous shell injection or execution tokens.
    - Root verb is a recognized Minecraft command verb.
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

    # Check for shell execution patterns
    for pat in DANGEROUS_SHELL_PATTERNS:
        if pat.search(cmd_body):
            raise CommandSecurityError(f"Prohibited shell or injection pattern detected in command: '{command}'")

    # Extract command root verb
    tokens = cmd_body.split()
    verb = tokens[0].lower() if tokens else ""

    if verb not in ALLOWED_COMMAND_VERBS:
        # Check if it starts with an execute prefix
        if not (verb == "execute" or cmd_body.startswith("execute")):
            raise CommandSecurityError(
                f"Unauthorized or unverified command verb '{verb}'. Permitted verbs: {sorted(list(ALLOWED_COMMAND_VERBS))}"
            )

    return cleaned


def validate_mcfunction_content(content: str) -> List[str]:
    """
    Validates all lines of an .mcfunction file for command safety.
    """
    validated_lines: List[str] = []
    for line in content.splitlines():
        trimmed = line.strip()
        if trimmed:
            val = validate_minecraft_command(trimmed)
            validated_lines.append(val)
        else:
            validated_lines.append("")

    return validated_lines
