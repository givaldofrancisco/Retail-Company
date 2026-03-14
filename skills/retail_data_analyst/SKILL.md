---
name: Retail Data Analyst
description: Expert guidelines and resources for building the Retail Company internal data agent, specializing in technical design, safety, and SQL-based insights.
---

# Retail Data Analyst Skill

This skill provides the comprehensive design principles, architectural patterns, and technical requirements for the Retail Data Analysis Chat Assistant project.

## 1. Project Overview
Building an internal data agent for non-technical executives (Store and Regional Managers) to query sales, inventory, and performance data from BigQuery (`bigquery-public-data.thelook_ecommerce`).

## 2. Core Requirements

### Hybrid Intelligence & "Golden Bucket"
- **Pattern**: Combine SQL generation with a "Golden Knowledge" bucket of (Question → SQL → Report) trios.
- **Logic**: Use past analyst interpretations to inform new queries.
- **Update Loop**: As new high-quality reports are generated, they should be reviewed and added to the "Golden Bucket."

### Safety & PII Masking
- **Strict Prohibition**: Never display Customer Phones or Emails in final outputs.
- **Filtering**: Use LLM-based post-processing or programmatic masking even if SQL retrieves PII.
- **Domain Guardrails**: Only answer analysis questions; refuse off-topic prompts.

### High-Stakes Oversight (GDPR)
- **Destructive Actions**: Requests like "Delete all reports mentioning Client X" require a strict confirmation flow.
- **Workflow**:
    1. Identify reports to delete.
    2. Present a summary of what will be deleted.
    3. Explicit user confirmation (Yes/No).
    4. Execution + Confirmation log.

### Continuous Improvement
- **User Personas**: Store preferences (e.g., Manager A likes tables; Manager B likes bullets).
- **System Memory**: Use conversation history or vector storage to learn from past interactions.

## 3. Technical Architecture
Use the provided `architecture.mermaid` as a reference for components:
- **UI**: Simple CLI or Chat Interface.
- **Orchestration**: LangGraph (preferred) or LangChain V1.
- **Database**: BigQuery (`BigQueryRunner` in `scripts/bq_client.py`).

## 4. Resilience & Observability
- **Self-Correction**: Detect SQL syntax errors or empty returns; attempt a retry with corrected logic.
- **Metrics**: Track query latency, LLM cost, success/fail rates, and self-correction volume.
- **Deep Dive**: Maintain logs of (User Message → Generated SQL → DB Return → Final Answer) for debugging.

## 5. Persona & Agility
- **System Instruction**: Store the "persona" or "tone" separately from the code.
- **Dynamic Updates**: Enable non-developers to update instructions via a configuration file (e.g., `config.yaml` or a GCP Secret) without redeploying.
