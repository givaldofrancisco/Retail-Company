from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.llm.prompts import build_repair_prompt, build_report_prompt, build_sql_prompt

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except Exception:  # pragma: no cover - import environment dependent
    ChatGoogleGenerativeAI = None

try:
    from langchain_ollama import ChatOllama
except Exception:  # pragma: no cover - import environment dependent
    ChatOllama = None




@dataclass
class LLMClient:
    model_name: str = "gemini-2.0-flash"
    temperature: float = 0.1

    def __post_init__(self) -> None:
        self.provider = os.getenv("LLM_PROVIDER", "gemini").lower()
        self._client: Optional[Any] = None
        self.enabled = False
        # Set True when we have to use heuristic fallback for any reason
        # (provider disabled or provider call failed).
        self.used_fallback = False

        if self.provider in {"gemini", "auto"}:
            self.enabled = self._try_init_gemini()
            if self.enabled:
                return

        if self.provider in {"ollama", "local", "auto"}:
            self.enabled = self._try_init_ollama()

    def _try_init_gemini(self) -> bool:
        if not bool(os.getenv("GOOGLE_API_KEY")) or ChatGoogleGenerativeAI is None:
            return False
        model = os.getenv("GEMINI_MODEL", self.model_name or "gemini-2.0-flash")
        # Disable provider retries to avoid long hangs on 429 and fall back quickly.
        self._client = ChatGoogleGenerativeAI(
            model=model,
            temperature=self.temperature,
            retries=0,
        )
        self.provider = "gemini"
        return True

    def _try_init_ollama(self) -> bool:
        if ChatOllama is None:
            return False
        model = os.getenv("OLLAMA_MODEL", self.model_name or "qwen2.5")
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self._client = ChatOllama(
            model=model,
            temperature=self.temperature,
            base_url=base_url,
        )
        self.model_name = model
        self.provider = "ollama"
        return True


    def generate_sql(self, question: str, schemas: Dict[str, Any], golden_examples: List[Dict[str, Any]]) -> str:
        if not self.enabled:
            self.used_fallback = True
            return self._heuristic_sql(question)
        prompt = build_sql_prompt(question=question, schemas=schemas, golden_examples=golden_examples)
        generated = self._safe_invoke(prompt)
        if generated:
            return generated
        self.used_fallback = True
        return self._heuristic_sql(question)

    def repair_sql(
        self,
        question: str,
        failed_sql: str,
        error_message: str,
        schemas: Dict[str, Any],
        golden_examples: List[Dict[str, Any]],
    ) -> str:
        if not self.enabled:
            self.used_fallback = True
            return self._heuristic_sql(question)
        prompt = build_repair_prompt(
            question=question,
            failed_sql=failed_sql,
            error_message=error_message,
            schemas=schemas,
            golden_examples=golden_examples,
        )
        repaired = self._safe_invoke(prompt)
        if repaired:
            return repaired
        self.used_fallback = True
        return self._heuristic_sql(question)

    def generate_report(
        self,
        question: str,
        row_count: int,
        data_preview: List[Dict[str, Any]],
        persona_text: str,
        preference_format: str,
        golden_examples: List[Dict[str, Any]],
    ) -> str:
        if not self.enabled:
            self.used_fallback = True
            return self._heuristic_report(question, row_count, data_preview)

        prompt = build_report_prompt(
            question=question,
            row_count=row_count,
            data_preview=data_preview,
            persona_text=persona_text,
            preference_format=preference_format,
            golden_examples=golden_examples,
        )
        report = self._safe_invoke(prompt)
        if report:
            return report
        self.used_fallback = True
        return self._heuristic_report(question, row_count, data_preview)

    def _safe_invoke(self, prompt: str) -> Optional[str]:
        try:
            response = self._client.invoke(prompt)
            return str(response.content).strip()
        except Exception as exc:  # pragma: no cover - depends on external API failures
            logging.getLogger(__name__).warning(
                "LLM invoke failed; using fallback behavior: %s",
                str(exc),
            )
            return None

    def _heuristic_sql(self, question: str) -> str:
        q = question.lower()
        if (
            ("top" in q or "principais" in q or "melhores" in q)
            and ("product" in q or "products" in q or "produto" in q or "produtos" in q)
            and ("revenue" in q or "receita" in q)
        ):
            return (
                "SELECT p.id, p.name, ROUND(SUM(oi.sale_price), 2) AS revenue "
                "FROM bigquery-public-data.thelook_ecommerce.order_items oi "
                "JOIN bigquery-public-data.thelook_ecommerce.orders o ON oi.order_id = o.order_id "
                "JOIN bigquery-public-data.thelook_ecommerce.products p ON oi.product_id = p.id "
                "GROUP BY p.id, p.name ORDER BY revenue DESC LIMIT 10"
            )
        if ("monthly" in q or "mensal" in q or "mês" in q or "mes" in q) and (
            "revenue" in q or "receita" in q
        ):
            return (
                "SELECT FORMAT_DATE('%Y-%m', DATE(o.created_at)) AS month, ROUND(SUM(oi.sale_price), 2) AS revenue "
                "FROM bigquery-public-data.thelook_ecommerce.order_items oi "
                "JOIN bigquery-public-data.thelook_ecommerce.orders o ON oi.order_id = o.order_id "
                "WHERE DATE(o.created_at) >= DATE_SUB(CURRENT_DATE(), INTERVAL 12 MONTH) "
                "GROUP BY month ORDER BY month"
            )
        if ("top" in q or "principais" in q or "melhores" in q) and (
            "customer" in q or "customers" in q or "cliente" in q or "clientes" in q
        ):
            return (
                "SELECT u.id AS customer_id, ROUND(SUM(oi.sale_price), 2) AS total_spend "
                "FROM bigquery-public-data.thelook_ecommerce.users u "
                "JOIN bigquery-public-data.thelook_ecommerce.orders o ON u.id = o.user_id "
                "JOIN bigquery-public-data.thelook_ecommerce.order_items oi ON o.order_id = oi.order_id "
                "GROUP BY customer_id ORDER BY total_spend DESC LIMIT 10"
            )
        if ("users" in q or "usuários" in q or "usuarios" in q) and (
            "column" in q or "columns" in q or "coluna" in q or "colunas" in q
        ):
            return (
                "SELECT column_name, data_type "
                "FROM bigquery-public-data.thelook_ecommerce.INFORMATION_SCHEMA.COLUMNS "
                "WHERE table_name = 'users' ORDER BY ordinal_position"
            )
        if ("compare" in q or "compar" in q) and ("month" in q or "mês" in q or "mes" in q) and (
            "revenue" in q or "receita" in q
        ):
            return (
                "WITH monthly AS ("
                "SELECT FORMAT_DATE('%Y-%m', DATE(o.created_at)) AS month, SUM(oi.sale_price) AS revenue "
                "FROM bigquery-public-data.thelook_ecommerce.order_items oi "
                "JOIN bigquery-public-data.thelook_ecommerce.orders o ON oi.order_id = o.order_id "
                "WHERE DATE(o.created_at) >= DATE_SUB(CURRENT_DATE(), INTERVAL 2 MONTH) "
                "GROUP BY month) "
                "SELECT month, ROUND(revenue, 2) AS revenue FROM monthly ORDER BY month"
            )

        return (
            "SELECT DATE(o.created_at) AS order_date, ROUND(SUM(oi.sale_price), 2) AS revenue "
            "FROM bigquery-public-data.thelook_ecommerce.order_items oi "
            "JOIN bigquery-public-data.thelook_ecommerce.orders o ON oi.order_id = o.order_id "
            "WHERE DATE(o.created_at) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY) "
            "GROUP BY order_date ORDER BY order_date DESC"
        )

    @staticmethod
    def _heuristic_report(question: str, row_count: int, data_preview: List[Dict[str, Any]]) -> str:
        if row_count == 0:
            return "No matching data was found for this question. Consider broadening filters or the date range."
        top = data_preview[0] if data_preview else {}
        return (
            f"Question: {question}\n"
            f"Rows analyzed: {row_count}\n"
            f"Top row snapshot: {top}\n"
            "Summary: Results are generated from validated read-only SQL over approved retail tables."
        )
