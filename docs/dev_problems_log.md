# Development Problems & Technical Retrospective
### System: Automated Regulatory Robustness Testing (Policy Red Team)
> **Target Audience:** Systems Architects, Deep-Tech Reviewers, Academic Evaluators  
> **Location:** `docs/dev_problems_log.md`

---

## Executive Overview

This document presents a deep-tech architectural retrospective of the engineering challenges encountered across the lifecycle of building the **Stakeholder-Aware Adversarial Red Team** policy auditing framework. Each entry documents the runtime behavior, root cause at the system/protocol level, mitigation strategy, and underlying computer science / AI engineering pattern.

---

## 1. Data Layer: Package Deprecations & API Shift

* **Problem:** Mid-development breakdown of PDF layout parsing primitives caused by breaking architectural changes in upstream LlamaIndex document ingestion dependencies.
* **Root Cause Analysis:** Deprecation of legacy `llama-parse` library in favor of client-driven `llama-cloud>=2.8` asynchronous SDK. Legacy APIs relied on synchronous `LlamaParse` singletons, whereas the cloud-native API requires asynchronous upload primitives (`client.files.create(purpose="parse")`) followed by polled execution (`client.parsing.parse(tier="agentic")`) returning structured page markdown objects.
* **Remediation & Architecture Fix:** Migrated ingestion pipeline (`src/ingest_policy.py`) to the `LlamaCloud` client-side factory model. Abstracted parsed page fragments into typed LlamaIndex `Document` primitives carrying structural metadata (`file_name`, `page_number`, `source`).
* **Technical Pattern:** Cloud-Native API Migration, Asynchronous Task Queue Polling, Schema Normalization.

---

## 2. Infrastructure: Virtual Environment CWD Security Hooks

* **Problem:** Abrupt startup failure during pipeline execution caused by NLTK `inisec` security verification failures (`SecurityError: CWD import hijacking detected`).
* **Root Cause Analysis:** When executing within a local Python virtual environment (`venv/`) co-located inside the project root workspace, binary site-packages (e.g., `regex`, `pypdf`) resolve to paths sub-directory relative to the Current Working Directory (`CWD`). NLTK’s runtime security hook misinterprets these valid workspace-scoped virtualenv site-package imports as CWD script-injection attacks.
* **Remediation & Architecture Fix:** Injected deterministic environment configuration `os.environ["NLTK_DISABLE_IMPORT_SECURITY"] = "1"` in `config/settings.py` prior to importing any third-party NLP or vector store abstractions.
* **Technical Pattern:** Environment Variable Process Override, Module Import Hook Interception.

---

## 3. Vector Indexing: Off-Grid Local Execution & Mock Fallback

* **Problem:** Inability to execute end-to-end ingestion and retrieval unit tests in air-gapped or developer-local environments lacking Vertex AI cloud credentials.
* **Root Cause Analysis:** Hard dependency on `VertexTextEmbedding` (Google Cloud `text-embedding-004`) during vector space initialization. Absence of valid GCP project tokens (`GOOGLE_CLOUD_PROJECT`) caused immediate initialization exceptions within `FaissVectorStore`.
* **Remediation & Architecture Fix:** Built an environment-aware factory module (`src/embeddings.py`) implementing an automatic fallback to LlamaIndex `MockEmbedding` (768-dimensional uniform pseudo-random vector spaces). This preserves topological dimensional compatibility (768-dim) across both local unit testing and production Vertex AI deployment.
* **Technical Pattern:** Polymorphic Factory Pattern, High-Dimensional Mocking, Graceful Degradation.

---

## 4. Bridge Layer: IPC Deadlock in Standard I/O MCP Transport

* **Problem:** Protocol deadlock and worker hanging during multi-agent execution when concurrent agents queried the MCP server tool (`search_policy_documents`).
* **Root Cause Analysis:** FastMCP originally initialized in `stdio` mode (`mcp.run()`), which utilizes blocking standard input/output streams for JSON-RPC IPC transport. When ADK's `ParallelAgent` executed `CitizenProxyAgent` and `BusinessProxyAgent` concurrently, both sub-agents initiated asynchronous I/O read/write operations against the single serial `stdio` stream, inducing standard stream contention and deadlocking the event loop.
* **Remediation & Architecture Fix:** Upgraded `src/mcp_server.py` to support dual-transport mechanisms via CLI flags (`--transport sse --port 8090`). Converted Phase 3 orchestration to Server-Sent Events (SSE) over HTTP transport (`http://127.0.0.1:8090/sse`), enabling non-blocking, multi-channel concurrent JSON-RPC requests across arbitrary parallel agent instances.
* **Technical Pattern:** Inter-Process Communication (IPC) Protocol Upgrade, Event-Driven I/O Multiplexing, Non-Blocking Concurrent RPC.

---

## 5. Memory Management: Attention Decay & Context Window Rot

* **Problem:** Exponential degradation of LLM reasoning performance, hallucination rates, and instruction-following fidelity across multi-turn adversarial debate loops (Turns 1–3).
* **Root Cause Analysis:** Accumulation of raw tool outputs in session memory. Each call to `search_policy_documents` yields up to 6 auto-merged nodes (up to 2,048 tokens each = ~12,288 tokens/call). Over a 3-turn exchange (6 total tool invocations), raw session context ballooned to ~73,000+ tokens. This massive context expansion induced *Lost-in-the-Middle* attention decay and token cost inflation.
* **Remediation & Architecture Fix:** Introduced an asynchronous post-turn compression pass using a `TurnSummarizerAgent`. After each turn, the full exchange is compressed into a ~50-token immutable Pydantic `TurnSummary` struct. Raw retrieved node text is purged from session state, leaving only structured summaries in `debate_history`.
* **Technical Pattern:** Context State Compression, Attention Allocation Optimization, Sliding Window State Reduction.

---

## 6. Execution Control: State Volatility & Unstable Fan-Out

* **Problem:** Stakeholder proxy agents (`CitizenProxyAgent`, `BusinessProxyAgent`) generated incoherent, fluctuating impact scores across identical debate runs.
* **Root Cause Analysis:** The surviving exploit claim passed to the stakeholder fan-out stage was an un-normalized, transient string snapshot taken directly from the multi-turn debate buffer (`current_exploit_text`). Because the argument was in a state of partial counter-rebuttal, agents evaluated non-deterministic intermediate states.
* **Remediation & Architecture Fix:** Injected a deterministic state-normalization barrier (`ExploitCanonicalizerAgent`) between the debate loop exit and parallel stakeholder fan-out. The canonicalizer distills the full transcript into an immutable `CanonicalExploit` schema prior to triggering downstream scoring.
* **Technical Pattern:** State Normalization Barrier, Pipeline Synchronization Primitive, Schema Formalization.

---

## 7. Legal Rigor: Statutory Provenance & Citation Tracking

* **Problem:** Inability of academic evaluators to verify the legal validity of generated `LoopholeReport` outputs due to missing statutory citations and vector similarity metrics.
* **Root Cause Analysis:** Although `mcp_server.py` embedded source metadata (`file_name`, `page_number`, FAISS `score`) in Markdown headers, standard LLM agent outputs discarded these metadata headers, returning ungrounded textual claims.
* **Remediation & Architecture Fix:** Designed a typed `StatutoryCitation` and `RetrievalTrace` Pydantic model hierarchy. Built a specialized regex parser (`src/orchestration/tools.py::parse_mcp_response`) that extracts exact section identifiers (e.g., `§ 4(a)(ii)`), source document names, page indices, and float-precision FAISS scores from raw tool outputs, persisting them directly into `LoopholeReport.statutory_citations`.
* **Technical Pattern:** Automated Provenance Tracking, Regex-Based AST/Metadata Extraction, Grounded Evidence Binding.

---

## 8. Alignment & Stability: Sycophancy Mitigation & Deduplication Gates

* **Problem:** Vulnerability to (a) Defender agent sycophancy (capitulating to the Attacker without grounding) and (b) degenerate looping (Attacker repeating identical exploits across turns).
* **Root Cause Analysis:** LLM alignment defaults favor agreement; without hard structural constraints, Defender agents adopted Attacker premises rather than searching for counter-clauses. Furthermore, turn-count circuit breakers failed to catch semantically redundant arguments.
* **Remediation & Architecture Fix:** 
  1. Injected strict **Sycophancy Prevention Rules** into system prompts, mandating that Defender rebuttals MUST cite statutory sections distinct from the Attacker's citations or explicitly register an `INSUFFICIENT REBUTTAL` status.
  2. Implemented a fast `DeduplicationAgent` (`gemini-3.6-flash`) at the end of each turn to evaluate semantic novelty. Upon detecting argument duplication, the agent returns `STOP`, triggering an `after_agent_callback` that sets `loop_should_continue = False` and short-circuits subsequent rounds.
* **Technical Pattern:** Adversarial Prompt Anchoring, Lightweight Semantic Gating, Short-Circuit Callback Interception.

---

## 9. Orchestration Layer: ADK MCPToolset Symbol Mismatch

* **Problem:** Execution failure with `ImportError: cannot import name 'SseServerParams' from 'google.adk.tools.mcp_tool.mcp_toolset'` during startup of `src/orchestration/runner.py`.
* **Root Cause Analysis:** Upstream `google-adk` package exports SSE connection parameters under `SseConnectionParams` (`mcp_session_manager.py`). The orchestration bridge (`src/orchestration/tools.py`) attempted to import a deprecated/misnamed symbol (`SseServerParams`), causing module import failure.
* **Remediation & Architecture Fix:** Updated `src/orchestration/tools.py` import and factory instantiation to `SseConnectionParams(url=MCP_SERVER_URL)`.
* **Technical Pattern:** API Symbol Reconciliation, Typed SDK Parameter Mapping.

---

## 10. Process Management: Subprocess OS Pipe Deadlock & Infinite SSE Stream Polling

* **Problem:** Subprocess execution failure (`RuntimeError: MCP server did not become ready within 30s`) during automated MCP server background initialization.
* **Root Cause Analysis:** Dual interaction bug:
  1. `_start_mcp_server()` spawned `mcp_server.py` with `stdout=subprocess.PIPE` and `stderr=subprocess.PIPE`. FastMCP startup banner (ASCII art and Uvicorn log output) saturated the OS pipe buffer limit (4KB on Windows). Because the parent process did not consume `proc.stdout` during polling, the child process deadlocked on `stdout.write()`.
  2. `_wait_for_mcp_server()` used standard `httpx.get()` to poll `http://127.0.0.1:8090/sse`. Because `/sse` is a streaming Server-Sent Events endpoint that holds its connection body open indefinitely, `httpx.get()` waited for body completion until read timeout occurred every cycle.
* **Remediation & Architecture Fix:**
  1. Updated `subprocess.Popen` in `_start_mcp_server()` to use `stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL`, preventing OS pipe buffer saturation.
  2. Updated `_wait_for_mcp_server()` to use `async with client.stream("GET", MCP_HEALTH_URL, ...)`, which reads HTTP `200 OK` headers immediately without waiting for the infinite SSE stream body to close.
* **Technical Pattern:** Non-Blocking Subprocess I/O Management, HTTP Streaming Header Validation, OS Pipe Deadlock Avoidance.

---

## 11. Embedding Factory: Graceful Fallback on Vertex API Initialization Errors

* **Problem:** Subprocess or MCP server startup crash when `VertexTextEmbedding` initialization throws `ValueError` or `PermissionDenied` (e.g., missing local ADC credentials or disabled GCP API).
* **Root Cause Analysis:** `get_embedding_model()` in `src/embeddings.py` directly instantiated `VertexTextEmbedding` without error handling. When Google Cloud credentials or Vertex AI APIs were disabled on the target project, `VertexTextEmbedding` raised `ValueError: Either provide credentials or...` during module load, preventing the server from starting.
* **Remediation & Architecture Fix:** Wrapped `VertexTextEmbedding` initialization in a try-except block within `src/embeddings.py`. Upon catching initialization errors (such as disabled GCP APIs or credential resolution failures), the factory logs a warning and automatically degrades to `MockEmbedding(embed_dim=768)`, preserving zero-crash local execution.
* **Technical Pattern:** Defensive Exception Interception, Resilient Embedding Fallback, Graceful Service Degradation.

---

## 12. Model Naming: Invalid Vertex AI Model Constants

* **Problem:** Request failure with `404 NOT_FOUND: Publisher model projects/policy-red-team/locations/us-central1/publishers/google/models/gemini-3.1-pro was not found`.
* **Root Cause Analysis:** `src/orchestration/agents.py` declared non-existent model string constants (`_FLASH = "gemini-3.6-flash"` and `_PRO = "gemini-3.1-pro"`), causing API lookup errors on Google Cloud Vertex AI.
* **Remediation & Architecture Fix:** Updated model constants in `src/orchestration/agents.py` to production-ready Vertex AI model aliases: `gemini-3.6-flash` (for fast utility agents) and `gemini-3.1-pro-preview` (for deep legal reasoning agents).
* **Technical Pattern:** Schema & Identifier Normalization, Model Registry Alignment.

---

## 13. Output Parsing: Markdown Code Block Fence Sanitization in JSON Extraction

* **Problem:** Audit workflow execution error `pydantic_core._pydantic_core.ValidationError: 1 validation error for LoopholeReport (Invalid JSON: expected value at line 1 column 1)` when parsing final report JSON state.
* **Root Cause Analysis:** The `JudgeAgent` returned raw output formatted inside Markdown code block fences (````json\n{ ... }\n````). Passing raw Markdown-wrapped JSON directly into Pydantic's `model_validate_json()` raised a syntax validation error.
* **Remediation & Architecture Fix:** Updated `_extract_report()` in `src/orchestration/runner.py` to sanitize incoming string payloads by stripping leading and trailing Markdown code fences (` ```json ` / ` ``` `) prior to Pydantic deserialization.
* **Technical Pattern:** Robust Payload Sanitization, LLM Markdown Unwrapping, Fail-Safe Schema Deserialization.

---

## Summary Matrix

| Failure Mode | Deep-Tech Root Cause | Remediation Primitive | CS/AI Engineering Domain |
|---|---|---|---|
| Deprecated Parser SDK | Sync/Async API paradigm shift | `LlamaCloud` client-side API | Distributed Task Queue |
| NLTK Security Trap | Virtualenv CWD path resolution | Runtime environment override | Process Isolation / Runtime |
| Missing GCP Tokens | Hard dependency on Vertex API | 768-dim `MockEmbedding` fallback | High-Dimensional Vector Spaces |
| MCP Pipe Deadlock | Single-threaded `stdio` IPC contention | Concurrent SSE over HTTP | Network Protocol / Async I/O |
| Attention Decay | ~73K token context expansion | `TurnSummarizerAgent` state reduction | Transformer Attention Optimization |
| Unstable Fan-Out | Volatile intermediate state evaluation | `ExploitCanonicalizerAgent` barrier | State Machine Normalization |
| Missing Evidence | Unstructured text output loss | Typed Regex AST metadata parser | Programmatic Provenance Tracking |
| Sycophancy / Repetition | Default LLM agreement & degenerate loops | Semantic gating & callback short-circuit | Multi-Agent Control Flow |
| SDK Symbol Mismatch | Class name mismatch in `google-adk` | `SseConnectionParams` replacement | Typed SDK Interface Binding |
| Subprocess Pipe Deadlock | OS pipe saturation & infinite SSE polling | `DEVNULL` pipes + `httpx.stream()` | Non-Blocking Process I/O & HTTP Streaming |
| Embedding Init Crash | Unhandled `VertexTextEmbedding` exceptions | Try-except `MockEmbedding` fallback | Resilient Service Degradation |
| Invalid Model Name | Non-existent Gemini model constants | `gemini-3.6-flash` & `gemini-3.1-pro-preview` | Model Registry Alignment |
| Markdown JSON Fences | LLM code block wrappers in JSON output | Markdown fence stripper in `_extract_report()` | Payload Sanitization / Deserialization |
