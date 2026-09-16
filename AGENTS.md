# AI Agent Instructions

## Purpose
This file defines the shared rules for any AI agent working on this repository, including Antigravity and ChatGPT/Codex.

## Before making changes
1. Read `.ai/PROJECT.md` to understand the project's purpose and architecture.
2. Read `.ai/STATE.md` for the current implementation state and known issues.
3. Read `.ai/DECISIONS.md` before changing architecture or established design choices.
4. Read `.ai/TASKS.md` to understand current and planned work.
5. Inspect the actual source code and tests before making assumptions.
6. Check Git status and recent commits when working from a local checkout.

## Core rules
- Preserve the project's existing architecture unless a deliberate architecture change is requested.
- Do not hardcode individual user requests, mobs, items, commands, or examples as special cases when a generic solution is required.
- Prefer data-driven, version-aware, deterministic implementations.
- Validate changes against the actual project files, tests, and Minecraft version knowledge.
- Do not expose or commit secrets such as `.env` contents, API keys, credentials, or tokens.
- Do not commit generated caches, Python bytecode, local environments, or temporary archives unless explicitly required.
- Make the smallest safe change that solves the requested problem.

## Shared AI context
The `.ai/` directory is the project's shared context between agents. It is not a substitute for the source code or Git history.

Source-of-truth priority:
1. Actual project files and executable behavior
2. Git history and diffs
3. `.ai/STATE.md`
4. `.ai/DECISIONS.md`
5. `.ai/PROJECT.md`
6. `.ai/CHANGELOG.md`
7. `.ai/TASKS.md`

If the context files disagree with the actual code, investigate and update the context rather than blindly trusting the context.

## After significant changes
- Run relevant tests or validation.
- Review the final diff.
- Update `.ai/STATE.md` with what is now working, what remains broken, and the next logical task.
- Add important architectural choices to `.ai/DECISIONS.md`.
- Add a concise entry to `.ai/CHANGELOG.md` describing what changed and why.
- Update `.ai/TASKS.md` if task status changed.
- Commit and push changes when the workflow calls for synchronization.

## Handoff
When switching between AI agents, the next agent should be able to continue by reading this file and the `.ai/` context files, then verifying the current Git state and source code.
