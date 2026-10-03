# MinecraftAI

**MinecraftAI** is an AI-powered, version-aware Minecraft Java datapack generator that converts natural-language gameplay requests into deterministic, validated datapacks.

The project is designed around a strict separation between **AI reasoning** and **Minecraft implementation**:

> Natural language → Understanding → Planning → Deterministic Generation → Validation → QA → Runtime Verification → ZIP

MinecraftAI is built to support arbitrary gameplay requests without relying on hard-coded request/entity mappings.

---

## Features

* Natural-language Minecraft gameplay requests
* AI-assisted request understanding
* Structured semantic planning
* Version-aware Minecraft architecture
* Deterministic datapack generation
* Minecraft command knowledge and retrieval
* Version-specific Minecraft knowledge
* Datapack structural validation
* Semantic and QA verification
* Autonomous repair architecture
* Runtime verification support
* Deterministic benchmark evaluation
* Multi-version support
* CLI and web pipeline architecture
* Automatic ZIP packaging
* Persistent project memory and development documentation

---

## Supported Minecraft Versions

MinecraftAI currently supports:

| Minecraft Version | Status    |
| ----------------- | --------- |
| **Java 1.21.11**  | Supported |
| **Java 1.21.1**   | Supported |

Minecraft **1.21.11** remains the default version.

Version information is propagated through the pipeline using the project's centralized version architecture rather than allowing individual components to independently assume a Minecraft version.

---

## Architecture

MinecraftAI follows a staged pipeline:

```text
Natural-Language Request
          │
          ▼
┌──────────────────────┐
│ AI Understanding     │
│ Intent Extraction    │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ Minecraft Knowledge  │
│ Version-Aware RAG    │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ Planner              │
│ Structured Intent    │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ Version Context      │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ Deterministic        │
│ Datapack Generator   │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ Structural Validator │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ QA / Semantic        │
│ Verification         │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ Runtime Verification │
└──────────┬───────────┘
           │
           ▼
      Final ZIP
```

### Design Principle

The AI should determine **what the user wants**, while deterministic Minecraft-specific code determines **how that request is implemented**.

This reduces the risk of invalid commands, incorrect datapack structures, and version-specific syntax errors.

---

## Version-Aware Architecture

Minecraft versions are treated as first-class pipeline context.

A request can therefore be evaluated against a specific Minecraft version:

```text
Request
   │
   ├── Minecraft 1.21.11
   │        │
   │        └── Version-specific knowledge
   │
   └── Minecraft 1.21.1
            │
            └── Version-specific knowledge
```

The version context is propagated through:

* Understanding
* Planning
* Generator
* Validator
* QA
* Runtime verification
* Evaluation benchmark

Pack formats and other version-dependent behavior are resolved through the centralized version architecture.

---

## Deterministic Generation

MinecraftAI does not depend on the LLM to directly produce the final datapack implementation.

Instead:

1. The AI interprets the request.
2. The planner creates a structured specification.
3. The deterministic generator converts that specification into Minecraft files.
4. Validators inspect the generated structure.
5. QA checks the intended behavior.
6. Runtime verification can test the result against Minecraft.

This architecture makes generated output reproducible and easier to test.

---

## Knowledge System

MinecraftAI uses version-specific Minecraft knowledge to support generation and validation.

Knowledge includes areas such as:

* Commands
* Command syntax
* Command descriptions
* Loot tables
* Predicates
* Version-specific Minecraft data
* Other Minecraft implementation metadata used by the pipeline

Knowledge is organized by Minecraft version where appropriate.

Example:

```text
knowledge/
├── commands/
│   └── java/
│       ├── 1.21.1/
│       └── 1.21.11/
│
├── descriptions/
│
└── loot_tables/
    └── java/
        ├── 1.21.1/
        └── 1.21.11/
```

The knowledge layer is intentionally separated from deterministic generation logic.

---

## Validation

Generated datapacks pass through structural validation before being considered valid.

Validation covers areas such as:

* Datapack structure
* `pack.mcmeta`
* Function files
* Function tags
* Function references
* Version-specific pack formats
* Minecraft resource paths
* Vanilla-preservation requirements
* Missing references
* Generated datapack integrity

This prevents structurally invalid datapacks from being treated as successful output.

---

## QA and Verification

MinecraftAI uses multiple levels of verification.

### Structural Verification

Checks whether the generated datapack is structurally valid.

### Semantic Verification

Checks whether the generated implementation corresponds to the requested behavior.

### Runtime Verification

Where supported, generated datapacks can be tested against an actual Minecraft runtime.

This distinction is important because a datapack can be structurally valid while still failing to implement the requested gameplay behavior.

---

## Benchmark

MinecraftAI includes a deterministic evaluation benchmark covering multiple capability domains.

### Current Benchmark

**78 / 78 cases passing**

| Version           |  Cases |    Result |
| ----------------- | -----: | --------: |
| Minecraft 1.21.11 |     53 |     53/53 |
| Minecraft 1.21.1  |     25 |     25/25 |
| **Total**         | **78** | **78/78** |

The benchmark covers **16 capability domains** across the supported versions.

The benchmark also verifies version-specific behavior rather than simply duplicating the same cases between versions.

---

## Testing

Current verified test state:

```text
Full pytest suite: 570 / 570
Warnings:           0
Benchmark:          78 / 78
```

The project treats warnings as errors during the full verification process.

Example:

```bash
pytest -W error
```

Additional verification includes:

```bash
git diff --check
```

The project also maintains focused regression suites for previous architectural phases.

---

## Project Structure

The repository is organized around the major components of the pipeline.

```text
MinecraftAI/
│
├── ai/
│   └── understanding.py
│
├── pipeline/
│   └── minecraft_pipeline.py
│
├── generator/
│   └── ...
│
├── validator/
│   └── ...
│
├── knowledge/
│   └── ...
│
├── qa/
│   ├── analyzer.py
│   ├── reviewer.py
│   ├── repair.py
│   ├── runtime.py
│   └── scoreboard_semantics.py
│
├── eval/
│   ├── benchmark.py
│   ├── dataset.json
│   └── models.py
│
├── tests/
│   └── ...
│
├── .ai/
│   ├── STATE.md
│   ├── TASKS.md
│   ├── DECISIONS.md
│   └── CHANGELOG.md
│
└── README.md
```

The exact repository structure may evolve as development continues.

---

## AI Models

MinecraftAI is designed to work with AI-assisted understanding and planning while keeping deterministic Minecraft implementation outside the model.

The project has been developed with local AI tooling in mind, including Ollama-based models.

Example local models previously used during development include:

```text
llama3.1:8b
phi3:latest
```

Model selection is separate from the deterministic Minecraft generation layer.

---

## Installation

Clone the repository:

```bash
git clone https://github.com/krishnabhardwaj-001/MinecraftAI.git
cd MinecraftAI
```

Create and activate a Python environment:

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

Install the project's dependencies according to the repository's current dependency configuration.

Then run the project's existing CLI or application entry point.

> The exact runtime commands should be taken from the current repository configuration rather than assumed here, as the project is still evolving.

---

## Example Workflow

A user could provide a request such as:

```text
When it rains, give every player one diamond.
```

MinecraftAI processes the request through the pipeline:

```text
Natural Language
      ↓
Intent Understanding
      ↓
Structured Gameplay Specification
      ↓
Minecraft Version Context
      ↓
Deterministic Datapack Generation
      ↓
Validation
      ↓
QA
      ↓
Runtime Verification
      ↓
ZIP Datapack
```

The important architectural property is that the AI does not need a special hard-coded implementation such as:

```text
rain_diamond.json
```

for every possible request.

The system is intended to generalize through structured intent and deterministic generation.

---

## Design Principles

### 1. Generic Over Hard-Coded

The system should support arbitrary valid gameplay requests rather than maintaining one implementation per request.

### 2. AI for Reasoning, Code for Determinism

The AI interprets and plans. Deterministic code generates Minecraft implementations.

### 3. Version Awareness

Minecraft version differences must be represented explicitly rather than hidden inside individual components.

### 4. Validation Before Release

Generated output should not be considered complete merely because an AI model produced it.

### 5. Runtime Evidence Matters

Where possible, generated datapacks should be verified in a real Minecraft runtime.

### 6. Determinism

The same input and version should produce reproducible deterministic output.

### 7. No Silent Failure

Unsupported versions, missing references, invalid structures, and failed verification should be surfaced explicitly.

### 8. Scope Discipline

Issues discovered outside the current milestone should be documented rather than implemented as unrelated "while we're here" changes.

---

## Development Methodology

The project follows a plan → implement → verify → review workflow.

Each major phase is expected to:

1. Define the scope.
2. Inspect the existing architecture.
3. Implement only the required changes.
4. Add or update tests.
5. Run focused verification.
6. Run regression verification.
7. Review the final diff.
8. Update project memory/documentation.
9. Commit and push only after verification.

Project-level development memory is maintained under:

```text
.ai/
├── STATE.md
├── TASKS.md
├── DECISIONS.md
└── CHANGELOG.md
```

---

## Current Development Status

### Completed

* Version-aware architecture
* Multi-version support
* Version-specific loot knowledge
* Version propagation through the pipeline
* Pytest warning cleanup
* Dual-version evaluation benchmark

### Current milestone

**Phase 25.4 — Dual-Version Evaluation Benchmark Suite**

Status:

```text
COMPLETE
```

Latest commit:

```text
e9b7fa2 Complete Phase 25.4 dual-version evaluation benchmark
```

Repository state:

```text
Branch: main
Remote: origin/main
Working tree: clean
```

### Next milestone

**Phase 25.5 — Final Dual-Version Verification, Documentation & Handoff**

Phase 25.5 is intended to perform the final audit and verification of the Phase 25 multi-version architecture without introducing unrelated gameplay capabilities.

---

## Roadmap

The project is being developed incrementally.

Current roadmap direction:

```text
Phase 23
Version-Aware Architecture
        ↓
Phase 24
Multi-Version Support
        ↓
Phase 25.1
Loot Knowledge
        ↓
Phase 25.2
Version Propagation
        ↓
Phase 25.3
Test/Warning Cleanup
        ↓
Phase 25.4
Dual-Version Benchmark
        ↓
Phase 25.5
Final Verification & Handoff
```

Future capabilities should be introduced as separate milestones after the current architecture is fully verified.

---

## Contributing

Development should preserve the project's architectural boundaries.

Before making changes:

* Understand the existing pipeline.
* Check `.ai/STATE.md`.
* Check `.ai/TASKS.md`.
* Check `.ai/DECISIONS.md`.
* Identify the current milestone.
* Avoid unrelated refactoring.

Before submitting changes:

* Run focused tests.
* Run regression tests.
* Run the full test suite.
* Run with warnings treated as errors.
* Run `git diff --check`.
* Review the complete diff.
* Report skipped or unavailable verification honestly.

Do not modify tests simply to make an implementation pass.

---

## License

A project license should be added to the repository before this section is treated as authoritative.

---

## Project

**MinecraftAI**
AI-powered, deterministic, version-aware Minecraft Java datapack generation.

GitHub:

https://github.com/krishnabhardwaj-001/MinecraftAI
