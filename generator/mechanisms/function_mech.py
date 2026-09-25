import json
import logging
import re
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

from generator.mechanisms.base import BaseMechanismGenerator
from generator.models import (
    ActionSpecification,
    DatapackResource,
    FunctionDefinition,
    MechanismSpecification,
    ScoreboardObjectiveDefinition,
    ScoreCompareCondition,
)


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

    @staticmethod
    def _format_display_name(display_name: Union[str, Dict[str, Any]]) -> str:
        if isinstance(display_name, dict):
            return json.dumps(display_name, ensure_ascii=False)
        raw = str(display_name).strip()
        if (raw.startswith("{") and raw.endswith("}")) or (raw.startswith("[") and raw.endswith("]")):
            return raw
        if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
            return raw
        escaped = raw.replace('"', '\\"')
        return f'"{escaped}"'

    def synthesize_objective_command(
        self,
        obj_def: Union[ScoreboardObjectiveDefinition, MechanismSpecification, Dict[str, Any]]
    ) -> List[str]:
        """
        Deterministically translates a scoreboard objective definition into valid
        Minecraft Java 1.21.11 command strings (add and optional setdisplay).
        """
        if isinstance(obj_def, dict):
            obj = str(obj_def.get("objective") or obj_def.get("path") or obj_def.get("target") or "").strip()
            criteria = str(obj_def.get("criteria") or "dummy").strip()
            display_name = obj_def.get("display_name")
            display_slot = obj_def.get("display_slot")
        elif isinstance(obj_def, ScoreboardObjectiveDefinition):
            obj = obj_def.objective
            criteria = obj_def.criteria
            display_name = obj_def.display_name
            display_slot = obj_def.display_slot
        elif isinstance(obj_def, MechanismSpecification):
            obj = str(obj_def.objective or obj_def.path or obj_def.target or "").strip()
            crit = obj_def.criteria or "dummy"
            criteria = str(crit) if isinstance(crit, str) else "dummy"
            display_name = obj_def.display_name
            display_slot = obj_def.display_slot
        else:
            raise ValueError(f"Unsupported scoreboard objective type: {type(obj_def)}")

        if not obj:
            raise ValueError("Scoreboard objective name cannot be empty.")

        cmds: List[str] = []
        if display_name is not None and str(display_name).strip():
            formatted_name = self._format_display_name(display_name)
            cmds.append(f"scoreboard objectives add {obj} {criteria} {formatted_name}")
        else:
            cmds.append(f"scoreboard objectives add {obj} {criteria}")

        if display_slot:
            cmds.append(f"scoreboard objectives setdisplay {display_slot} {obj}")

        return cmds

    def _generate_score_action(self, action: ActionSpecification, a_type: str, target: str) -> Optional[str]:
        holder = action.score_holder or target
        obj = action.objective

        if a_type in ("set_score", "score_set"):
            target_obj = obj or "state"
            val = action.score_value if action.score_value is not None else 0
            return f"scoreboard players set {holder} {target_obj} {val}"

        elif a_type in ("add_score", "score_add"):
            target_obj = obj or "state"
            val = action.score_value if action.score_value is not None else 1
            return f"scoreboard players add {holder} {target_obj} {val}"

        elif a_type in ("remove_score", "score_remove"):
            target_obj = obj or "state"
            val = action.score_value if action.score_value is not None else 0
            return f"scoreboard players remove {holder} {target_obj} {val}"

        elif a_type in ("reset_score", "score_reset"):
            if obj:
                return f"scoreboard players reset {holder} {obj}"
            return f"scoreboard players reset {holder}"

        elif a_type in ("remove_objective", "objective_remove"):
            if obj:
                return f"scoreboard objectives remove {obj}"

        return None

    def _generate_score_operation(self, action: ActionSpecification, target: str) -> Optional[str]:
        target_holder = action.score_holder or target
        target_obj = action.objective
        op = action.operation
        source_holder = action.source_holder
        source_obj = action.source_objective

        if target_holder and target_obj and op and source_holder and source_obj:
            return f"scoreboard players operation {target_holder} {target_obj} {op} {source_holder} {source_obj}"
        return None

    def _generate_score_condition(self, cond: Union[Dict[str, Any], ScoreCompareCondition]) -> Optional[str]:
        if isinstance(cond, ScoreCompareCondition):
            prefix = "unless" if cond.inverted else "if"
            return f"{prefix} score {cond.target} {cond.target_objective} {cond.operator} {cond.source} {cond.source_objective}"

        if isinstance(cond, dict):
            c_type = str(cond.get("type", "")).strip().lower()
            if c_type == "score_compare":
                inv = bool(cond.get("inverted", False) or cond.get("unless", False))
                prefix = "unless" if inv else "if"
                target_h = cond.get("target") or cond.get("score_holder") or "@s"
                target_o = cond.get("target_objective") or cond.get("objective")
                op = cond.get("operator") or "="
                src_h = cond.get("source") or cond.get("source_holder") or "#global"
                src_o = cond.get("source_objective") or cond.get("objective")
                if target_o and src_o:
                    return f"{prefix} score {target_h} {target_o} {op} {src_h} {src_o}"
            elif c_type == "score" or "score" in cond or "objective" in cond:
                holder = cond.get("holder", cond.get("score_holder", cond.get("target", "#global")))
                obj = cond.get("objective", cond.get("score"))
                matches = cond.get("matches", cond.get("range", cond.get("value", 0)))
                inv = bool(cond.get("inverted", False) or cond.get("unless", False))
                prefix = "unless" if inv else "if"
                if obj:
                    return f"{prefix} score {holder} {obj} matches {matches}"
        return None

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
            if isinstance(cond, ScoreCompareCondition):
                score_cond = self._generate_score_condition(cond)
                if score_cond:
                    cond_parts.append(score_cond)
            elif isinstance(cond, dict):
                c_type = str(cond.get("type", "")).strip().lower()
                if c_type == "predicate" or "predicate" in cond:
                    pred_id = self._normalize_id(cond.get("predicate"))
                    if pred_id:
                        inv = bool(cond.get("inverted", False) or cond.get("unless", False))
                        prefix = "unless" if inv else "if"
                        cond_parts.append(f"{prefix} predicate {pred_id}")
                else:
                    score_cond = self._generate_score_condition(cond)
                    if score_cond:
                        cond_parts.append(score_cond)

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
        elif a_type in (
            "set_score", "score_set",
            "add_score", "score_add",
            "remove_score", "score_remove",
            "reset_score", "score_reset",
            "remove_objective", "objective_remove"
        ):
            cmd_body = self._generate_score_action(action, a_type, target) or ""

        elif a_type in ("operation_score", "score_operation"):
            cmd_body = self._generate_score_operation(action, target) or ""

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
