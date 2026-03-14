# Retail Company Agent Guidelines

This file provides project-specific instructions and rules for AI agents working on the Retail Company project. These rules augment the global agent behavior and focus on safety, quality, and technical design for the Retail Data Analysis assistant.

## Core Rules

### 1. Safety & PII Masking
- **Strict Prohibition**: Never display Customer Phones or Emails in final outputs or logs.
- **Filtering**: Use LLM-based post-processing or programmatic masking even if SQL retrieves PII.
- **Domain Guardrails**: Only answer analysis questions related to the retail dataset; refuse off-topic prompts.

### 2. High-Stakes Oversight (GDPR Compliance)
- **Destructive Actions**: Any command to delete reports or user data requires a strict confirmation flow.
- **Workflow**:
    1. Identify target data.
    2. Present a summary of the impact.
    3. Generate a unique confirmation token.
    4. Explicit user confirmation using `/confirm <token>`.

### 3. Hybrid Intelligence (Golden Bucket)
- **Strategy**: Always check `data/golden_trios.json` for historical Question → SQL → Report examples before generating new queries.
- **Logic**: Apply similar analyst reasoning to new, related questions.

### 4. Technical Design
- **Orchestration**: Use LangGraph for explicit, stateful workflow management.
- **Database**: Target the BigQuery public dataset `bigquery-public-data.thelook_ecommerce`.
- **Validation**: Every SQL query must pass through the `SQLValidator` to ensure it is read-only and limited to allowed tables.

### 5. Resilience & Observability
- **Self-Correction**: Implement bounded retry loops for SQL syntax or execution errors.
- **Logging**: Ensure all significant events (SQL generation, validation, execution, masking) are logged with a `request_id`.

## Context References
- **Skill Definition**: [SKILL.md](Retail Company/skills/retail_data_analyst/SKILL.md)
- **Architecture**: [architecture.md](Retail Company/architecture.md)
- **Main App**: [app.py](Retail Company/app.py)
