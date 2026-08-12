# Contributing to Policy Red Team

Thank you for considering contributing to the **Automated Regulatory Robustness Testing** project. This guide will help you get started.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Making Changes](#making-changes)
- [Testing](#testing)
- [Pull Request Process](#pull-request-process)
- [Style Guide](#style-guide)

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/version/2/1/code_of_conduct/). By participating, you are expected to uphold this code. Please report unacceptable behavior via the repository issue tracker.

## Getting Started

1. **Fork** the repository on GitHub.
2. **Clone** your fork locally:
   ```bash
   git clone https://github.com/<your-username>/policy-red-team.git
   cd policy-red-team
   ```
3. **Create a branch** for your feature or fix:
   ```bash
   git checkout -b feature/your-feature-name
   ```

## Development Setup

### Prerequisites

- Python 3.10+
- [LlamaCloud API key](https://cloud.llamaindex.ai/api-key) (required for PDF parsing)
- Google Cloud account with Vertex AI API enabled (optional — the system falls back to `MockEmbedding` for local testing)

### Environment Setup

```bash
# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (macOS/Linux)
# source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env
# Edit .env with your credentials
```

### Local Test Mode (No GCP Required)

Leave `GOOGLE_CLOUD_PROJECT` empty in `.env` to run in **Local Test Mode**. The system automatically uses `MockEmbedding` (768-dim pseudo-random vectors) for FAISS indexing, allowing you to test the full pipeline without any Google Cloud credentials.

## Project Structure

```
policy-red-team/
├── config/           # Centralized settings (settings.py)
├── data/             # User-supplied policy PDFs
├── docs/             # Architecture docs & development retrospective
├── src/
│   ├── embeddings.py       # Embedding model factory (Vertex AI / MockEmbedding)
│   ├── ingest_policy.py    # Phase 1: PDF → hierarchical FAISS index
│   ├── mcp_server.py       # Phase 2: FAISS → MCP tool (AutoMergingRetriever)
│   └── orchestration/      # Phase 3: ADK multi-agent workflow
│       ├── state.py        # Pydantic models & session state
│       ├── tools.py        # MCP toolset factory & response parser
│       ├── agents.py       # Agent factory functions
│       ├── workflow.py     # SequentialAgent DAG & callbacks
│       └── runner.py       # MCP subprocess launcher & ADK Runner
├── tests/            # Automated test suite (pytest)
├── main.py           # FastAPI server & API endpoints
├── static/           # Vanilla HTML/CSS/JS frontend
├── Dockerfile        # Cloud Run container definition
└── requirements.txt  # Pinned dependencies
```

## Making Changes

### Architecture Guidelines

- **Immutability**: All Pydantic models use `ConfigDict(frozen=True)`. Use `model_copy(update={...})` for state transitions.
- **No local inference**: All heavy compute (PDF parsing, embedding, LLM inference) is offloaded to cloud APIs. Do not introduce PyTorch or local model dependencies.
- **Jurisdiction modularity**: Legal context is injected via `_build_jurisdiction_context()` in `agents.py`. To add a new jurisdiction, extend this single function.
- **Preserve docstrings**: Do not remove existing docstrings or comments unless directly related to your change.

### Adding a New Agent

1. Create a factory function in `src/orchestration/agents.py` following the existing pattern.
2. Add the agent's output key to `PolicyAuditState.to_session_dict()` in `state.py`.
3. Wire the agent into the workflow in `workflow.py`.
4. Add unit tests in `tests/`.

## Testing

Run the full test suite:

```bash
pytest tests/ -v
```

Run a specific test file:

```bash
pytest tests/test_state.py -v
```

### What to Test

- **State models**: Pydantic serialization/deserialization, `to_session_dict()`, `from_session_dict()`.
- **MCP response parsing**: Regex extraction of citations, scores, page numbers from Markdown output.
- **Embedding fallback**: `MockEmbedding` activation when GCP credentials are absent.

## Pull Request Process

1. **Ensure tests pass**: Run `pytest tests/ -v` and verify all tests are green.
2. **Update documentation**: If you change behavior, update the relevant docs in `docs/` and `README.md`.
3. **Write a clear PR description**: Explain *what* changed and *why*.
4. **One concern per PR**: Keep pull requests focused. Separate bug fixes from feature additions.
5. **Review**: A maintainer will review your PR. Please be responsive to feedback.

## Style Guide

### Python

- Follow [PEP 8](https://peps.python.org/pep-0008/) conventions.
- Use type annotations for all function signatures.
- Write docstrings for all public functions and classes.
- Use `from __future__ import annotations` for modern type annotation syntax.

### Documentation

- Use Markdown for all documentation.
- Include Mermaid diagrams for architectural changes.
- Document design decisions, not just what the code does.

### Commits

- Write clear, descriptive commit messages.
- Use the imperative mood: "Add feature" not "Added feature".
- Reference issue numbers where applicable: `Fix #42: handle empty PDF input`.

---

Thank you for helping improve the **Automated Regulatory Robustness Testing** framework!
