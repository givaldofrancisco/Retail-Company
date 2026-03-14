# Architecture (HLD) - Retail Analytics Assistant

## Design Goals
- Deliver executive-friendly analytics from natural language.
- Guarantee strong safety posture (PII + read-only SQL controls).
- Provide deterministic orchestration and debuggable behavior.
- Keep prototype small while preserving clear production evolution.

## Architectural Principles
- **Explicit workflow over opaque agent loops**.
- **Safety layers before and after data access**.
- **Bounded retries and fail-safe defaults**.
- **Structured observability by default**.
- **Configuration-driven tone/persona for non-engineering agility**.

## Major Components
1. CLI Interface (`app.py`)
- Accepts user questions and user-id.
- Supports preference updates (`/format table|bullets`).
- Prints user-safe final response.

2. LangGraph Orchestrator (`src/graph/workflow.py`)
- Nodes: `classify_intent`, `load_schema`, `retrieve_golden_examples`, `generate_sql`, `validate_sql`, `execute_sql`, `repair_sql`, `sanitize_results`, `generate_report`, `finalize_response`.
- Conditional routes for unsupported intent, schema lookup, and repair loop.
- Compiled with `InMemorySaver` (checkpointer) and `InMemoryStore` for LangGraph-native memory wiring in prototype scope.

3. Guardrail Layer (`src/safety/guardrails.py`)
- Keeps conversation within retail analytics boundaries (analysis/schema/admin-destructive).
- Detects destructive report operations and routes to confirmation-required path.
- Rejects out-of-domain requests without adding manual approval on each analytical query.

4. Schema Layer (`src/tools/schema_tool.py`)
- Fetches schema for required tables: `orders`, `order_items`, `products`, `users`.
- Uses fallback schema when API calls fail.

5. Golden Knowledge Retriever (`src/tools/golden_retriever.py`)
- Retrieves prior Question/SQL/Report examples from local bucket.
- Improves SQL/report grounding for related prompts.
- Prototype uses simple retrieval; production path is designed for `>10K` examples.

6. LLM Layer (`src/llm/client.py`)
- Gemini via LangChain for SQL generation, SQL repair, and executive reporting.
- Has deterministic heuristic fallback when model key is unavailable.

7. SQL Safety Layer (`src/tools/sql_validator.py`)
- Enforces SELECT-only.
- Blocks DML/DDL/exec operations.
- Restricts tables to allowlist.
- Enforces expected dataset.
- Appends LIMIT if missing.

8. Query Execution (`src/tools/bigquery_runner.py`)
- Executes validated SQL only against BigQuery.
- Returns DataFrame or controlled execution error.

9. PII Sanitization (`src/safety/pii_masker.py`)
- Removes high-risk columns (email/phone patterns).
- Masks residual PII in text values and final output text.

10. Report Generation (`src/reporting/report_generator.py`)
- Uses persona YAML + user format preference.
- Generates concise manager-ready output.

11. Preference Memory (`src/memory/user_preferences.py`)
- Local JSON preference persistence by user-id.

13. LangGraph Memory Runtime
- `thread_id` is passed via invoke config (`configurable.thread_id`) to isolate conversation state per user session.
- Checkpointer/store are in-memory for prototype; production would replace with durable backing stores.

12. Observability (`src/observability/logger.py`)
- JSON logs containing request_id, question, SQL, retries, row_count, errors, status.

## End-to-End Sequence
1. CLI receives question and creates initial state.
2. CLI invokes graph with `configurable.thread_id=<user_id>:cli`.
3. `classify_intent` labels intent.
4. If unsupported: reject safely.
5. If destructive report command: require confirmation and stop.
6. For schema lookup: load schema and answer directly from metadata.
7. For analysis:
   - load schema
   - retrieve golden examples
   - generate SQL
   - validate SQL
   - execute SQL
   - if execution fails -> repair SQL and retry (bounded)
   - sanitize results for PII
   - generate report with persona + user preference
8. Finalize with safe output and logs.

## Error Handling Model
- SQL validation errors: immediate safe failure (no execution).
- SQL execution errors: bounded repair loop (`max_retries=2` by default).
- Repair exhaustion: graceful user-facing failure (no stack traces).
- Empty results: explicit, helpful explanation.
- Schema API failures: fallback schema context to keep pipeline functional.

## Security Model
- Read-only query policy by validator.
- Strict blocked keyword list (INSERT/UPDATE/DELETE/DROP/ALTER/MERGE/TRUNCATE/CREATE/EXECUTE/CALL).
- Dataset enforcement and table allowlist enforcement.
- PII output control in two layers:
  - data layer (column removal)
  - text layer (regex masking)

## Observability Model
### Prototype logs
- `request_id`
- `user_id`
- `question`
- `intent`
- retrieved golden examples
- generated SQL
- validation/execution errors
- retry count
- row count
- final status

### Production metrics
- SQL generation success rate
- SQL validation failure rate
- repair success rate
- empty result rate
- refusal rate
- PII incident rate
- latency p50/p95
- token/cost per request
- user feedback score
- offline eval quality score

## Learning Loop
### Prototype
- Persist user response format preference.
- Keep historical golden trios in a local JSON bucket.

### Production evolution
- Automatically propose new triads from high-quality sessions.
- Queue for analyst review and approval.
- Promote approved examples to versioned golden knowledge store.
- Use metadata filters by topic/region/time window.
- Add indexing pipeline + vector retrieval + reranking for `>10K` examples.

## Persona Management
- Persona is externalized in YAML (`config/personas/default.yaml`).
- Non-developers can update tone/style safely without code redeploy.
- Weekly CEO direction changes become config-only edits.

## Destructive Operations Confirmation Design (HLD)
Current prototype executes destructive operations only after explicit token confirmation.

Production confirmation design:
1. Detect destructive intent and generate operation summary.
2. Generate short-lived confirmation token + hash of command scope.
3. Require explicit second user confirmation with token.
4. Execute idempotent delete against saved reports library.
5. Audit log actor/time/scope/outcome.
6. Return confirmation receipt.

## QA / Evaluation Approach
Evaluation artifact: `src/evaluation/eval_cases.json`

Dimensions:
- Intent match
- SQL correctness
- Business interpretation correctness
- Safety compliance
- Report usefulness

Priority for this assignment:
- SQL correctness and business interpretation alignment with the user question.

Pre-deploy gates (recommended):
- 0 critical safety failures (PII leaks)
- >=95% intent classification accuracy on benchmark set
- >=90% SQL validity
- >=85% analyst-rated report usefulness

## Production Evolution Path
1. Replace lexical retriever with embeddings + vector DB.
2. Add caching and cost guards for repeated queries.
3. Add full tracing (OpenTelemetry) and centralized dashboarding.
4. Add robust integration test harness with BigQuery dry-run + sampled execution.
5. Implement destructive op confirmation service and RBAC.
