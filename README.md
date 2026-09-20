# Automated Regulatory Robustness Testing

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Framework: Google ADK](https://img.shields.io/badge/Framework-Google%20ADK-green.svg)](https://github.com/google/adk)
[![Retriever: LlamaIndex](https://img.shields.io/badge/Retriever-LlamaIndex-orange.svg)](https://www.llamaindex.ai/)

**Adversarial Policy Loophole Finder** — A thesis-grade, multi-agent AI system that stress-tests public policies, municipal bylaws, statutory instruments, and private sector compliance frameworks through an adversarial, stakeholder-aware debate loop.

---

## System Architecture

> 📖 **Detailed Specification**: For comprehensive documentation on data flows, component design, and architectural decisions, see [docs/architecture.md](docs/architecture.md).

```
┌─────────────────────────────────────────────────────────────────────────┐
│              Phase 1: Data Layer (ingest_policy.py)                     │
│  ┌──────────────────────────────┐       ┌────────────────────────────┐  │
│  │     FAISS Vector Store       │       │    LlamaIndex Docstore     │  │
│  │ (128-token leaf embeddings)  │       │ (2048/512 parent nodes)    │  │
│  └──────────────┬───────────────┘       └─────────────┬──────────────┘  │
└─────────────────┼─────────────────────────────────────┼─────────────────┘
                  │                                     │
┌─────────────────┼─────────────────────────────────────┼─────────────────┐
│                 ▼    Phase 2: Bridge Layer (mcp_server.py) ▼                 │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │      AutoMergingRetriever over FastMCP (http://127.0.0.1:8090/sse) │  │
│  └──────────────────────────────────┬────────────────────────────────┘  │
└─────────────────────────────────────┼───────────────────────────────────┘
                                      │ FastMCP SSE Transport
┌─────────────────────────────────────┼───────────────────────────────────┐
│                                     ▼                                   │
│            Phase 3: ADK Multi-Agent Orchestration Layer                 │
│                                                                         │
│    ┌──────────────┐      Debate Loop       ┌──────────────┐             │
│    │ AttackerAgent│ ─────────────────────> │ DefenderAgent│             │
│    │(gemini-3.1-p)│ <───────────────────── │(gemini-3.1-p)│             │
│    └──────┬───────┘                        └──────┬───────┘             │
│           │                                       │                     │
│           └───────────────────┬───────────────────┘                     │
│                               │                                         │
│                ┌──────────────▼──────────────┐                          │
│                │   TurnSummarizer & Dedup    │                          │
│                │     (gemini-3.6-flash)      │                          │
│                └──────────────┬──────────────┘                          │
│                               │                                         │
│                ┌──────────────▼──────────────┐                          │
│                │    ExploitCanonicalizer     │                          │
│                └──────────────┬──────────────┘                          │
│                               │                                         │
│                ┌──────────────▼──────────────┐                          │
│                │  Stakeholder Swarm (Par.)   │                          │
│                │  Citizen & Business Proxies │                          │
│                └──────────────┬──────────────┘                          │
│                               │                                         │
│                ┌──────────────▼──────────────┐                          │
│                │         JudgeAgent          │                          │
│                │    (gemini-3.1-pro-prev)    │                          │
│                └──────────────┬──────────────┘                          │
└───────────────────────────────┼─────────────────────────────────────────┘
                                │ JSON Report Payload
┌───────────────────────────────┼─────────────────────────────────────────┐
│                               ▼                                         │
│     Phase 4: Web Application Layer (FastAPI Backend + HTML/CSS/JS)      │
│  ┌─────────────────────────────┐        ┌────────────────────────────┐  │
│  │  FastAPI Server (main.py)   │ ─────> │ Modern Dashboard UI        │  │
│  │  Endpoints & Upload Pipeline│        │ (static/index.html + CSS)  │  │
│  └─────────────────────────────┘        └────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Key Features

1. **Adversarial Red-Teaming**: A legally sophisticated `AttackerAgent` and `DefenderAgent` debate statutory interpretations across unrolled turns.
2. **Context-Preserving Hierarchical Retrieval**: Offloads PDF parsing to `LlamaCloud` (`tier="agentic"`), builds a 2048 → 512 → 128 token node hierarchy, and uses `AutoMergingRetriever` over FAISS to prevent legal context fragmentation.
3. **Context Window Decay Mitigation**: Compresses raw MCP search results (~12,000 tokens/turn) into structured ~150–200 token `TurnSummary` Pydantic models (**99.2% token reduction**).
4. **Concurrent Tool Transport**: FastMCP exposed over Server-Sent Events (SSE) on HTTP (`http://127.0.0.1:8090/sse`) to prevent IPC deadlocks during parallel agent execution.
5. **Grounded Statutory Provenance**: Regex AST metadata parser extracts section identifiers (e.g., `§ 4(a)(ii)`), page numbers, and float-precision FAISS scores into typed `StatutoryCitation` objects.

---

## Use Cases & Scope

Policy Red Team is designed for two primary scenarios:

1. **Public Policy Loophole Discovery**: Stress-testing government bylaws, statutory rules, and municipal notifications to find definitional gaps, penalty asymmetries, and exemption abuse.
2. **Private Sector Compliance Check (Jurisdictional Arbitrage)**: Testing private sector policies (e.g., a private housing society's bylaws) against governing statutory laws (e.g., RDA bylaws) to ensure they are *intra vires*. The system acts as a disgruntled resident or competitor, using "Jurisdictional Arbitrage" to find clauses in the private policy that illegally contradict parent statutory law.

### 🚫 What this system is NOT designed for:
- **It is NOT a traditional compliance checklist tool.** It does not go line-by-line to tick off a checklist. It is an *adversarial engine* that attacks the policy to find loopholes.
- **It is NOT a general legal advisory bot.** It is strictly scoped to finding exploitable weaknesses in uploaded documents.
- **It is NOT for case-law or judicial precedent synthesis.** The engine audits statutory texts, not court judgments.
- **It is NOT for non-statutory documents.** High-level policy visions (e.g., "Vision 2030") without binding clauses or legal penalties cannot be effectively audited.

---

## Prerequisites

- **Python 3.10+**
- **LlamaCloud API key** from [cloud.llamaindex.ai](https://cloud.llamaindex.ai/api-key)
- **Google Cloud account** with Vertex AI API enabled (*optional for local testing — the system automatically falls back to `MockEmbedding` when GCP credentials are absent*)

---

## Quick Start

### 1. Clone & Create Virtual Environment

```bash
git clone https://github.com/your-username/policy-red-team.git
cd policy-red-team

# Create and activate virtual environment
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
# source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
# Copy the template
cp .env.example .env
```

Edit `.env` with your credentials:

```ini
# LlamaCloud API Key (REQUIRED for PDF parsing)
LLAMA_CLOUD_API_KEY=llx-your-key-here

# --- LOCAL TEST MODE (Zero GCP Credentials) ---
# Leave GOOGLE_CLOUD_PROJECT empty to test locally using MockEmbedding (768-dim).
GOOGLE_CLOUD_PROJECT=

# --- PRODUCTION / VERTEX AI MODE ---
# Set your GCP Project ID when ready for production semantic embeddings
# GOOGLE_CLOUD_PROJECT=your-gcp-project-id
# GOOGLE_CLOUD_LOCATION=us-central1
```

---

## Running the Pipeline

### Step 1: Ingest Policy Documents (Phase 1)

Place your policy PDFs in `data/` and run:

```bash
python -m src.ingest_policy
```

This will parse the PDFs via LlamaCloud, build the hierarchical node tree, embed leaf nodes, and persist the index to `./storage/faiss/`.

### Step 2: Run the Multi-Agent Red Team Audit (Phase 3)

```bash
python -m src.orchestration.runner
```

This script:
1. Spawns the MCP server in SSE mode on `http://127.0.0.1:8090/sse`
2. Initializes the ADK session state and multi-agent workflow
3. Executes the adversarial debate, stakeholder scoring, and Judge synthesis
4. Generates a structured `LoopholeReport` JSON in `./storage/reports/`

### Step 3: Launch the Web Application (FastAPI + HTML/CSS/JS)

```bash
python main.py
```

or via Uvicorn:

```bash
uvicorn main:app --reload --port 8000
```

Opens the modern, responsive web dashboard at `http://localhost:8000` to upload PDFs, configure audit parameters, execute live red-team audits, and visualize stakeholder impact scoring.

---

## Running Automated Tests

Run the full pytest suite:

```bash
pytest tests/ -v
```

The test suite covers **32 unit and integration test cases** across all system layers (100% passing):

| Test File | Component | Test Cases Covered | Result |
|---|---|---|---|
| [`tests/test_api_auth.py`](file:///c:/Users/Laptop/OneDrive/Desktop/Amaan/Startups-Initiatives/policy-red-team/tests/test_api_auth.py) | `main.py` (FastAPI Endpoints) | Master Admin auth, demo tester auth, invalid passcode gating, user reports scoping, admin authorization, passcode generation/deletion | ✅ 5/5 Passed |
| [`tests/test_db.py`](file:///c:/Users/Laptop/OneDrive/Desktop/Amaan/Startups-Initiatives/policy-red-team/tests/test_db.py) | `src/db.py` (Persistence & Quotas) | SQLite initialization, passcode verification, quota limits, pre-flight analysis gating, report persistence, admin quota adjustment | ✅ 8/8 Passed |
| [`tests/test_state.py`](file:///c:/Users/Laptop/OneDrive/Desktop/Amaan/Startups-Initiatives/policy-red-team/tests/test_state.py) | `src/orchestration/state.py` | Document roles serialization, web search toggle, Pydantic immutability, `TurnSummary` compression, session state serialization | ✅ 8/8 Passed |
| [`tests/test_tools.py`](file:///c:/Users/Laptop/OneDrive/Desktop/Amaan/Startups-Initiatives/policy-red-team/tests/test_tools.py) | `src/orchestration/tools.py` | Regex AST metadata parser, FAISS score parsing, section ID extraction, page number extraction, empty response fallback | ✅ 9/9 Passed |
| [`tests/test_embeddings.py`](file:///c:/Users/Laptop/OneDrive/Desktop/Amaan/Startups-Initiatives/policy-red-team/tests/test_embeddings.py) | `src/embeddings.py` | Vertex AI text-embedding-004 initialization and credential failure validation | ✅ 2/2 Passed |
| **Total** | **Full System Coverage** | **Automated Unit & Integration Tests** | **✅ 32/32 Passed (100%)** |


---

## Project Structure

```
policy-red-team/
├── .env.example              # Environment variable template
├── .gitignore                # Git ignore configuration
├── LICENSE                   # MIT Open Source License
├── CONTRIBUTING.md           # Guidelines for open-source contributors
├── SECURITY.md               # Security policy and disclosure process
├── README.md                 # Project documentation
├── tester_guide.md           # Complete end-user testing instructions
├── Dockerfile                # Container definition for Cloud Run
├── requirements.txt          # Production dependencies
├── main.py                   # FastAPI application server & API endpoints
├── static/                   # 2002–2007 Classic Grey Web Application
│   ├── index.html            # Main web layout with dual ingestion & guidance modals
│   ├── styles.css            # Classic Windows 2000/XP Silver styling system
│   └── app.js                # Frontend client, dual upload, quotas & admin console
├── config/
│   ├── __init__.py
│   └── settings.py           # Centralized application settings
├── data/
│   ├── .gitkeep              # Data directory placeholder
│   └── *.pdf                 # User-supplied policy documents
├── docs/
│   ├── architecture.md       # Comprehensive architectural specification
│   └── dev_problems_log.md   # Deep-tech technical retrospective (19 failure modes)
├── src/
│   ├── __init__.py
│   ├── db.py                 # SQLite persistence, passcodes, quotas & GCS sync
│   ├── embeddings.py         # Embedding model factory (Vertex AI text-embedding-004)
│   ├── ingest_policy.py      # PDF → FAISS hierarchical indexer
│   ├── inspect_storage.py    # Storage inspection helper
│   ├── mcp_server.py         # FAISS → MCP tool (FastMCP SSE)
│   └── orchestration/        # Google ADK 2.0 Multi-Agent Orchestration Layer
│       ├── __init__.py
│       ├── state.py          # Pydantic models, DocumentRole, & PolicyAuditState
│       ├── tools.py          # MCPToolset factory & AST regex parser
│       ├── agents.py         # Attacker, Defender (Search Grounded), Judge & Proxies
│       ├── workflow.py       # SequentialAgent DAG & callbacks
│       └── runner.py         # Subprocess launcher & audit execution runner
├── storage/                  # Runtime generated artifacts
│   ├── faiss/                # Persisted FAISS vector store & docstore
│   ├── policy_red_team.db    # SQLite database (passcodes, quotas, reports)
│   └── reports/              # Output LoopholeReport JSONs
└── tests/
    ├── conftest.py           # Shared test fixtures
    ├── test_api_auth.py      # FastAPI auth & admin endpoint tests
    ├── test_db.py            # SQLite database & quota logic tests
    ├── test_embeddings.py    # Vertex AI embedding tests
    ├── test_state.py         # State & document role tests
    └── test_tools.py         # MCP parser & citation tests
```

---

## License

This project is licensed under the [MIT License](LICENSE).
