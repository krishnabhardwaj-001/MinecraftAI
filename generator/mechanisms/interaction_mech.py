"""
Deterministic Interaction Mechanism Generator for Minecraft Java Edition.
Supports Minecraft Java 1.21.11 and 1.21.1.

Transforms semantic InteractionSpecification and InteractionOption contracts into
server-side, datapack-compatible Minecraft resources:
- Scoreboard objectives using vanilla /trigger for safe, unprivileged player choice submission
- tellraw interactive prompts with run_command clickEvents and show_text hoverEvents
- Deterministic lifecycle functions (init, open, tick, select_<id>, cancel, timeout)
- Game loop function tag integration (#minecraft:load, #minecraft:tick)
"""

import hashlib
import json
import re
from typing import Any, Dict, List, Optional, Union

from ai.version_registry import VersionContext
from generator.mechanisms.base import BaseMechanismGenerator
from generator.mechanisms.function_mech import FunctionMechanismGenerator
from generator.models import (
    ActionSpecification,
    DatapackResource,
    InteractionOption,
    InteractionSpecification,
    MechanismSpecification,
)


def derive_objective_name(interaction_name: str, prefix: str = "trg_") -> str:
    """
    Deterministically derives a valid Minecraft scoreboard objective name (1-16 chars)
    from an interaction name.
    Scoreboard objective names in Minecraft Java Edition have a hard limit of 16 characters.
    """
    clean = re.sub(r"[^a-zA-Z0-9_]", "", interaction_name.lower())
    clean = clean.strip("_") or "int"
    candidate = f"{prefix}{clean}"
    if len(candidate) <= 16:
        return candidate

    # Use prefix + truncated clean name + _ + 5-char deterministic SHA256 hex digest
    h = hashlib.sha256(interaction_name.encode("utf-8")).hexdigest()[:5]
    prefix_len = len(prefix)
    avail = 16 - prefix_len - 1 - len(h)  # 16 - 4 - 1 - 5 = 6 chars
    short_clean = clean[:avail] if avail > 0 else clean[:4]
    return f"{prefix}{short_clean}_{h}"


class InteractionMechanismGenerator(BaseMechanismGenerator):
    """
    Deterministic mechanism generator for Minecraft Java 1.21.11 and 1.21.1 interactions.
    Generates:
    - data/<namespace>/function/interaction/<name>/init.mcfunction
    - data/<namespace>/function/interaction/<name>/open.mcfunction
    - data/<namespace>/function/interaction/<name>/tick.mcfunction
    - data/<namespace>/function/interaction/<name>/select_<id>.mcfunction (per option)
    - data/<namespace>/function/interaction/<name>/cancel.mcfunction (if cancellation allowed)
    - data/<namespace>/function/interaction/<name>/timeout.mcfunction (if timeout configured)
    - data/minecraft/tags/function/load.json (#minecraft:load tag)
    - data/minecraft/tags/function/tick.json (#minecraft:tick tag)
    """

    def __init__(self, version: str = "1.21.11", version_context: Optional[VersionContext] = None):
        self.version_context = version_context or VersionContext.from_version(version)
        self.version = self.version_context.version_id
        self.func_gen = FunctionMechanismGenerator(version=self.version, version_context=self.version_context)

    def _resolve_target_selector(self, target_scope: Optional[str]) -> str:
        scope = (target_scope or "self").strip().lower()
        if scope == "self":
            return "@s"
        elif scope == "player":
            return "@p"
        elif scope == "all_players":
            return "@a"
        elif scope == "target":
            return "@s"
        return "@s"

    def _resolve_cancel_id(self, options: List[InteractionOption]) -> int:
        """
        Determines a reserved integer score for cancellation that is guaranteed
        never to collide with any defined option ID.
        """
        existing_ids = {opt.id for opt in options}
        if 999 not in existing_ids:
            return 999
        return max(existing_ids, default=0) + 1

    def _build_tellraw_components(
        self,
        interaction: InteractionSpecification,
        trigger_obj: str,
        cancel_id: int
    ) -> List[Dict[str, Any]]:
        """
        Constructs deterministic JSON text components for tellraw interactive display.
        """
        components: List[Dict[str, Any]] = [
            {"text": "=== ", "color": "gold", "bold": True},
            {"text": interaction.prompt or interaction.name, "color": "yellow", "bold": True},
            {"text": " ===\n", "color": "gold", "bold": True},
        ]

        # Deterministically iterate options sorted by ID
        sorted_options = sorted(interaction.options, key=lambda o: o.id)
        for opt in sorted_options:
            hover_text = opt.description or f"Select {opt.label}"
            opt_entry: Dict[str, Any] = {
                "text": f"  [ {opt.label} ]",
                "color": "aqua",
                "bold": True,
                "clickEvent": {
                    "action": "run_command",
                    "value": f"/trigger {trigger_obj} set {opt.id}"
                },
                "hoverEvent": {
                    "action": "show_text",
                    "contents": hover_text
                }
            }
            components.append(opt_entry)
            components.append({"text": "\n"})

        if interaction.allow_cancel:
            cancel_label = interaction.cancel_label or "Cancel"
            cancel_entry: Dict[str, Any] = {
                "text": f"  [ {cancel_label} ]",
                "color": "red",
                "bold": True,
                "clickEvent": {
                    "action": "run_command",
                    "value": f"/trigger {trigger_obj} set {cancel_id}"
                },
                "hoverEvent": {
                    "action": "show_text",
                    "contents": "Cancel and close this interaction"
                }
            }
            components.append(cancel_entry)
            components.append({"text": "\n"})

        return components

    def generate(self, spec: Union[MechanismSpecification, InteractionSpecification, Dict[str, Any]]) -> List[DatapackResource]:
        """
        Deterministically transforms an InteractionSpecification into concrete DatapackResource instances.
        """
        if isinstance(spec, MechanismSpecification):
            interaction = spec.to_interaction_specification()
            ns = spec.namespace or "minecraft_ai"
        elif isinstance(spec, InteractionSpecification):
            interaction = spec
            ns = "minecraft_ai"
        elif isinstance(spec, dict):
            if "interaction" in spec and spec["interaction"] is not None:
                raw_int = spec["interaction"]
                interaction = raw_int if isinstance(raw_int, InteractionSpecification) else InteractionSpecification.model_validate(raw_int)
                ns = spec.get("namespace") or "minecraft_ai"
            else:
                interaction = InteractionSpecification.model_validate(spec)
                ns = "minecraft_ai"
        else:
            raise ValueError(f"Expected MechanismSpecification, InteractionSpecification, or dict, got {type(spec)}")

        clean_name = re.sub(r"[^a-zA-Z0-9_]", "_", interaction.name.lower()).strip("_") or "interaction"
        func_base = f"data/{ns}/function/interaction/{clean_name}"

        # Deterministic objective names (1-16 chars)
        trigger_obj = derive_objective_name(clean_name, prefix="trg_")
        act_obj = derive_objective_name(clean_name, prefix="act_")
        timer_obj = derive_objective_name(clean_name, prefix="tmr_")
        cancel_id = self._resolve_cancel_id(interaction.options)
        target_sel = self._resolve_target_selector(interaction.target_scope)

        resources: List[DatapackResource] = []

        # -------------------------------------------------------------
        # 1. init.mcfunction: Objective Declarations
        # -------------------------------------------------------------
        init_lines: List[str] = [
            f"# Generated by MinecraftAI - Interaction Setup: {interaction.name}",
            f"scoreboard objectives add {trigger_obj} trigger",
            f"scoreboard objectives add {act_obj} dummy",
        ]
        if interaction.timeout_seconds is not None:
            init_lines.append(f"scoreboard objectives add {timer_obj} dummy")

        resources.append(
            DatapackResource(
                relative_path=f"{func_base}/init.mcfunction",
                content="\n".join(init_lines) + "\n",
                resource_type="function"
            )
        )

        # -------------------------------------------------------------
        # 2. open.mcfunction: Presentation & Trigger Enabling
        # -------------------------------------------------------------
        tellraw_components = self._build_tellraw_components(interaction, trigger_obj, cancel_id)
        tellraw_json = json.dumps(tellraw_components, ensure_ascii=False)

        open_lines: List[str] = [
            f"# Generated by MinecraftAI - Open Interaction: {interaction.name}",
            f"scoreboard players enable {target_sel} {trigger_obj}",
            f"scoreboard players set {target_sel} {act_obj} 1",
        ]
        if interaction.timeout_seconds is not None:
            open_lines.append(f"scoreboard players set {target_sel} {timer_obj} 0")

        open_lines.append(f"tellraw {target_sel} {tellraw_json}")

        resources.append(
            DatapackResource(
                relative_path=f"{func_base}/open.mcfunction",
                content="\n".join(open_lines) + "\n",
                resource_type="function"
            )
        )

        # -------------------------------------------------------------
        # 3. select_<id>.mcfunction: Option Dispatch Handlers
        # -------------------------------------------------------------
        sorted_options = sorted(interaction.options, key=lambda o: o.id)
        for opt in sorted_options:
            select_lines: List[str] = [
                f"# Generated by MinecraftAI - Option Selection: {opt.label} (ID: {opt.id})",
            ]

            # Synthesize actions
            if opt.actions:
                for action in opt.actions:
                    cmd = self.func_gen.synthesize_action(action)
                    if cmd:
                        if opt.condition_predicate:
                            select_lines.append(f"execute if predicate {opt.condition_predicate} run {cmd}")
                        else:
                            select_lines.append(cmd)
            else:
                select_lines.append(f'tellraw @s {{"text": "Selected: {opt.label}", "color": "green"}}')

            # Reset score and active state
            select_lines.append(f"scoreboard players reset @s {trigger_obj}")
            select_lines.append(f"scoreboard players set @s {act_obj} 0")
            if interaction.timeout_seconds is not None:
                select_lines.append(f"scoreboard players reset @s {timer_obj}")

            resources.append(
                DatapackResource(
                    relative_path=f"{func_base}/select_{opt.id}.mcfunction",
                    content="\n".join(select_lines) + "\n",
                    resource_type="function"
                )
            )

        # -------------------------------------------------------------
        # 4. cancel.mcfunction: Cancellation Handler
        # -------------------------------------------------------------
        if interaction.allow_cancel:
            cancel_lines: List[str] = [
                f"# Generated by MinecraftAI - Cancel Interaction: {interaction.name}",
                f"scoreboard players reset @s {trigger_obj}",
                f"scoreboard players set @s {act_obj} 0",
            ]
            if interaction.timeout_seconds is not None:
                cancel_lines.append(f"scoreboard players reset @s {timer_obj}")
            cancel_lines.append('tellraw @s {"text": "Interaction cancelled.", "color": "gray"}')

            resources.append(
                DatapackResource(
                    relative_path=f"{func_base}/cancel.mcfunction",
                    content="\n".join(cancel_lines) + "\n",
                    resource_type="function"
                )
            )

        # -------------------------------------------------------------
        # 5. timeout.mcfunction: Timeout Expiration Handler
        # -------------------------------------------------------------
        if interaction.timeout_seconds is not None:
            timeout_lines: List[str] = [
                f"# Generated by MinecraftAI - Interaction Timeout: {interaction.name}",
                f"scoreboard players reset @s {trigger_obj}",
                f"scoreboard players set @s {act_obj} 0",
                f"scoreboard players reset @s {timer_obj}",
                'tellraw @s {"text": "Interaction timed out.", "color": "gray"}',
            ]
            resources.append(
                DatapackResource(
                    relative_path=f"{func_base}/timeout.mcfunction",
                    content="\n".join(timeout_lines) + "\n",
                    resource_type="function"
                )
            )

        # -------------------------------------------------------------
        # 6. tick.mcfunction: Choice Detection & Timer Loop
        # -------------------------------------------------------------
        tick_lines: List[str] = [
            f"# Generated by MinecraftAI - Interaction Tick Loop: {interaction.name}",
        ]

        # Item trigger activation check
        if interaction.interaction_type == "item_trigger" and interaction.trigger_item:
            item_id = interaction.trigger_item.strip()
            if ":" not in item_id:
                item_id = f"minecraft:{item_id}"
            tick_lines.append(
                f'execute as @a[scores={{{act_obj}=0}}] at @s if entity @s[nbt={{SelectedItem:{{id:"{item_id}"}}}}] run function {ns}:interaction/{clean_name}/open'
            )

        # Choice detection for each option
        for opt in sorted_options:
            tick_lines.append(
                f"execute as @a[scores={{{trigger_obj}={opt.id}}}] at @s run function {ns}:interaction/{clean_name}/select_{opt.id}"
            )

        # Cancellation detection
        if interaction.allow_cancel:
            tick_lines.append(
                f"execute as @a[scores={{{trigger_obj}={cancel_id}}}] at @s run function {ns}:interaction/{clean_name}/cancel"
            )

        # Timeout tracking
        if interaction.timeout_seconds is not None:
            timeout_ticks = int(interaction.timeout_seconds) * 20
            tick_lines.append(f"execute as @a[scores={{{act_obj}=1}}] run scoreboard players add @s {timer_obj} 1")
            tick_lines.append(
                f"execute as @a[scores={{{act_obj}=1,{timer_obj}={timeout_ticks}..}}] at @s run function {ns}:interaction/{clean_name}/timeout"
            )

        resources.append(
            DatapackResource(
                relative_path=f"{func_base}/tick.mcfunction",
                content="\n".join(tick_lines) + "\n",
                resource_type="function"
            )
        )

        # -------------------------------------------------------------
        # 7. Lifecycle Function Tags: load.json and tick.json
        # -------------------------------------------------------------
        load_tag_json = json.dumps({"values": [f"{ns}:interaction/{clean_name}/init"]}, indent=2, ensure_ascii=False) + "\n"
        resources.append(
            DatapackResource(
                relative_path="data/minecraft/tags/function/load.json",
                content=load_tag_json,
                resource_type="function_tag"
            )
        )

        tick_tag_json = json.dumps({"values": [f"{ns}:interaction/{clean_name}/tick"]}, indent=2, ensure_ascii=False) + "\n"
        resources.append(
            DatapackResource(
                relative_path="data/minecraft/tags/function/tick.json",
                content=tick_tag_json,
                resource_type="function_tag"
            )
        )

        return resources
