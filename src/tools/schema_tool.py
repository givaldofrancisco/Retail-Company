from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from src.observability.logger import get_logger, log_event
from src.tools.bigquery_runner import BigQueryRunner


logger = get_logger(__name__)


FALLBACK_SCHEMAS: Dict[str, List[dict]] = {
    "orders": [
        {"name": "order_id", "type": "INTEGER"},
        {"name": "user_id", "type": "INTEGER"},
        {"name": "created_at", "type": "TIMESTAMP"},
        {"name": "status", "type": "STRING"},
    ],
    "order_items": [
        {"name": "order_id", "type": "INTEGER"},
        {"name": "product_id", "type": "INTEGER"},
        {"name": "sale_price", "type": "FLOAT"},
        {"name": "created_at", "type": "TIMESTAMP"},
    ],
    "products": [
        {"name": "id", "type": "INTEGER"},
        {"name": "name", "type": "STRING"},
        {"name": "category", "type": "STRING"},
        {"name": "retail_price", "type": "FLOAT"},
    ],
    "users": [
        {"name": "id", "type": "INTEGER"},
        {"name": "email", "type": "STRING"},
        {"name": "phone_number", "type": "STRING"},
        {"name": "created_at", "type": "TIMESTAMP"},
    ],
}


@dataclass
class SchemaTool:
    runner: BigQueryRunner
    tables: List[str]

    def fetch(self) -> Dict[str, List[dict]]:
        schemas: Dict[str, List[dict]] = {}
        for table in self.tables:
            try:
                schemas[table] = self.runner.get_table_schema(table)
            except Exception as exc:
                log_event(logger, "schema_fallback", table=table, error=str(exc))
                schemas[table] = FALLBACK_SCHEMAS.get(table, [])
        return schemas
