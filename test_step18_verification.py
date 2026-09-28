"""
test_step18_verification.py - Comprehensive Verification Gate for Step 18

Validates the full end-to-end Property Modification Pipeline, Static Validation,
QA Analysis, and Verification Gate for Minecraft Java 1.21.11.

Covers:
1. Validator Invariants: Attribute command syntax, single-entity target rules,
   valid 1.21.11 attribute IDs & aliases, modifier operations, numeric values, modifier IDs.
2. Generator Invariants: Mechanism extraction for property_modification,
   safe resource path derivation from property names (no '@a.mcfunction'), deterministic ZIP output.
3. QA Static Semantic Analysis Invariants: Context checking for unanchored 'attribute @s',
   duplicate modifier ID detection, hazardous attribute values (max_health <= 0, scale <= 0).
4. End-to-End Pipeline Invariants: Multipliers, relative additions, entity targets,
   compound requests, and structured clarification halts for missing/ambiguous parameters.
5. Layered Failure Injection: Verification that malformed targets, invalid operations,
   and duplicate modifier IDs are caught at the proper architectural layer.
6. Datapack Artifact Parity: Verification of root pack.mcmeta, data/ structure,
   and folder-to-ZIP integrity.
"""

import json
import re
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from ai.property_registry import PropertyCapabilityRegistry
from ai.semantic_models import PropertyModification, SemanticNumericValue
from ai.implementation_mapper import ImplementationMapper
from ai.planner import MinecraftPlanner
from generator.datapack_generator import DatapackGenerator
from generator.models import ActionSpecification, MechanismSpecification
from pipeline.minecraft_pipeline import MinecraftPipeline
from pipeline.models import PipelineResult
from qa.analyzer import StaticSemanticAnalyzer
from qa.models import QACategory, QASeverity
from validator.datapack_validator import DatapackValidator


class MockStep18AI:
    """
    Deterministic mock AI provider for testing Step 18 pipeline stages.
    """
    def __init__(self, understanding_handler=None, planner_handler=None, qa_handler=None):
        self.understanding_handler = understanding_handler
        self.planner_handler = planner_handler
        self.qa_handler = qa_handler
        self.calls = []

    def generate_structured(self, system_prompt: str, user_prompt: str, schema: Dict[str, Any]) -> Dict[str, Any]:
        self.calls.append({
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "schema": schema
        })
        sys_lower = system_prompt.lower()
        if "understanding layer" in sys_lower:
            if self.understanding_handler:
                return self.understanding_handler(user_prompt, schema)
            return {
                "status": "understood",
                "minecraft_version": "1.21.11",
                "edition": "Java",
                "understood_request": "Speed modification",
                "requirements": [
                    {
                        "intent": "modify_property",
                        "property": "speed",
                        "operation": "multiply",
                        "value": 10.0,
                        "value_kind": "multiplier",
                        "target": "@a"
                    }
                ]
            }
        elif "planning engine" in sys_lower:
            if self.planner_handler:
                return self.planner_handler(user_prompt, schema)
            return {
                "status": "ready",
                "minecraft_version": "1.21.11",
                "summary": "Plan for speed modification",
                "implementation_plan": [],
                "missing_knowledge": [],
                "clarifications": []
            }
        elif "qa reviewer" in sys_lower or "repair" in sys_lower:
            if self.qa_handler:
                return self.qa_handler(user_prompt, schema)
            return {
                "diagnosis": "Mock repair",
                "regenerate": True,
                "repaired_plan": {}
            }
        return {"status": "ready"}


class TestStep18ValidatorInvariants(unittest.TestCase):
    """
    Tests for DatapackValidator command and attribute validation.
    """

    def setUp(self):
        self.validator = DatapackValidator(version="1.21.11")
        self.temp_dir = tempfile.mkdtemp()
        self.dp_dir = Path(self.temp_dir) / "test_pack"
        self.fn_dir = self.dp_dir / "data" / "minecraft_ai" / "function"
        self.fn_dir.mkdir(parents=True, exist_ok=True)
        # Create minimal pack.mcmeta
        mcmeta = {
            "pack": {
                "pack_format": 48,
                "description": "Step 18 Test Pack"
            }
        }
        with open(self.dp_dir / "pack.mcmeta", "w", encoding="utf-8") as f:
            json.dump(mcmeta, f)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _write_function(self, name: str, lines: List[str]) -> Path:
        fn_path = self.fn_dir / f"{name}.mcfunction"
        with open(fn_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return fn_path

    def test_valid_attribute_commands_pass(self):
        """Valid 1.21.11 attribute commands pass validation without errors."""
        self._write_function("valid_attrs", [
            "execute as @a run attribute @s minecraft:generic.movement_speed modifier add minecraft_ai:speed_mult_10 9.0 add_multiplied_total",
            "execute as @a run attribute @s minecraft:movement_speed modifier add minecraft_ai:speed_add_5 5.0 add_value",
            "execute as @a run attribute @s minecraft:movement_speed modifier remove minecraft_ai:speed_add_5",
            "execute as @a run attribute @s minecraft:attack_damage base set 10.0",
            "execute as @a run attribute @s minecraft:attack_damage base get",
            "execute as @a run attribute @s minecraft:attack_damage base reset",
            "execute as @a run attribute @s minecraft:scale base set 1.5",
            "attribute @s minecraft:movement_speed get 1.0",
        ])
        result = self.validator.validate(self.dp_dir)
        attr_errors = [e for e in result.errors if "attribute" in e.message.lower() or "modifier" in e.message.lower()]
        self.assertEqual(len(attr_errors), 0, f"Expected 0 attribute errors, got: {attr_errors}")
        check_names = [c.name for c in result.checks]
        self.assertIn("Attribute Command & Modifier Validation", check_names)
        attr_check = next(c for c in result.checks if c.name == "Attribute Command & Modifier Validation")
        self.assertTrue(attr_check.passed)

    def test_multi_target_entity_rejected(self):
        """Direct attribute commands targeting @a or @e without limit=1 must be rejected."""
        self._write_function("multi_target", [
            "attribute @a minecraft:movement_speed base set 0.2",
            "attribute @e minecraft:attack_damage base set 5.0",
        ])
        result = self.validator.validate(self.dp_dir)
        target_errors = [e for e in result.errors if e.code == "INVALID_ATTRIBUTE_TARGET"]
        self.assertEqual(len(target_errors), 2)
        self.assertIn("@a", target_errors[0].message)
        self.assertIn("@e", target_errors[1].message)

    def test_single_target_entity_accepted(self):
        """Attribute commands with single-entity targets or limit=1 are accepted."""
        self._write_function("single_target", [
            "attribute @s minecraft:movement_speed base set 0.2",
            "attribute @p minecraft:movement_speed base set 0.2",
            "attribute @r minecraft:movement_speed base set 0.2",
            "attribute @a[limit=1] minecraft:movement_speed base set 0.2",
            "attribute @e[type=zombie,limit=1] minecraft:movement_speed base set 0.2",
        ])
        result = self.validator.validate(self.dp_dir)
        target_errors = [e for e in result.errors if e.code == "INVALID_ATTRIBUTE_TARGET"]
        self.assertEqual(len(target_errors), 0, f"Expected 0 target errors, got: {target_errors}")

    def test_invalid_attribute_id_rejected(self):
        """Unrecognized attribute IDs must be rejected with INVALID_ATTRIBUTE_ID."""
        self._write_function("invalid_attr", [
            "attribute @s minecraft:not_a_real_attribute base set 5.0",
        ])
        result = self.validator.validate(self.dp_dir)
        id_errors = [e for e in result.errors if e.code == "INVALID_ATTRIBUTE_ID"]
        self.assertEqual(len(id_errors), 1)
        self.assertIn("not_a_real_attribute", id_errors[0].message)

    def test_invalid_modifier_operation_rejected(self):
        """Modifier operations outside add_value, add_multiplied_base, add_multiplied_total are rejected."""
        self._write_function("invalid_op", [
            "attribute @s minecraft:movement_speed modifier add minecraft_ai:mod1 1.0 multiply",
            "attribute @s minecraft:movement_speed modifier add minecraft_ai:mod2 1.0 add",
        ])
        result = self.validator.validate(self.dp_dir)
        op_errors = [e for e in result.errors if e.code == "INVALID_MODIFIER_OPERATION"]
        self.assertEqual(len(op_errors), 2)

    def test_invalid_attribute_value_rejected(self):
        """Non-numeric values in base set or modifier add are rejected."""
        self._write_function("invalid_val", [
            "attribute @s minecraft:movement_speed base set not_a_number",
            "attribute @s minecraft:movement_speed modifier add minecraft_ai:mod1 bad_value add_value",
        ])
        result = self.validator.validate(self.dp_dir)
        val_errors = [e for e in result.errors if e.code == "INVALID_ATTRIBUTE_VALUE"]
        self.assertEqual(len(val_errors), 2)

    def test_invalid_modifier_id_rejected(self):
        """Invalid modifier identifier format is rejected with INVALID_MODIFIER_ID."""
        self._write_function("invalid_id", [
            "attribute @s minecraft:movement_speed modifier add NOT_VALID_$$$ 1.0 add_value",
        ])
        result = self.validator.validate(self.dp_dir)
        id_errors = [e for e in result.errors if e.code == "INVALID_MODIFIER_ID"]
        self.assertEqual(len(id_errors), 1)


class TestStep18GeneratorInvariants(unittest.TestCase):
    """
    Tests for DatapackGenerator extraction and synthesis of property modifications.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.output_dir = Path(self.temp_dir) / "output"
        self.generator = DatapackGenerator(output_dir=self.output_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_generator_extracts_property_modification_mechanism(self):
        """Generator correctly extracts property_modification mechanisms and produces valid mcfunction."""
        mod = PropertyModification(
            property="speed",
            operation="multiply",
            value=SemanticNumericValue(kind="multiplier", value=10.0),
        )
        mapper = ImplementationMapper()
        mapped = mapper.map_modification(mod, default_target="@a", step_id="step_0")

        plan = {
            "status": "ready",
            "implementation_plan": [
                {
                    "step_id": "step_0",
                    "mechanisms": [mapped.mechanism_spec]
                }
            ]
        }

        res = self.generator.generate(plan=plan)
        self.assertEqual(res.status, "success")
        self.assertTrue(res.datapack_path.exists())

        # Check function file generated
        fn_file = res.datapack_path / "data" / "minecraft_ai" / "function" / "modify_speed.mcfunction"
        self.assertTrue(fn_file.exists(), f"Expected {fn_file} to exist")

        with open(fn_file, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("attribute @s minecraft:generic.movement_speed modifier add minecraft_ai:speed_mult_10_step_0 9.0 add_multiplied_total", content)
        self.assertIn("execute as @a run", content)

    def test_generator_selector_target_does_not_corrupt_path(self):
        """Mechanism with selector target (e.g. '@a') and no explicit path derives clean function path."""
        spec = MechanismSpecification(
            type="property_modification",
            target="@a",
            property_modification=PropertyModification(
                property="attack_damage",
                operation="add",
                value=SemanticNumericValue(kind="relative", value=5.0),
            ),
            actions=[
                ActionSpecification(
                    action_type="raw_command",
                    raw_command="execute as @a run attribute @s minecraft:generic.attack_damage modifier add minecraft_ai:dmg_5 5.0 add_value"
                )
            ]
        )
        fn_def = spec.to_function_definition()
        self.assertFalse(fn_def.function_path.startswith("@"))
        self.assertEqual(fn_def.function_path, "modify_attack_damage")

    def test_generator_deterministic_zip_output(self):
        """Repeat generation produces identical files and matching ZIP contents."""
        mod = PropertyModification(
            property="speed",
            operation="add",
            value=SemanticNumericValue(kind="relative", value=5.0),
        )
        mapper = ImplementationMapper()
        mapped = mapper.map_modification(mod, default_target="@a", step_id="step_0")
        plan = {
            "status": "ready",
            "implementation_plan": [{"step_id": "step_0", "mechanisms": [mapped.mechanism_spec]}]
        }

        dir1 = Path(self.temp_dir) / "run1"
        dir2 = Path(self.temp_dir) / "run2"

        gen1 = DatapackGenerator(output_dir=dir1)
        res1 = gen1.generate(plan=plan)
        gen2 = DatapackGenerator(output_dir=dir2)
        res2 = gen2.generate(plan=plan)

        self.assertEqual(res1.status, "success")
        self.assertEqual(res2.status, "success")
        self.assertIsNotNone(res1.zip_path)
        self.assertIsNotNone(res2.zip_path)

        with zipfile.ZipFile(res1.zip_path, "r") as z1, zipfile.ZipFile(res2.zip_path, "r") as z2:
            self.assertEqual(sorted(z1.namelist()), sorted(z2.namelist()))
            for name in z1.namelist():
                self.assertEqual(z1.read(name), z2.read(name), f"File {name} differs between runs")


class TestStep18QAInvariants(unittest.TestCase):
    """
    Tests for StaticSemanticAnalyzer attribute semantics and modifier checks.
    """

    def setUp(self):
        self.analyzer = StaticSemanticAnalyzer(version="1.21.11")
        self.temp_dir = tempfile.mkdtemp()
        self.dp_dir = Path(self.temp_dir) / "qa_pack"
        self.fn_dir = self.dp_dir / "data" / "minecraft_ai" / "function"
        self.fn_dir.mkdir(parents=True, exist_ok=True)
        mcmeta = {"pack": {"pack_format": 48, "description": "QA Pack"}}
        with open(self.dp_dir / "pack.mcmeta", "w", encoding="utf-8") as f:
            json.dump(mcmeta, f)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _write_fn(self, name: str, lines: List[str]):
        with open(self.fn_dir / f"{name}.mcfunction", "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    def test_qa_catches_unanchored_attribute_at_s(self):
        """QA flags attribute @s without preceding 'as <target>' execution context."""
        self._write_fn("unanchored", [
            "attribute @s minecraft:movement_speed base set 0.2",
        ])
        findings = self.analyzer.analyze(self.dp_dir)
        ctx_findings = [f for f in findings if f.id.startswith("FIND-CTX-MISSING-AS")]
        self.assertTrue(len(ctx_findings) > 0, "Expected FIND-CTX-MISSING-AS finding")
        self.assertEqual(ctx_findings[0].severity, QASeverity.ERROR)

    def test_qa_catches_duplicate_modifier_id_same_target(self):
        """QA flags duplicate modifier ID added to same target entity without removal."""
        self._write_fn("dup_mod", [
            "execute as @a run attribute @s minecraft:movement_speed modifier add minecraft_ai:speed_boost 1.0 add_multiplied_total",
            "execute as @a run attribute @s minecraft:movement_speed modifier add minecraft_ai:speed_boost 1.0 add_multiplied_total",
        ])
        findings = self.analyzer.analyze(self.dp_dir)
        dup_findings = [f for f in findings if f.id.startswith("FIND-ATTR-DUP-MOD")]
        self.assertEqual(len(dup_findings), 1)
        self.assertIn("speed_boost", dup_findings[0].problem)
        self.assertEqual(dup_findings[0].severity, QASeverity.ERROR)

    def test_qa_permits_modifier_readd_after_removal(self):
        """QA permits adding a modifier ID after it was previously removed on the target."""
        self._write_fn("clean_readd", [
            "execute as @a run attribute @s minecraft:movement_speed modifier add minecraft_ai:speed_boost 1.0 add_multiplied_total",
            "execute as @a run attribute @s minecraft:movement_speed modifier remove minecraft_ai:speed_boost",
            "execute as @a run attribute @s minecraft:movement_speed modifier add minecraft_ai:speed_boost 2.0 add_multiplied_total",
        ])
        findings = self.analyzer.analyze(self.dp_dir)
        dup_findings = [f for f in findings if f.id.startswith("FIND-ATTR-DUP-MOD")]
        self.assertEqual(len(dup_findings), 0)

    def test_qa_catches_hazardous_max_health_zero(self):
        """QA flags hazardous max_health base set <= 0."""
        self._write_fn("zero_health", [
            "execute as @a run attribute @s minecraft:generic.max_health base set 0.0",
        ])
        findings = self.analyzer.analyze(self.dp_dir)
        health_findings = [f for f in findings if "HAZARD-HEALTH" in f.id]
        self.assertEqual(len(health_findings), 1)
        self.assertEqual(health_findings[0].severity, QASeverity.ERROR)

    def test_qa_catches_hazardous_scale_zero(self):
        """QA flags hazardous scale base set <= 0."""
        self._write_fn("zero_scale", [
            "execute as @a run attribute @s minecraft:generic.scale base set 0.0",
        ])
        findings = self.analyzer.analyze(self.dp_dir)
        scale_findings = [f for f in findings if "HAZARD-SCALE" in f.id]
        self.assertEqual(len(scale_findings), 1)
        self.assertEqual(scale_findings[0].severity, QASeverity.ERROR)


class TestStep18EndToEndPipeline(unittest.TestCase):
    """
    End-to-end pipeline execution tests for Step 18 property modifications.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.output_dir = Path(self.temp_dir) / "pipeline_output"

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_pipeline_e2e_speed_multiplier(self):
        """Pipeline runs 'make me 10 times faster' to verified ZIP with modifier."""
        def understanding_handler(prompt, schema):
            return {
                "status": "understood",
                "minecraft_version": "1.21.11",
                "edition": "Java",
                "understood_request": "Make player 10 times faster",
                "requirements": [
                    {
                        "intent": "modify_property",
                        "property": "speed",
                        "operation": "multiply",
                        "value": 10.0,
                        "value_kind": "multiplier",
                        "target": "@a"
                    }
                ]
            }

        mock_ai = MockStep18AI(understanding_handler=understanding_handler)
        pipeline = MinecraftPipeline(ai_provider=mock_ai, output_dir=self.output_dir, verbose=False)
        result: PipelineResult = pipeline.run("make me 10 times faster")

        self.assertIn(result.status, ("verified", "success"))
        self.assertIsNotNone(result.final_zip_path)
        self.assertTrue(Path(result.final_zip_path).exists())

        # Inspect generated mcfunction inside zip
        with zipfile.ZipFile(result.final_zip_path, "r") as zf:
            fn_names = [n for n in zf.namelist() if n.endswith(".mcfunction")]
            self.assertTrue(len(fn_names) > 0)
            content = zf.read(fn_names[0]).decode("utf-8")
            self.assertIn("attribute @s minecraft:generic.movement_speed modifier add", content)
            self.assertIn("9.0 add_multiplied_total", content)
            self.assertIn("execute as @a run", content)

    def test_pipeline_e2e_relative_speed(self):
        """Pipeline runs 'make me 5 faster' to additive modifier without error."""
        def understanding_handler(prompt, schema):
            return {
                "status": "understood",
                "minecraft_version": "1.21.11",
                "edition": "Java",
                "understood_request": "Make player 5 faster",
                "requirements": [
                    {
                        "intent": "modify_property",
                        "property": "speed",
                        "operation": "add",
                        "value": 5.0,
                        "value_kind": "relative",
                        "target": "@a"
                    }
                ]
            }

        mock_ai = MockStep18AI(understanding_handler=understanding_handler)
        pipeline = MinecraftPipeline(ai_provider=mock_ai, output_dir=self.output_dir, verbose=False)
        result: PipelineResult = pipeline.run("make me 5 faster")

        self.assertIn(result.status, ("verified", "success"))
        self.assertIsNotNone(result.final_zip_path)
        with zipfile.ZipFile(result.final_zip_path, "r") as zf:
            fn_names = [n for n in zf.namelist() if n.endswith(".mcfunction")]
            content = zf.read(fn_names[0]).decode("utf-8")
            self.assertIn("5.0 add_value", content)

    def test_pipeline_e2e_target_entity(self):
        """Pipeline applies property modification to specific entity target (zombies)."""
        def understanding_handler(prompt, schema):
            return {
                "status": "understood",
                "minecraft_version": "1.21.11",
                "edition": "Java",
                "understood_request": "Make zombies 2 times faster",
                "requirements": [
                    {
                        "intent": "modify_property",
                        "property": "speed",
                        "operation": "multiply",
                        "value": 2.0,
                        "value_kind": "multiplier",
                        "target": "@e[type=zombie]"
                    }
                ]
            }

        mock_ai = MockStep18AI(understanding_handler=understanding_handler)
        pipeline = MinecraftPipeline(ai_provider=mock_ai, output_dir=self.output_dir, verbose=False)
        result: PipelineResult = pipeline.run("make zombies 2 times faster")

        self.assertIn(result.status, ("verified", "success"))
        with zipfile.ZipFile(result.final_zip_path, "r") as zf:
            fn_names = [n for n in zf.namelist() if n.endswith(".mcfunction")]
            content = zf.read(fn_names[0]).decode("utf-8")
            self.assertIn("execute as @e[type=zombie] run attribute @s", content)

    def test_pipeline_e2e_clarification_on_missing_value(self):
        """Pipeline halts at planning stage with needs_clarification on missing value."""
        def understanding_handler(prompt, schema):
            return {
                "status": "understood",
                "minecraft_version": "1.21.11",
                "edition": "Java",
                "understood_request": "Make player faster (missing value)",
                "requirements": [
                    {
                        "intent": "modify_property",
                        "property": "speed",
                        "operation": "add",
                        "missing": ["value"],
                        "target": "@a"
                    }
                ]
            }

        mock_ai = MockStep18AI(understanding_handler=understanding_handler)
        pipeline = MinecraftPipeline(ai_provider=mock_ai, output_dir=self.output_dir, verbose=False)
        result: PipelineResult = pipeline.run("make me faster")

        self.assertEqual(result.status, "needs_clarification")
        self.assertIsNotNone(result.clarification)
        self.assertTrue(len(result.clarification_requirements) > 0)
        self.assertTrue(any(term in str(result.clarification).lower() for term in ("amount", "percentage", "multiplier", "value")))
        self.assertEqual(result.clarification_requirements[0].get("parameter"), "value")

    def test_pipeline_e2e_clarification_on_missing_property(self):
        """Pipeline halts with needs_clarification on ambiguous property ('make me better')."""
        def understanding_handler(prompt, schema):
            return {
                "status": "needs_clarification",
                "minecraft_version": "1.21.11",
                "edition": "Java",
                "clarification": {
                    "reason": "Request 'make me better' is ambiguous.",
                    "question": "Which specific attribute or capability should be improved?"
                },
                "requirements": []
            }

        mock_ai = MockStep18AI(understanding_handler=understanding_handler)
        pipeline = MinecraftPipeline(ai_provider=mock_ai, output_dir=self.output_dir, verbose=False)
        result: PipelineResult = pipeline.run("make me better")

        self.assertEqual(result.status, "needs_clarification")
        self.assertIn("attribute", result.clarification.lower())
        self.assertTrue(len(result.clarification_requirements) > 0)

    def test_pipeline_e2e_compound_with_give(self):
        """Compound request with both give command and attribute modification succeeds."""
        def understanding_handler(prompt, schema):
            return {
                "status": "understood",
                "minecraft_version": "1.21.11",
                "edition": "Java",
                "understood_request": "give me 5 diamonds and make me 2 times faster",
                "requirements": [
                    {
                        "intent": "give_item",
                        "item": "minecraft:diamond",
                        "count": 5,
                        "target": "@a"
                    },
                    {
                        "intent": "modify_property",
                        "property": "speed",
                        "operation": "multiply",
                        "value": 2.0,
                        "value_kind": "multiplier",
                        "target": "@a"
                    }
                ]
            }

        mock_ai = MockStep18AI(understanding_handler=understanding_handler)
        pipeline = MinecraftPipeline(ai_provider=mock_ai, output_dir=self.output_dir, verbose=False)
        result: PipelineResult = pipeline.run("give me 5 diamonds and make me 2 times faster")

        self.assertIn(result.status, ("verified", "success"))
        with zipfile.ZipFile(result.final_zip_path, "r") as zf:
            fn_names = [n for n in zf.namelist() if n.endswith(".mcfunction")]
            all_cmds = "\n".join(zf.read(fn).decode("utf-8") for fn in fn_names)
            self.assertIn("give @s minecraft:diamond 5", all_cmds)
            self.assertIn("attribute @s minecraft:generic.movement_speed modifier add", all_cmds)


class TestStep18LayeredFailureInjection(unittest.TestCase):
    """
    Validates that violations are rejected cleanly at the expected architectural layer.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_failure_injection_validator_invalid_target(self):
        """Injected un-anchored multi-target attribute is rejected at the validator layer."""
        validator = DatapackValidator(version="1.21.11")
        dp_dir = Path(self.temp_dir) / "pack_inj_target"
        fn_dir = dp_dir / "data" / "minecraft_ai" / "function"
        fn_dir.mkdir(parents=True, exist_ok=True)
        with open(dp_dir / "pack.mcmeta", "w", encoding="utf-8") as f:
            json.dump({"pack": {"pack_format": 48, "description": "Inj"}}, f)

        with open(fn_dir / "bad.mcfunction", "w", encoding="utf-8") as f:
            f.write("attribute @a minecraft:movement_speed base set 0.5\n")

        res = validator.validate(dp_dir)
        self.assertFalse(res.is_valid)
        self.assertTrue(any(e.code == "INVALID_ATTRIBUTE_TARGET" for e in res.errors))

    def test_failure_injection_qa_duplicate_modifier(self):
        """Injected duplicate modifier is rejected at the QA layer."""
        analyzer = StaticSemanticAnalyzer(version="1.21.11")
        dp_dir = Path(self.temp_dir) / "pack_inj_dup"
        fn_dir = dp_dir / "data" / "minecraft_ai" / "function"
        fn_dir.mkdir(parents=True, exist_ok=True)
        with open(dp_dir / "pack.mcmeta", "w", encoding="utf-8") as f:
            json.dump({"pack": {"pack_format": 48, "description": "Inj"}}, f)

        with open(fn_dir / "dup.mcfunction", "w", encoding="utf-8") as f:
            f.write(
                "execute as @a run attribute @s minecraft:movement_speed modifier add minecraft_ai:dup 1.0 add_value\n"
                "execute as @a run attribute @s minecraft:movement_speed modifier add minecraft_ai:dup 1.0 add_value\n"
            )

        findings = analyzer.analyze(dp_dir)
        self.assertTrue(any(f.id.startswith("FIND-ATTR-DUP-MOD") for f in findings))


class TestStep18ArtifactParity(unittest.TestCase):
    """
    Tests for directory and ZIP archive structure, formatting, and parity.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.output_dir = Path(self.temp_dir) / "out"

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_artifact_parity_folder_matches_zip(self):
        """Files in extracted directory match ZIP archive exactly."""
        gen = DatapackGenerator(output_dir=self.output_dir)
        mod = PropertyModification(
            property="speed",
            operation="multiply",
            value=SemanticNumericValue(kind="multiplier", value=3.0),
        )
        mapper = ImplementationMapper()
        mapped = mapper.map_modification(mod, default_target="@a", step_id="step_0")
        plan = {
            "status": "ready",
            "implementation_plan": [{"step_id": "step_0", "mechanisms": [mapped.mechanism_spec]}]
        }

        res = gen.generate(plan=plan)
        self.assertEqual(res.status, "success")
        self.assertIsNotNone(res.zip_path)

        with zipfile.ZipFile(res.zip_path, "r") as zf:
            zip_names = sorted(zf.namelist())
            # Verify root entries
            self.assertIn("pack.mcmeta", zip_names)
            self.assertTrue(any(n.startswith("data/") for n in zip_names))

            # Verify every file on disk matches zip
            for zip_name in zip_names:
                disk_file = res.datapack_path / zip_name
                self.assertTrue(disk_file.exists(), f"File {zip_name} missing on disk")
                self.assertEqual(disk_file.read_bytes(), zf.read(zip_name))


if __name__ == "__main__":
    unittest.main()
