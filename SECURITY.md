# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it responsibly.

**Do NOT open a public GitHub issue for security vulnerabilities.**

Instead, please email the maintainer directly with:

1. A description of the vulnerability.
2. Steps to reproduce the issue.
3. The potential impact.

We will acknowledge your report within **48 hours** and provide an estimated timeline for a fix.

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| main    | :white_check_mark: |

## Scope

The following are in scope for security reports:

- **Credential exposure**: Hardcoded API keys, service account keys, or secrets in source code or configuration files.
- **Injection vulnerabilities**: Prompt injection, command injection, or path traversal in the policy ingestion or agent orchestration pipelines.
- **Dependency vulnerabilities**: Known CVEs in pinned or unpinned dependencies listed in `requirements.txt`.
- **Data exfiltration**: Unintended leakage of policy document content, user inputs, or audit results.

## Security Best Practices for Contributors

1. **Never commit secrets**: API keys, service account JSON files, and `.env` files must never be committed to version control. Use `.env.example` as a template.
2. **Use `.gitignore`**: Ensure credential files are listed in `.gitignore` before initializing the repository.
3. **Rotate exposed keys immediately**: If a key is accidentally committed, rotate it on the cloud provider console *before* removing it from Git history.
4. **Pin dependencies**: When adding new dependencies, pin to a specific version to prevent supply chain attacks.
5. **Validate inputs**: All user-supplied inputs (policy PDFs, jurisdiction strings, custom instructions) should be validated before processing.

## Known Security Considerations

- **LLM prompt injection**: The adversarial agent architecture intentionally uses adversarial prompts. The system includes anti-sycophancy rules and structured output validation to mitigate prompt-based attacks on the Judge agent.
- **MCP server**: The MCP server runs on `localhost:8090` and is not intended for public network exposure. In production deployments, ensure the server is behind a firewall or internal network.
- **PDF parsing**: Policy PDFs are parsed via the LlamaCloud API. Malicious PDFs could potentially exploit the cloud parsing service. Only process PDFs from trusted sources.
