# Retail Company AI Technical Assignment

A production-minded CLI analytics assistant for retail managers that combines **SQL analytics** with a **Golden Knowledge retrieval layer**, while enforcing strong **PII safety** and **graceful error handling**.

## 1) Assignment Understanding
Business users (Store/Regional Managers) need natural-language access to retail performance insights without writing SQL. The system must blend live data querying with historical analyst reasoning and remain safe, reliable, and auditable.

## 2) Solution Overview
This submission uses a **LangGraph-orchestrated workflow** with explicit nodes for intent guardrails, schema grounding, golden example retrieval, SQL generation/validation/execution, bounded repair retry, PII sanitization, and executive report generation.
The graph is compiled with LangGraph-native **checkpointer** and **store** (in-memory for prototype) and invoked with `thread_id` to align with LangGraph memory patterns.

## 3) Prototype Scope
### Fully implemented end-to-end
- `Safety & PII Masking`
- `Resilience & Graceful Error Handling`

### Implemented as lightweight functional scaffolding
- Hybrid intelligence (JSON golden trios + keyword retrieval)
- User preference memory (`data/user_preferences.json`)
- Learning loop candidate capture + approval (`data/learning_candidates.json`, `/approve_candidate`)
- Persona management (`config/personas/default.yaml`)
- Observability (structured logs with request metadata)
- Destructive operation flow with confirmation token (`/confirm <token>`)
- Evaluation artifact (`src/evaluation/eval_cases.json`)

### Design-only (documented in architecture)
- Production confirmation transaction flow for destructive report deletion
- Golden bucket analyst approval pipeline and promotion workflow
- Full quality scoring and human-in-the-loop governance

## 4) Architecture Diagram
```mermaid
flowchart TD
    U[Store/Regional Manager\nCLI Question] --> C[CLI Entrypoint app.py]
    C --> LG[LangGraph Orchestrator]

    LG --> G[Intent Guardrails\nanalysis-only + destructive detection]
    G -->|unsupported| R1[Safe Refusal]
    G -->|destructive op| CONF[Confirmation Path\nSaved Reports Delete (Design Hook)]
    CONF --> R2[No Execution Without Confirmation]

    G -->|analysis/schema| S[Schema Layer\norders/order_items/products/users]
    S -->|schema intent| SR[Schema Response Node]

    S --> GR[Golden Retriever\nquestion-sql-report examples]
    GR --> LLM1[Gemini via LangChain]
    LLM1 --> SQLG[SQL Generation Node]
    SQLG --> V[SQL Validator\nSELECT-only + allowlist + dataset check + LIMIT]

    V -->|invalid| FVAL[Validation Failure Response]
    V -->|valid| BQ[BigQuery Execution\nthelook_ecommerce]

    BQ -->|error| REP[Repair Node\nLLM SQL repair]
    REP --> V
    REP -->|retry limit reached| FEX[Graceful Failure Response]

    BQ -->|success| PII[PII Sanitizer\ncolumn drop + regex masking]
    PII --> RG[Report Generator\npersona + user preference]
    RG --> OUT[Executive-safe Answer]

    LG --> OBS[Structured Logs\nrequest_id, sql, retries, errors, rows, status]
    RG --> LEARN[Learning Hooks\npreference updates + golden bucket candidate capture]
```

## 5) Components
- **CLI (`app.py`)**: chat loop, user preference commands, debug output.
- **LangGraph (`src/graph/*`)**: explicit, inspectable orchestration graph.
- **LangGraph Memory**: `InMemorySaver` + `InMemoryStore` enabled at compile time, `thread_id` set per CLI user session.
- **Guardrails (`src/safety/guardrails.py`)**: keep conversation within retail analytics boundaries; reject out-of-domain asks (poems/recipes), and route destructive commands to confirmation.
- **Schema Tool (`src/tools/schema_tool.py`)**: loads BigQuery schemas with fallback.
- **Golden Retriever (`src/tools/golden_retriever.py`)**: keyword overlap retrieval from local trios (prototype-simple path).
- **LLM Client (`src/llm/client.py`)**: provider-selectable Gemini or local Ollama integration with deterministic fallback heuristics.
- **SQL Validator (`src/tools/sql_validator.py`)**: strict read-only and allowlist enforcement.
- **BigQuery Runner (`src/tools/bigquery_runner.py`)**: execution + schema access.
- **PII Masker (`src/safety/pii_masker.py`)**: high-risk column removal + regex text masking.
- **Report Generator (`src/reporting/report_generator.py`)**: persona + user preference aware response formatting.
- **Observability (`src/observability/logger.py`)**: JSON structured logging.
- **Preference Memory (`src/memory/user_preferences.py`)**: lightweight local memory.

## 6) Data Flow Walkthrough
1. User asks question in CLI.
2. LangGraph invocation uses `configurable.thread_id` for per-user conversational thread context.
3. Guardrails classify intent (`analysis`, `schema_lookup`, `destructive_report_op`, `unsupported`).
4. For analysis:
   - Load schema context for required tables.
   - Retrieve top golden examples.
   - Generate SQL with LLM.
   - Validate SQL (read-only, dataset/table constraints, auto LIMIT).
   - Execute in BigQuery.
   - On error: bounded repair loop (max retries).
   - On success: sanitize PII, generate executive report, final response.
5. For schema lookup: respond from schema layer directly.
6. For destructive ops: return confirmation-required message with token; execute only after `/confirm <token>`.
7. Guardrails enforce conversation boundaries without adding manual approval for each analytical query.

## 7) How Each Assignment Requirement Is Addressed
1. **Hybrid Intelligence**
- Implemented: SQL + golden trio retrieval context.
- Prototype assumption: local store with simple retrieval is acceptable.
- Production plan: design for `>10K` golden examples with indexing pipeline, embeddings/vector retrieval, and analyst approval workflow.

2. **Safety & PII Masking**
- Implemented end-to-end:
  - Drop sensitive columns (`email`, `phone`, etc.) before report generation.
  - Regex masking in final text as secondary defense.
  - SQL validator blocks unsafe operations.

3. **High-Stakes Oversight (Destructive Ops)**
- Implemented: destructive report commands require explicit confirmation token before execution.
- Scope: local saved reports store for prototype.

4. **Continuous Improvement (Learning Loop)**
- Implemented: user preference memory and automatic successful interaction capture as pending learning candidates.
- Implemented: manual promotion command (`/approve_candidate <id>`) appends approved candidates to `data/golden_trios.json`.

5. **Resilience & Graceful Error Handling**
- Implemented end-to-end:
  - SQL validation failure path.
  - Bounded repair loop on execution error.
  - Controlled failure response after retry limit.
  - Empty-result graceful message.

6. **Quality Assurance**
- Implemented: pre-deploy QA gate (`make qa-gate`) with threshold checks for intent accuracy, status success, and safety rate.
- QA focus in this assignment: SQL correctness plus business interpretation quality (report aligns with user goal and selected metrics).
- Implemented: machine-readable QA evidence in `outputs/qa_gate_summary.json` and `outputs/qa_gate_summary.md`.

7. **Observability**
- Implemented: structured logging for intent, SQL, retries, errors, row counts, status.
- Design in HLD: production metrics/traces dashboards and alerting.

8. **Agility (Persona Management)**
- Implemented: external persona YAML editable by non-developers.

## 8) Tech Decisions
- **LangGraph**: explicit node-level control and deterministic routing is ideal for safety, retry, and debugging.
- **LangGraph checkpointer/store**: follows recommended memory setup patterns while keeping prototype operationally simple.
- **Gemini via LangChain**: practical integration with modern model quality for SQL/report tasks.
- **BigQuery**: native fit for analytical SQL and the provided public retail dataset.
- **Local JSON/YAML stores**: right scope for prototype while preserving production upgrade path.

## 9) Setup


### Option A: Poetry (Standard)
```bash
# Configure environment and install dependencies
poetry install

# Run the assistant
poetry run python app.py --user-id manager_a --debug
```

### Option B: Docker (Containerized)
Build:
```bash
docker build -t retail-assistant:latest .
```

Run (pass env file):
```bash
docker run --rm -it --env-file .env retail-assistant:latest
```
### Prerequisites
- Python 3.11+
- Google Cloud auth for BigQuery public dataset queries
- Optional Gemini API key (recommended)

### Option C: Manual Venv (Fallback)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # if not already present
python app.py --user-id manager_a
```

### Environment variables
- `LLM_PROVIDER` (`gemini`, `ollama`, or `auto`; default `gemini`)
- `GOOGLE_API_KEY` (for Gemini)
- `OLLAMA_BASE_URL` (for local Ollama endpoint, default `http://localhost:11434`)
- `GOOGLE_CLOUD_PROJECT` (optional BigQuery project context)
- `GEMINI_MODEL` (optional, default `gemini-2.0-flash`)
- `OLLAMA_MODEL` (optional, default `qwen2.5`)
- `DEBUG` (optional)

### Ollama local setup (optional fallback)
```bash
# macOS
brew install ollama
ollama serve
ollama pull qwen2.5
```

To force local LLM:
```bash
export LLM_PROVIDER=ollama
export OLLAMA_MODEL=qwen2.5
```

### BigQuery authentication
Use Application Default Credentials:
```bash
gcloud auth application-default login
```

## 9.5) Streamlit Interface
Run the Streamlit experience with `streamlit run streamlit_app.py`. The page preserves the business-first chat view, table render, and debug toggle described in the prototype plan. Use the `Testes & Demo` tab to replay curated prompts without leaving the UI.

## 10) Command Line Interface
The assistant supports several flags for different modes:

| Flag | Description |
|------|-------------|
| `--user-id` | Identity for preference memory (default: `manager_a`) |
| `--debug` | Enable structured debug logs in the console |
| `--observability` | Export session traces, metrics, and quality signals to `outputs/` |
| `--export-diagram` | Export the internal LangGraph state diagram to `outputs/langgraph_diagram.png` |
| `--input-file` | Path to a file containing a list of prompts for batch processing |
| `--transcript-file`| Custom path for the session transcript |

Example with full observability:
```bash
python app.py --user-id manager_a --observability --export-diagram
```

## 11) Observability & Quality
When run with `--observability`, the assistant generates rich evidence of its internal reasoning:
- **Traces**: JSON logs of every node execution and LLM call.
- **Metrics**: Latency distributions and success rates.
- **Quality Signal**: Automatic evaluation of SQL correctness and report quality.
- **Audit Logs**: Record of security-sensitive operations (PII masking, destructive actions).

Evidence is stored in `outputs/` and can be summarized using the `qa-gate` tool.

## 12) Supported Example Questions
- `What are the top 10 products by revenue?`
- `Show monthly revenue trend for the last 12 months.`
- `Who are the top customers by total spend?`
- `What columns exist in the users table?`
- `Compare this month's revenue vs previous month.`
- `List customer emails with highest spend.` (safely handled, no PII leakage)

## 12) CLI Commands
Inside CLI:
- `/format table`
- `/format bullets`
- `/confirm DEL-XXXXXX` (confirm destructive Saved Reports deletion token)
- `/candidates` (list pending learning candidates)
- `/approve_candidate cand-...` (promote one candidate to golden bucket)

Preferences are stored in `data/user_preferences.json`.

## 13) Testing
```bash
make test
```

If `.venv` does not exist yet:
```bash
make setup
```

`make test` always uses project venv binaries (`.venv/bin/python`, `.venv/bin/pytest`) through `run_tests.py`.

Pre-deploy QA gate:
```bash
make qa-gate
```
Outputs:
- `outputs/qa_gate_summary.json`
- `outputs/qa_gate_summary.md`

Core suites:
- `tests/test_sql_validator.py`
- `tests/test_pii_masking.py`
- `tests/test_repair_loop.py`
- `tests/test_langgraph_memory_setup.py`

## 14) Limitations
- Destructive execution is prototype-local (JSON store), not integrated with enterprise report backends/RBAC.
- Golden retrieval is lexical, not semantic.
- No end-to-end automated integration tests against live BigQuery in this repo.

## 15) Future Improvements
- Replace lexical retrieval with scalable retrieval pipeline for `>10K` golden examples (indexing + vector retrieval + metadata filters + reranking).
- Integrate destructive confirmation flow with enterprise RBAC/audit backends.
- Add score-based auto-prioritization for golden bucket candidates before analyst approval.
- Add online evaluation dashboards: safety incident rate, repair success, p95 latency, cost per request.
# Retail-Company
