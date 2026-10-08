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

    def __init__(self, version: str = "1.21.11", version_context: Optional[Any] = None):
        self.version = version
        self.version_context = version_context

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

        elif a_type in ("enable_trigger", "enable", "trigger_enable", "enable_scoreboard", "scoreboard_enable"):
            if obj:
                return f"scoreboard players enable {holder} {obj}"

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
    @staticmethod
    def _format_modifier_val(val: Any) -> str:
        try:
            f = float(val)
            if f.is_integer():
                i = int(f)
                return f"neg_{abs(i)}" if i < 0 else str(i)
            s = str(abs(f)).replace(".", "_")
            return f"neg_{s}" if f < 0 else s
        except (ValueError, TypeError):
            clean = re.sub(r"[^a-z0-9_.-]", "_", str(val).lower())
            return clean or "val"

    def _build_modifier_id(
        self,
        action: ActionSpecification,
        mod: Any,
        op_tag: str,
        val: Any,
    ) -> str:
        # 1. Explicit modifier_id on action
        act_mod_id = getattr(action, "modifier_id", None)
        if act_mod_id:
            custom = str(act_mod_id).strip().lower()
            if ":" in custom:
                return custom
            clean = re.sub(r"[^a-z0-9_.-]", "_", custom)
            return f"minecraft_ai:{clean}"

        # 2. Explicit modifier_id in extra_metadata
        extra_meta = getattr(mod, "extra_metadata", None) or {}
        if isinstance(extra_meta, dict) and extra_meta.get("modifier_id"):
            custom = str(extra_meta["modifier_id"]).strip().lower()
            if ":" in custom:
                return custom
            clean = re.sub(r"[^a-z0-9_.-]", "_", custom)
            return f"minecraft_ai:{clean}"

        # 3. Deterministic semantic modifier ID
        prop = mod.property or "property"
        clean_prop = re.sub(r"[^a-z0-9_.-]", "_", prop.strip().lower().split(".")[-1])
        val_str = self._format_modifier_val(val)

        # Optional step or action qualifier if present
        qualifier = ""
        q = getattr(action, "step_id", None) or getattr(action, "action_id", None)
        if not q and isinstance(extra_meta, dict):
            q = extra_meta.get("step_id") or extra_meta.get("action_id")
        if q:
            clean_q = re.sub(r"[^a-z0-9_.-]", "_", str(q).strip().lower())
            qualifier = f"_{clean_q}"

        return f"minecraft_ai:{clean_prop}_{op_tag}_{val_str}{qualifier}"

    def _generate_property_modification(self, action: ActionSpecification, target: str) -> Optional[str]:
        mod = action.property_modification
        if not mod or not mod.property:
            return None
        from ai.property_registry import DEFAULT_PROPERTY_REGISTRY
        cap = DEFAULT_PROPERTY_REGISTRY.lookup(mod.property)
        impl = action.implementation or (cap.primary_mechanism if cap else "attribute")

        extra_meta = getattr(mod, "extra_metadata", None) or {}
        if not isinstance(extra_meta, dict):
            extra_meta = {}

        identifier = None
        if cap:
            mech_cap = cap.get_mechanism(impl)
            if mech_cap and mech_cap.minecraft_identifier:
                identifier = mech_cap.minecraft_identifier
            elif cap.minecraft_identifier:
                identifier = cap.minecraft_identifier

        # 1. Attribute mechanism
        if impl == "attribute":
            attr_name = self._normalize_id(identifier or f"minecraft:generic.{mod.property}")
            if not mod.value or getattr(mod.value, "kind", None) == "qualitative":
                return None

            op = mod.operation or "set"
            val_kind = getattr(mod.value, "kind", "absolute")

            inner_cmd: Optional[str] = None

            if op == "set" and val_kind == "absolute":
                val = mod.value.value
                inner_cmd = f"attribute @s {attr_name} base set {val}"

            elif op in ("add", "subtract"):
                val = float(mod.value.value)
                if op == "subtract":
                    val = -val
                if val_kind == "percentage":
                    val = val / 100.0
                    mod_type = "add_multiplied_base"
                    op_tag = "add_pct" if op == "add" else "sub_pct"
                elif val_kind == "relative":
                    mod_type = "add_value"
                    op_tag = "add" if op == "add" else "sub"
                else:
                    return None
                mod_id = self._build_modifier_id(action, mod, op_tag, mod.value.value)
                inner_cmd = f"attribute @s {attr_name} modifier add {mod_id} {val} {mod_type}"

            elif op == "multiply" and val_kind == "multiplier":
                mult = float(mod.value.value)
                # Minecraft add_multiplied_total multiplies total by (1 + amount).
                # To multiply by M, modifier amount must be M - 1.0.
                amount = mult - 1.0
                mod_id = self._build_modifier_id(action, mod, "mult", mod.value.value)
                inner_cmd = f"attribute @s {attr_name} modifier add {mod_id} {amount} add_multiplied_total"

            elif op == "divide" and val_kind == "multiplier":
                div = float(mod.value.value)
                if div == 0:
                    return None
                amount = (1.0 / div) - 1.0
                mod_id = self._build_modifier_id(action, mod, "div", mod.value.value)
                inner_cmd = f"attribute @s {attr_name} modifier add {mod_id} {amount} add_multiplied_total"

            if not inner_cmd:
                return None

            if target == "@s":
                return inner_cmd
            else:
                return f"execute as {target} run {inner_cmd}"

        # 2. Effect mechanism
        elif impl == "effect":
            eff_name = self._normalize_id(identifier or f"minecraft:{mod.property}")

            # Effect CANNOT represent relative, multiplier, or qualitative semantics
            val_kind = getattr(mod.value, "kind", None) if mod.value else None
            if val_kind in ("multiplier", "relative", "qualitative"):
                return None

            if mod.operation not in ("set", None):
                return None

            # Effect CANNOT invent duration
            raw_duration = action.duration if action.duration is not None else extra_meta.get("duration")
            if raw_duration is None:
                return None

            if raw_duration == "infinite":
                dur_str = "infinite"
            else:
                try:
                    dur_str = str(int(raw_duration))
                except (ValueError, TypeError):
                    return None

            # Absolute level handling
            if mod.value and val_kind == "absolute":
                try:
                    val = float(mod.value.value)
                    amplifier = max(0, int(val) - 1)
                except (ValueError, TypeError):
                    amplifier = 0
            else:
                amplifier = max(0, int(action.amplifier or 0))

            hide_particles = "false" if action.show_particles else "true"
            return f"effect give {target} {eff_name} {dur_str} {amplifier} {hide_particles}"

        # 3. Scoreboard mechanism
        elif impl == "scoreboard":
            obj_name = mod.property or "property"
            op = mod.operation or "set"
            if not mod.value or getattr(mod.value, "kind", None) == "qualitative":
                return None
            try:
                val = int(mod.value.value)
            except (ValueError, TypeError):
                return None

            if op == "set":
                return f"scoreboard players set {target} {obj_name} {val}"
            elif op == "add":
                return f"scoreboard players add {target} {obj_name} {val}"
            elif op == "subtract":
                return f"scoreboard players remove {target} {obj_name} {val}"

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

        # Property modification actions (Step 17.5)
        if a_type in ("modify_property", "property_modification"):
            cmd_body = self._generate_property_modification(action, target) or ""

        # 1. Effect actions
        elif a_type in ("apply_effect", "effect", "give_effect"):
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
            "remove_objective", "objective_remove",
            "enable_trigger", "trigger_enable", "enable",
            "enable_scoreboard", "scoreboard_enable"
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
        elif a_type in ("tellraw", "send_message", "message", "say", "broadcast_message", "tellraw_clickable", "clickable_tellraw", "chat", "say_message", "display_chat"):
            if action.raw_command:
                cmd_body = action.raw_command
            elif getattr(action, "components", None):
                comp = action.components
                comp_json = json.dumps(comp, ensure_ascii=False) if not isinstance(comp, str) else comp
                cmd_body = f"tellraw {target} {comp_json}"
            else:
                msg = (action.message or "Hello").strip()
                if msg.startswith(("{", "[")):
                    try:
                        json.loads(msg)
                        cmd_body = f"tellraw {target} {msg}"
                    except Exception:
                        escaped_msg = msg.replace('"', '\\"')
                        cmd_body = f'tellraw {target} {{"text": "{escaped_msg}"}}'
                else:
                    escaped_msg = msg.replace('"', '\\"')
                    cmd_body = f'tellraw {target} {{"text": "{escaped_msg}"}}'

        # 6. Entity summoning
        elif a_type in ("summon_entity", "summon"):
            entity_id = self._normalize_id(action.entity or "minecraft:zombie")
            if target in ("@a", "@p", "@s") or target.startswith("@"):
                cmd_body = f"execute at {target} run summon {entity_id} ~ ~ ~"
            else:
                cmd_body = f"summon {entity_id} ~ ~ ~"

        # 7. Raw command escape hatch (audited)
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
