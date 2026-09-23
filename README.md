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

## Requirements

The project is currently designed around:

* Python
* Minecraft Java Edition
* Minecraft Java Edition 1.21.11
* Ollama-compatible local AI models
* FastAPI for the web interface

A local AI model can be used without requiring a conventional external API key.

---

## Running MinecraftAI

Clone the repository and enter the project directory:

```bash
git clone <repository-url>
cd MinecraftAI
```

Install the required Python dependencies:

```bash
pip install -r requirements.txt
```

Make sure Ollama is installed and a supported model is available.

Then MinecraftAI can be run through its CLI or web interface.

Example CLI request:

```bash
python run_pipeline.py "When it is raining, give every player one diamond."
```

The exact commands and configuration may change as development continues.

---

## Design Philosophy

MinecraftAI is built around several important principles.

### Natural Language First

Users should be able to describe behavior naturally rather than manually construct datapack files.

### AI for Understanding, Not Everything

The AI should understand the user's intent and help with reasoning.

It should not be responsible for blindly generating every implementation detail.

### Deterministic Generation

Once a structured plan exists, deterministic code should handle Minecraft implementation wherever possible.

### Version Awareness

Minecraft commands and datapack formats change between versions.

MinecraftAI therefore treats Minecraft version information as an important part of generation and validation.

### Validation Before Delivery

A generated datapack should not simply be returned because it was generated successfully.

It should pass appropriate validation and verification gates.

### Automatic Recovery

When a problem is detected, the system should attempt structured repair and regenerate the datapack rather than immediately failing.

### Generic Behavior

The system should work from general mechanisms rather than hardcoded solutions for individual user phrases or specific entities.

---

## Current Development

MinecraftAI is actively being developed.

Current architectural work is focused on strengthening the boundary between the AI Planner and the deterministic Generator.

The goal is for the Planner to describe gameplay behavior using structured specifications while the Generator owns the actual Minecraft command implementation.

This includes improvements such as:

* Structured gameplay actions
* Deterministic command synthesis
* State-machine generation
* Better separation between planning and implementation
* Structured AI repair
* Stronger planner/generator validation
* Maintaining backward compatibility with existing mechanisms

This architecture is intended to make the system more reliable as the number and complexity of supported Minecraft behaviors increase.

---

## Future Roadmap

The long-term goal is to make MinecraftAI capable of handling increasingly complex Minecraft datapack requests automatically.

Planned areas include:

### More Minecraft Versions

Expand version-aware generation beyond the current primary target.

### Expanded Minecraft Knowledge

Increase coverage of:

* Commands
* Entities
* Items
* Components
* Predicates
* Loot systems
* Recipes
* Advancements
* Other datapack systems

### More Complex Behaviors

Support increasingly complex multi-step mechanics such as:

```text
Event
  ↓
Condition
  ↓
State transition
  ↓
Multiple actions
  ↓
Cooldown
  ↓
Repeated/conditional behavior
```

### Advanced Runtime Testing

Improve automated testing using Minecraft server environments so generated datapacks can be tested against an actual Minecraft runtime.

### Better AI Repair

Improve diagnosis and structured repair for complex datapack failures.

### Improved Web Experience

Future versions may include:

* Better generation interface
* Generation progress
* Datapack previews
* Error explanations
* Generated-file inspection
* Easier download and testing workflows

### Larger Mechanism Coverage

Continue expanding support for Minecraft systems so more natural-language requests can be converted into complete datapacks.

### Multi-Mechanism Generation

Improve the ability to combine multiple Minecraft systems into a single coherent datapack.

For example:

```text
Predicate
   +
Advancement
   +
Function
   +
Scoreboard State
   +
Loot Table
```

while maintaining correct references and behavior between them.

---

## Project Vision

The long-term vision of MinecraftAI is:

> **Describe the Minecraft behavior you want. Let AI understand it. Let deterministic systems build it. Let automated verification check it.**

The goal is not simply to generate Minecraft commands.

The goal is to build an intelligent system capable of turning a player's idea into a **complete, reliable, version-aware, and verified Minecraft datapack**.

---

## Status

**Active Development**

Current primary target:

```text
Minecraft Java Edition 1.21.11
```

The project is continuously evolving as new mechanisms, validation methods, AI capabilities, and testing systems are added.

---

## License

License information will be added as the project reaches its intended release stage.
