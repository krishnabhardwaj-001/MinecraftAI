"""
test_datapack_name_length.py - Regression tests for bounded datapack output naming.

Verifies:
1. Normal-length requests retain their exact existing slug format.
2. Long natural-language requests produce valid, bounded names (<= 60 chars).
3. Repeated generation of the same request produces identical names (deterministic).
4. Long requests with identical prefixes but different endings produce different names (no collision).
5. The rain datapack request that previously caused WinError 123 produces a valid bounded directory and ZIP.
6. Explicitly supplied datapack_name values are preserved.
7. Generated directory names and ZIP filenames are consistent.
"""
import tempfile
import unittest
from pathlib import Path

from generator.datapack_generator import DatapackGenerator, slugify
from generator.models import DatapackResource, FunctionDefinition, MechanismSpecification


class TestDatapackNameLength(unittest.TestCase):
    """Verifies deterministic bounded slugification and Windows filesystem compatibility."""

    def test_1_normal_length_request_retains_current_slug(self):
        """Normal-length requests must preserve their exact existing slug format without truncation."""
        test_cases = [
            ("Make every creeper drop diamonds.", "make_every_creeper_drop_diamonds"),
            ("Make every skeleton drop iron ingots.", "make_every_skeleton_drop_iron_ingots"),
            ("When it starts raining, give every player one diamond.", "when_it_starts_raining_give_every_player_one_diamond"),
            ("Make rotten flesh smelt into leather.", "make_rotten_flesh_smelt_into_leather"),
            ("add_a_predicate_that_checks_if_it_is_raining", "add_a_predicate_that_checks_if_it_is_raining"),
        ]

        for text, expected in test_cases:
            slug = slugify(text)
            self.assertEqual(slug, expected)
            self.assertLessEqual(len(slug), 60)

    def test_2_long_request_produces_valid_bounded_name(self):
        """A very long natural-language request must produce a valid name of at most 60 characters."""
        long_request = (
            "When it starts raining, give every player one diamond specifically only once "
            "when the rain starts and do not give them another diamond until the rain stops "
            "and starts again and announce it in chat with title text"
        )
        slug = slugify(long_request)

        self.assertLessEqual(len(slug), 60)
        self.assertTrue(slug.isascii())
        # Must only contain lowercase alphanumeric and underscores
        self.assertRegex(slug, r"^[a-z0-9_]+$")
        # Must end with an 8-character hex hash suffix
        self.assertRegex(slug, r"_[a-f0-9]{8}$")

    def test_3_repeated_generation_produces_identical_name(self):
        """Repeated generation of the same long request must produce the exact same name (deterministic)."""
        prompt = (
            "When it is raining, give all players a diamond only once when the rain starts "
            "and play a pleasant chime sound in the game"
        )
        slug1 = slugify(prompt)
        slug2 = slugify(prompt)
        slug3 = slugify(prompt)

        self.assertEqual(slug1, slug2)
        self.assertEqual(slug2, slug3)
        self.assertLessEqual(len(slug1), 60)

    def test_4_different_long_requests_sharing_prefix_do_not_collide(self):
        """Two long requests with identical beginnings but different endings must produce distinct names."""
        prefix = "When it is raining, give all players a diamond only once when the rain starts "
        req_a = prefix + "and summon lightning on every nearby creeper immediately."
        req_b = prefix + "and play a church bell chime sound at the spawn point."

        slug_a = slugify(req_a)
        slug_b = slugify(req_b)

        self.assertNotEqual(slug_a, slug_b)
        self.assertLessEqual(len(slug_a), 60)
        self.assertLessEqual(len(slug_b), 60)

        # Both share the readable prefix portion
        prefix_part_a = slug_a.rsplit("_", 1)[0]
        prefix_part_b = slug_b.rsplit("_", 1)[0]
        self.assertEqual(prefix_part_a, prefix_part_b)

        # But have different hash suffixes
        hash_a = slug_a.rsplit("_", 1)[1]
        hash_b = slug_b.rsplit("_", 1)[1]
        self.assertNotEqual(hash_a, hash_b)

    def test_5_rain_request_previously_causing_winerror_passes_generation(self):
        """
        The rain datapack request that previously triggered WinError 123
        must successfully create the output directory and ZIP archive on Windows.
        """
        rain_request = "When it is raining, give me a diamond specifically only once when the rain starts"

        # Verify slugify bounds it
        slug = slugify(rain_request)
        self.assertLessEqual(len(slug), 60)

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = Path(tmp_dir)
            generator = DatapackGenerator(output_dir=out_path, version="1.21.11")

            understanding = {
                "status": "understood",
                "understood_request": rain_request,
                "minecraft_version": "1.21.11",
                "requirements": [
                    {
                        "subject": "weather",
                        "intent": "give diamond once when rain starts",
                        "conditions": ["weather: rain"],
                        "constraints": ["only once"]
                    }
                ]
            }

            plan = {
                "status": "planned",
                "summary": "Give player a diamond once when it starts raining.",
                "mechanisms": []
            }

            funcs = [
                FunctionDefinition(
                    function_path="rain_check",
                    commands=["give @a diamond 1"],
                    namespace="minecraft_ai"
                )
            ]

            gen_result = generator.generate(
                plan=plan,
                understanding=understanding,
                functions=funcs,
                create_zip=True,
                clean=True
            )

            # 1. Output directory was created successfully (no WinError 123)
            self.assertTrue(gen_result.datapack_path.exists())
            self.assertTrue(gen_result.datapack_path.is_dir())

            # 2. Output ZIP was created successfully
            self.assertIsNotNone(gen_result.zip_path)
            self.assertTrue(gen_result.zip_path.exists())

            # 3. Directory name matches ZIP stem exactly
            self.assertEqual(gen_result.datapack_path.name, gen_result.zip_path.stem)
            self.assertLessEqual(len(gen_result.datapack_name), 60)

            # 4. Manifest exists inside generated folder
            mcmeta = gen_result.datapack_path / "pack.mcmeta"
            self.assertTrue(mcmeta.exists())

    def test_6_explicitly_supplied_datapack_name_is_preserved(self):
        """Explicitly passed datapack_name values must be preserved as supplied."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = Path(tmp_dir)
            generator = DatapackGenerator(output_dir=out_path, version="1.21.11")

            funcs = [
                FunctionDefinition(
                    function_path="hello",
                    commands=["say hello"],
                    namespace="minecraft_ai"
                )
            ]

            gen_result = generator.generate(
                functions=funcs,
                datapack_name="custom_explicit_pack_name",
                create_zip=True
            )

            self.assertEqual(gen_result.datapack_name, "custom_explicit_pack_name")
            self.assertEqual(gen_result.datapack_path.name, "custom_explicit_pack_name")
            self.assertEqual(gen_result.zip_path.name, "custom_explicit_pack_name.zip")

    def test_7_empty_text_slugify_fallback(self):
        """Empty or whitespace-only strings must fallback safely to 'datapack'."""
        self.assertEqual(slugify(""), "datapack")
        self.assertEqual(slugify("   "), "datapack")
        self.assertEqual(slugify("---___---"), "datapack")


if __name__ == "__main__":
    unittest.main()
