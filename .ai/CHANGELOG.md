# AI Change Log

## 2026-09-16
- Established the repository as shared context for multiple AI agents.
- Added `AGENTS.md` with instructions for Antigravity and ChatGPT/Codex.
- Documented project purpose, architecture, current state, decisions, and tasks in `.ai/`.
- Recorded the generic pipeline requirement and the prohibition on request-specific hardcoding.
- Implemented generic Minecraft Java 1.21.11 entity, item, and loot table RAG retrieval with morphological normalization in `knowledge_retriever.py` and `ai/context.py`.
- Implemented STEP 5: Deterministic Datapack Generator v1 (`generator/` package) with loot table modification/override preserving original Minecraft drops, `pack_format: 94`, singular `loot_table` directory layout, and deterministic zip archiving.
- Implemented STEP 6: Deterministic Datapack Validator / Tester (`validator/` package) checking `pack.mcmeta` (`pack_format: 94`), directory hierarchy, JSON syntax, loot table schemas, item IDs against 1.21.11 knowledge, zip path traversal guards, and vanilla drop preservation. Added comprehensive automated test suite `test_validator.py`.
- Implemented STEP 7: Automatic AI Repair Loop (`repair/` package) with `AIRepairLoop`, `RepairAttempt`, `RepairPlan`, and `RepairResult`. Diagnoses structured validator errors against Minecraft knowledge and requirements, returns corrected implementation plans to `DatapackGenerator`, enforces configurable retry protection without infinite loops, records full attempt history, and short-circuits on valid datapacks. Added comprehensive automated test suite `test_repair_loop.py` (7 tests passing).

## Earlier development
- Built and iterated natural-language Minecraft request understanding.
- Added Minecraft Java 1.21.11 command knowledge/retrieval.
- Fixed semantic retrieval and target validation issues.
- Added clarification behavior for ambiguous requests.
