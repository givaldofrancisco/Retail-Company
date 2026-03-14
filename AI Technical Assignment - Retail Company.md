AI Technical Assignment - Retail Company 

The Challenge: Design and Build a Data Analysis Chat Assistant

You are building an internal data agent for a Retail Company's non-technical executive team (Store and Regional Managers). These managers need to ask complex questions about sales, inventory, and performance (e.g., "Why is the Tel Aviv branch underperforming?")
The agent will have access to:

* The Database: A read-only connection to a SQL database containing raw transaction logs.
* The "Golden Knowledge" Bucket: A data lake containing historical "Trios" (Question → SQL Query → Analyst Report) created by human experts.

The Task: Design a production-ready full High-Level Design (HLD), accompanied by a detailed technical explanation, and build a prototype that allows executives to query this data naturally.

Requirements:

1. Hybrid Intelligence: The agent cannot rely on SQL alone. It must use the "Golden Bucket" to understand how analysts previously interpreted questions and apply similar logic to new queries. Explain how you will update the golden bucket over time.

2. Safety & PII Masking: The raw transaction logs contain Customer Phones and Emails. The agent is strictly forbidden from displaying this PII in the final output, even if the SQL query retrieves it. Furthermore, it is only allowed to answer analysis questions

3. High-Stakes Oversight (Destructive Ops): While the DB is read-only, the agent manages a "Saved Reports" library. The agent must support commands like "Delete all reports mentioning Client X" (GDPR compliance). This is a destructive action and requires a strict confirmation flow before execution.

4. Continuous Improvement (The Learning Loop):
    1. User Level: The agent should remember that "Manager A" prefers tables while "Manager B" prefers bullet points.
    2. System Level: The agent should be able to learn from past interactions.

5. Resilience & Graceful Error Handling: The system must detect SQL syntax errors or empty returns and attempt to self-correct before giving up, without crashing the user interface and without inflating costs. The system should be resilient to API/3rd party services failures/downtime 

6. Quality Assurance: How do you evaluate the agent before deployment? How do you verify that the generated reports answer users intent correctly?

7. Observability: We need to know when the agent is failing and why. Define the metrics you would track at the agent level and how you would support deep dive analysis (understanding what the message correspondence is and what went wrong).

8. Agility (Persona Management): The CEO wants to change the "tone" of the reports weekly. The system must allow non-developers to update the agent's instructions without redeployment.

 Deliverables:

1. Architecture Diagram (Mermaid etc): Highlighting the building blocks, services and flow of the system based on the requirements above. In case you are planning to use a framework / service for one of the building blocks, specify which one and include an explanation.

2. Detailed technical explanation covering:
    1. Reasoning for the chosen Cloud services / LLM models / frameworks used.
    2. Data flow between components (if needs to elaborate on HLD).
    3. Error handling and fallback strategies.
    4. Setup Instructions and example run
    5. Make sure to include how you handle/solve each of the requirements

3.  Working Code/Prototype: Build a chat agent that can generate and run SQL queries against the DB listed below and create a report. The prototype needs to support 2 of the following requirements (defined above): 
    1. Safety & PII Masking
    2. High-Stakes Oversight
    3. Resilience & Graceful Error Handling
    4. Quality Assurance
    5. Observability

4. Simple CLI-based interface for chat interactions. (UI's won't gain any additional points)

5. Your solution must be runnable on another machine (Docker is not a must, just proper setup instructions).

6. Use a framework of your choice (preferably Lang Graph / Lang Chain V1).

Note: the prototype needs to be simple and working.
Our assessment will focus mainly on system design, the technical explanation, and an elegant Prototype

Dataset Specification:

* Dataset: bigquery-public-data.thelook_ecommerce
* Required Tables:
    * orders - Customer order information
    * order_items - Individual items within orders
    * products - Product catalog and details
    * users - Customer demographics and information

Expected Agent Capabilities:

Your prototype agent should be able to perform data analysis and generate insights such as:

* Customer behavior (e.g., top customers, total spend)
* Product performance
* Time-based metrics (e.g., monthly revenue, up-to-date revenue by product)
* Answer questions about the general structure of the database

1. Use BigQuery integration to query and analyze the specified tables. Your agent should be able to construct and execute SQL queries dynamically based on the analysis requirements.
2. You should preferably use one of the newer Google Gemini models. You can get a free API key from Google AI Studio. Please be mindful of the rate limits. Alternatively, you can use OpenRouter or Ollama if you prefer (or have issues with rate limits) . We have created a simple client for your convenience:  https://github.com/Opsfleet/lc-openrouter-ollama-client

Setup Instructions

Environment Setup

1. Install Python dependencies:

pip install -r requirements.txt

GCP/BigQuery Setup

1. Set up BigQuery access by following the BigQuery Client Libraries documentation if you don't already have BigQuery access configured.
2. Free Tier: Google Cloud provides 1TB of free BigQuery compute per month, which is more than sufficient for this challenge.
3. Authentication: Ensure your environment is authenticated with Google Cloud to access the public datasets.


Time Expectation

We expect this assignment to take between 6 to 12 hours of work.

Submission

Share (make it public or invite us with our emails) with us a your Git repository (GitHub, GitLab, etc) with:

* Documentation
* Source code
* Architecture diagram

Resources

Quick Starts

* https://docs.langchain.com/oss/python/langchain/quickstart
* https://docs.langchain.com/oss/python/langgraph/quickstart
* https://docs.langchain.com/oss/python/langgraph/add-memory




bq_client.py
Owned by Alex Freidman
Created on August 11th, 2025
import logging
from typing import Optional, List, Dict, Any
import pandas as pd
from google.cloud import bigquery
​
​
class BigQueryRunner:
    """A lean BigQuery client for executing SQL queries and returning DataFrame results."""
    
    def __init__(self, project_id: Optional[str] = None, dataset_id: Optional[str] = "bigquery-public-data.thelook_ecommerce") -> None:
        """Initialize BigQuery client.
        
        Args:
            project_id: Google Cloud project ID. If None, uses default credentials.
            dataset_id: BigQuery dataset ID. If None, uses default dataset.
        """
        logging.info("Initializing BigQuery client")
        try:
            self.client = bigquery.Client(project=project_id)
            self.dataset_id = dataset_id
            logging.info(f"BigQuery client initialized for dataset: {self.dataset_id}")
        except Exception as e:
            logging.error(f"Failed to initialize BigQuery client: {str(e)}")
            raise
    
    def execute_query(self, sql_query: str) -> pd.DataFrame:
        """Execute a SQL query and return results as a DataFrame.
        
        Args:
            sql_query: The SQL query to execute.
            
        Returns:
            DataFrame containing the query results.
            
        Raises:
            Exception: If query execution fails.
        """
        try:
            logging.info(f"Executing BigQuery query")
            query_job = self.client.query(sql_query)
            df = query_job.result().to_dataframe()
            logging.info(f"Query completed successfully, returned {len(df)} rows")
            return df
        except Exception as e:
            logging.error(f"BigQuery execution failed: {str(e)}")
            raise 
​
    def get_table_schema(self, table_name: str) -> List[Dict[str, Any]]:
        """Get schema information for a specific table.
        
        Args:
            table_name: Name of the table (orders, order_items, products, users).
            
        Returns:
            List of dictionaries containing column information.
        """
        try:
            table_ref = f"{self.dataset_id}.{table_name}"
            table = self.client.get_table(table_ref)
            schema_info = []
            for field in table.schema:
                schema_info.append({
                    "name": field.name,
                    "type": field.field_type,
                    "mode": field.mode,
                    "description": field.description or ""
                })
            logging.info(f"Retrieved schema for table {table_name}")
            return schema_info
        except Exception as e:
            logging.error(f"Failed to get schema for table {table_name}: {str(e)}")
            raise     