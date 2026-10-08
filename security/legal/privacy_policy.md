# MinecraftAI Privacy Policy

**Effective Date:** October 7, 2026
**Last Updated:** October 7, 2026

MinecraftAI is committed to transparent, privacy-respecting operations. This Privacy Policy accurately describes the information processed when you use the MinecraftAI web interface and API service.

---

## 1. Information We Process

### A. Prompts & Natural-Language Inputs
When you submit a request to generate a datapack, the text of your prompt is processed by the backend pipeline to interpret your desired game mechanics, retrieve relevant Minecraft data, and generate datapack files.
* **Storage:** Prompts are processed in memory during the execution of your request.
* **Logging:** Truncated and sanitized prompt excerpts may be temporarily recorded in server application logs for operational diagnostics and rate limiting, unless logging is explicitly disabled in the server configuration.

### B. Generated Datapacks & Temporary Artifacts
Generated datapack directories and downloadable ZIP archives are stored temporarily in the application's designated `generated/` directory on the hosting server.
* **Retention:** Generated files remain available for download temporarily and are subject to periodic cleanup.
* **Access:** Datapack files are public to anyone with the exact generated ZIP filename. Do not include personal secrets, credentials, or confidential information in your prompts.

### C. Technical & Connection Data
When making requests to our web server:
* **IP Addresses:** Client IP addresses are processed in memory by the rate-limiting system to prevent automated denial-of-service and abuse. In application logs, IP addresses are anonymized (e.g. `192.168.*.*`).
* **HTTP Headers:** Standard browser headers (User-Agent, Accept-Encoding) are processed to serve appropriate responses.

---

## 2. What We DO NOT Collect

To maintain strict privacy:
* **No User Accounts:** MinecraftAI does not require registration, passwords, email addresses, or personal profiles.
* **No Tracking Cookies:** The MinecraftAI web application does not set any tracking, advertising, or profiling cookies.
* **No Third-Party Analytics:** We do not embed Google Analytics, Meta Pixel, or any third-party tracking scripts.
* **No Payment Information:** MinecraftAI does not collect or process financial or payment data.

---

## 3. AI Model & Processing Architecture

* **Local LLM Execution:** In default deployments, natural-language processing is performed locally via a self-hosted Ollama instance. Your prompts are transmitted solely to the local model runtime configured on the server, not to commercial external cloud APIs.
* **Data Training:** MinecraftAI does not use your submitted prompts to train or fine-tune public foundation models.

---

## 4. Data Security

We implement reasonable technical safeguards to protect your interactions:
* Automated input sanitization and length bounds.
* Strict path traversal defenses and sandboxed filesystem output.
* In-memory sliding-window rate limiting to prevent abuse.
* Content Security Policy (CSP) and modern browser security headers.

---

## 5. Contact & Questions

If you have questions regarding this Privacy Policy or wish to inquire about operational data practices, please refer to the project repository at [https://github.com/krishnabhardwaj-001/MinecraftAI](https://github.com/krishnabhardwaj-001/MinecraftAI) or review the [Security Policy](security_policy.md).
