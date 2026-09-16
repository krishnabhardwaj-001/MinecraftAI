# MinecraftAI Tasks

## Current
- [ ] Support custom recipe generation (`data/<ns>/recipe/*.json`) and crafting mechanics.
- [ ] Support custom predicates (`data/<ns>/predicate/*.json`) and advanced condition trees.
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

## Rule
Tasks describe project work, not special cases for individual example prompts. If an example exposes a problem, fix the underlying generic capability.
