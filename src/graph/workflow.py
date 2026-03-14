from __future__ import annotations

from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from src.graph.nodes import WorkflowNodes
from src.graph.state import AgentState


def route_after_intent(state: AgentState) -> str:
    if state.get("intent") in {"unsupported", "destructive_report_op"}:
        return "finalize_response"
    return "load_schema"


def route_after_schema(state: AgentState) -> str:
    if state.get("intent") == "schema_lookup":
        return "generate_schema_response"
    return "retrieve_golden_examples"


def route_after_validate(state: AgentState) -> str:
    if state.get("final_status") == "failed_validation":
        return "finalize_response"
    return "execute_sql"


def route_after_execute(state: AgentState) -> str:
    if state.get("error_message"):
        if state.get("retry_count", 0) < state.get("max_retries", 2):
            return "repair_sql"
        return "finalize_response"
    return "sanitize_results"


def build_workflow(nodes: WorkflowNodes, checkpointer=None, store=None):
    graph = StateGraph(AgentState)

    graph.add_node("classify_intent", nodes.classify_intent)
    graph.add_node("reject_or_route", nodes.reject_or_route)
    graph.add_node("load_schema", nodes.load_schema)
    graph.add_node("generate_schema_response", nodes.generate_schema_response)
    graph.add_node("retrieve_golden_examples", nodes.retrieve_golden_examples)
    graph.add_node("generate_sql", nodes.generate_sql)
    graph.add_node("validate_sql", nodes.validate_sql)
    graph.add_node("execute_sql", nodes.execute_sql)
    graph.add_node("repair_sql", nodes.repair_sql)
    graph.add_node("sanitize_results", nodes.sanitize_results)
    graph.add_node("generate_report", nodes.generate_report)
    graph.add_node("finalize_response", nodes.finalize_response)

    graph.set_entry_point("classify_intent")
    graph.add_edge("classify_intent", "reject_or_route")
    graph.add_conditional_edges(
        "reject_or_route",
        route_after_intent,
        {
            "load_schema": "load_schema",
            "finalize_response": "finalize_response",
        },
    )

    graph.add_conditional_edges(
        "load_schema",
        route_after_schema,
        {
            "generate_schema_response": "generate_schema_response",
            "retrieve_golden_examples": "retrieve_golden_examples",
        },
    )
    graph.add_edge("generate_schema_response", "finalize_response")

    graph.add_edge("retrieve_golden_examples", "generate_sql")
    graph.add_edge("generate_sql", "validate_sql")

    graph.add_conditional_edges(
        "validate_sql",
        route_after_validate,
        {
            "execute_sql": "execute_sql",
            "finalize_response": "finalize_response",
        },
    )

    graph.add_conditional_edges(
        "execute_sql",
        route_after_execute,
        {
            "repair_sql": "repair_sql",
            "sanitize_results": "sanitize_results",
            "finalize_response": "finalize_response",
        },
    )

    graph.add_edge("repair_sql", "validate_sql")
    graph.add_edge("sanitize_results", "generate_report")
    graph.add_edge("generate_report", "finalize_response")
    graph.add_edge("finalize_response", END)

    if checkpointer is None:
        checkpointer = InMemorySaver()
    if store is None:
        store = InMemoryStore()
    return graph.compile(checkpointer=checkpointer, store=store)
