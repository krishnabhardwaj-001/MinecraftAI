import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from generator.mechanisms.base import BaseMechanismGenerator
from generator.models import ActionSpecification, DatapackResource, FunctionDefinition


class FunctionMechanismGenerator(BaseMechanismGenerator):
    """
    Deterministic mechanism generator for Minecraft Java 1.21.11 .mcfunction files.
    Generates command files under 'data/<namespace>/function/'.
    Enforces vanilla syntax rules:
    - Synthesizes exact commands from structured ActionSpecification models
    - Strips illegal leading slashes from legacy raw commands
    - Preserves comment headers
    - Emits deterministic UNIX line endings (\n)
    """

    def __init__(self, version: str = "1.21.11"):
        self.version = version

    def _normalize_id(self, raw_id: Optional[str], default_prefix: str = "minecraft:") -> str:
        if not raw_id:
            return ""
        clean = str(raw_id).strip()
        if not clean:
            return clean
        if clean.startswith("#"):
            tag_name = clean[1:].strip()
            if ":" not in tag_name:
                return f"#{default_prefix}{tag_name}"
            return f"#{tag_name}"
        if ":" not in clean:
            return f"{default_prefix}{clean}"
        return clean

    def synthesize_action(self, action: ActionSpecification) -> Optional[str]:
        """
        Deterministically translates an ActionSpecification into a valid
        Minecraft Java 1.21.11 command string.
        """
        a_type = str(action.action_type).strip().lower()
        target = str(action.target or "@a").strip()

        # Build conditions prefix if specified
        cond_parts: List[str] = []
        for cond in (action.conditions or []):
            if isinstance(cond, dict):
                c_type = cond.get("type", "")
                if c_type == "predicate" or "predicate" in cond:
                    pred_id = self._normalize_id(cond.get("predicate"))
                    if pred_id:
                        cond_parts.append(f"if predicate {pred_id}")
                elif c_type == "score" or "score" in cond or "objective" in cond:
                    holder = cond.get("holder", cond.get("score_holder", "#global"))
                    obj = cond.get("objective", cond.get("score"))
                    matches = cond.get("matches", cond.get("value", 0))
                    if obj:
                        cond_parts.append(f"if score {holder} {obj} matches {matches}")

        cond_prefix = " ".join(cond_parts).strip()

        cmd_body = ""

        # 1. Effect actions
        if a_type in ("apply_effect", "effect", "give_effect"):
            eff_name = self._normalize_id(action.effect or "minecraft:speed")
            amplifier = max(0, int(action.amplifier or 0))
            hide_particles = "true" if not action.show_particles else "false"
            if action.duration == "infinite":
                cmd_body = f"effect give {target} {eff_name} infinite {amplifier} {hide_particles}"
            elif isinstance(action.duration, int):
                cmd_body = f"effect give {target} {eff_name} {action.duration} {amplifier} {hide_particles}"
            else:
                # Default behavior when duration is None:
                # Fall back to standard Minecraft default duration (30 seconds)
                cmd_body = f"effect give {target} {eff_name} 30 {amplifier} {hide_particles}"

        elif a_type in ("clear_effect", "remove_effect"):
            if action.effect:
                eff_name = self._normalize_id(action.effect)
                cmd_body = f"effect clear {target} {eff_name}"
            else:
                cmd_body = f"effect clear {target}"

        # 2. Item actions
        elif a_type in ("give_item", "give", "item"):
            item_id = self._normalize_id(action.item or "minecraft:diamond")
            count = max(1, int(action.count or 1))
            # Entity execution context: for player selectors in function execution,
            # pair 'execute as <target> at @s run give @s ...' to maintain anchor consistency
            if target in ("@a", "@p", "@s") or target.startswith("@"):
                cmd_body = f"execute as {target} at @s run give @s {item_id} {count}"
            else:
                cmd_body = f"give {target} {item_id} {count}"

        elif a_type in ("clear_item", "remove_item"):
            if action.item:
                item_id = self._normalize_id(action.item)
                count_str = f" {action.count}" if action.count is not None else ""
                cmd_body = f"clear {target} {item_id}{count_str}"
            else:
                cmd_body = f"clear {target}"

        # 3. Scoreboard actions
        elif a_type in ("set_score", "score_set"):
            holder = action.score_holder or target
            obj = action.objective or "state"
            val = action.score_value if action.score_value is not None else 0
            cmd_body = f"scoreboard players set {holder} {obj} {val}"

        elif a_type in ("add_score", "score_add"):
            holder = action.score_holder or target
            obj = action.objective or "state"
            val = action.score_value if action.score_value is not None else 1
            cmd_body = f"scoreboard players add {holder} {obj} {val}"

        elif a_type in ("reset_score", "score_reset"):
            holder = action.score_holder or target
            obj = action.objective or "state"
            cmd_body = f"scoreboard players reset {holder} {obj}"

        # 4. Audio / Visual
        elif a_type in ("play_sound", "sound"):
            sound_id = self._normalize_id(action.sound or "minecraft:entity.player.levelup")
            cmd_body = f"playsound {sound_id} master {target}"

        elif a_type in ("spawn_particle", "particle"):
            part_id = self._normalize_id(action.particle or "minecraft:happy_villager")
            cmd_body = f"particle {part_id} ~ ~ ~ 0.5 0.5 0.5 0 10"

        # 5. Communication
        elif a_type in ("send_message", "message", "say"):
            msg = action.message or "Hello"
            escaped_msg = msg.replace('"', '\\"')
            cmd_body = f'tellraw {target} {{"text": "{escaped_msg}"}}'

        # 6. Raw command escape hatch (audited)
        elif a_type == "raw_command":
            raw = (action.raw_command or "").strip()
            if raw.startswith("/") and not raw.startswith("//"):
                raw = raw[1:].strip()
            logger.warning(
                "AUDIT: ActionSpecification used raw_command escape hatch: '%s'",
                raw
            )
            cmd_body = raw

        else:
            # Fallback for generic or unknown action type
            if action.raw_command:
                raw = action.raw_command.strip()
                if raw.startswith("/") and not raw.startswith("//"):
                    raw = raw[1:].strip()
                logger.warning(
                    "AUDIT: ActionSpecification used raw_command escape hatch: '%s'",
                    raw
                )
                cmd_body = raw

        if not cmd_body:
            return None

        # Combine with condition prefix if present
        if cond_prefix:
            if cmd_body.startswith("execute "):
                merged = f"execute {cond_prefix} {cmd_body[8:]}"
                return merged
            return f"execute {cond_prefix} run {cmd_body}"

        return cmd_body

    def generate(self, spec: FunctionDefinition) -> List[DatapackResource]:
        clean_path = spec.function_path.strip().replace("\\", "/").strip("/")
        if not clean_path.endswith(".mcfunction"):
            clean_path = f"{clean_path}.mcfunction"

        lines: List[str] = []

        # Optional comment header
        if spec.description:
            for desc_line in spec.description.strip().splitlines():
                desc_clean = desc_line.strip()
                if not desc_clean.startswith("#"):
                    lines.append(f"# {desc_clean}")
                else:
                    lines.append(desc_clean)
        else:
            lines.append("# Generated by MinecraftAI")

        # 1. Synthesize commands from structured actions
        if spec.actions:
            for act in spec.actions:
                act_spec = act if isinstance(act, ActionSpecification) else ActionSpecification(**act)
                cmd = self.synthesize_action(act_spec)
                if cmd:
                    lines.append(cmd)

        # 2. Process and normalize legacy raw commands if present
        if spec.commands:
            for cmd in spec.commands:
                cmd_clean = cmd.strip()
                if not cmd_clean:
                    continue

                # Strip illegal leading slash if command is not a comment
                if cmd_clean.startswith("/") and not cmd_clean.startswith("//"):
                    cmd_clean = cmd_clean[1:].strip()

                lines.append(cmd_clean)

        content = "\n".join(lines) + "\n"
        namespace = spec.namespace or "minecraft"
        rel_path = f"data/{namespace}/function/{clean_path}"

        return [
            DatapackResource(
                relative_path=rel_path,
                content=content,
                resource_type="function"
            )
        ]
