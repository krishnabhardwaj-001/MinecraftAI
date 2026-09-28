# MinecraftAI — Project Context

## Purpose
MinecraftAI is being developed as a fully automatic Minecraft Java datapack maker. A user should be able to describe a desired datapack in natural language and the system should understand the request, use Minecraft-version-specific knowledge, plan the implementation, generate a deterministic datapack, validate/test it, repair problems when possible, and return the final datapack ZIP.

## Target Minecraft version
- Minecraft Java Edition 1.21.11

## Required architecture
The project operates as an authoritative 8-stage pipeline:
1. Natural-Language Understanding (`ai/understanding.py`)
2. Minecraft 1.21.11 Knowledge & RAG Retrieval (`knowledge_retriever.py`, `knowledge/`)
3. Planning & Disambiguation (`ai/planner.py`, `ai/clarification.py`)
4. Deterministic Implementation Mapping (`ai/implementation_mapper.py`, `ai/property_registry.py`)
5. Deterministic Multi-Mechanism Generation (`generator/`, `generator/mechanisms/`)
6. Deterministic Static Validation & Structural Repair (`validator/`, `repair/`)
7. Autonomous Datapack QA, Temporal Simulation & Deep Intent Verification (`qa/`)
8. Strict READY Gate & Byte-for-Byte Reproducible ZIP Output (`pipeline/`, `run_pipeline.py`, `web/`)

This architecture is generic, version-aware, and deterministic.

## Target Minecraft version
- Minecraft Java Edition 1.21.11 (Data Pack version 94.1 / `pack_format: 94`, `min_format: [94, 0]`, `max_format: [94, 1]`)

## Authoritative Mechanism Domains (7 Supported Domains)
The deterministic generator and validator support 7 first-class mechanism domains:
1. `loot_table`: Vanilla drop preservation, conditions, and arbitrary entity drops (`generator/mechanisms/loot_table_mech.py`).
2. `function`: Sanitized leading slashes, context-aware command synthesis (`generator/mechanisms/function_mech.py`).
3. `function_tag`: Canonical minimal formatting (`values: [...]`), `#minecraft:load`/`#minecraft:tick` game-loop routing, multi-datapack aggregation, and dangling reference sanitization (`generator/mechanisms/tag_mech.py`).
4. `advancement`: Custom criteria, triggers, display info, and rewards (`generator/mechanisms/advancement_mech.py`).
5. `recipe`: Modern 1.21+ result schema (`{"id": ..., "count": ...}`), shaped crafting, shapeless crafting, and smelting (`generator/mechanisms/recipe_mech.py`).
6. `predicate`: All 19 Java 1.21.11 condition types and composite trees (`all_of`, `any_of`, `inverted`) (`generator/mechanisms/predicate_mech.py`).
7. `state_machine`: Dedicated generator for temporal state machines, `#global` persistent environmental scoreboards, dynamic join per-player scoreboards, and multi-mechanism function merging (`generator/mechanisms/state_machine_mech.py`).

## Semantic Property Modification Pipeline
- Structured semantic models (`PropertyModification`, `SemanticNumericValue`, `SemanticValue`) strictly preserve numeric kinds (`absolute`, `relative`, `percentage`, `multiplier`, `qualitative`).
- Generic numeric interpretation (`NumericSemanticInterpreter`) parses natural-language modifications without entity/property hardcoding.
- Sourced purely from `PropertyCapabilityRegistry`; exact `(property, operation, value.kind)` capability selection via `ImplementationMapper`.
- Multipliers and relative values map to `attribute` (`minecraft:generic.movement_speed`) compiling `add_multiplied_total` and `add_value`/`add_multiplied_base`.
- Single-entity target context wrapping (`execute as {target} run attribute @s ...`).
- Deterministic modifier identities (`minecraft_ai:{property}_{op}_{val}_{step_id}`) preventing collisions while allowing independent stacking.

## Real-Minecraft Verification Harness
- Automated sandbox runtime harness (`qa/runtime.py`) executing Java 21 LTS (`21.0.12`), `versions/1.21.11/server-1.21.11.jar`, and runtime classpath dependencies in `libraries/`.
- Empirically verifies server boot, datapack discovery, ZIP installation, load function execution, 20Hz tick loop advancement, rain state-machine transitions, attribute modifiers, duplicate modifier coexistence, tag integrity on `/reload`, and clean shutdown with exit code 0.
- Authoritative manual verification protocol documented in `.ai/REAL_MINECRAFT_VERIFICATION.md` for in-game client verification (advancement screen GUI, scoreboard sidebar display, visual FOV/particle feel).

## Packaging & Distribution Architecture
- Standard `pyproject.toml` specification utilizing `setuptools>=61.0`.
- Python runtime requirement `>=3.10` (supporting 3.10, 3.11, 3.12, 3.13).
- Explicit minimal runtime dependencies (`pydantic>=2.0.0`, `fastapi>=0.100.0`, `uvicorn>=0.20.0`, `jinja2>=3.1.0`, `ollama>=0.2.0`, `openai>=1.0.0`, `python-dotenv>=1.0.0`, `httpx>=0.24.0`).
- Console script entry points: `minecraft-ai` (`run_pipeline:main`) and `minecraft-ai-web` (`run_web:main`).
- Windows launchers: `launch_cli.bat` and `launch_web.bat` with directory anchoring (`cd /d "%~dp0"`), python environment verification, and clean parameter forwarding.
- Editable installation supported via `pip install -e .` without altering repository layout.

## Important design requirement
The system supports arbitrary user requests. It does not implement individual examples with hardcoded `if/else` mappings or special files such as `zombie.json` or `chicken.json`. Examples are regression tests, not special-case code.

## Current knowledge base
- Minecraft Java 1.21.11 command knowledge generated from Minecraft report data (~1273 syntax records across 85 commands).
- Full domain registries for entities, items, effects, loot tables, recipes, predicates, scoreboards, and attributes.
- Authoritative registry files under `knowledge/` indexed dynamically by `MinecraftKnowledgeRetriever`.

## AI/runtime & diagnostic direction
- Local Ollama models (`llama3.1:8b`) are supported by default without requiring an external API key.
- Offline diagnostic hardening: When Ollama is offline or unreachable, the system returns clear, actionable troubleshooting instructions (`ollama serve`, endpoint info, model pull instructions) rather than unhandled tracebacks.
- External providers (e.g. OpenAI via `OPENAI_API_KEY`) can be configured where supported.

## Working principle
Every implementation change improves the generic pipeline rather than optimizing for one demonstration request.
