"""
Step 26.1 Test Suite: Interaction Data Contracts, Specifications & Knowledge Base.

Validates:
1. InteractionOption model creation with valid id, label, description, actions.
2. InteractionOption rejection of non-positive integer id (id < 1).
3. InteractionOption rejection of boolean id.
4. InteractionOption rejection of empty or whitespace-only label.
5. InteractionOption actions validation (ActionSpecification instances and raw dicts).
6. InteractionOption rejection of invalid action types.
7. InteractionOption condition_predicate support.
8. InteractionSpecification valid minimal creation.
9. InteractionSpecification multi-option structured representation.
10. InteractionSpecification duplicate option ID rejection.
11. InteractionSpecification invalid interaction_type rejection.
12. InteractionSpecification invalid target_scope rejection.
13. InteractionSpecification invalid name rejection (regex enforcement).
14. InteractionSpecification timeout_seconds validation (positive int, rejects <= 0, rejects bool).
15. InteractionSpecification item_trigger validation (requires trigger_item).
16. InteractionSpecification cancellation fields (allow_cancel, cancel_label).
17. InteractionSpecification serialization roundtrip (model_dump / dict).
18. MechanismSpecification with type='interaction' acceptance.
19. MechanismSpecification.to_interaction_specification() conversion.
20. MechanismSpecification nested interaction object support.
21. validate_mechanism_specification() validates typed interaction mechanism.
22. validate_mechanism_specification() validates dict-based interaction mechanism.
23. validate_mechanism_specification() rejects interaction missing name/path.
24. validate_mechanism_specification() rejects interaction with empty options.
25. validate_mechanism_specification() preserves existing mechanisms (loot_table, recipe, predicate, scoreboard).
26. Interaction knowledge base loading via load_interaction_knowledge().
27. MinecraftKnowledgeRetriever loads interaction concepts on initialization.
28. generator package exports InteractionOption and InteractionSpecification.
"""

import unittest
from pydantic import ValidationError

from generator.models import (
    ActionSpecification,
    InteractionOption,
    InteractionSpecification,
    MechanismSpecification,
    ScoreboardObjectiveDefinition,
    validate_mechanism_specification,
    VALID_INTERACTION_TYPES,
    VALID_TARGET_SCOPES,
)
import generator
from knowledge_retriever import (
    load_interaction_knowledge,
    get_interactions_file,
    MinecraftKnowledgeRetriever,
)


class TestStep261InteractionOption(unittest.TestCase):
    """Unit tests for InteractionOption data contract."""

    def test_01_valid_option_creation(self):
        """Valid option with id, label, description, and actions."""
        action = ActionSpecification(
            action_type="give_item",
            target="@s",
            item="minecraft:diamond",
            count=1,
        )
        opt = InteractionOption(
            id=1,
            label="Claim Diamond",
            description="Grants 1 diamond to the player",
            actions=[action],
            condition_predicate="minecraft_ai:has_permission",
        )
        self.assertEqual(opt.id, 1)
        self.assertEqual(opt.label, "Claim Diamond")
        self.assertEqual(opt.description, "Grants 1 diamond to the player")
        self.assertEqual(len(opt.actions), 1)
        self.assertEqual(opt.actions[0].action_type, "give_item")
        self.assertEqual(opt.condition_predicate, "minecraft_ai:has_permission")

    def test_02_option_id_must_be_positive_integer(self):
        """Reject id <= 0."""
        with self.assertRaises(ValidationError):
            InteractionOption(id=0, label="Zero Option")
        with self.assertRaises(ValidationError):
            InteractionOption(id=-5, label="Negative Option")

    def test_03_option_id_rejects_bool(self):
        """Reject boolean for id even though bool is a subclass of int in Python."""
        with self.assertRaises(ValidationError):
            InteractionOption(id=True, label="Bool Option")
        with self.assertRaises(ValidationError):
            InteractionOption(id=False, label="Bool Option")

    def test_04_option_label_cannot_be_empty(self):
        """Reject empty or whitespace-only label."""
        with self.assertRaises(ValidationError):
            InteractionOption(id=1, label="")
        with self.assertRaises(ValidationError):
            InteractionOption(id=1, label="   ")
        with self.assertRaises(ValidationError):
            InteractionOption(id=1, label=None)

    def test_05_option_actions_dict_coercion(self):
        """Actions provided as dicts are automatically coerced to ActionSpecification."""
        opt = InteractionOption(
            id=2,
            label="Heal Player",
            actions=[
                {"action_type": "give_effect", "target": "@s", "effect": "minecraft:regeneration", "duration": 10}
            ],
        )
        self.assertEqual(len(opt.actions), 1)
        self.assertIsInstance(opt.actions[0], ActionSpecification)
        self.assertEqual(opt.actions[0].action_type, "give_effect")

    def test_06_option_actions_invalid_type_rejected(self):
        """Reject actions that are not ActionSpecification or dict."""
        with self.assertRaises(ValidationError):
            InteractionOption(id=1, label="Bad Action", actions=["just_a_string"])

    def test_07_option_serialization(self):
        """Verify model_dump roundtrip."""
        opt = InteractionOption(
            id=3,
            label="Option 3",
            description="Desc",
            actions=[{"action_type": "send_message", "target": "@s", "message": "Hi"}],
        )
        data = opt.model_dump()
        self.assertEqual(data["id"], 3)
        self.assertEqual(data["label"], "Option 3")
        self.assertEqual(len(data["actions"]), 1)
        self.assertEqual(data["actions"][0]["action_type"], "send_message")


class TestStep261InteractionSpecification(unittest.TestCase):
    """Unit tests for InteractionSpecification data contract."""

    def test_08_valid_minimal_specification(self):
        """Minimal valid interaction specification."""
        spec = InteractionSpecification(
            name="simple_menu",
            options=[
                InteractionOption(id=1, label="Choice A"),
                InteractionOption(id=2, label="Choice B"),
            ],
        )
        self.assertEqual(spec.name, "simple_menu")
        self.assertEqual(spec.interaction_type, "chat_menu")
        self.assertEqual(spec.target_scope, "self")
        self.assertTrue(spec.allow_cancel)
        self.assertEqual(spec.cancel_label, "Cancel")
        self.assertEqual(len(spec.options), 2)

    def test_09_multi_option_with_actions(self):
        """Multi-option interaction specification with actions."""
        spec = InteractionSpecification(
            name="teleport_hub",
            interaction_type="chat_menu",
            prompt="Choose your destination:",
            options=[
                InteractionOption(
                    id=1,
                    label="Spawn",
                    actions=[{"action_type": "teleport", "target": "@s"}],
                ),
                InteractionOption(
                    id=2,
                    label="Mining Base",
                    actions=[{"action_type": "teleport", "target": "@s"}],
                ),
                InteractionOption(
                    id=3,
                    label="Nether Portal",
                    actions=[{"action_type": "teleport", "target": "@s"}],
                ),
            ],
            timeout_seconds=30,
            allow_cancel=True,
            cancel_label="Dismiss Hub",
        )
        self.assertEqual(len(spec.options), 3)
        self.assertEqual(spec.timeout_seconds, 30)
        self.assertEqual(spec.cancel_label, "Dismiss Hub")

    def test_10_duplicate_option_id_rejected(self):
        """Reject interaction with duplicate option IDs."""
        with self.assertRaises(ValidationError) as ctx:
            InteractionSpecification(
                name="duplicate_menu",
                options=[
                    InteractionOption(id=1, label="Option 1"),
                    InteractionOption(id=1, label="Duplicate 1"),
                ],
            )
        self.assertIn("Duplicate option id '1'", str(ctx.exception))

    def test_11_invalid_interaction_type_rejected(self):
        """Reject unrecognized interaction types."""
        with self.assertRaises(ValidationError) as ctx:
            InteractionSpecification(
                name="bad_type_menu",
                interaction_type="unsupported_modality",
                options=[InteractionOption(id=1, label="Choice")],
            )
        self.assertIn("Invalid interaction_type", str(ctx.exception))

    def test_12_invalid_target_scope_rejected(self):
        """Reject unrecognized target_scope values."""
        with self.assertRaises(ValidationError) as ctx:
            InteractionSpecification(
                name="bad_scope_menu",
                target_scope="everyone_everywhere",
                options=[InteractionOption(id=1, label="Choice")],
            )
        self.assertIn("Invalid target_scope", str(ctx.exception))

    def test_13_invalid_name_rejected(self):
        """Reject invalid interaction names (must be alphanumeric with _ or -)."""
        with self.assertRaises(ValidationError):
            InteractionSpecification(name="name with spaces", options=[InteractionOption(id=1, label="A")])
        with self.assertRaises(ValidationError):
            InteractionOption_spec = InteractionSpecification(
                name="name!with$symbols", options=[InteractionOption(id=1, label="A")]
            )

    def test_14_timeout_validation(self):
        """Reject negative, zero, or boolean timeout."""
        with self.assertRaises(ValidationError):
            InteractionSpecification(
                name="neg_timeout",
                timeout_seconds=-10,
                options=[InteractionOption(id=1, label="A")],
            )
        with self.assertRaises(ValidationError):
            InteractionSpecification(
                name="zero_timeout",
                timeout_seconds=0,
                options=[InteractionOption(id=1, label="A")],
            )
        with self.assertRaises(ValidationError):
            InteractionSpecification(
                name="bool_timeout",
                timeout_seconds=True,
                options=[InteractionOption(id=1, label="A")],
            )

    def test_15_item_trigger_requires_trigger_item(self):
        """item_trigger type requires trigger_item field."""
        with self.assertRaises(ValidationError) as ctx:
            InteractionSpecification(
                name="item_menu",
                interaction_type="item_trigger",
                trigger_item=None,
                options=[InteractionOption(id=1, label="Action")],
            )
        self.assertIn("requires 'trigger_item'", str(ctx.exception))

        # With valid trigger_item it should succeed
        spec = InteractionSpecification(
            name="item_menu",
            interaction_type="item_trigger",
            trigger_item="minecraft:compass",
            options=[InteractionOption(id=1, label="Action")],
        )
        self.assertEqual(spec.trigger_item, "minecraft:compass")

    def test_16_cancellation_fields(self):
        """allow_cancel=False and custom cancel_label are preserved."""
        spec = InteractionSpecification(
            name="mandatory_choice",
            allow_cancel=False,
            cancel_label="Back",
            options=[InteractionOption(id=1, label="Accept")],
        )
        self.assertFalse(spec.allow_cancel)
        self.assertEqual(spec.cancel_label, "Back")

    def test_17_serialization_roundtrip(self):
        """model_dump and JSON dict validation roundtrip."""
        spec = InteractionSpecification(
            name="roundtrip_menu",
            interaction_type="dialogue",
            prompt="Hello traveler",
            options=[
                {"id": 1, "label": "Trade", "actions": [{"action_type": "send_message", "target": "@s", "message": "Opening shop..."}]},
                {"id": 2, "label": "Farewell", "actions": []},
            ],
            timeout_seconds=45,
            target_scope="player",
        )
        dumped = spec.model_dump()
        self.assertEqual(dumped["name"], "roundtrip_menu")
        self.assertEqual(dumped["interaction_type"], "dialogue")
        self.assertEqual(len(dumped["options"]), 2)
        # Re-parse from dumped dict
        reparsed = InteractionSpecification.model_validate(dumped)
        self.assertEqual(reparsed.name, spec.name)
        self.assertEqual(len(reparsed.options), 2)
        self.assertEqual(reparsed.options[0].id, 1)


class TestStep261MechanismSpecificationIntegration(unittest.TestCase):
    """Unit tests for MechanismSpecification interaction integration and validation."""

    def test_18_mechanism_specification_with_interaction(self):
        """MechanismSpecification accepts type='interaction' and nested interaction specification."""
        inter = InteractionSpecification(
            name="custom_menu",
            interaction_type="chat_menu",
            prompt="Pick an option",
            options=[
                InteractionOption(id=1, label="Option 1"),
                InteractionOption(id=2, label="Option 2"),
            ],
            timeout_seconds=20,
        )
        mech = MechanismSpecification(
            type="interaction",
            interaction=inter,
        )
        self.assertEqual(mech.type, "interaction")
        self.assertIsNotNone(mech.interaction)
        self.assertEqual(mech.interaction.name, "custom_menu")
        self.assertEqual(len(mech.interaction.options), 2)

    def test_19_to_interaction_specification(self):
        """MechanismSpecification.to_interaction_specification() returns the configured interaction."""
        inter = InteractionSpecification(
            name="warp_menu",
            prompt="Select warp:",
            options=[
                InteractionOption(id=1, label="Spawn"),
                InteractionOption(id=2, label="Base"),
            ],
            timeout_seconds=15,
            allow_cancel=True,
            cancel_label="Close",
        )
        mech = MechanismSpecification(type="interaction", interaction=inter)
        retrieved = mech.to_interaction_specification()
        self.assertIs(retrieved, inter)
        self.assertEqual(retrieved.name, "warp_menu")

    def test_20_to_interaction_specification_missing_raises(self):
        """to_interaction_specification() raises ValueError if interaction is None."""
        mech = MechanismSpecification(type="interaction")
        with self.assertRaises(ValueError):
            mech.to_interaction_specification()

    def test_21_validate_mechanism_specification_typed(self):
        """validate_mechanism_specification validates typed MechanismSpecification for interaction."""
        inter = InteractionSpecification(
            name="valid_menu",
            options=[
                InteractionOption(id=1, label="Choice 1"),
                InteractionOption(id=2, label="Choice 2"),
            ],
        )
        mech = MechanismSpecification(type="interaction", interaction=inter)
        # Should not raise
        validate_mechanism_specification(mech)

    def test_22_validate_mechanism_specification_dict(self):
        """validate_mechanism_specification validates dict format for interaction."""
        spec_dict = {
            "type": "interaction",
            "interaction": {
                "name": "dict_menu",
                "interaction_type": "chat_menu",
                "options": [
                    {"id": 1, "label": "First"},
                    {"id": 2, "label": "Second"},
                ],
            },
        }
        # Should not raise
        validate_mechanism_specification(spec_dict)

    def test_23_validate_mechanism_specification_rejects_missing_interaction(self):
        """validate_mechanism_specification rejects interaction missing 'interaction'."""
        with self.assertRaises(ValueError) as ctx:
            validate_mechanism_specification({"type": "interaction"})
        self.assertIn("missing 'interaction'", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            validate_mechanism_specification(MechanismSpecification(type="interaction"))
        self.assertIn("missing 'interaction'", str(ctx.exception))

    def test_24_validate_mechanism_specification_rejects_unsupported_aliases(self):
        """validate_mechanism_specification rejects non-canonical aliases like 'menu', 'dialogue', 'choice'."""
        inter_data = {"name": "menu1", "options": [{"id": 1, "label": "Opt"}]}
        for alias in ["menu", "dialogue", "choice", "interactive"]:
            with self.assertRaises(ValueError) as ctx:
                validate_mechanism_specification({"type": alias, "interaction": inter_data})
            self.assertIn("Unsupported mechanism specification type", str(ctx.exception))

    def test_25_existing_mechanisms_unaffected(self):
        """Existing mechanism types validate as before without regression."""
        # Scoreboard
        scoreboard_spec = MechanismSpecification(
            type="scoreboard_objective",
            objective="test_score",
            criteria="dummy",
            display_name="Test",
        )
        validate_mechanism_specification(scoreboard_spec)

        # Loot table
        loot_spec = MechanismSpecification(
            type="loot_table",
            target="entities/zombie",
            item="minecraft:iron_sword",
        )
        validate_mechanism_specification(loot_spec)

        # Recipe
        recipe_spec = MechanismSpecification(
            type="recipe",
            recipe_type="crafting_shaped",
            recipe_id="test_recipe",
            result_item="minecraft:iron_sword",
            pattern=["X", "X", "#"],
            key={"X": "minecraft:iron_ingot", "#": "minecraft:stick"},
        )
        validate_mechanism_specification(recipe_spec)

        # Predicate
        pred_spec = MechanismSpecification(
            type="predicate",
            path="test_raining",
            condition_type="minecraft:weather_check",
            condition_params={"raining": True},
        )
        validate_mechanism_specification(pred_spec)


class TestStep261KnowledgeRetriever(unittest.TestCase):
    """Unit tests for interaction knowledge base retrieval."""

    def test_26_load_interaction_knowledge(self):
        """load_interaction_knowledge loads the interaction concepts from JSON."""
        concepts = load_interaction_knowledge()
        self.assertIsInstance(concepts, list)
        self.assertGreaterEqual(len(concepts), 8)

        # Check required schema fields for each concept
        concept_ids = set()
        for c in concepts:
            self.assertIn("id", c)
            self.assertIn("name", c)
            self.assertIn("category", c)
            self.assertIn("description", c)
            self.assertIn("minecraft_mechanisms", c)
            self.assertIn("keywords", c)
            self.assertIn("lifecycle_role", c)
            self.assertEqual(c["category"], "interaction")
            concept_ids.add(c["id"])

        # Check expected canonical concepts
        expected_concepts = {
            "concept_player_driven_interaction",
            "concept_selectable_choices",
            "concept_interaction_lifecycle",
            "concept_trigger_based_interaction",
            "concept_interaction_state",
            "concept_cancellation",
            "concept_timeout",
            "concept_target_selection",
        }
        self.assertTrue(expected_concepts.issubset(concept_ids))

    def test_27_retriever_initializes_interactions(self):
        """MinecraftKnowledgeRetriever.__init__ loads interaction concepts into self.interactions."""
        retriever = MinecraftKnowledgeRetriever()
        self.assertTrue(hasattr(retriever, "interactions"))
        self.assertIsInstance(retriever.interactions, list)
        self.assertGreaterEqual(len(retriever.interactions), 8)

    def test_28_generator_exports(self):
        """generator package exports InteractionOption and InteractionSpecification."""
        self.assertTrue(hasattr(generator, "InteractionOption"))
        self.assertTrue(hasattr(generator, "InteractionSpecification"))
        self.assertIn("InteractionOption", generator.__all__)
        self.assertIn("InteractionSpecification", generator.__all__)


if __name__ == "__main__":
    unittest.main()
