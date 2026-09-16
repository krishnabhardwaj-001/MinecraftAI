# MinecraftAI — Project Context

## Purpose
MinecraftAI is being developed as a fully automatic Minecraft Java datapack maker. A user should be able to describe a desired datapack in natural language and the system should understand the request, use Minecraft-version-specific knowledge, plan the implementation, generate a deterministic datapack, validate/test it, repair problems when possible, and return the final datapack ZIP.

## Target Minecraft version
- Minecraft Java Edition 1.21.11

## Required architecture
Natural-language user request
→ Generic AI Understanding
→ Minecraft-specific Knowledge / RAG
→ Planner
→ Deterministic Datapack Generator
→ Validator / Tester
→ AI repair loop
→ Final datapack ZIP

This architecture must remain generic and extensible.

## Important design requirement
The system must support arbitrary user requests. Do not implement individual examples with hardcoded `if/else` mappings or special files such as `zombie.json` or `chicken.json`. Examples are tests, not features that should be hardcoded.

## Current knowledge base
- Minecraft Java 1.21.11 command knowledge has been generated from the Minecraft report data.
- Command syntax knowledge contains about 1273 syntax records.
- The command description index contains about 85 unique commands.
- Source command report: `generated/reports/commands.json` for the relevant 1.21.11 generated data.

## AI/runtime direction
- Local Ollama models are preferred where practical because the project should work without requiring an external API key.
- The development machine has limited RAM for very large local models, so model selection should consider resource usage.

## Current capabilities and recent work
- Semantic retrieval traceback was fixed.
- Target validation was fixed for targets such as `@s`.
- Ambiguous requests can produce `needs_clarification` instead of blindly choosing an interpretation.
- Example: `make me stronger` can ask whether the user means Strength, health, equipment, or another kind of strengthening.
- Example: `make me faster` can produce a speed effect.
- Multiple actions in one request can be represented, such as a speed change plus giving an item.

## Known gaps to continue improving
- Numeric natural-language expressions such as `10 times faster` need more robust interpretation.
- Ambiguous multi-part requests need systematic clarification rules rather than request-specific hacks.
- The deterministic generator, validator/tester, and AI repair loop still need to be developed into the complete automatic pipeline.
- Minecraft-specific knowledge needs to expand beyond command syntax into entities, items, effects, loot tables, predicates, functions, and other datapack-relevant resources in a version-aware way.

## Working principle
Every implementation change should improve the generic pipeline rather than optimize for one demonstration request.
