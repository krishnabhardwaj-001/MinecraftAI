# MinecraftAI Tasks

## Current
- [x] Step 16: Support advanced scoreboard-based systems, objectives, and arithmetic operations.
  - [x] Step 16.1: Scoreboard domain knowledge registry, indexing, and RAG retrieval.
  - [x] Step 16.2: Structured data contracts and Pydantic models (ActionSpecification & MechanismSpecification).
  - [x] Step 16.3: Deterministic scoreboard command compilation and generator integration.
  - [x] Step 16.4: Deterministic static validation for scoreboard commands.
  - [x] Step 16.5: QA semantic analysis & runtime simulation for scoreboards.
  - [x] Step 16.6: Planner system prompt and instruction alignment.
  - [x] Step 16.7: Automated verification & regression testing.
- [x] Step 17.1: Semantic property modification models (PropertyModification, SemanticNumericValue, SemanticValue).
- [x] Step 17.2: Generic natural-language numeric interpretation (NumericSemanticInterpreter).
- [x] Step 17.3: Planner semantic property-modification integration (plan_property_modification, action & mechanism specs).
  - [x] Step 17.3 Audit Blocker Remediation: extra_metadata contract, qualitative operation=None, data-driven PropertyCapabilityRegistry, generic compound request planning.
- [x] Step 17.4: Generic clarification redesign for underspecified properties and magnitudes (ai/clarification.py, test_step17_clarification.py).
- [x] Step 17.5: Deterministic Minecraft implementation mapping (ImplementationMapper in ai/implementation_mapper.py, test_step17_mapper.py).
  - [x] Step 17.5 Audit Remediation: Generic capability modeling in PropertyCapabilityRegistry, exact (property, operation, value.kind) selection, attribute mechanism mapping for speed multipliers/relatives, strict semantic preservation, structural failure for invalid generator inputs, comparative numeric interpretation, single-target /attribute execution context wrapping, and deterministic unique modifier identities for identical independently intended actions.
- [x] Step 18: Full End-to-End Property Modification Pipeline, Static Validation & Verification Gate.
  - [x] Step 18.1: DatapackGenerator extraction of `property_modification` / `modify_property` mechanisms and safe function resource paths (no '@a.mcfunction').
  - [x] Step 18.2: Deterministic static validation for Minecraft Java 1.21.11 `/attribute` commands, single-entity targets, valid attribute IDs/aliases, operations, values, and modifier IDs (`validator/datapack_validator.py`).
  - [x] Step 18.3: QA Static Semantic Analysis for attribute command execution context, unanchored `@s` detection, duplicate modifier ID collision detection, and hazardous attribute values (`qa/analyzer.py`).
  - [x] Step 18.4: Pipeline-level structured clarification propagation (`pipeline/models.py`, `pipeline/minecraft_pipeline.py`).
  - [x] Step 18.5: Comprehensive Step 18 automated verification test suite (`test_step18_verification.py`, 24 tests).
- [x] Step 19: Pipeline & Interface Alignment (Completed & Remediated).
  - [x] Step 19.1: Web clarification options exposure and dynamic chip rendering (`web/app.py`, `web/static/js/app.js`, `web/templates/index.html`).
  - [x] Step 19.2: CLI clarification options display, numbered selection, and request refinement (`run_pipeline.py`).
  - [x] Step 19.3: Web UI authoritative 8-stage pipeline tracker (`web/templates/index.html`, `web/static/js/app.js`).
  - [x] Step 19.4: Strengthened QA property modification intent verification against capabilities and generated commands (`qa/reviewer.py`).
  - [x] Step 19.5: Collision-safe QA structured duplicate modifier repair (`qa/repair.py`).
  - [x] Step 19.6: Comprehensive Step 19 automated test suite (`test_step19_alignment.py`, 17 tests).
- [ ] Step 20: Final Project Completion & Verification.
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
- [x] Step 16.1: Scoreboard Domain Knowledge and RAG Integration (`knowledge/scoreboards/java/1.21.11/scoreboards.json`, `knowledge_retriever.py`, `ai/context.py`, `test_retrieval.py`).
- [x] Step 16.2: Structured Data Contracts & Models for Scoreboards (`generator/models.py`, `test_step16_models.py`).
- [x] Step 16.3: Deterministic Scoreboard Command Generation and Resource Consolidation (`generator/mechanisms/function_mech.py`, `generator/mechanisms/state_machine_mech.py`, `generator/datapack_generator.py`, `test_step16_generator.py`).

## Rule
Tasks describe project work, not special cases for individual example prompts. If an example exposes a problem, fix the underlying generic capability.
