# MinecraftAI

**MinecraftAI** is an AI-powered system that converts natural-language Minecraft Java Edition requests into structured, validated, and automatically generated datapacks.

Instead of requiring users to manually write Minecraft commands, functions, predicates, recipes, loot tables, and other datapack files, MinecraftAI allows users to describe what they want in natural language.

For example:

> "When it starts raining, give every player one diamond."

MinecraftAI analyzes the request, understands the intended behavior, uses Minecraft-specific knowledge, creates an implementation plan, generates the datapack, validates it, reviews it for semantic issues, and produces a verified datapack ZIP.

---

## Overview

Minecraft datapacks normally require knowledge of:

* Minecraft commands
* `.mcfunction` files
* JSON-based datapack formats
* Predicates
* Loot tables
* Recipes
* Advancements
* Function tags
* Scoreboards
* Minecraft version-specific syntax

MinecraftAI aims to hide this implementation complexity behind a natural-language interface.

The user describes **what they want**, while MinecraftAI determines **how it should be implemented**.

---

## How It Works

The system follows a multi-stage pipeline:

```text
Natural Language Request
          ↓
     AI Understanding
          ↓
 Minecraft Knowledge / RAG
          ↓
        Planner
          ↓
 Deterministic Generator
          ↓
 Structural Validation
          ↓
  Autonomous QA Review
          ↓
   Intent Verification
          ↓
 Final Verification Gate
          ↓
   Verified Datapack ZIP
```

### 1. AI Understanding

The user's natural-language request is analyzed to determine:

* What the user wants
* Target entities
* Conditions
* Effects
* Constraints
* Timing requirements
* Missing information

If the request is ambiguous, MinecraftAI can ask a clarification question instead of making an arbitrary assumption.

For example:

```text
User:
"Make me stronger."

MinecraftAI:
"What should 'stronger' mean?

- Higher attack damage
- More health
- Better equipment
- Strength effect
- Something else"
```

This allows the system to understand the user's actual intent before generating anything.

---

### 2. Minecraft Knowledge / RAG

MinecraftAI uses Minecraft-specific knowledge to support generation.

The knowledge system can provide information about:

* Commands
* Command syntax
* Items
* Entities
* Loot tables
* Predicates
* Recipes
* Minecraft-specific structures
* Version-specific behavior

The current primary target is:

**Minecraft Java Edition 1.21.11**

The knowledge layer helps separate general AI reasoning from Minecraft-specific implementation knowledge.

---

### 3. Planner

The Planner converts the understood request into a structured implementation plan.

The goal of the architecture is to keep the Planner focused on:

> **What should happen?**

rather than:

> **Which exact Minecraft command should be written?**

Structured actions can represent operations such as:

* Give an item
* Apply an effect
* Clear an effect
* Set a scoreboard value
* Add to a scoreboard
* Reset a scoreboard
* Play a sound
* Spawn particles
* Send a message
* Spawn an entity
* Teleport an entity

The deterministic generator is then responsible for converting these structured specifications into Minecraft syntax.

---

### 4. Deterministic Datapack Generation

MinecraftAI generates the actual datapack files from structured specifications.

Depending on the request, the generator can create mechanisms such as:

* Functions
* Function tags
* Predicates
* Loot tables
* Recipes
* Advancements
* State-based behavior

The generator handles Minecraft command syntax and implementation details rather than relying on the language model to manually construct every command.

This makes generation more predictable and easier to validate.

---

### 5. Structural Validation

Before a datapack is considered ready, MinecraftAI validates its structure.

Validation can check things such as:

* Required datapack files
* JSON validity
* File references
* Function references
* Function tags
* Command syntax
* Minecraft version compatibility
* Mechanism structure

Invalid output can be rejected before it reaches the final verification stage.

---

### 6. Autonomous QA Review

MinecraftAI includes an additional semantic review layer.

The QA system examines the generated datapack as a complete system rather than only checking whether individual files are syntactically valid.

It can identify problems involving:

* Missing files
* Invalid references
* Command context
* State management
* Temporal behavior
* State transitions
* Inconsistent mechanisms
* Logic that may work syntactically but not behave as intended

This is important because a datapack can be syntactically valid while still implementing the wrong behavior.

---

### 7. Automatic Repair

When a problem is detected, MinecraftAI can use an AI-assisted repair process.

The intended repair flow is:

```text
Problem Detected
      ↓
AI Diagnosis
      ↓
Structured Repair
      ↓
Deterministic Regeneration
      ↓
Validation
      ↓
QA Review
```

The system can repeat this process when necessary rather than simply returning the first generated result.

The architecture is designed so that AI repair modifies structured specifications instead of freely editing generated datapack files.

---

### 8. Intent Verification

The final stages verify that the generated datapack still matches the original user request.

This provides another layer of protection against situations where:

* The datapack is valid but does something different
* A repair fixes one issue but introduces another
* A mechanism is technically correct but does not satisfy the user's intended behavior

A datapack is only considered ready when the required verification gates pass.

---

## Supported Datapack Mechanisms

MinecraftAI currently supports multiple datapack mechanisms, including:

### Functions

For executable Minecraft logic.

### Function Tags

For automatic execution through Minecraft lifecycle events such as:

* Load
* Tick

### Predicates

For condition-based behavior using Minecraft's predicate system.

### Loot Tables

For custom drops and loot behavior.

### Recipes

Support includes recipe types such as:

* Shaped recipes
* Shapeless recipes
* Smelting
* Blasting
* Smoking
* Campfire cooking
* Stonecutting

### Advancements

For event and achievement-based triggers.

### State-Based Behavior

MinecraftAI can represent stateful behavior where actions depend on transitions between states.

For example:

```text
Rain starts
    ↓
Give diamond once
    ↓
Rain continues
    ↓
Do nothing
    ↓
Rain stops
    ↓
Reset state
    ↓
Rain starts again
    ↓
Give diamond once
```

This allows environmental conditions and other stateful mechanics to be handled without repeatedly triggering the same action.

---

## Example

### User Request

```text
When it is raining, give every player one diamond, but only once when the rain starts.
```

MinecraftAI can understand this as:

```text
Condition:
    Rain starts

Action:
    Give diamond

Target:
    Players

Frequency:
    Once per rain event
```

The implementation can then use a state mechanism to distinguish:

```text
Inactive → Rain starts → Active
```

and prevent the action from repeating every tick while rain continues.

---

## Verification

MinecraftAI includes both automated testing and real Minecraft verification.

The project has previously undergone real-world Minecraft verification for the rain state-machine behavior.

The verified behavior included:

* Datapack discovery
* `/reload`
* Rain detection
* State initialization
* One-time reward when rain begins
* No repeated rewards during continuous rain
* State reset after rain ends
* Correct behavior when rain starts again
* Mid-game reload behavior
* Clean server logs

The project also maintains automated regression tests for its major components.

---

## Web Interface

MinecraftAI includes a web interface that provides a user-facing way to interact with the generator.

The web interface is designed around the same underlying generation pipeline used by the CLI.

The project also maintains a command-line interface for development and testing.

---

## Project Structure

A simplified view of the project:

```text
MinecraftAI/
│
├── ai/
│   ├── planner.py
│   ├── context.py
│   └── ...
│
├── generator/
│   ├── mechanisms/
│   ├── datapack_generator.py
│   └── models.py
│
├── knowledge/
│   ├── commands/
│   ├── descriptions/
│   └── ...
│
├── qa/
│   ├── analyzer.py
│   ├── reviewer.py
│   ├── repair.py
│   ├── runtime.py
│   └── models.py
│
├── pipeline/
│   ├── minecraft_pipeline.py
│   └── models.py
│
├── validator/
│   └── datapack_validator.py
│
├── generated/
│
├── tests/
│
├── run_pipeline.py
├── knowledge_retriever.py
└── README.md
```

The exact project structure may evolve as the system develops.

---

## Prerequisites & Requirements

* **Operating System**: Windows, Linux, or macOS
* **Python**: Version `3.10` or higher (`3.10`, `3.11`, `3.12`, `3.13` supported)
* **AI Provider**:
  * **Ollama (Default / Local)**: [Ollama](https://ollama.com) running locally.
    * Expected local endpoint: `http://localhost:11434` (configurable via `OLLAMA_HOST`)
    * Recommended model: `ollama pull llama3.1:8b` (configurable via `OLLAMA_MODEL`)
  * **OpenAI (Alternative)**: Export `OPENAI_API_KEY` to use OpenAI models where configured.
* **Minecraft Target**: Minecraft Java Edition `1.21.11` (Data Pack version `94.1` / `pack_format: 94`)
* **Optional Runtime Verification**: Java 21 LTS (64-bit JVM) for automated headless server testing.

---

## Installation & Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/krishnabhardwaj-001/MinecraftAI.git
   cd MinecraftAI
   ```

2. **Install the package in editable mode**:
   ```bash
   pip install -e .
   ```
   This registers the `minecraft-ai` and `minecraft-ai-web` console commands and installs all runtime dependencies (`fastapi`, `uvicorn`, `pydantic`, `ollama`, `jinja2`, `python-dotenv`, `httpx`).

3. **Start Ollama and pull the recommended model**:
   ```bash
   ollama serve
   ollama pull llama3.1:8b
   ```

---

## Launching MinecraftAI

### Windows Launchers (One-Click)
Double-click or run from terminal:
* **`launch_cli.bat`**: Launches the interactive CLI directly.
* **`launch_web.bat`**: Launches the Obsidian & Emerald Web interface at `http://127.0.0.1:8000`.

### Command-Line Interface (CLI)
Run using the installed entrypoint or Python runner:
```bash
# Interactive mode (prompts for request):
minecraft-ai

# Direct request mode:
minecraft-ai "When it is raining, give all players a diamond only once when the rain starts."

# Alternatively via python:
python run_pipeline.py "Make every creeper drop diamonds."
```

### Web Interface
Start the local FastAPI server:
```bash
# Using installed entrypoint:
minecraft-ai-web

# Alternatively via python:
python run_web.py --port 8000
```
Open your browser to `http://127.0.0.1:8000` to access:
* Visual **8-Stage Pipeline Tracker** (Understanding → RAG → Planning → Generator → Validation & Repair → Autonomous QA → Intent Verification → READY Gate).
* Interactive **Dynamic Clarification Chips**.
* Instant **Datapack ZIP Download**.
* Generated **File Tree & Inspection Panel**.

---

## Key Features & Behaviors

### 1. Authoritative 7 Mechanism Domains
MinecraftAI deterministically generates and validates:
* **Loot Tables** (`data/<ns>/loot_table/`): Modifies entity/block drops while strictly preserving vanilla items and conditions.
* **Functions** (`data/<ns>/function/`): Synthesizes valid `.mcfunction` files with sanitized leading slashes and execution context wrapping (`as @a at @s`).
* **Function Tags** (`data/<ns>/tags/function/`): Game loop registration (`#minecraft:load`, `#minecraft:tick`), minimal canonical format (`values: [...]`), multi-datapack aggregation, and dangling reference sanitization.
* **Advancements** (`data/<ns>/advancement/`): Custom triggers, display formatting, and rewards.
* **Recipes** (`data/<ns>/recipe/`): Modern 1.21+ result structure (`{"id": ..., "count": ...}`), shaped, shapeless, and smelting.
* **Predicates** (`data/<ns>/predicate/`): All 19 Java 1.21.11 condition types and composite condition trees (`all_of`, `any_of`, `inverted`).
* **State Machines**: Dedicated generator for global persistent state machines (`#global` scoreboards) and dynamic per-player scoreboards.

### 2. Semantic Property Modifications
Natural-language modifications (`make me 10 times faster`, `increase speed by 25%`, `set zombie speed to 0.4`):
* Interprets numeric and comparative semantics without hardcoded mob/item logic.
* Queries [`PropertyCapabilityRegistry`](ai/property_registry.py) for exact `(property, operation, value.kind)` capability selection.
* Compiles speed multipliers and relative increments to `/attribute` (`minecraft:generic.movement_speed`) using `add_multiplied_total` and `add_value`/`add_multiplied_base`.
* Enforces single-entity target constraints (`execute as {target} run attribute @s ...`).
* Disambiguates modifier IDs deterministically (`minecraft_ai:{property}_{op}_{val}_{step_id}`) to prevent collision while allowing intentional stacking.

### 3. Interactive Clarification
When requests are underspecified or ambiguous (e.g. `make me faster` without magnitude/duration, or `make the zombie stronger` without specifying health vs attack damage):
* The pipeline halts early before writing files.
* **Web UI**: Dynamically renders clickable clarification buttons/chips for rapid selection.
* **CLI**: Displays numbered choices and accepts index selection or custom refinement.

### 4. Offline Ollama Diagnostics
If the local Ollama service is not running or unreachable:
* The CLI and Web interfaces intercept connection failures.
* Rather than crashing with an unhandled traceback, the system displays clear actionable instructions:
  * The attempted endpoint (`http://localhost:11434`)
  * How to start the service (`ollama serve`)
  * How to pull the required model (`ollama pull llama3.1:8b`)
  * How to configure alternative providers (`OPENAI_API_KEY`)
* Web API returns HTTP 503 (Service Unavailable) with structured diagnostic detail.

---

---

## Verification & Testing

### Automated Regression Suite
Run all 425 automated unit, integration, and boundary tests:
```bash
python -m unittest discover -s . -p "test_*.py"
```

### Automated Evaluation Benchmark
MinecraftAI includes a structured evaluation benchmark (`eval/`) assessing the natural-language pipeline across 53 diverse requests covering 16 capability domains without request-specific implementation logic:

* **Categories Evaluated (16 Domains)**: `mob_loot`, `functions`, `function_tags`, `predicates`, `advancements`, `recipes`, `state_machines`, `scoreboard_operations`, `property_multipliers`, `property_relative`, `property_percentage`, `property_absolute`, `entity_specific_targets`, `compound_requests`, `clarification_required`, and `invalid_unsupported`.
* **Run via CLI Entry Point**:
```bash
minecraft-ai-eval
```
* **Run via Python Module**:
```bash
python -m eval.benchmark
```
* **Benchmark Purpose & Limitations**:
  * Evaluates deterministic semantic interpretation, clarification triggering, mechanism mapping, static validation, and QA simulation.
  * Clearly distinguishes between deterministic regression benchmarks (100% offline, zero external API keys) and model-dependent evaluations.
  * The benchmark is not a general claim of universal AI intelligence or arbitrary natural-language perfection; it serves as a rigorous, deterministic regression test against Minecraft 1.21.11 capabilities.

### Continuous Integration (CI/CD)
GitHub Actions workflow configured in [`.github/workflows/ci.yml`](.github/workflows/ci.yml):
* **Triggers**: Automated runs on push and pull requests to `main`.
* **Matrix**: Tests across supported Python versions (`3.10`, `3.11`, `3.12`, `3.13`).
* **Environment-Aware**: Installs packaging via `pip install -e ".[dev]"`, runs `git diff --check`, executes the full unit test suite (425 tests), runs the evaluation benchmark, and performs environment-aware headless Minecraft testing (reporting unavailable environment cleanly in constrained CI while maintaining 17/17 PASS in environments with Java 21 LTS).

### Verification Boundary: Headless vs In-Game Client

MinecraftAI enforces a strict distinction between automated headless testing and interactive client playtesting:

1. **Automated Headless Server Verification (Empirically Verified)**:
   * Tested via `qa/runtime.py` and `test_step20_golden.py` using Java 21 LTS and Mojang's official `server-1.21.11.jar` in an isolated sandbox.
   * Proves: Exact version `1.21.11` boot, native ZIP discovery and loading, automatic boot load execution, 20Hz automatic tick loop advancement, rain state-machine transitions (0 -> 1 -> 0), `/attribute` modifier application on live entities, duplicate modifier coexistence, tag integrity on `/reload`, and clean shutdown with exit code `0`.
2. **Optional In-Game Client Verification (Manual)**:
   * Visual and audio rendering (camera FOV changes, particle swirls, sound chimes), GUI advancement window (`L` key), scoreboard sidebar HUD, and crafting table inventory slot synchronization require a human player in an interactive Minecraft 1.21.11 client.
   * Full protocol and regression checklist documented in [`.ai/REAL_MINECRAFT_VERIFICATION.md`](.ai/REAL_MINECRAFT_VERIFICATION.md).

---

## License

MIT License. See project files for details.
