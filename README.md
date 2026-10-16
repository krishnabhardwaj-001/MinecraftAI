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

## Quick Start: Local Website with Ollama Cloud Sign-In

Anyone can clone MinecraftAI and run the local website on their computer **without downloading a large 120-billion-parameter model locally and without needing to paste an API key into MinecraftAI**.

Inference runs on **Ollama Cloud** using Ollama's official sign-in authentication (`ollama signin`), while the web interface, Minecraft knowledge retrieval, validation, and ZIP generation run on your local machine.

```
+-----------------------------------------------------------------------------------------+
|                               LOCAL WEBSITE USER JOURNEY                                |
|                                                                                         |
|  1. Clone Repo -> 2. Run setup.bat -> 3. Run start.bat -> 4. Enter Prompt -> 5. Get ZIP |
|                                                                                         |
|  * ZERO Large Model Downloads (Cloud inference)    * ZERO API Keys to Paste             |
|  * Uses 'ollama signin' account authentication    * Local RAM only ~200MB - 500MB       |
+-----------------------------------------------------------------------------------------+
```

### 1. Prerequisites

* **Operating System**: Windows 10/11, macOS, or Linux
* **Python**: Version **3.10 or newer** ([python.org](https://www.python.org/)) with "Add Python to PATH" enabled
* **Ollama**: Official Ollama application ([ollama.com/download](https://ollama.com/download))
* **Ollama Account**: Sign in to your account via `ollama signin` (free tier or paid)
* **Internet Connection**: Required for cloud AI inference

### 2. Windows 10/11 Setup (One-Click)

1. **Clone the repository**:
   ```powershell
   git clone https://github.com/krishnabhardwaj-001/MinecraftAI.git
   cd MinecraftAI
   ```

2. **Run the setup script**:
   ```cmd
   setup.bat
   ```
   This automated script:
   * Checks for Python 3.10+
   * Creates and activates a virtual environment (`.venv`)
   * Installs project dependencies (`pip install -e .`)
   * Verifies Ollama is installed
   * Registers the lightweight cloud model pointer (`ollama pull gpt-oss:120b-cloud` — downloads only a 384-byte manifest, **zero large model weights**)
   * Creates a default local configuration (no API key required)

3. **Sign in to Ollama** (if you haven't already):
   ```cmd
   ollama signin
   ```
   Follow the prompt to authenticate with your Ollama account in your browser.

4. **Launch the local website**:
   ```cmd
   start.bat
   ```
   The local server starts at `http://127.0.0.1:8000`, verifies port availability, and **automatically opens your default web browser** once ready!

5. **Stop the server**:
   Press `Ctrl+C` in the command prompt window at any time.

---

### 3. macOS / Linux Setup (Manual Commands)

```bash
# 1. Clone repository
git clone https://github.com/krishnabhardwaj-001/MinecraftAI.git
cd MinecraftAI

# 2. Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -e .

# 4. Sign in to Ollama and register cloud model
ollama signin
ollama pull gpt-oss:120b-cloud

# 5. Launch local website
python run_web.py --open-browser
```

---

### 4. How to Generate & Download a Datapack

1. Open `http://127.0.0.1:8000` in your browser.
2. Select target Minecraft version (**Java 1.21.11** or **Java 1.21.1**).
3. Type your natural-language request (e.g., *"When it starts raining, give every player one diamond."*).
4. Click **Generate Datapack** — watch the 8-stage progress tracker execute.
5. If the request is ambiguous (e.g. *"make me faster"*), click a suggested option or type your clarification.
6. Click **Download Datapack (.zip)**.
7. Place the ZIP file directly into your Minecraft world's `datapacks/` folder (`.minecraft/saves/<world_name>/datapacks/`) and run `/reload`.

---

### 5. Local Hardware vs. Cloud Execution

| Component | Where It Runs | Resource Usage |
| :--- | :--- | :--- |
| **AI Model (`gpt-oss:120b-cloud`)** | **Ollama Cloud** | **0 GB Local VRAM / RAM** (116.8B parameters execute entirely in the cloud; only a 384-byte pointer is stored locally) |
| **Web Server & UI** | Local Machine (`127.0.0.1:8000`) | ~50 MB RAM |
| **Minecraft RAG & Generator** | Local Machine | ~100–150 MB RAM |
| **Structural Validator & QA** | Local Machine | ~50–100 MB RAM |
| **Total Local Footprint** | Local Machine | **~200–500 MB RAM total** (runs smoothly on any standard PC or laptop) |

> [!NOTE]
> Python, FastAPI, knowledge retrieval, and static validation still consume ~200–500 MB of local system memory even though the large AI model executes remotely in the cloud.

---

### 6. Cloud Usage, Privacy & Limitations

* **No API Key Required**: When using `ollama signin` through your local Ollama installation, you **never** need to paste an API key into MinecraftAI or `.env`. Authentication is handled directly by Ollama.
* **Usage Allowances & Limits**: Access to cloud models depends on your Ollama account tier and current usage allowances. Account eligibility, hourly/daily usage caps, model availability, and service terms are determined by Ollama ([ollama.com](https://ollama.com)).
* **Privacy Considerations**: Your natural-language datapack requests are sent to Ollama Cloud for model inference. No telemetry, analytics beacons, or personal data are collected or sent by MinecraftAI.
* **No Silent Local Fallback**: If Ollama Cloud inference is unavailable or interrupted, MinecraftAI **strictly reports the error** instead of silently falling back to a small local model.

---

### 7. Troubleshooting

| Issue | Cause | Solution |
| :--- | :--- | :--- |
| `[!] OLLAMA SERVICE UNREACHABLE` | Local Ollama daemon is offline | Start Ollama from your desktop menu or run `ollama serve` in a terminal. |
| `Ollama Cloud authentication required` | Account not signed in | Open a terminal and run `ollama signin` to authenticate with Ollama. |
| `Cloud model 'gpt-oss:120b-cloud' not found` | Manifest not registered | Run `ollama pull gpt-oss:120b-cloud` (only downloads 384 bytes, no weights). |
| `Port 8000 is already in use` | Server already running | Close the existing terminal, or start on a new port: `python run_web.py --port 8001 --open-browser` |
| `Usage limit or rate limit exceeded` | Account quota reached | Check your account status at [ollama.com](https://ollama.com) or wait before submitting requests. |
| `Python is not found in your PATH` | Python not in PATH | Reinstall Python from [python.org](https://www.python.org/) and check **"Add Python to PATH"**. |

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
| `POST` | `/api/generate` | Synchronous / non-blocking datapack generation |
| `POST` | `/api/jobs` | Asynchronous job submission (returns job ID) |
| `GET` | `/api/jobs/{job_id}` | Poll generation job progress, status, and download URL |
| `GET` | `/api/generate/{job_id}` | Alias endpoint for polling generation job status |
| `GET` | `/api/download/{filename}` | Path-traversal protected ZIP download |
| `GET` | `/api/health` | Service health, provider readiness, and security checks |
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

## Deployment & Development Modes

MinecraftAI clearly separates **Public Production Deployment** from **Local Development**:

```text
PUBLIC PRODUCTION FLOW:
Browser (Zero-Setup Client)
   │  HTTPS (Prompt / No Credentials)
   ▼
Hosting Platform / Reverse Proxy (Caddy, Nginx, Cloudflare)
   │  HTTP (Port 8000)
   ▼
MinecraftAI Container (Non-root `appuser`, Port 8000)
   │  Server-Side Secret (`OLLAMA_API_KEY`)
   ▼
AI Provider Backend (Ollama Cloud: gpt-oss:120b-cloud)
   │  Mechanisms / Plans
   ▼
Deterministic Generator → Static Validator → Autonomous QA → ZIP
   │
   ▼
Browser downloads verified datapack ZIP
```

### 1. Public Production Deployment (Server-Side AI Provider)

In production, **all AI credentials and model execution belong strictly to the server**. End-users browsing the public website never provide API keys, install Ollama, or run local models.

* **Server Prerequisites**: Docker & Docker Compose, and a server-side AI provider account (e.g. Ollama Cloud).
* **Security & Non-Root**: Runs under unprivileged user `appuser` (UID 10001).
* **Automatic Retention**: Expired generated archives are automatically purged after 1 hour.
* **CORS Restraint**: Configure `PUBLIC_ORIGIN` to your production domain.

#### Production Configuration (`.env` on server only — NEVER committed)

```ini
ENVIRONMENT=production
HOST=0.0.0.0
PORT=8000
PUBLIC_ORIGIN=https://minecraftai.yourdomain.com

# Server-Side AI Provider (Ollama Cloud)
LLM_PROVIDER=ollama
OLLAMA_HOST=https://ollama.com
OLLAMA_MODEL=gpt-oss:120b-cloud
OLLAMA_API_KEY=<SERVER_SECRET_MANAGED_BY_HOSTING_PLATFORM>

# Abuse Protection & Artifact Lifecycle
MC_MAX_PROMPT_LENGTH=2000
MC_RATE_LIMIT_PER_MINUTE=30
MC_BURST_ALLOWANCE=10
MC_MAX_CONCURRENT_GENERATIONS=4
MC_GENERATION_TIMEOUT_SECONDS=60.0
MC_ARTIFACT_RETENTION_SECONDS=3600
```

#### Launching with Docker Compose

```bash
# Build and start container in detached mode
docker compose up -d --build

# Monitor container health and logs
docker compose logs -f minecraft-ai
```

---

### 2. Local Development (For Contributors)

Developers modifying MinecraftAI source code can run local development servers with local Ollama or mock backends:

```ini
ENVIRONMENT=development
HOST=127.0.0.1
PORT=8000

# Local Ollama daemon
LLM_PROVIDER=ollama
OLLAMA_HOST=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.1:8b
```

Run locally:
```bash
python run_web.py --port 8000
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
