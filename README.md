# MinecraftAI

**MinecraftAI** is a production-grade, AI-powered, version-aware Minecraft Java datapack generation platform that converts natural-language gameplay requests into deterministic, structurally validated, and semantically verified datapacks.

The platform provides both a **modern web application** and a **CLI pipeline**, backed by a hardened defense-in-depth security layer, comprehensive legal and privacy policies, multi-stage Docker deployment, and dual-version support for Minecraft Java **1.21.11** (default) and **1.21.1**.

```text
Natural Language → AI Understanding → Version-Aware RAG → Structured Planning
       │
       ▼
Deterministic Generation → Static Validation → Autonomous QA → Intent Verification → Validated ZIP
```

MinecraftAI supports arbitrary gameplay requests without relying on hard-coded request/entity mappings.

---

## Key Features

* **Natural-Language Understanding**: Converts user gameplay intent into strongly-typed semantic specifications.
* **Modern Web Interface**: Single-page application featuring Obsidian & Emerald aesthetics, live 8-stage visual progress tracker, dynamic clarification options, outcome cards, and direct ZIP download.
* **Full REST API**: Robust FastAPI endpoints for generation, streaming downloads, server health diagnostics, version metadata, and legal documentation.
* **Dual-Version Minecraft Architecture**:
  * **Minecraft Java 1.21.11** (default, `pack_format: 94`)
  * **Minecraft Java 1.21.1** (`pack_format: 48`)
* **7 Authoritative Mechanism Domains**:
  * Entity Loot Tables (`data/<ns>/loot_table/...`)
  * Custom Functions (`data/<ns>/function/...`)
  * Function Tags (`data/<ns>/tags/function/...` including `#minecraft:load` and `#minecraft:tick`)
  * Custom Advancements (`data/<ns>/advancement/...`)
  * Custom Recipes (`data/<ns>/recipe/...`)
  * Custom Predicates (`data/<ns>/predicate/...`)
  * Event State Machines & Latches (scoreboard objectives and `#global` score holders)
* **Defense-in-Depth Security Layer**:
  * Strict input validation and prompt length limiting
  * Canonical path-traversal prevention for file generation and ZIP downloads
  * Zip Slip, path escape, and decompression bomb protection
  * Minecraft command verb whitelisting and shell metacharacter blocking (`;`, `&`, `|`, `` ` ``)
  * Sliding-window IP rate limiting and concurrent generation slot management
  * Hardened HTTP security headers (CSP, X-Content-Type-Options, X-Frame-Options, Referrer-Policy)
  * Safe logging with IP anonymization and sensitive text masking
  * Production error sanitizer stripping stack traces and filesystem paths
* **Legal & Privacy Policies**:
  * Local-first execution (zero external telemetry, zero tracking cookies)
  * Clear Terms of Service with explicit Mojang / Microsoft disclaimers
  * Responsible disclosure security policy
* **Docker & Container Deployment**:
  * Multi-stage build with non-root security (`appuser` UID 10001)
  * `docker-compose.yml` preconfigured for local Ollama host gateway
* **Autonomous QA & Self-Repair**:
  * Deterministic static structural validator
  * Multi-tick scoreboard state-machine simulator
  * Bounded automated repair loop recovering from validation defects
  * Strict final READY gate verifying structural, QA, and intent requirements

---

## Supported Minecraft Versions

MinecraftAI propagates version context through the entire pipeline:

| Minecraft Version | Pack Format | Directory Structure | Status |
| :--- | :---: | :---: | :--- |
| **Java 1.21.11** | `94` | Singular (`recipe/`, `predicate/`, `loot_table/`) | Supported (Default) |
| **Java 1.21.1** | `48` | Singular (`recipe/`, `predicate/`, `loot_table/`) | Supported |

Version differences (such as item IDs, entity attributes, component schemas, and pack formats) are loaded from version-isolated registries rather than ad-hoc heuristics.

---

## Architecture

MinecraftAI enforces a strict separation between **AI reasoning** and **Minecraft implementation**:

```text
Natural-Language Request (e.g. "When it starts raining, give every player one diamond.")
          │
          ▼
┌──────────────────────────────┐
│ Stage 1: AI Understanding    │  Extracts gameplay goals, triggers, and targets.
│ Intent & Ambiguity Analysis  │  Pauses on underspecified input for clarification.
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Stage 2: Minecraft Knowledge │  Retrieves version-isolated domain knowledge:
│ Version-Aware RAG            │  items, entities, attributes, predicates, tags.
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Stage 3: Structured Planner  │  Synthesizes typed MechanismSpecifications
│ Abstract Gameplay Contracts  │  without raw Minecraft commands or file paths.
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Stage 4: Deterministic       │  Generates canonical, reproducible Minecraft
│ Datapack Generator           │  resources, JSON files, and .mcfunction files.
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Stage 5: Static Validator    │  Verifies JSON syntax, pack.mcmeta, tags,
│ & Autonomous Repair Loop     │  command syntax, and vanilla loot preservation.
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Stage 6: Autonomous QA       │  Simulates state-machine transitions, verifies
│ Semantic Analysis            │  target context, and checks reference integrity.
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Stage 7: Intent Verification │  Cross-examines generated datapack against
│ Goal-to-Artifact Validation  │  original user request to ensure alignment.
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Stage 8: READY Gate & ZIP    │  Creates byte-deterministic, production ZIP.
│ Output Packaging             │  Ready for installation in .minecraft/saves.
└──────────────────────────────┘
```

---

## Web Application & REST API

MinecraftAI includes a high-performance web interface built with FastAPI:

### Running the Web Server

```bash
# Start the web server on port 8000
python run_web.py --port 8000

# Or using the Windows launcher:
launch_web.bat
```

Access the web UI at `http://localhost:8000`.

### REST API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | Web application single-page interface |
| `POST` | `/api/generate` | Generate datapack from natural-language request |
| `GET` | `/api/download/{filename}` | Path-traversal protected ZIP download |
| `GET` | `/api/health` | Service health, Ollama status, and diagnostic checks |
| `GET` | `/api/versions` | List supported Minecraft versions and defaults |
| `GET` | `/privacy` | Privacy Policy page |
| `GET` | `/terms` | Terms of Service & Mojang disclaimer page |
| `GET` | `/security` | Security & Responsible Disclosure policy page |
| `GET` | `/api/legal/{doc_name}` | Raw legal policy markdown (`privacy`, `terms`, `security`) |

### Generation Request Schema

```json
POST /api/generate
Content-Type: application/json

{
  "request": "When it starts raining, give every player one diamond.",
  "minecraft_version": "1.21.11",
  "clarification_answer": null,
  "previous_request": null
}
```

### Generation Response Schema (Success)

```json
{
  "status": "success",
  "is_success": true,
  "datapack_name": "when_it_starts_raining_give_every_player_one_diamond",
  "download_url": "/api/download/when_it_starts_raining_give_every_player_one_diamond.zip",
  "minecraft_version": "1.21.11",
  "pack_format": 94,
  "plan": { ... },
  "clarification": null,
  "clarification_requirements": null,
  "errors": []
}
```

### Clarification Handling

When an ambiguous request is submitted (e.g. `"Make me faster."`), the API returns:

```json
{
  "status": "needs_clarification",
  "is_success": false,
  "clarification": "How would you like your speed to be increased? Please specify...",
  "clarification_requirements": [ ... ]
}
```

The user can resolve the ambiguity by providing `clarification_answer` (e.g. `"10 times faster"`) and `previous_request`, which the pipeline synthesizes into a complete prompt without manual retyping.

---

## Security Architecture

MinecraftAI features a dedicated security layer under `security/`:

* **Input Security (`security/input_security.py`)**:
  * Prompt length enforcement (`MAX_PROMPT_LENGTH = 2000`)
  * Control character, null-byte, and `<script>` injection stripping
  * Strict version whitelisting against `VersionRegistry`
  * Safe alphanumeric filesystem naming (`sanitize_datapack_name`)
* **Path Security (`security/path_security.py`)**:
  * Resolves canonical absolute paths and strictly confines all write and read operations to `generated/`
  * Neutralizes POSIX (`../`), Windows (`..\`), UNC (`\\`), and URL-encoded traversal attempts
* **Archive Security (`security/archive_security.py`)**:
  * Zip Slip vulnerability defense: inspects every ZIP entry before extraction
  * Decompression bomb prevention: enforces maximum uncompressed size (`100 MB`) and expansion ratio (`100:1`)
  * Structure verification: requires valid `pack.mcmeta` and `data/` namespace root
* **Command Security (`security/command_security.py`)**:
  * Whitelists valid Minecraft Java command verbs (`scoreboard`, `execute`, `give`, `effect`, `tellraw`, etc.)
  * Blocks shell injection metacharacters (`;`, `&`, `|`, `` ` ``)
* **Rate Limiting & Concurrency (`security/rate_limit.py`)**:
  * Sliding-window in-memory IP rate limiter (e.g. 30 requests/minute)
  * Concurrency semaphore preventing server saturation from simultaneous LLM generations
* **HTTP Headers Middleware (`security/headers.py`)**:
  * Content-Security-Policy (`default-src 'self'`)
  * `X-Content-Type-Options: nosniff`
  * `X-Frame-Options: DENY`
  * `Referrer-Policy: strict-origin-when-cross-origin`
* **Safe Logging & Error Sanitization (`security/logging.py`, `security/error_sanitizer.py`)**:
  * Anonymizes IPv4 and IPv6 client addresses
  * Masks potential credentials, tokens, and sensitive strings
  * Sanitizes error messages returned over HTTP, stripping Python stack traces and server filepaths

---

## Legal & Compliance

All legal and operational policies are located under `security/legal/` and accessible via the web interface:

1. **Privacy Policy (`security/legal/privacy_policy.md` / `/privacy`)**:
   * Local-first architecture: requests are processed on your hardware with no remote data collection.
   * Zero tracking cookies, zero analytics beacons, zero third-party telemetry.
2. **Terms of Service (`security/legal/terms_of_service.md` / `/terms`)**:
   * Acceptable use policy for generated datapacks.
   * **Mojang / Microsoft Disclaimer**: MinecraftAI is an independent, community-developed software project. It is **NOT AN OFFICIAL MINECRAFT PRODUCT** and is **NOT APPROVED BY OR ASSOCIATED WITH MOJANG OR MICROSOFT**.
3. **Security Policy (`security/legal/security_policy.md` / `/security`)**:
   * Responsible disclosure guidelines and security vulnerability reporting.

---

## Docker & Production Deployment

### Prerequisites

* [Docker](https://docs.docker.com/get-docker/) & Docker Compose
* [Ollama Cloud](https://ollama.com/) account with API key (or local Ollama instance / OpenAI API key)

### Running with Docker Compose

```bash
# 1. Copy the environment configuration
cp .env.example .env

# 2. Build and start the container
docker compose up -d --build

# 3. View container logs
docker compose logs -f minecraft-ai
```

The container runs as an unprivileged user (`appuser`, UID `10001`), mounts a persistent volume for `generated/`, binds to port `8000`, and includes an automatic health check querying `/api/health`.

### Environment Configuration (`.env`)

```ini
HOST=0.0.0.0
PORT=8000
LLM_PROVIDER=ollama
OLLAMA_HOST=https://ollama.com
OLLAMA_MODEL=gpt-oss:120b-cloud
OLLAMA_API_KEY=your_ollama_cloud_api_key_here
RATE_LIMIT_ENABLED=true
RATE_LIMIT_PER_MINUTE=30
MAX_CONCURRENT_GENERATIONS=4
```

---

## CLI Usage

MinecraftAI provides a full command-line pipeline:

```bash
# Interactive CLI
python run_pipeline.py

# Or via Windows launcher:
launch_cli.bat

# Direct prompt execution
python run_pipeline.py --request "When it starts raining, give every player one diamond." --version 1.21.11

# Skeletons drop iron on 1.21.1
python run_pipeline.py --request "Make every skeleton drop iron ingots." --version 1.21.1
```

---

## Testing & Quality Assurance

The codebase maintains strict quality gates with zero warnings under `-W error`:

```bash
# Run full unit and regression test suite
python -m pytest -v

# Run with warnings treated as errors
python -m pytest -W error

# Run security test suite
python -m pytest test_security_input.py test_security_paths.py test_security_zip.py test_security_rate_limit.py test_security_headers.py -v

# Run full web application suite
python -m pytest test_web.py test_web_full.py -v

# Run dual-version evaluation benchmark (78/78 cases)
python -m eval.benchmark

# Verify clean git whitespace
git diff --check
```

### Evaluation Benchmark

The deterministic benchmark evaluates **78 comprehensive cases** across 16 capability domains with **100% accuracy**:

| Version | Cases | Status |
| :--- | :---: | :---: |
| Minecraft 1.21.11 | 53 | 53 / 53 Passed |
| Minecraft 1.21.1 | 25 | 25 / 25 Passed |
| **Total Benchmark** | **78** | **78 / 78 Passed (100.0%)** |

---

## Project Structure

```text
MinecraftAI/
├── ai/                      # AI request understanding, context RAG, and planning
│   ├── clarification.py     # Semantic ambiguity detection and option generation
│   ├── implementation_mapper.py # Deterministic Minecraft mechanism mapping
│   ├── numeric_interpreter.py   # Natural-language numeric parsing
│   ├── planner.py           # Structured gameplay planner
│   ├── property_registry.py # Version-aware property capabilities
│   └── understanding.py     # Goal and trigger extraction
│
├── generator/               # Deterministic Minecraft Java datapack generation
│   ├── mechanisms/          # Modular mechanism generators
│   │   ├── advancement_mech.py  # Custom advancements
│   │   ├── function_mech.py     # Command compilation & .mcfunction synthesis
│   │   ├── interaction_mech.py  # Clickable chat /trigger interaction menus
│   │   ├── predicate_mech.py    # Authoritative predicates
│   │   ├── recipe_mech.py       # Custom crafting & smelting recipes
│   │   ├── state_machine_mech.py# Scoreboard game loop state machines
│   │   └── tag_mech.py          # Function tags (#minecraft:load, #minecraft:tick)
│   ├── datapack_generator.py# Core datapack generator
│   └── models.py            # Strongly-typed data contracts & ActionSpecifications
│
├── validator/               # Static structural validator
│   └── datapack_validator.py# pack.mcmeta, JSON schemas, command syntax validation
│
├── qa/                      # Autonomous QA & semantic verification
│   ├── analyzer.py          # Static semantic analysis & reference checking
│   ├── reviewer.py          # Autonomous QA review & intent verification
│   ├── repair.py            # Structured plan repair engine
│   ├── runtime.py           # Real Minecraft headless server verification harness
│   └── scoreboard_semantics.py # Multi-tick scoreboard logic simulation
│
├── security/                # Production security & compliance layer
│   ├── archive_security.py  # Zip Slip & zip bomb defenses
│   ├── command_security.py  # Command verb whitelisting & injection blocking
│   ├── config.py            # Centralized security configuration
│   ├── error_sanitizer.py   # Traceback & filesystem path stripping
│   ├── headers.py           # CSP & HTTP security headers middleware
│   ├── input_security.py    # Prompt & version validation
│   ├── logging.py           # Safe logging with IP anonymization
│   ├── path_security.py     # Canonical output confinement & traversal defense
│   ├── rate_limit.py        # Sliding-window IP rate limiter
│   └── legal/               # Legal & compliance policies
│       ├── privacy_policy.md    # Local-first privacy documentation
│       ├── terms_of_service.md  # Terms & Mojang/Microsoft disclaimer
│       └── security_policy.md   # Responsible disclosure policy
│
├── web/                     # FastAPI web application & user interface
│   ├── static/              # Obsidian & Emerald dark-mode UI (CSS, JS)
│   ├── templates/           # Jinja2 templates (index.html, legal.html)
│   └── app.py               # REST API & application server
│
├── versions/                # Version registries & headless server runtimes
│   ├── 1.21.11/             # Minecraft 1.21.11 registry & server jar
│   └── 1.21.1/              # Minecraft 1.21.1 registry & server jar
│
├── eval/                    # Deterministic evaluation benchmark suite
│   ├── benchmark.py         # Dual-version evaluation runner
│   ├── dataset.json         # 78 verified benchmark test cases
│   └── models.py            # Benchmark schema models
│
├── generated/               # Output directory for generated datapacks & ZIPs
├── Dockerfile               # Production multi-stage Docker container
├── docker-compose.yml       # Production Docker Compose orchestration
├── run_web.py               # Web server launcher
├── run_pipeline.py          # CLI pipeline launcher
└── pyproject.toml           # Project packaging specification
```

---

## Disclaimer

**MinecraftAI is not an official Minecraft product. It is not approved by or associated with Mojang or Microsoft.**

Minecraft is a registered trademark of Mojang Synergies AB. All Minecraft-related assets, terms, and concepts referenced herein are the intellectual property of their respective owners.
