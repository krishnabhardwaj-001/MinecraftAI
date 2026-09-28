"""
test_step17_clarification.py - Step 17.4 Clarification Boundary Test Suite

Validates that the clarification system asks for specific missing semantic information,
isolates clarification analysis from question generation and planning, and produces
structured, machine-readable ClarificationRequirement models.

Covers all 10 required scenarios + structured contract validation:
1. Missing property: 'make the zombie stronger'
2. Missing value: 'increase speed'
3. Missing operation: 'change speed by 10'
4. Ambiguous numeric relationship: 'make me faster by 10'
5. Unknown property: 'set mana to 10'
6. Qualitative request: 'make me faster' (must NOT ask for arithmetic operation)
7. Complete numeric modification: 'increase speed by 5' (must NOT ask clarification)
8. Multiplier request: 'make me 10 times faster' (must NOT ask clarification)
9. Compound request: mixed complete and incomplete requirements
10. Existing Step 16 scoreboard backward compatibility
11. Machine-readable ClarificationRequirement contract validation
"""

import unittest
from ai.clarification import (
    ClarificationAnalyzer,
    ClarificationIssue,
    ClarificationQuestionGenerator,
    ClarificationRequirement,
    SemanticClarificationEngine,
    DEFAULT_CLARIFICATION_ENGINE,
)
from ai.numeric_interpreter import NumericSemanticInterpreter
from ai.property_registry import (
    DEFAULT_PROPERTY_REGISTRY,
    PropertyCapability,
    PropertyCapabilityRegistry,
)
from ai.planner import MinecraftPlanner, create_plan, validate_plan_mechanisms
from ai.semantic_models import (
    PropertyModification,
    SemanticNumericValue,
    SemanticValue,
)
from generator.models import (
    ActionSpecification,
    MechanismSpecification,
    validate_mechanism_specification,
)


class TestStep17Clarification(unittest.TestCase):
    """
    Step 17.4 Focused Test Suite for Clarification Boundary Redesign.
    """

    def setUp(self):
        self.interpreter = NumericSemanticInterpreter()
        self.planner = MinecraftPlanner(version="1.21.11")
        self.engine = DEFAULT_CLARIFICATION_ENGINE
        self.analyzer = ClarificationAnalyzer()
        self.generator = ClarificationQuestionGenerator()

    # 1. Missing property: 'make the zombie stronger'
    def test_01_missing_property_make_the_zombie_stronger(self):
        mod = self.interpreter.interpret("make the zombie stronger")
        self.assertIsNone(mod.property)
        self.assertIn("property", mod.missing)
        self.assertEqual(mod.extra_metadata.get("target"), "zombie")

        # Clarification analysis
        issue = self.analyzer.analyze(mod, registry=DEFAULT_PROPERTY_REGISTRY)
        self.assertIsNotNone(issue)
        self.assertEqual(issue.issue_type, "missing_property")
        self.assertEqual(issue.parameter, "property")
        self.assertEqual(issue.details.get("target"), "zombie")

        # Question generation
        req = self.generator.generate(issue)
        self.assertIsInstance(req, ClarificationRequirement)
        self.assertEqual(req.parameter, "property")
        self.assertIn("property", req.question.lower())
        self.assertIn("zombie", req.question.lower())
        self.assertTrue(len(req.options) > 0)
        self.assertIn("attack_damage", req.options)

        # Planner integration
        plan = self.planner.plan_property_modification(mod)
        self.assertIsNone(plan.mechanisms[0].implementation)
        self.assertEqual(len(plan.clarification_requirements), 1)
        self.assertEqual(plan.clarification_requirements[0].parameter, "property")

        # End-to-end plan
        result = self.planner.plan({"understood_request": "make the zombie stronger", "status": "understood"})
        self.assertEqual(result["status"], "needs_clarification")
        self.assertTrue(len(result["clarifications"]) > 0)
        self.assertTrue(any("property" in c.lower() for c in result["clarifications"]))
        self.assertTrue(any("zombie" in c.lower() for c in result["clarifications"]))
        self.assertEqual(len(result["clarification_requirements"]), 1)
        self.assertEqual(result["clarification_requirements"][0]["parameter"], "property")

        # Verify planner did NOT invent an implementation
        mech = result["implementation_plan"][0]["mechanisms"][0]
        self.assertIsNone(mech.get("implementation"))

    # 2. Missing value: 'increase speed'
    def test_02_missing_value_increase_speed(self):
        mod = self.interpreter.interpret("increase speed")
        self.assertEqual(mod.property, "speed")
        self.assertEqual(mod.operation, "add")
        self.assertIsNone(mod.value)
        self.assertIn("value", mod.missing)

        # Engine analysis
        req = self.engine.analyze_modification(mod, registry=DEFAULT_PROPERTY_REGISTRY)
        self.assertIsNotNone(req)
        self.assertEqual(req.parameter, "value")
        self.assertIn("speed", req.question.lower())
        self.assertTrue(any("amount" in opt.lower() or "percentage" in opt.lower() for opt in req.options))

        # Planner integration
        result = self.planner.plan({"understood_request": "increase speed", "status": "understood"})
        self.assertEqual(result["status"], "needs_clarification")
        self.assertTrue(any("speed" in c.lower() for c in result["clarifications"]))
        self.assertEqual(len(result["clarification_requirements"]), 1)
        self.assertEqual(result["clarification_requirements"][0]["parameter"], "value")

    # 3. Missing operation: 'change speed by 10'
    def test_03_missing_operation_change_speed_by_10(self):
        mod = self.interpreter.interpret("change speed by 10")
        self.assertEqual(mod.property, "speed")
        self.assertIsNone(mod.operation)
        self.assertIn("operation", mod.missing)
        self.assertIsNotNone(mod.value)
        self.assertEqual(mod.value.value, 10)

        # Engine analysis
        req = self.engine.analyze_modification(mod, registry=DEFAULT_PROPERTY_REGISTRY)
        self.assertIsNotNone(req)
        self.assertEqual(req.parameter, "operation")
        self.assertIn("how", req.question.lower())
        self.assertIn("speed", req.question.lower())
        self.assertIn("add", req.options)
        self.assertIn("multiply", req.options)
        self.assertIn("set", req.options)

        # Planner integration: must NOT default to set
        plan_entry = self.planner.plan_property_modification(mod)
        self.assertIsNone(plan_entry.mechanisms[0].implementation)
        self.assertNotIn("set speed", plan_entry.objective.lower())

        result = self.planner.plan({"understood_request": "change speed by 10", "status": "understood"})
        self.assertEqual(result["status"], "needs_clarification")
        self.assertEqual(len(result["clarification_requirements"]), 1)
        self.assertEqual(result["clarification_requirements"][0]["parameter"], "operation")

    # 4. Ambiguous numeric relationship: 'make me faster by 10'
    def test_04_ambiguous_numeric_relationship_faster_by_10(self):
        mod = self.interpreter.interpret("make me faster by 10")
        self.assertTrue(mod.extra_metadata.get("ambiguous"))
        self.assertEqual(mod.extra_metadata.get("ambiguous_number"), 10)

        # Engine analysis
        req = self.engine.analyze_modification(mod, registry=DEFAULT_PROPERTY_REGISTRY)
        self.assertIsNotNone(req)
        self.assertEqual(req.parameter, "value")
        self.assertIn("ambiguous", req.question.lower())
        self.assertTrue(any("10" in opt for opt in req.options))

        # Planner integration
        result = self.planner.plan({"understood_request": "make me faster by 10", "status": "understood"})
        self.assertEqual(result["status"], "needs_clarification")
        self.assertTrue(any("ambiguous" in c.lower() for c in result["clarifications"]))
        self.assertEqual(len(result["clarification_requirements"]), 1)
        self.assertEqual(result["clarification_requirements"][0]["metadata"]["ambiguous_number"], 10)

    # 5. Unknown property: 'set mana to 10'
    def test_05_unknown_property_not_guessed(self):
        mod = self.interpreter.interpret("set mana to 10")
        self.assertEqual(mod.property, "mana")
        self.assertEqual(mod.operation, "set")
        self.assertEqual(mod.value.value, 10)

        # Engine analysis
        req = self.engine.analyze_modification(mod, registry=DEFAULT_PROPERTY_REGISTRY)
        self.assertIsNotNone(req)
        self.assertEqual(req.parameter, "property")
        self.assertIn("mana", req.question.lower())
        self.assertTrue("not recognized" in req.question.lower() or "not supported" in req.question.lower())

        # Planner integration
        plan_entry = self.planner.plan_property_modification(mod)
        self.assertIsNone(plan_entry.mechanisms[0].implementation)
        self.assertIn("mana", plan_entry.missing_knowledge)

        result = self.planner.plan(
            {"understood_request": "set mana to 10", "status": "understood"},
            property_modifications=[mod],
        )
        self.assertEqual(result["status"], "needs_clarification")
        self.assertEqual(len(result["clarification_requirements"]), 1)
        self.assertEqual(result["clarification_requirements"][0]["parameter"], "property")

    # 6. Qualitative request: 'make me faster' must NOT ask for arithmetic operation
    def test_06_qualitative_request_requires_no_clarification(self):
        mod = self.interpreter.interpret("make me faster")
        self.assertEqual(mod.property, "speed")
        self.assertIsNone(mod.operation)
        self.assertEqual(mod.value.kind, "qualitative")
        self.assertEqual(mod.value.value, "faster")

        # Engine analysis: must return None
        req = self.engine.analyze_modification(mod, registry=DEFAULT_PROPERTY_REGISTRY)
        self.assertIsNone(req)
        self.assertTrue(self.engine.is_qualitative_complete(mod, registry=DEFAULT_PROPERTY_REGISTRY))

        # Planner integration: qualitative without magnitude cannot safely map to a mechanism
        plan_entry = self.planner.plan_property_modification(mod)
        self.assertIsNone(plan_entry.mechanisms[0].implementation)
        self.assertTrue(len(plan_entry.clarifications) > 0)

        result = self.planner.plan({"understood_request": "make me faster", "status": "understood"})
        self.assertEqual(result["status"], "needs_clarification")
        self.assertTrue(len(result["clarifications"]) > 0)

    # 7. Complete numeric modification: 'increase speed by 5' must NOT ask clarification
    def test_07_complete_numeric_modification_no_clarification(self):
        mod = self.interpreter.interpret("increase speed by 5")
        self.assertEqual(mod.property, "speed")
        self.assertEqual(mod.operation, "add")
        self.assertEqual(mod.value.kind, "relative")
        self.assertEqual(mod.value.value, 5)

        req = self.engine.analyze_modification(mod, registry=DEFAULT_PROPERTY_REGISTRY)
        self.assertIsNone(req)

        result = self.planner.plan({"understood_request": "increase speed by 5", "status": "understood"})
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["clarifications"], [])
        self.assertEqual(result["clarification_requirements"], [])

    # 8. Multiplier request: 'make me 10 times faster' must NOT ask clarification
    def test_08_multiplier_request_no_clarification(self):
        mod = self.interpreter.interpret("make me 10 times faster")
        self.assertEqual(mod.property, "speed")
        self.assertEqual(mod.operation, "multiply")
        self.assertEqual(mod.value.kind, "multiplier")
        self.assertEqual(mod.value.value, 10)

        req = self.engine.analyze_modification(mod, registry=DEFAULT_PROPERTY_REGISTRY)
        self.assertIsNone(req)

        result = self.planner.plan({"understood_request": "make me 10 times faster", "status": "understood"})
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["clarifications"], [])
        self.assertEqual(result["clarification_requirements"], [])

    # 9. Compound request: preserves clarification state correctly
    def test_09_compound_request_mixed_clarification(self):
        req_text = "make me 10 times faster and make the zombie stronger"
        result = self.planner.plan({"understood_request": req_text, "status": "understood"})

        self.assertEqual(result["status"], "needs_clarification")
        self.assertEqual(len(result["implementation_plan"]), 2)

        # Plan 0: complete speed multiplier mapped to attribute
        plan_0 = result["implementation_plan"][0]
        self.assertEqual(plan_0["property_modification"]["property"], "speed")
        self.assertEqual(plan_0["mechanisms"][0]["implementation"], "attribute")
        self.assertEqual(plan_0.get("clarification_requirements", []), [])

        # Plan 1: incomplete zombie modification (missing property)
        plan_1 = result["implementation_plan"][1]
        self.assertIsNone(plan_1["mechanisms"][0]["implementation"])
        self.assertTrue(len(plan_1.get("clarification_requirements", [])) > 0)

        # Top-level result preserves structured clarification requirement
        self.assertEqual(len(result["clarification_requirements"]), 1)
        self.assertEqual(result["clarification_requirements"][0]["parameter"], "property")
        self.assertEqual(result["clarification_requirements"][0]["metadata"]["target"], "zombie")

    # 10. Existing Step 16 scoreboard behavior remains unchanged
    def test_10_step16_scoreboard_compatibility(self):
        obj_mech = MechanismSpecification(
            type="scoreboard_objective",
            objective="player_kills",
            criteria="playerKillCount",
            display_slot="sidebar",
        )
        validate_mechanism_specification(obj_mech)

        full_plan = {
            "status": "ready",
            "minecraft_version": "1.21.11",
            "summary": "Track player kills",
            "implementation_plan": [
                {
                    "requirement_index": 0,
                    "objective": "Track player kills",
                    "mechanisms": [obj_mech.model_dump()],
                    "steps": [],
                    "constraints": [],
                    "missing_knowledge": [],
                    "clarifications": [],
                    "clarification_requirements": [],
                }
            ],
            "missing_knowledge": [],
            "clarifications": [],
            "clarification_requirements": [],
        }
        validate_plan_mechanisms(full_plan)

    # 11. Machine-readable ClarificationRequirement contract validation
    def test_11_machine_readable_contract_validation(self):
        cr = ClarificationRequirement(
            parameter="property",
            reason="Property is missing.",
            question="Which property do you want to modify?",
            options=["speed", "health"],
            source_text="make stronger",
            metadata={"target": "zombie", "severity": "high"},
        )
        dumped = cr.model_dump()
        self.assertEqual(dumped["parameter"], "property")
        self.assertEqual(dumped["reason"], "Property is missing.")
        self.assertEqual(dumped["question"], "Which property do you want to modify?")
        self.assertEqual(dumped["options"], ["speed", "health"])
        self.assertEqual(dumped["source_text"], "make stronger")
        self.assertEqual(dumped["metadata"]["target"], "zombie")

        # Re-parse from dict
        loaded = ClarificationRequirement.model_validate(dumped)
        self.assertEqual(loaded.parameter, "property")
        self.assertEqual(loaded.options, ["speed", "health"])

    # 12. Generic entity handling: 'make the skeleton stronger' -> missing property for skeleton
    def test_12_generic_entity_skeleton_missing_property(self):
        mod = self.interpreter.interpret("make the skeleton stronger")
        self.assertIsNone(mod.property)
        self.assertIn("property", mod.missing)
        self.assertEqual(mod.extra_metadata.get("target"), "skeleton")

        req = self.engine.analyze_modification(mod, registry=DEFAULT_PROPERTY_REGISTRY)
        self.assertIsNotNone(req)
        self.assertEqual(req.parameter, "property")
        self.assertIn("skeleton", req.question.lower())
        self.assertEqual(req.metadata.get("target"), "skeleton")

    # 13. Generic entity handling: 'make the creeper stronger' -> missing property for creeper
    def test_13_generic_entity_creeper_missing_property(self):
        mod = self.interpreter.interpret("make the creeper stronger")
        self.assertIsNone(mod.property)
        self.assertIn("property", mod.missing)
        self.assertEqual(mod.extra_metadata.get("target"), "creeper")

        req = self.engine.analyze_modification(mod, registry=DEFAULT_PROPERTY_REGISTRY)
        self.assertIsNotNone(req)
        self.assertEqual(req.parameter, "property")
        self.assertIn("creeper", req.question.lower())
        self.assertEqual(req.metadata.get("target"), "creeper")

    # 14. Missing operation for attack damage: does not assume speed
    def test_14_missing_operation_attack_damage_no_speed_assumption(self):
        mod = self.interpreter.interpret("change attack damage by 10")
        self.assertEqual(mod.property, "attack_damage")
        self.assertIsNone(mod.operation)
        self.assertIn("operation", mod.missing)

        req = self.engine.analyze_modification(mod, registry=DEFAULT_PROPERTY_REGISTRY)
        self.assertIsNotNone(req)
        self.assertEqual(req.parameter, "operation")
        self.assertIn("attack damage", req.question.lower())
        self.assertNotIn("speed", req.question.lower())

    # 15. Missing operation for health: does not assume speed
    def test_15_missing_operation_health_no_speed_assumption(self):
        mod = self.interpreter.interpret("change health by 10")
        self.assertEqual(mod.property, "health")
        self.assertIsNone(mod.operation)
        self.assertIn("operation", mod.missing)

        req = self.engine.analyze_modification(mod, registry=DEFAULT_PROPERTY_REGISTRY)
        self.assertIsNotNone(req)
        self.assertEqual(req.parameter, "operation")
        self.assertIn("health", req.question.lower())
        self.assertNotIn("speed", req.question.lower())

    # 16. Unknown property options dynamically sourced from PropertyCapabilityRegistry
    def test_16_unknown_property_options_from_registry(self):
        mod = self.interpreter.interpret("set mana to 10")
        req = self.engine.analyze_modification(mod, registry=DEFAULT_PROPERTY_REGISTRY)
        self.assertEqual(req.options, DEFAULT_PROPERTY_REGISTRY.get_supported_properties())
        self.assertTrue(len(req.options) > 0)
        self.assertIn("speed", req.options)
        self.assertIn("attack_damage", req.options)
        self.assertIn("health", req.options)

    # 17. Dynamically register new property and verify options see it without modifying clarification.py
    def test_17_dynamic_property_registration_visible_in_options(self):
        custom_reg = PropertyCapabilityRegistry()
        custom_reg.register(PropertyCapability(
            property_name="stamina",
            primary_mechanism="attribute",
            supported_mechanisms=["attribute"],
            description="Custom stamina attribute",
        ))
        self.assertIn("stamina", custom_reg.get_supported_properties())

        # Missing property question with custom registry
        mod_missing = self.interpreter.interpret("make the zombie stronger")
        req_missing = self.engine.analyze_modification(mod_missing, registry=custom_reg)
        self.assertIn("stamina", req_missing.options)

        # Unknown property question with custom registry
        mod_unknown = self.interpreter.interpret("set mana to 10")
        req_unknown = self.engine.analyze_modification(mod_unknown, registry=custom_reg)
        self.assertIn("stamina", req_unknown.options)

    # 18. Verify no production code in Step 17.4 path contains entity-specific checks
    def test_18_no_entity_specific_checks_in_production_code(self):
        import inspect
        import ai.clarification as clar
        import ai.numeric_interpreter as num_int

        clar_source = inspect.getsource(clar)
        num_source = inspect.getsource(num_int)

        # Ensure no entity branches like target == "zombie" or "zombie" in norm_text
        self.assertNotIn('== "zombie"', clar_source)
        self.assertNotIn('== "skeleton"', clar_source)
        self.assertNotIn('== "creeper"', clar_source)
        self.assertNotIn('"zombie" in norm_text', num_source)
        self.assertNotIn('"skeleton" in norm_text', num_source)
        self.assertNotIn('"creeper" in norm_text', num_source)

    # 19. Verify no production code uses default property of "speed" for absent properties
    def test_19_no_speed_fallback_in_clarification(self):
        import inspect
        import ai.clarification as clar

        clar_source = inspect.getsource(clar)
        self.assertNotIn('.get("property", "speed")', clar_source)

        # When property is omitted from issue, question generator must NOT invent "speed"
        issue = ClarificationIssue(
            issue_type="ambiguous_value",
            parameter="value",
            details={"ambiguous_number": 10},
        )
        req = self.generator.generate(issue)
        self.assertNotIn("speed", req.question.lower())
        self.assertIsNone(req.metadata.get("property"))

    # 20. Ambiguous numeric clarification uses actual semantic property without "times faster" wording
    def test_20_ambiguous_numeric_clarification_uses_actual_property_without_times_faster(self):
        # 1. Faster by 10 (speed property)
        mod_speed = self.interpreter.interpret("make me faster by 10")
        req_speed = self.engine.analyze_modification(mod_speed, registry=DEFAULT_PROPERTY_REGISTRY)
        self.assertIn("speed", req_speed.question.lower())
        self.assertNotIn("times faster", req_speed.question.lower())
        self.assertTrue(any("10x" in opt for opt in req_speed.options))

        # 2. Attack damage property
        issue_dmg = ClarificationIssue(
            issue_type="ambiguous_value",
            parameter="value",
            details={"property": "attack_damage", "ambiguous_number": 10},
        )
        req_dmg = self.generator.generate(issue_dmg)
        self.assertIn("attack damage", req_dmg.question.lower())
        self.assertNotIn("speed", req_dmg.question.lower())
        self.assertNotIn("times faster", req_dmg.question.lower())

        # 3. Health property
        issue_hp = ClarificationIssue(
            issue_type="ambiguous_value",
            parameter="value",
            details={"property": "health", "ambiguous_number": 10},
        )
        req_hp = self.generator.generate(issue_hp)
        self.assertIn("health", req_hp.question.lower())
        self.assertNotIn("speed", req_hp.question.lower())
        self.assertNotIn("times faster", req_hp.question.lower())


if __name__ == "__main__":
    unittest.main()
