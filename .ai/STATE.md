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

## Known issues / gaps
- `10 times faster` is not yet interpreted reliably.
- Some combined requests still need better generic clarification when a property is underspecified, such as attack damage.
- The full deterministic datapack generator is not yet the final completed pipeline.
- Validator/tester and automatic AI repair loop need further implementation.
- Knowledge coverage beyond command syntax needs expansion.

## Current priority
Build the generic end-to-end pipeline without hardcoded request-specific behavior.

## Next logical work
1. Strengthen generic intent normalization and ambiguity handling.
2. Improve Minecraft knowledge retrieval and typed planning.
3. Build deterministic datapack generation from validated plans.
4. Add validation/testing and structured AI repair.
5. Keep shared AI context synchronized for Antigravity and ChatGPT/Codex.

## Agent handoff rule
Before changing code, verify this state against the actual repository and Git history. After significant changes, update this file and the other relevant `.ai/` files.
