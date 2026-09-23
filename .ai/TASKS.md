# MinecraftAI Tasks

## Current
- [ ] Support advanced scoreboard-based systems and objectives.
- [ ] Improve generic natural-language numeric interpretation, including multiplier expressions.
- [ ] Improve generic clarification handling for underspecified properties.
- [ ] Keep AI context files synchronized after significant changes.

## Completed / established
- [x] Git repository established and connected to the project workflow.
- [x] Shared `.ai/` context structure created.
- [x] `AGENTS.md` added with cross-agent instructions.
- [x] Command knowledge generated for Minecraft Java 1.21.11.
- [x] Semantic retrieval traceback fixed.
- [x] Target validation fixed for targets such as `@s`.
- [x] Clarification state added for ambiguous requests.
- [x] Expand Minecraft 1.21.11 knowledge/RAG to entities, items, and loot tables with generic morphological normalization.
- [x] Build deterministic datapack generator from structured plans (Step 5 - `generator/`).
- [x] Build deterministic datapack validator/tester (Step 6 - `validator/`).
- [x] Build structured AI repair loop with retry protection and diagnostic history (Step 7 - `repair/`).
- [x] Complete end-to-end natural-language → datapack ZIP pipeline (Step 8 Orchestrator - `pipeline/`, `run_pipeline.py`, `test_pipeline.py`).
- [x] Build user-facing web interface and direct ZIP download endpoint (Step 9 - `web/`, `run_web.py`, `test_web.py`).
# MinecraftAI Tasks

## Current
- [ ] Support advanced scoreboard-based systems and objectives.
- [ ] Improve generic natural-language numeric interpretation, including multiplier expressions.
- [ ] Improve generic clarification handling for underspecified properties.
- [ ] Keep AI context files synchronized after significant changes.

## Completed / established
- [x] Git repository established and connected to the project workflow.
- [x] Shared `.ai/` context structure created.
- [x] `AGENTS.md` added with cross-agent instructions.
- [x] Command knowledge generated for Minecraft Java 1.21.11.
- [x] Semantic retrieval traceback fixed.
- [x] Target validation fixed for targets such as `@s`.
- [x] Clarification state added for ambiguous requests.
- [x] Expand Minecraft 1.21.11 knowledge/RAG to entities, items, and loot tables with generic morphological normalization.
- [x] Build deterministic datapack generator from structured plans (Step 5 - `generator/`).
- [x] Build deterministic datapack validator/tester (Step 6 - `validator/`).
- [x] Build structured AI repair loop with retry protection and diagnostic history (Step 7 - `repair/`).
- [x] Complete end-to-end natural-language → datapack ZIP pipeline (Step 8 Orchestrator - `pipeline/`, `run_pipeline.py`, `test_pipeline.py`).
- [x] Build user-facing web interface and direct ZIP download endpoint (Step 9 - `web/`, `run_web.py`, `test_web.py`).
- [x] Build multi-mechanism deterministic generator & validator architecture supporting loot tables, functions, function tags, and advancements (Step 10 - `generator/mechanisms/`, `test_mechanisms.py`).
- [x] Improve Planner → Generator boundary with structured MechanismSpecification schemas, typed parameter validation, and direct deterministic generator consumption (Step 11 - `generator/models.py`, `ai/planner.py`, `generator/datapack_generator.py`, `test_planner_boundary.py`).
- [x] Support custom recipe generation (`data/<ns>/recipe/*.json`) across shaped crafting, shapeless crafting, and smelting with modern 1.21+ result schema and item ID validation (Step 12 - `generator/mechanisms/recipe_mech.py`, `generator/models.py`, `validator/datapack_validator.py`, `test_recipes.py`).
- [x] Support custom predicate generation (`data/<ns>/predicate/*.json`) and advanced condition trees across 19 authoritative 1.21.11 condition types, composite predicates (`all_of`, `any_of`, `inverted`), strongly-typed Planner specification models, deterministic generation, entity/item identifier validation, and RAG knowledge integration (Step 13 - `generator/mechanisms/predicate_mech.py`, `generator/models.py`, `validator/datapack_validator.py`, `knowledge/predicates/`, `test_predicates.py`).
- [x] Investigate and resolve Minecraft 1.21.11 runtime execution failure in Step 13 state machine design: load function empty selector resolution, global vs per-player state machine architecture, dynamic per-player tick initialization, DatapackValidator EMPTY_SELECTOR_ON_LOAD warning check, and generic regression test suite (`test_state_machine.py`).
- [x] Implement Autonomous Datapack QA, Verification & Auto-Repair (Step 14 - `qa/` package, `StaticSemanticAnalyzer`, `AutonomousQAReviewer`, `QARepairEngine`, `RuntimeTestRunner`, bounded QA loop with repeat failure detection, final READY gate, and `test_qa.py`).
- [x] Strengthen Planner → Generator Boundary with structured declarative ActionSpecifications, deterministic command synthesis, dedicated state machine generator with replace: false function tags, and shared resource consolidation (Step 15 - `generator/models.py`, `generator/mechanisms/function_mech.py`, `generator/mechanisms/state_machine_mech.py`, `ai/planner.py`, `qa/repair.py`, `test_step15_boundary.py`).
- [x] Function Tag Minimal Formatting, Multi-Datapack Tag Aggregation, and Dangling Reference Sanitization (`generator/mechanisms/tag_mech.py`, `generator/mechanisms/state_machine_mech.py`, `generator/datapack_generator.py`, `validator/datapack_validator.py`, `knowledge/tags/`, `test_generator.py`, `test_mechanisms.py`, `test_validator.py`).

## Rule
Tasks describe project work, not special cases for individual example prompts. If an example exposes a problem, fix the underlying generic capability.
