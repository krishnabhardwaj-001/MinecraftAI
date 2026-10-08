# MinecraftAI Security Policy

**Effective Date:** October 7, 2026
**Last Updated:** October 7, 2026

MinecraftAI takes the security of our application, users, and open-source software seriously. This document outlines our vulnerability disclosure process, reporting guidelines, and security scope.

---

## 1. Reporting a Vulnerability

If you discover a security vulnerability or potential exploit in MinecraftAI, please report it privately and responsibly. **Do not create public GitHub issues or disclose details publicly until a fix has been published.**

### Reporting Procedure:
1. **Repository Security Advisory:** Use GitHub's [Private Vulnerability Reporting](https://github.com/krishnabhardwaj-001/MinecraftAI/security/advisories) feature on the repository.
2. **Alternative Contact:** If private advisories are unavailable, open a confidential communication channel with the project maintainer via the repository profile.

---

## 2. Information to Include in Your Report

To help us investigate and triage your report efficiently, please include:
* **Description:** A clear summary of the issue and potential impact.
* **Component:** The affected endpoint, module, or file (e.g. `web/app.py`, `security/archive_security.py`).
* **Reproduction Steps:** Step-by-step instructions or proof-of-concept (PoC) payload demonstrating the vulnerability.
* **Environment:** Python version, OS platform, and relevant configuration settings.
* **Suggested Remediation:** Any recommended patch or architectural fix if known.

---

## 3. Scope & Priorities

### In Scope:
* Path traversal escapes in file generation, download, or archive handling.
* Archive manipulation vulnerabilities (Zip Slip, decompression bombs).
* Server-side command injection or unauthorized OS execution through the generator.
* Denial-of-service vulnerabilities via unbounded payload handling or unmetered generation.
* Cross-Site Scripting (XSS) or header bypass in the web application.
* Information leakage exposing server secrets, private tokens, or sensitive host paths.

### Out of Scope:
* Bugs or mechanics bugs in vanilla Minecraft Java Edition itself.
* Upstream bugs in third-party foundation models or self-hosted Ollama runtimes.
* Denial-of-service against third-party network infrastructure.
* Social engineering or physical access attacks against server operators.

---

## 4. Response & Remediation Commitment

* **Acknowledgment:** We aim to acknowledge receipt of security reports within 48 to 72 business hours.
* **Assessment & Fix:** We will prioritize verification and develop a patch in a dedicated private branch.
* **Credit & Disclosure:** Once a security patch is deployed or committed, we will credit the security researcher (if desired) and publish a public security advisory detailing the fix.
