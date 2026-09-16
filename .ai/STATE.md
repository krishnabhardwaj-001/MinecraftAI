# Current Project State

## Last synchronized
2026-09-16

## Current implementation
- Natural-language Minecraft request understanding is being developed in the `ai/` package.
- Minecraft command knowledge/retrieval is available for Java 1.21.11.
- Planner/context/schema components exist and are being iterated.
- Local Ollama inference is part of the intended runtime path.
- GitHub is connected as the shared repository source for AI-agent synchronization.

## Working behavior verified during development
- Semantic retrieval works after a previous traceback fix.
- Targets such as `@s` pass target validation.
- Ambiguous requests can return a clarification state instead of forcing an arbitrary interpretation.
- `make me faster` has produced a speed effect in testing.
- Multi-action requests can produce multiple planned actions.
- Generic entity, item, and loot-table RAG retrieval operational for arbitrary mobs and items (verified on creepers, zombies, skeletons, spiders).
- Deterministic Datapack Generator v1 (`generator/`) operational: creates valid Java 1.21.11 datapacks (`pack_format: 94`), modifies entity loot tables while preserving original drops/conditions/random sequences, and produces reproducible JSON and ZIP files.
- Deterministic Datapack Validator / Tester (`validator/`) operational: validates directories and ZIPs, detects corrupt/unsafe archives, enforces 1.21.11 `pack_format: 94` and singular `loot_table` paths, validates item IDs against 1.21.11 knowledge base, and checks vanilla drop preservation.
- Automatic AI Repair Loop (`repair/`) operational: diagnoses deterministic validator errors against Minecraft knowledge, generates corrected implementation plans, feeds them into the deterministic generator, enforces configurable retry protection without infinite loops, and records comprehensive attempt histories (verified with 7 automated tests in `test_repair_loop.py`).
- End-to-End Pipeline Orchestration (`pipeline/`) operational: public entry point `run_minecraft_pipeline()` coordinates Understanding, RAG Knowledge Retrieval, Planner, Generator, Validator, AI Repair Loop, and Final Validated Datapack ZIP. Full integration verified across 8 automated tests in `test_pipeline.py` (creeper drops diamonds, skeleton drops iron, ambiguous clarification halt, invalid pack repair recovery, permanent failure reporting with attempt history, arbitrary spider->iron_ingot drops, and ZIP tamper detection).
- CLI entry point `run_pipeline.py` operational with stage progress indicators `[1/7]` to `[7/7]`.
- Authoritative pack format 94 / 94.1 audit completed: generator emits `pack_format: 94`, `min_format: [94, 0]`, and `max_format: [94, 1]` for universal compatibility.
- User-facing Web Interface (`web/`) operational: decoupled FastAPI backend with endpoints (`GET /`, `POST /api/generate`, `GET /api/download/{filename}`, `GET /api/health`), path-traversal protected ZIP streaming, and modern Obsidian & Emerald dark-mode single-page UI with visual 7-stage tracker, dynamic outcome cards (Success with ZIP download, Clarification with refinement prompt, and Repair diagnostics), verified with 6 automated tests in `test_web.py`.
- Web CLI runner `run_web.py` operational (`python run_web.py --port 8000`).
- Multi-Mechanism Datapack Generator Architecture (`generator/mechanisms/`) operational: modular mechanism generators (`LootTableMechanismGenerator`, `FunctionMechanismGenerator`, `FunctionTagMechanismGenerator`, `AdvancementMechanismGenerator`) implementing `BaseMechanismGenerator` and returning `DatapackResource` objects. Supports custom functions (`data/<ns>/function/*.mcfunction`) with automatic leading slash sanitization, function tags (`data/<ns>/tags/function/*.json`) supporting `#minecraft:tick` and `#minecraft:load`, and advancements (`data/<ns>/advancement/*.json`). The validator verifies all mechanisms and rejects legacy 1.20- plural directories. Multi-mechanism composition and deterministic byte-identical zip reproducibility verified with 7 automated tests in `test_mechanisms.py` and 46/46 tests passing across all suites.
- Structured Planner → Generator Boundary (Step 11) operational: machine-readable `MechanismSpecification` data contract established in `generator/models.py`, `ai/planner.py`, and `generator/datapack_generator.py`. The Planner populates strongly typed mechanism parameters (`target`, `item`, `count`, `operation`, `commands`, `namespace`, `path`, `tag_name`, `values`, `criteria`, `rewards`) using retrieved Minecraft domain facts rather than vague prose. `validate_mechanism_specification` strictly validates specification completeness per mechanism type before resource generation. `DatapackGenerator.extract_mechanisms()` directly maps specifications into deterministic mechanism definitions (`to_*()` methods) while preserving backward compatibility for legacy minimal plans. Dynamic clarification pauses and arbitrary mob/item genericity verified with 13 automated tests in `test_planner_boundary.py` and 59/59 tests passing across the entire project repository.

## Known issues / gaps
- `10 times faster` is not yet interpreted reliably.
- Some combined requests still need better generic clarification when a property is underspecified, such as attack damage.
- Generator mechanisms now support loot tables, functions, tick/load tags, and advancements with structured planner specifications; custom recipes, predicates, and complex multi-scoreboard systems remain for future steps.

## Current priority
Expand deterministic datapack generation and validation capabilities to custom recipes, predicates, and advanced scoreboards.

## Next logical work
1. Support custom recipe creation (`data/<ns>/recipe/*.json`) and crafting mechanics.
2. Support custom predicates (`data/<ns>/predicate/*.json`) and advanced condition trees.
3. Strengthen generic numeric multiplier parsing and parameter normalization.
4. Keep shared AI context synchronized for Antigravity and ChatGPT/Codex.

## Agent handoff rule
Before changing code, verify this state against the actual repository and Git history. After significant changes, update this file and the other relevant `.ai/` files.
