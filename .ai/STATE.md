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

## Known issues / gaps
- `10 times faster` is not yet interpreted reliably.
- Some combined requests still need better generic clarification when a property is underspecified, such as attack damage.
- Generator, validator, and repair coverage currently focus on loot tables and pack structure; custom `.mcfunction` functions, recipes, and advancement pipelines will expand in future steps.

## Current priority
Maintain stability of the generic end-to-end pipeline and prepare for feature expansion (functions, recipes, advancements).

## Next logical work
1. Step 9: Expand generator, validator, and repair loop to support custom `.mcfunction` functions, command triggers, recipes, and advancements.
2. Strengthen generic numeric multiplier parsing and parameter normalization.
3. Add web UI or interactive frontend on top of the clean pipeline API.
4. Keep shared AI context synchronized for Antigravity and ChatGPT/Codex.

## Agent handoff rule
Before changing code, verify this state against the actual repository and Git history. After significant changes, update this file and the other relevant `.ai/` files.
