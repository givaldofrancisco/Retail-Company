from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import pandas as pd
from google.cloud import bigquery


class BigQueryExecutionError(RuntimeError):
    pass


class BigQueryRunner:
    """Lean BigQuery client for SQL execution and schema retrieval."""

    def __init__(
        self,
        project_id: Optional[str] = None,
        dataset_id: str = "bigquery-public-data.thelook_ecommerce",
        location: Optional[str] = None,
    ) -> None:
        self.client = bigquery.Client(project=project_id, location=location)
        self.dataset_id = dataset_id

    def execute_query(self, sql_query: str) -> pd.DataFrame:
        try:
            query_job = self.client.query(sql_query)
            return query_job.result().to_dataframe()
        except Exception as exc:  # pragma: no cover - network/service behavior
            logging.exception("BigQuery execution failed")
            raise BigQueryExecutionError(str(exc)) from exc

    def get_table_schema(self, table_name: str) -> List[Dict[str, Any]]:
        table_ref = f"{self.dataset_id}.{table_name}"
        table = self.client.get_table(table_ref)
        return [
            {
                "name": field.name,
                "type": field.field_type,
                "mode": field.mode,
                "description": field.description or "",
            }
            for field in table.schema
        ]
