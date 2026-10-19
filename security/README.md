# MinecraftAI Security Architecture & Documentation

## Overview
The `security/` package serves as the centralized defensive perimeter and security enforcement layer for MinecraftAI. It implements defenses against input abuse, directory traversal, archive vulnerabilities (Zip Slip/Zip Bomb), unauthorized command synthesis, denial-of-service, and sensitive data leakage.

---

## 1. Threat Model & Trust Boundaries

```
[ Untrusted Client / Browser ]
             │
             ▼
[ SecurityHeadersMiddleware & RateLimiter ] ─── (CORS, Rate limits, Concurrency slot)
             │
             ▼
[ Input Validation (input_security.py) ] ─── (Length bounds, null byte, script tag checks)
             │
             ▼
[ FastAPI Route Handler (web/app.py) ]
             │
             ▼
[ Minecraft Pipeline & Deterministic Generator ]
             │
             ▼
[ Command & Archive Validation (command_security.py, archive_security.py) ]
             │
             ▼
[ Sandboxed Filesystem (path_security.py) ] ─── (Controlled generated/ directory)
             │
             ▼
[ Error Sanitizer (error_sanitizer.py) ] ─── (Safe user response, scrubbed logs)
```

### Trust Assumptions:
* **Untrusted:** User prompts, HTTP request headers, query parameters, submitted file paths, and archive member names.
* **Semi-Trusted:** Local LLM output (Ollama) — validated structurally and semantically before any filesystem or command operations.
* **Trusted:** MinecraftAI internal deterministic generators and version metadata registries.

---

## 2. Defensive Controls Implemented

### A. Input Security (`input_security.py`)
* **Length Bounds:** Prompts must satisfy `min_prompt_length` (3 chars) and `max_prompt_length` (2,000 chars).
* **Binary Injection Guard:** Scans for and rejects null bytes (`\x00`) and unapproved control characters.
* **Script Injection Guard:** Rejects `<script>` and HTML injection tokens.
* **Version Validation:** Validates format with regex and enforces membership in registered supported versions (`1.21.11`, `1.21.1`).
* **Datapack Name Sanitization:** Converts untrusted strings into safe alphanumeric identifiers.

### B. Path Security & Sandboxing (`path_security.py`)
* **Path Traversal Prevention:** Blocks sequences containing `..`, absolute paths, Windows drive letters (`C:`), and UNC paths (`\\server\share`).
* **Sandbox Containment:** All generated output paths are validated with `Path.relative_to()` to ensure containment within approved output directories (`generated/`).
* **Download Filename Validation:** Download endpoints require strict regex adherence (`^[a-zA-Z0-9_\-]+\.zip$`), preventing arbitrary file retrieval from host systems.

### C. Archive & ZIP Security (`archive_security.py`)
* **Zip Slip Defense:** Every archive entry is inspected before reading or extracting. Entries with traversal sequences or root escapes are rejected.
* **Zip Bomb Defense:** Enforces strict limits:
  * Maximum 500 files per archive.
  * Maximum 5 MB per individual file.
  * Maximum 50 MB total uncompressed bytes.
  * Maximum 100:1 compression ratio limit.
* **Extension Whitelisting:** Permits only `.json`, `.mcfunction`, `.mcmeta`, `.png`, and `.txt`. Executables (`.exe`, `.sh`, `.bat`, `.py`) are rejected.
* **Datapack Structure Verification:** Enforces root-level `pack.mcmeta` and `data/` directory presence.

### D. Command Security (`command_security.py`)
* **Minecraft Verb Whitelist:** Commands synthesized by the pipeline must start with recognized Minecraft Java verbs (`give`, `scoreboard`, `tellraw`, `execute`, `function`, etc.).
* **Shell Execution Blocking:** Prohibits shell invocations (`cmd.exe`, `bash`, `powershell`, `eval`, `system`, backticks).

### E. Rate Limiting & Concurrency (`rate_limit.py`)
* **Sliding Window Rate Limiter:** Limits clients to 30 requests per minute with a burst cap of 10 requests per 5-second window.
* **Concurrency Semaphore:** Restricts concurrent pipeline executions (default: 4) to protect host memory and CPU.

### F. Security Headers (`headers.py`)
* **Content-Security-Policy:** Restricts asset sources to `'self'`, Google Fonts, and inline styling.
* **X-Content-Type-Options:** `nosniff` prevents MIME-type confusion attacks.
* **X-Frame-Options:** `DENY` prevents clickjacking.
* **Referrer-Policy:** `strict-origin-when-cross-origin`.
* **Cache Control:** Prevents proxy caching of generated downloads and sensitive API responses.

### G. Logging & Error Sanitization (`logging.py`, `error_sanitizer.py`)
* **Secret Scrubbing:** Regex maskers remove API keys, bearer tokens, passwords, and host paths from log output.
* **Safe User Responses:** Internal exceptions are converted into clean user-facing error messages, preventing stack trace or system path disclosure.

---

## 3. Legal & Policy Documentation (`security/legal/`)
* [Privacy Policy](legal/privacy_policy.md): Accurate disclosure of processed prompts, temporary artifacts, and zero-tracking commitment.
* [Terms of Service](legal/terms_of_service.md): Acceptable use, disclaimers, and Mojang/Microsoft trademark notices.
* [Security Policy](legal/security_policy.md): Vulnerability reporting procedures and response commitments.

---

## 4. Controls NOT Provided (Operational Boundaries)
* **Authentication/Authorization:** MinecraftAI is designed as an open-access generator tool. If deployed behind restricted corporate firewalls, external reverse-proxy authentication (OAuth/SSO) should be utilized.
* **Distributed State:** The default rate limiter uses thread-safe in-memory state. For multi-node load-balanced deployments, a centralized cache (such as Redis) can be integrated by extending `InMemoryRateLimiter`.
