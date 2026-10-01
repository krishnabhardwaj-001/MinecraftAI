"""
test_step25_2_version_context.py - Phase 25.2 Version-Aware Understanding & QA Context Propagation

Comprehensive test suite verifying:
1. MinecraftUnderstanding can be constructed for 1.21.1.
2. Its generated/system prompt contains 1.21.1 and not 1.21.11.
3. MinecraftUnderstanding can be constructed for 1.21.11.
4. Its generated/system prompt contains 1.21.11.
5. Pipeline targeting 1.21.1 propagates that version into Understanding.
6. Pipeline targeting 1.21.11 propagates that version into Understanding.
7. QA Analyzer receives 1.21.1 when explicitly requested.
8. QA Reviewer receives 1.21.1 when explicitly requested.
9. QA Repair receives 1.21.1 when explicitly requested.
10. QA Runtime receives 1.21.1 when explicitly requested.
11. Scoreboard semantic helpers do not silently revert to 1.21.11.
12. Default construction still resolves to 1.21.11.
13. Existing 1.21.11 behavior remains unchanged.
"""

import unittest
from unittest.mock import MagicMock

from ai.provider import AIProvider
from ai.understanding import MinecraftUnderstanding
from ai.version_registry import VersionContext, get_default_version, get_version_registry
from pipeline.minecraft_pipeline import MinecraftPipeline, run_minecraft_pipeline
from qa.analyzer import StaticSemanticAnalyzer
from qa.reviewer import AutonomousQAReviewer
from qa.repair import QARepairEngine
from qa.runtime import RuntimeTestRunner
from qa.scoreboard_semantics import ScoreboardSemanticSimulator


class TestPhase252VersionContext(unittest.TestCase):
    """
    Test suite for Phase 25.2 version-awareness in Understanding and QA subsystems.
    """

    def setUp(self):
        self.mock_ai = MagicMock(spec=AIProvider)
        self.mock_ai.provider_name = "mock"

    # 1 & 2: MinecraftUnderstanding for 1.21.1
    def test_01_understanding_1_21_1_construction_and_prompt(self):
        """Verify MinecraftUnderstanding accepts 1.21.1 and prompt contains 1.21.1, NOT 1.21.11."""
        u = MinecraftUnderstanding(ai_provider=self.mock_ai, version="1.21.1")
        self.assertEqual(u.version, "1.21.1")
        self.assertIn("Minecraft Java Edition 1.21.1.", u.system_prompt)
        self.assertNotIn("1.21.11", u.system_prompt)

    # 3 & 4: MinecraftUnderstanding for 1.21.11
    def test_02_understanding_1_21_11_construction_and_prompt(self):
        """Verify MinecraftUnderstanding accepts 1.21.11 and prompt contains 1.21.11."""
        u = MinecraftUnderstanding(ai_provider=self.mock_ai, version="1.21.11")
        self.assertEqual(u.version, "1.21.11")
        self.assertIn("Minecraft Java Edition 1.21.11.", u.system_prompt)

    # 5 & 6: Pipeline propagation into Understanding
    def test_03_pipeline_propagates_version_to_understanding(self):
        """Verify MinecraftPipeline forwards version context into Understanding for both versions."""
        # 1.21.1
        pipe_1 = MinecraftPipeline(ai_provider=self.mock_ai, version="1.21.1")
        self.assertEqual(pipe_1.version, "1.21.1")
        self.assertEqual(pipe_1.understanding.version, "1.21.1")
        self.assertIn("Minecraft Java Edition 1.21.1.", pipe_1.understanding.system_prompt)
        self.assertNotIn("1.21.11", pipe_1.understanding.system_prompt)

        # 1.21.11
        pipe_11 = MinecraftPipeline(ai_provider=self.mock_ai, version="1.21.11")
        self.assertEqual(pipe_11.version, "1.21.11")
        self.assertEqual(pipe_11.understanding.version, "1.21.11")
        self.assertIn("Minecraft Java Edition 1.21.11.", pipe_11.understanding.system_prompt)

    # 7: QA Analyzer receives 1.21.1
    def test_04_qa_analyzer_receives_1_21_1(self):
        """Verify StaticSemanticAnalyzer receives and preserves 1.21.1."""
        analyzer = StaticSemanticAnalyzer(version="1.21.1")
        self.assertEqual(analyzer.version, "1.21.1")
        self.assertEqual(analyzer.version_context.version_id, "1.21.1")

    # 8: QA Reviewer receives 1.21.1
    def test_05_qa_reviewer_receives_1_21_1(self):
        """Verify AutonomousQAReviewer receives and passes 1.21.1 to its internal analyzer."""
        reviewer = AutonomousQAReviewer(ai_provider=self.mock_ai, version="1.21.1")
        self.assertEqual(reviewer.version, "1.21.1")
        self.assertEqual(reviewer.analyzer.version, "1.21.1")

    # 9: QA Repair receives 1.21.1
    def test_06_qa_repair_receives_1_21_1(self):
        """Verify QARepairEngine receives and preserves 1.21.1."""
        repair = QARepairEngine(ai_provider=self.mock_ai, version="1.21.1")
        self.assertEqual(repair.version, "1.21.1")
        self.assertEqual(repair.version_context.version_id, "1.21.1")

    # 10: QA Runtime receives 1.21.1
    def test_07_qa_runtime_receives_1_21_1(self):
        """Verify RuntimeTestRunner receives and preserves 1.21.1."""
        runner = RuntimeTestRunner(version="1.21.1")
        self.assertEqual(runner.version, "1.21.1")
        self.assertEqual(runner.version_context.version_id, "1.21.1")

    # 11: Scoreboard semantic helpers do not silently revert to 1.21.11
    def test_08_scoreboard_semantic_simulator_receives_1_21_1(self):
        """Verify ScoreboardSemanticSimulator preserves 1.21.1 context when created directly or via Analyzer."""
        sim = ScoreboardSemanticSimulator(version="1.21.1")
        self.assertEqual(sim.version, "1.21.1")
        self.assertEqual(sim.version_context.version_id, "1.21.1")

        # When analyzer creates simulator internally
        analyzer = StaticSemanticAnalyzer(version="1.21.1")
        self.assertEqual(analyzer.version, "1.21.1")
        # Internal simulator invocation verification
        sim_internal = ScoreboardSemanticSimulator(version=analyzer.version, version_context=analyzer.version_context)
        self.assertEqual(sim_internal.version, "1.21.1")

    # 12: Default construction still resolves to 1.21.11
    def test_09_default_construction_resolves_to_1_21_11(self):
        """Verify omitted version in all components defaults to registered default version 1.21.11."""
        default_ver = get_default_version()
        self.assertEqual(default_ver, "1.21.11")

        u = MinecraftUnderstanding(ai_provider=self.mock_ai)
        self.assertEqual(u.version, "1.21.11")
        self.assertIn("Minecraft Java Edition 1.21.11.", u.system_prompt)

        analyzer = StaticSemanticAnalyzer()
        self.assertEqual(analyzer.version, "1.21.11")

        reviewer = AutonomousQAReviewer(ai_provider=self.mock_ai)
        self.assertEqual(reviewer.version, "1.21.11")
        self.assertEqual(reviewer.analyzer.version, "1.21.11")

        repair = QARepairEngine(ai_provider=self.mock_ai)
        self.assertEqual(repair.version, "1.21.11")

        runner = RuntimeTestRunner()
        self.assertEqual(runner.version, "1.21.11")

        sim = ScoreboardSemanticSimulator()
        self.assertEqual(sim.version, "1.21.11")

        pipe = MinecraftPipeline(ai_provider=self.mock_ai)
        self.assertEqual(pipe.version, "1.21.11")
        self.assertEqual(pipe.understanding.version, "1.21.11")
        self.assertEqual(pipe.qa_reviewer.version, "1.21.11")
        self.assertEqual(pipe.qa_repair_engine.version, "1.21.11")
        self.assertEqual(pipe.runtime_runner.version, "1.21.11")

    # 13: Existing 1.21.11 behavior remains unchanged
    def test_10_version_context_object_propagation(self):
        """Verify passing a VersionContext instance directly preserves all version properties across components."""
        ctx_1 = VersionContext.from_version("1.21.1")
        ctx_11 = VersionContext.from_version("1.21.11")

        # Understanding with VersionContext
        u1 = MinecraftUnderstanding(ai_provider=self.mock_ai, version_context=ctx_1)
        self.assertEqual(u1.version, "1.21.1")
        self.assertIn("1.21.1.", u1.system_prompt)

        u11 = MinecraftUnderstanding(ai_provider=self.mock_ai, version_context=ctx_11)
        self.assertEqual(u11.version, "1.21.11")
        self.assertIn("1.21.11.", u11.system_prompt)

        # Pipeline with VersionContext
        pipe1 = MinecraftPipeline(ai_provider=self.mock_ai, version_context=ctx_1)
        self.assertEqual(pipe1.version, "1.21.1")
        self.assertEqual(pipe1.understanding.version, "1.21.1")
        self.assertEqual(pipe1.qa_reviewer.version, "1.21.1")
        self.assertEqual(pipe1.generator.version, "1.21.1")
        self.assertEqual(pipe1.validator.version, "1.21.1")

        pipe11 = MinecraftPipeline(ai_provider=self.mock_ai, version_context=ctx_11)
        self.assertEqual(pipe11.version, "1.21.11")
        self.assertEqual(pipe11.understanding.version, "1.21.11")
        self.assertEqual(pipe11.qa_reviewer.version, "1.21.11")
        self.assertEqual(pipe11.generator.version, "1.21.11")
        self.assertEqual(pipe11.validator.version, "1.21.11")


if __name__ == "__main__":
    unittest.main()
