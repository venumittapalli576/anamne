# Security Policy

## Supported Versions

| Version | Supported |
|---|---|
| 1.x | ✅ Current |
| < 1.0 | ❌ No longer supported |

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

ANAMNE is a local-first tool — it never transmits your data to any server
other than the LLM API you configure (Anthropic or Google). The main
attack surfaces are:

- **API key exposure** — keys are read from `.env` files; never commit them
- **Prompt injection** — malicious content in git commits or imported chats
  could influence LLM output (standard RAG risk)
- **Local SQLite/ChromaDB data** — stored unencrypted in `~/.anamne/`

To report a vulnerability privately, open a
[GitHub Security Advisory](https://github.com/venumittapalli576/anamne/security/advisories/new).

I'll respond within 7 days. This is a solo personal project — please be patient.
