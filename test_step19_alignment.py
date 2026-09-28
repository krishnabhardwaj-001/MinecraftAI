"""
test_step19_alignment.py - Step 19: Pipeline & Interface Alignment Test Suite

Verifies:
1. Web API exposes clarification_requirements.
2. Web clarification options are rendered from structured data.
3. CLI displays structured clarification choices.
4. Selected clarification option is propagated correctly.
5. Web UI contains all 8 authoritative stages.
6. QA detects missing property implementation.
7. QA accepts correctly generated property implementation.
8. Duplicate attribute modifier finding is repaired.
9. Repair remains deterministic.
10. No regression in existing pipeline behavior.
"""

import copy
import io
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from pipeline.models import PipelineResult
from qa.models import QACategory, QAFinding, QAResult, QASeverity, IntentVerificationResult
from qa.reviewer import AutonomousQAReviewer as QAReviewer
from qa.repair import QARepairEngine
from ai.semantic_models import PropertyModification, SemanticNumericValue
from generator.models import ActionSpecification, MechanismSpecification


class TestStep19Alignment(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    # -------------------------------------------------------------------------
    # 1. Web API exposes clarification_requirements
    # -------------------------------------------------------------------------
    def test_1_web_api_exposes_clarification_requirements(self):
        from fastapi.testclient import TestClient
        from web.app import app

        mock_clarif_reqs = [
            {
                "parameter": "property",
                "question": "Which property would you like to modify?",
                "options": ["speed", "health", "attack_damage"],
            }
        ]

        mock_result = PipelineResult(
            status="needs_clarification",
            minecraft_version="1.21.11",
            original_request="make me stronger",
            clarification="Which property would you like to modify?",
            clarification_requirements=mock_clarif_reqs,
            execution_summary="Pipeline halted at planner stage: implementation requires clarification."
        )

        with patch("web.app.run_minecraft_pipeline", return_value=mock_result):
            client = TestClient(app)
            resp = client.post("/api/generate", json={"request": "make me stronger"})
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["status"], "needs_clarification")
            self.assertEqual(data["clarification"], "Which property would you like to modify?")
            self.assertIn("clarification_requirements", data)
            self.assertEqual(data["clarification_requirements"], mock_clarif_reqs)

    # -------------------------------------------------------------------------
    # 2. Web clarification options rendered from structured data
    # -------------------------------------------------------------------------
    def test_2_web_clarification_options_rendered_from_structured_data(self):
        # Verify HTML template contains clarification options container
        html_path = Path("web/templates/index.html")
        self.assertTrue(html_path.exists())
        html_content = html_path.read_text(encoding="utf-8")
        self.assertIn('id="clarificationOptionsSection"', html_content)
        self.assertIn('id="clarificationOptionsChips"', html_content)

        # Verify app.js dynamically renders chips from data.clarification_requirements
        js_path = Path("web/static/js/app.js")
        self.assertTrue(js_path.exists())
        js_content = js_path.read_text(encoding="utf-8")
        self.assertIn("data.clarification_requirements", js_content)
        self.assertIn("chip-option", js_content)
        self.assertIn("clarificationOptionsChips", js_content)

        # Verify no hardcoded options exist in app.js
        self.assertNotIn("'+10'", js_content)
        self.assertNotIn("'10x'", js_content)
        self.assertNotIn("'+10%'", js_content)

    # -------------------------------------------------------------------------
    # 3. CLI displays structured clarification choices
    # -------------------------------------------------------------------------
    def test_3_cli_displays_structured_clarification_choices(self):
        import run_pipeline

        mock_clarif_reqs = [
            {
                "parameter": "operation",
                "question": "What type of speed modification?",
                "options": ["speed +5", "speed x2", "speed set 0.2"],
            }
        ]

        mock_result = PipelineResult(
            status="needs_clarification",
            minecraft_version="1.21.11",
            original_request="speed up",
            clarification="What type of speed modification?",
            clarification_requirements=mock_clarif_reqs,
            execution_summary="Pipeline halted."
        )

        captured_stdout = io.StringIO()
        with patch("sys.stdout", captured_stdout):
            exit_code = run_pipeline.run_cli(
                args=["speed up"],
                input_fn=lambda prompt: "quit",
                pipeline_fn=lambda **kwargs: mock_result
            )

        output = captured_stdout.getvalue()
        self.assertEqual(exit_code, 2)
        self.assertIn("Available choices:", output)
        self.assertIn("[1] speed +5", output)
        self.assertIn("[2] speed x2", output)
        self.assertIn("[3] speed set 0.2", output)

    # -------------------------------------------------------------------------
    # 4. Selected clarification option is propagated correctly
    # -------------------------------------------------------------------------
    def test_4_selected_clarification_option_is_propagated_correctly(self):
        import run_pipeline

        mock_clarif_reqs = [
            {
                "parameter": "operation",
                "question": "What speed modification?",
                "options": ["speed +5", "speed x2"],
            }
        ]

        result_clarif = PipelineResult(
            status="needs_clarification",
            minecraft_version="1.21.11",
            original_request="make me faster",
            clarification="What speed modification?",
            clarification_requirements=mock_clarif_reqs,
            execution_summary="Needs clarification"
        )

        result_success = PipelineResult(
            status="success",
            minecraft_version="1.21.11",
            original_request="make me faster Specifically: speed +5.",
            final_datapack_path=str(self.test_dir / "datapack"),
            execution_summary="Datapack successfully created"
        )

        calls = []

        def mock_pipeline_fn(**kwargs):
            req = kwargs.get("request")
            calls.append(req)
            if len(calls) == 1:
                return result_clarif
            return result_success

        captured_stdout = io.StringIO()
        with patch("sys.stdout", captured_stdout):
            exit_code = run_pipeline.run_cli(
                args=["make me faster"],
                input_fn=lambda prompt: "1",
                pipeline_fn=mock_pipeline_fn
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], "make me faster")
        self.assertIn("speed +5", calls[1])
        self.assertIn("Specifically:", calls[1])

    # -------------------------------------------------------------------------
    # 5. Web UI contains all 8 authoritative stages
    # -------------------------------------------------------------------------
    def test_5_web_ui_contains_all_8_authoritative_stages(self):
        html_path = Path("web/templates/index.html")
        html = html_path.read_text(encoding="utf-8")

        expected_stages = [
            (1, "Understanding"),
            (2, "RAG Retrieval"),
            (3, "Planning"),
            (4, "Generator"),
            (5, "Validation & Repair"),
            (6, "Autonomous QA"),
            (7, "Intent Verification"),
            (8, "READY Gate"),
        ]

        for num, title in expected_stages:
            self.assertIn(f'id="stage{num}"', html, f"Missing stage{num} in index.html")
            self.assertIn(f'id="statusStage{num}"', html, f"Missing statusStage{num} in index.html")
            self.assertIn(title, html, f"Missing stage title '{title}' in index.html")

        # Verify JavaScript tracker handles all 8 stages
        js_path = Path("web/static/js/app.js")
        js = js_path.read_text(encoding="utf-8")
        for num in range(1, 9):
            self.assertIn(f"stage{num}", js)
            self.assertIn(f"statusStage{num}", js)

    # -------------------------------------------------------------------------
    # 6. QA detects missing property implementation
    # -------------------------------------------------------------------------
    def test_6_qa_detects_missing_property_implementation(self):
        reviewer = QAReviewer()

        dp_dir = self.test_dir / "unimplemented_prop_dp"
        dp_dir.mkdir(parents=True)
        fn_dir = dp_dir / "data" / "minecraft_ai" / "function"
        fn_dir.mkdir(parents=True)
        # Function has diamond give, but lacks the requested speed property modification
        (fn_dir / "tick.mcfunction").write_text("give @a diamond 1\n", encoding="utf-8")

        plan = {
            "status": "ready",
            "minecraft_version": "1.21.11",
            "summary": "speed modification plan",
            "implementation_plan": [
                {
                    "requirement_index": 0,
                    "objective": "speed +5",
                    "property_modification": {
                        "property": "speed",
                        "operation": "add",
                        "value": {"kind": "relative", "value": 5.0}
                    },
                    "mechanisms": []
                }
            ]
        }

        qa_res = reviewer.review(
            datapack_dir=dp_dir,
            original_request="speed +5",
            plan=plan,
            understanding={"requirements": [{"property": "speed"}]}
        )

        self.assertFalse(qa_res.intent_verification.matches_intent)
        self.assertTrue(any("speed" in m.lower() for m in qa_res.intent_verification.missing_aspects))
        self.assertEqual(qa_res.status, "failed")
        self.assertTrue(any(f.category == QACategory.INTENT_MISMATCH for f in qa_res.findings))

    # -------------------------------------------------------------------------
    # 7. QA accepts correctly generated property implementation
    # -------------------------------------------------------------------------
    def test_7_qa_accepts_correctly_generated_property_implementation(self):
        reviewer = QAReviewer()

        dp_dir = self.test_dir / "implemented_prop_dp"
        dp_dir.mkdir(parents=True)
        fn_dir = dp_dir / "data" / "minecraft_ai" / "function"
        fn_dir.mkdir(parents=True)
        # Function contains the exact attribute command for generic.movement_speed
        (fn_dir / "tick.mcfunction").write_text(
            "execute as @a run attribute @s minecraft:generic.movement_speed modifier add minecraft_ai:speed_add_5 5.0 add_value\n",
            encoding="utf-8"
        )

        plan = {
            "status": "ready",
            "minecraft_version": "1.21.11",
            "summary": "speed modification plan",
            "implementation_plan": [
                {
                    "requirement_index": 0,
                    "objective": "speed +5",
                    "property_modification": {
                        "property": "speed",
                        "operation": "add",
                        "value": {"kind": "relative", "value": 5.0}
                    },
                    "mechanisms": []
                }
            ]
        }

        qa_res = reviewer.review(
            datapack_dir=dp_dir,
            original_request="speed +5",
            plan=plan,
            understanding={"requirements": [{"property": "speed"}]}
        )

        self.assertTrue(qa_res.intent_verification.matches_intent)
        self.assertEqual(len(qa_res.intent_verification.missing_aspects), 0)
        self.assertIn("Verified generated implementation for property 'speed'", qa_res.intent_verification.reasoning)

    # -------------------------------------------------------------------------
    # 7b. QA rejects wrong operation/value (Step 19 remediation: speed x10 vs speed set 5)
    # -------------------------------------------------------------------------
    def test_7b_qa_rejects_wrong_operation_or_value(self):
        reviewer = QAReviewer()

        dp_dir = self.test_dir / "wrong_op_dp"
        dp_dir.mkdir(parents=True)
        fn_dir = dp_dir / "data" / "minecraft_ai" / "function"
        fn_dir.mkdir(parents=True)
        # Function contains 'base set 5' instead of multiplier 'add_multiplied_total 9.0'
        (fn_dir / "tick.mcfunction").write_text(
            "attribute @a minecraft:generic.movement_speed base set 5\n",
            encoding="utf-8"
        )

        plan = {
            "status": "ready",
            "minecraft_version": "1.21.11",
            "summary": "speed multiply 10 plan",
            "implementation_plan": [
                {
                    "requirement_index": 0,
                    "objective": "speed ×10",
                    "property_modification": {
                        "property": "speed",
                        "operation": "multiply",
                        "value": {"kind": "multiplier", "value": 10.0}
                    },
                    "mechanisms": []
                }
            ]
        }

        qa_res = reviewer.review(
            datapack_dir=dp_dir,
            original_request="speed ×10",
            plan=plan,
            understanding={"requirements": [{"property": "speed"}]}
        )

        self.assertFalse(qa_res.intent_verification.matches_intent)
        self.assertEqual(qa_res.status, "failed")
        self.assertTrue(any("speed" in m.lower() for m in qa_res.intent_verification.missing_aspects))
        self.assertTrue(any(f.category == QACategory.INTENT_MISMATCH for f in qa_res.findings))

    # -------------------------------------------------------------------------
    # 7c. QA rejects wrong numeric value (Step 19 remediation: speed +5 vs speed +2)
    # -------------------------------------------------------------------------
    def test_7c_qa_rejects_wrong_numeric_value(self):
        reviewer = QAReviewer()

        dp_dir = self.test_dir / "wrong_num_dp"
        dp_dir.mkdir(parents=True)
        fn_dir = dp_dir / "data" / "minecraft_ai" / "function"
        fn_dir.mkdir(parents=True)
        # Function contains amount 2.0 instead of requested 5.0
        (fn_dir / "tick.mcfunction").write_text(
            "execute as @a run attribute @s minecraft:generic.movement_speed modifier add minecraft_ai:speed_add_2 2.0 add_value\n",
            encoding="utf-8"
        )

        plan = {
            "status": "ready",
            "minecraft_version": "1.21.11",
            "summary": "speed add 5 plan",
            "implementation_plan": [
                {
                    "requirement_index": 0,
                    "objective": "speed +5",
                    "property_modification": {
                        "property": "speed",
                        "operation": "add",
                        "value": {"kind": "relative", "value": 5.0}
                    },
                    "mechanisms": []
                }
            ]
        }

        qa_res = reviewer.review(
            datapack_dir=dp_dir,
            original_request="speed +5",
            plan=plan,
            understanding={"requirements": [{"property": "speed"}]}
        )

        self.assertFalse(qa_res.intent_verification.matches_intent)
        self.assertEqual(qa_res.status, "failed")
        self.assertTrue(any("speed" in m.lower() for m in qa_res.intent_verification.missing_aspects))

    # -------------------------------------------------------------------------
    # 7d. QA rejects wrong value kind (Step 19 remediation: speed +25% vs speed +25 relative)
    # -------------------------------------------------------------------------
    def test_7d_qa_rejects_wrong_value_kind(self):
        reviewer = QAReviewer()

        dp_dir = self.test_dir / "wrong_kind_dp"
        dp_dir.mkdir(parents=True)
        fn_dir = dp_dir / "data" / "minecraft_ai" / "function"
        fn_dir.mkdir(parents=True)
        # Function contains 'add_value 25.0' instead of 'add_multiplied_base 0.25'
        (fn_dir / "tick.mcfunction").write_text(
            "execute as @a run attribute @s minecraft:generic.movement_speed modifier add minecraft_ai:speed_add_25 25.0 add_value\n",
            encoding="utf-8"
        )

        plan = {
            "status": "ready",
            "minecraft_version": "1.21.11",
            "summary": "speed add 25 percent plan",
            "implementation_plan": [
                {
                    "requirement_index": 0,
                    "objective": "speed +25%",
                    "property_modification": {
                        "property": "speed",
                        "operation": "add",
                        "value": {"kind": "percentage", "value": 25.0}
                    },
                    "mechanisms": []
                }
            ]
        }

        qa_res = reviewer.review(
            datapack_dir=dp_dir,
            original_request="speed +25%",
            plan=plan,
            understanding={"requirements": [{"property": "speed"}]}
        )

        self.assertFalse(qa_res.intent_verification.matches_intent)
        self.assertEqual(qa_res.status, "failed")
        self.assertTrue(any("speed" in m.lower() for m in qa_res.intent_verification.missing_aspects))

    # -------------------------------------------------------------------------
    # 7e. QA verifies correct target and mechanism (Step 19 remediation)
    # -------------------------------------------------------------------------
    def test_7e_qa_verifies_target_and_mechanism(self):
        reviewer = QAReviewer()

        dp_dir = self.test_dir / "zombie_target_dp"
        dp_dir.mkdir(parents=True)
        fn_dir = dp_dir / "data" / "minecraft_ai" / "function"
        fn_dir.mkdir(parents=True)
        # Valid zombie targeting command
        (fn_dir / "tick.mcfunction").write_text(
            "execute as @e[type=zombie] run attribute @s minecraft:generic.movement_speed modifier add minecraft_ai:speed_mult_2 1.0 add_multiplied_total\n",
            encoding="utf-8"
        )

        plan = {
            "status": "ready",
            "minecraft_version": "1.21.11",
            "summary": "double zombie speed",
            "implementation_plan": [
                {
                    "requirement_index": 0,
                    "objective": "double zombie speed",
                    "property_modification": {
                        "property": "speed",
                        "operation": "multiply",
                        "value": {"kind": "multiplier", "value": 2.0},
                        "target": "@e[type=zombie]"
                    },
                    "mechanisms": []
                }
            ]
        }

        qa_res = reviewer.review(
            datapack_dir=dp_dir,
            original_request="double zombie speed",
            plan=plan,
            understanding={"requirements": [{"property": "speed"}]}
        )

        self.assertTrue(qa_res.intent_verification.matches_intent)
        self.assertEqual(len(qa_res.intent_verification.missing_aspects), 0)

        # Mismatched target test: if command targeted @a instead of @e[type=zombie]
        (fn_dir / "tick.mcfunction").write_text(
            "execute as @a run attribute @s minecraft:generic.movement_speed modifier add minecraft_ai:speed_mult_2 1.0 add_multiplied_total\n",
            encoding="utf-8"
        )
        qa_res2 = reviewer.review(
            datapack_dir=dp_dir,
            original_request="double zombie speed",
            plan=plan,
            understanding={"requirements": [{"property": "speed"}]}
        )
        self.assertFalse(qa_res2.intent_verification.matches_intent)
        self.assertTrue(any("speed" in m.lower() for m in qa_res2.intent_verification.missing_aspects))

    # -------------------------------------------------------------------------
    # 8. Duplicate attribute modifier finding is repaired
    # -------------------------------------------------------------------------
    def test_8_duplicate_attribute_modifier_finding_is_repaired(self):
        repair_engine = QARepairEngine()

        dup_finding = QAFinding(
            id="FIND-ATTR-DUP-MOD-2",
            severity=QASeverity.ERROR,
            category=QACategory.COMMAND_SEMANTICS,
            file="data/minecraft_ai/function/tick.mcfunction",
            line_or_reference="Line 2: attribute @s minecraft:generic.movement_speed modifier add minecraft_ai:speed_mult_2 1.0 add_multiplied_total",
            problem="Duplicate attribute modifier ID 'minecraft_ai:speed_mult_2' added to @s without prior removal.",
            explanation="Duplicate attribute modifier",
            expected_behavior="Unique modifier IDs",
            repair_required="Assign unique modifier ID"
        )

        qa_res = QAResult(
            status="failed",
            summary="QA failed: duplicate attribute modifier",
            findings=[dup_finding],
            intent_verification=IntentVerificationResult(
                matches_intent=True, reasoning="Matches", missing_aspects=[], unwanted_aspects=[]
            )
        )

        plan = {
            "status": "ready",
            "minecraft_version": "1.21.11",
            "summary": "Double speed plan",
            "implementation_plan": [
                {
                    "requirement_index": 0,
                    "objective": "double speed twice",
                    "mechanisms": [
                        {
                            "type": "function",
                            "namespace": "minecraft_ai",
                            "path": "tick",
                            "actions": [
                                {
                                    "action_type": "property_modification",
                                    "target": "@a",
                                    "modifier_id": "speed_mult_2",
                                    "property_modification": {
                                        "property": "speed",
                                        "operation": "multiply",
                                        "value": {"kind": "multiplier", "value": 2.0}
                                    }
                                },
                                {
                                    "action_type": "property_modification",
                                    "target": "@a",
                                    "modifier_id": "speed_mult_2",
                                    "property_modification": {
                                        "property": "speed",
                                        "operation": "multiply",
                                        "value": {"kind": "multiplier", "value": 2.0}
                                    }
                                }
                            ]
                        }
                    ]
                }
            ]
        }

        repair_plan, repaired_plan = repair_engine.diagnose_and_repair(
            qa_result=qa_res,
            plan=plan
        )

        self.assertTrue(repair_plan.regenerate)
        self.assertIn("Duplicate attribute modifier ID", repair_plan.diagnosis)

        # Verify second action's modifier_id was disambiguated
        actions = repaired_plan["implementation_plan"][0]["mechanisms"][0]["actions"]
        self.assertEqual(actions[0]["modifier_id"], "speed_mult_2")
        self.assertEqual(actions[1]["modifier_id"], "speed_mult_2_1")

    # -------------------------------------------------------------------------
    # 8b. Duplicate modifier skips colliding existing IDs (Step 19 remediation)
    # -------------------------------------------------------------------------
    def test_8b_duplicate_modifier_skips_colliding_existing_ids(self):
        repair_engine = QARepairEngine()

        dup_finding = QAFinding(
            id="FIND-ATTR-DUP-MOD-4",
            severity=QASeverity.ERROR,
            category=QACategory.COMMAND_SEMANTICS,
            problem="Duplicate attribute modifier ID 'minecraft_ai:speed_add_5_step_0' detected.",
            explanation="Duplicate attribute modifier",
            expected_behavior="Unique modifier IDs"
        )
        qa_res = QAResult(
            status="failed",
            summary="QA failed",
            findings=[dup_finding],
            intent_verification=IntentVerificationResult(
                matches_intent=True, reasoning="Matches", missing_aspects=[], unwanted_aspects=[]
            )
        )

        # Plan with existing IDs:
        # Action 0: speed_add_5_step_0
        # Action 1: speed_add_5_step_0 (duplicate of Action 0)
        # Action 2: speed_add_5_step_1 (already existing in plan!)
        # Action 3: health_add_10 (independent action)
        plan = {
            "status": "ready",
            "minecraft_version": "1.21.11",
            "summary": "Colliding IDs plan",
            "implementation_plan": [
                {
                    "requirement_index": 0,
                    "objective": "colliding actions",
                    "mechanisms": [
                        {
                            "type": "function",
                            "namespace": "minecraft_ai",
                            "path": "tick",
                            "actions": [
                                {
                                    "action_type": "property_modification",
                                    "target": "@a",
                                    "modifier_id": "speed_add_5_step_0",
                                    "property_modification": {"property": "speed", "operation": "add", "value": {"kind": "relative", "value": 5.0}}
                                },
                                {
                                    "action_type": "property_modification",
                                    "target": "@a",
                                    "modifier_id": "speed_add_5_step_0",
                                    "property_modification": {"property": "speed", "operation": "add", "value": {"kind": "relative", "value": 5.0}}
                                },
                                {
                                    "action_type": "property_modification",
                                    "target": "@a",
                                    "modifier_id": "speed_add_5_step_1",
                                    "property_modification": {"property": "speed", "operation": "add", "value": {"kind": "relative", "value": 5.0}}
                                },
                                {
                                    "action_type": "property_modification",
                                    "target": "@a",
                                    "modifier_id": "health_add_10",
                                    "property_modification": {"property": "health", "operation": "add", "value": {"kind": "relative", "value": 10.0}}
                                }
                            ]
                        }
                    ]
                }
            ]
        }

        repair_plan, repaired_plan = repair_engine.diagnose_and_repair(qa_res, plan)
        actions = repaired_plan["implementation_plan"][0]["mechanisms"][0]["actions"]
        ids = [a["modifier_id"] for a in actions]

        # Action 0 preserved
        self.assertEqual(ids[0], "speed_add_5_step_0")
        # Action 1 disambiguated to next unused ID (speed_add_5_step_2, skipping speed_add_5_step_1)
        self.assertEqual(ids[1], "speed_add_5_step_2")
        # Action 2 preserved
        self.assertEqual(ids[2], "speed_add_5_step_1")
        # Action 3 preserved
        self.assertEqual(ids[3], "health_add_10")
        # All resulting IDs are unique
        self.assertEqual(len(ids), len(set(ids)))

    # -------------------------------------------------------------------------
    # 8c. Custom unique modifier IDs remain unchanged (Step 19 remediation)
    # -------------------------------------------------------------------------
    def test_8c_custom_unique_modifier_id_preserved(self):
        repair_engine = QARepairEngine()

        dup_finding = QAFinding(
            id="FIND-ATTR-DUP-MOD-5",
            severity=QASeverity.ERROR,
            category=QACategory.COMMAND_SEMANTICS,
            problem="Duplicate attribute modifier ID 'minecraft_ai:dup_action' detected.",
            explanation="Duplicate attribute modifier",
            expected_behavior="Unique modifier IDs"
        )
        qa_res = QAResult(
            status="failed",
            summary="QA failed",
            findings=[dup_finding],
            intent_verification=IntentVerificationResult(
                matches_intent=True, reasoning="Matches", missing_aspects=[], unwanted_aspects=[]
            )
        )

        plan = {
            "status": "ready",
            "minecraft_version": "1.21.11",
            "summary": "Custom ID preservation plan",
            "implementation_plan": [
                {
                    "requirement_index": 0,
                    "objective": "custom and duplicate",
                    "mechanisms": [
                        {
                            "type": "function",
                            "namespace": "minecraft_ai",
                            "path": "tick",
                            "actions": [
                                {
                                    "action_type": "property_modification",
                                    "target": "@a",
                                    "modifier_id": "my_custom_user_modifier",
                                    "property_modification": {"property": "speed", "operation": "add", "value": {"kind": "relative", "value": 1.0}}
                                },
                                {
                                    "action_type": "property_modification",
                                    "target": "@a",
                                    "modifier_id": "dup_action",
                                    "property_modification": {"property": "speed", "operation": "add", "value": {"kind": "relative", "value": 2.0}}
                                },
                                {
                                    "action_type": "property_modification",
                                    "target": "@a",
                                    "modifier_id": "dup_action",
                                    "property_modification": {"property": "speed", "operation": "add", "value": {"kind": "relative", "value": 2.0}}
                                }
                            ]
                        }
                    ]
                }
            ]
        }

        repair_plan, repaired_plan = repair_engine.diagnose_and_repair(qa_res, plan)
        actions = repaired_plan["implementation_plan"][0]["mechanisms"][0]["actions"]
        ids = [a["modifier_id"] for a in actions]

        self.assertEqual(ids[0], "my_custom_user_modifier")
        self.assertEqual(ids[1], "dup_action")
        self.assertEqual(ids[2], "dup_action_1")
        self.assertEqual(len(ids), len(set(ids)))

    # -------------------------------------------------------------------------
    # 9. Repair remains deterministic
    # -------------------------------------------------------------------------
    def test_9_repair_remains_deterministic(self):
        repair_engine = QARepairEngine()

        dup_finding = QAFinding(
            id="FIND-ATTR-DUP-MOD-3",
            severity=QASeverity.ERROR,
            category=QACategory.COMMAND_SEMANTICS,
            problem="Duplicate attribute modifier ID 'minecraft_ai:health_add_10' added to @s without prior removal.",
            explanation="Duplicate attribute modifier",
            expected_behavior="Unique modifier IDs"
        )

        qa_res = QAResult(
            status="failed",
            summary="QA failed",
            findings=[dup_finding],
            intent_verification=IntentVerificationResult(
                matches_intent=True, reasoning="Matches", missing_aspects=[], unwanted_aspects=[]
            )
        )

        base_plan = {
            "status": "ready",
            "minecraft_version": "1.21.11",
            "summary": "Duplicate health modifiers",
            "implementation_plan": [
                {
                    "requirement_index": 0,
                    "objective": "health +10 twice",
                    "mechanisms": [
                        {
                            "type": "function",
                            "namespace": "minecraft_ai",
                            "path": "tick",
                            "actions": [
                                {
                                    "action_type": "property_modification",
                                    "target": "@a",
                                    "modifier_id": "health_add_10",
                                    "property_modification": {"property": "health", "operation": "add", "value": {"kind": "relative", "value": 10.0}}
                                },
                                {
                                    "action_type": "property_modification",
                                    "target": "@a",
                                    "modifier_id": "health_add_10",
                                    "property_modification": {"property": "health", "operation": "add", "value": {"kind": "relative", "value": 10.0}}
                                },
                                {
                                    "action_type": "property_modification",
                                    "target": "@a",
                                    "modifier_id": "health_add_10",
                                    "property_modification": {"property": "health", "operation": "add", "value": {"kind": "relative", "value": 10.0}}
                                }
                            ]
                        }
                    ]
                }
            ]
        }

        # Run 1
        plan_copy1 = copy.deepcopy(base_plan)
        rplan1, rep1 = repair_engine.diagnose_and_repair(qa_res, plan_copy1)
        actions1 = rep1["implementation_plan"][0]["mechanisms"][0]["actions"]
        ids1 = [a["modifier_id"] for a in actions1]

        # Run 2
        plan_copy2 = copy.deepcopy(base_plan)
        rplan2, rep2 = repair_engine.diagnose_and_repair(qa_res, plan_copy2)
        actions2 = rep2["implementation_plan"][0]["mechanisms"][0]["actions"]
        ids2 = [a["modifier_id"] for a in actions2]

        self.assertEqual(ids1, ["health_add_10", "health_add_10_1", "health_add_10_2"])
        self.assertEqual(ids1, ids2)
        self.assertEqual(rplan1.diagnosis, rplan2.diagnosis)

    # -------------------------------------------------------------------------
    # 9b. Repeated repair on structured plan is deterministic (Step 19 remediation)
    # -------------------------------------------------------------------------
    def test_9b_repeated_repair_on_structured_plan_is_deterministic(self):
        repair_engine = QARepairEngine()

        dup_finding = QAFinding(
            id="FIND-ATTR-DUP-MOD-6",
            severity=QASeverity.ERROR,
            category=QACategory.COMMAND_SEMANTICS,
            problem="Duplicate attribute modifier ID detected.",
            explanation="Duplicate attribute modifier",
            expected_behavior="Unique modifier IDs"
        )
        qa_res = QAResult(
            status="failed",
            summary="QA failed",
            findings=[dup_finding],
            intent_verification=IntentVerificationResult(
                matches_intent=True, reasoning="Matches", missing_aspects=[], unwanted_aspects=[]
            )
        )

        base_plan = {
            "status": "ready",
            "minecraft_version": "1.21.11",
            "summary": "Multi duplicate plan",
            "implementation_plan": [
                {
                    "requirement_index": 0,
                    "objective": "test deterministic idempotency",
                    "mechanisms": [
                        {
                            "type": "function",
                            "namespace": "minecraft_ai",
                            "path": "tick",
                            "actions": [
                                {
                                    "action_type": "property_modification",
                                    "target": "@a",
                                    "modifier_id": "speed_add_5_step_0",
                                    "property_modification": {"property": "speed", "operation": "add", "value": {"kind": "relative", "value": 5.0}}
                                },
                                {
                                    "action_type": "property_modification",
                                    "target": "@a",
                                    "modifier_id": "speed_add_5_step_0",
                                    "property_modification": {"property": "speed", "operation": "add", "value": {"kind": "relative", "value": 5.0}}
                                },
                                {
                                    "action_type": "property_modification",
                                    "target": "@a",
                                    "modifier_id": "speed_add_5_step_1",
                                    "property_modification": {"property": "speed", "operation": "add", "value": {"kind": "relative", "value": 5.0}}
                                }
                            ]
                        }
                    ]
                }
            ]
        }

        # First repair run
        rplan1, rep1 = repair_engine.diagnose_and_repair(qa_res, copy.deepcopy(base_plan))
        ids1 = [a["modifier_id"] for a in rep1["implementation_plan"][0]["mechanisms"][0]["actions"]]

        # Second repair run from original input
        rplan2, rep2 = repair_engine.diagnose_and_repair(qa_res, copy.deepcopy(base_plan))
        ids2 = [a["modifier_id"] for a in rep2["implementation_plan"][0]["mechanisms"][0]["actions"]]

        # Third repair run on the already repaired output (idempotency check)
        rplan3, rep3 = repair_engine.diagnose_and_repair(qa_res, copy.deepcopy(rep1))
        ids3 = [a["modifier_id"] for a in rep3["implementation_plan"][0]["mechanisms"][0]["actions"]]

        self.assertEqual(ids1, ["speed_add_5_step_0", "speed_add_5_step_2", "speed_add_5_step_1"])
        self.assertEqual(ids1, ids2)
        self.assertEqual(ids1, ids3)

    # -------------------------------------------------------------------------
    # 10. No regression in existing pipeline behavior
    # -------------------------------------------------------------------------
    def test_10_no_regression_in_existing_pipeline_behavior(self):
        reviewer = QAReviewer()

        dp_dir = self.test_dir / "normal_dp"
        dp_dir.mkdir(parents=True)
        fn_dir = dp_dir / "data" / "minecraft_ai" / "function"
        fn_dir.mkdir(parents=True)
        (fn_dir / "tick.mcfunction").write_text("give @a diamond 1\n", encoding="utf-8")

        # Standard non-property plan
        plan = {
            "status": "ready",
            "minecraft_version": "1.21.11",
            "summary": "give diamond plan",
            "implementation_plan": [
                {
                    "requirement_index": 0,
                    "objective": "give diamond",
                    "mechanisms": []
                }
            ]
        }

        qa_res = reviewer.review(
            datapack_dir=dp_dir,
            original_request="give me a diamond",
            plan=plan,
            understanding={"requirements": [{"item": "diamond"}]}
        )

        self.assertTrue(qa_res.intent_verification.matches_intent)
        self.assertEqual(len(qa_res.intent_verification.missing_aspects), 0)


if __name__ == "__main__":
    unittest.main()
