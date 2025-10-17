import re
import time
import json
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from sqlalchemy.sql import select
import sqlglot
from app.core.database import SessionLocal
from app.models.nlq_query import NLQQuery

class NLQService:
    """Service for safe natural language to SQL conversion with security guardrails."""

    # Schema whitelist - only allow these tables and columns
    ALLOWED_SCHEMA = {
        "transactions": [
            "id", "transaction_date", "vendor_id", "amount", "category",
            "normalized_description", "raw_description", "source", "statement_id",
            "created_at", "updated_at"
        ],
        "vendors": [
            "id", "name", "normalized_name", "embedding", "created_at", "updated_at"
        ],
        "statements": [
            "id", "source_file", "period_start", "period_end",
            "account_type", "processed_at", "created_at"
        ],
        "anomalies": [
            "id", "transaction_id", "anomaly_type", "severity", "description",
            "expected_value", "actual_value", "confidence", "detected_at",
            "resolved_at", "notes"
        ],
        "nlq_queries": [
            "id", "user_query", "generated_sql", "parameters", "execution_time_ms",
            "result_count", "error_message", "executed_successfully", "created_at"
        ]
    }

    # Allowed SQL functions and operators
    ALLOWED_FUNCTIONS = [
        "SUM", "COUNT", "AVG", "MIN", "MAX", "DATE_TRUNC", "EXTRACT",
        "UPPER", "LOWER", "LENGTH", "COALESCE", "ABS", "ROUND"
    ]

    # Common query templates for better SQL generation
    QUERY_TEMPLATES = {
        "total_spend": "SELECT SUM(amount) as total FROM transactions WHERE amount < 0 AND {date_filter}",
        "total_income": "SELECT SUM(amount) as total FROM transactions WHERE amount > 0 AND {date_filter}",
        "spend_by_month": "SELECT DATE_TRUNC('month', transaction_date) as month, SUM(amount) as total FROM transactions WHERE amount < 0 AND {date_filter} GROUP BY month ORDER BY month",
        "income_by_month": "SELECT DATE_TRUNC('month', transaction_date) as month, SUM(amount) as total FROM transactions WHERE amount > 0 AND {date_filter} GROUP BY month ORDER BY month",
        "top_vendors": "SELECT v.name, SUM(t.amount) as total FROM transactions t JOIN vendors v ON t.vendor_id = v.id WHERE t.amount < 0 AND {date_filter} GROUP BY v.id, v.name ORDER BY total ASC LIMIT {limit}",
        "spend_by_category": "SELECT category, SUM(amount) as total FROM transactions WHERE amount < 0 AND category IS NOT NULL AND {date_filter} GROUP BY category ORDER BY total ASC",
        "transaction_count": "SELECT COUNT(*) as count FROM transactions WHERE {date_filter}",
        "average_transaction": "SELECT AVG(amount) as average FROM transactions WHERE {date_filter}",
        "recent_transactions": "SELECT t.*, v.name as vendor_name FROM transactions t LEFT JOIN vendors v ON t.vendor_id = v.id WHERE {date_filter} ORDER BY t.transaction_date DESC LIMIT {limit}",
        "anomalies_count": "SELECT COUNT(*) as count FROM anomalies WHERE {date_filter}",
        "unresolved_anomalies": "SELECT a.*, t.amount, v.name as vendor_name FROM anomalies a JOIN transactions t ON a.transaction_id = t.id LEFT JOIN vendors v ON t.vendor_id = v.id WHERE a.resolved_at IS NULL AND {date_filter} ORDER BY a.detected_at DESC"
    }

    def __init__(self, db: Session = None):
        self.db = db or SessionLocal()

    def _validate_sql_safety(self, sql: str) -> Tuple[bool, str]:
        """Validate that SQL only uses whitelisted tables, columns, and functions."""
        try:
            # Parse SQL using sqlglot
            parsed = sqlglot.parse(sql)
            if not parsed:
                return False, "Failed to parse SQL"

            # Check each parsed statement
            for statement in parsed:
                if not isinstance(statement, sqlglot.expressions.Select):
                    return False, "Only SELECT statements are allowed"

                # Check for dangerous operations
                if self._contains_dangerous_operations(statement):
                    return False, "SQL contains disallowed operations"

                # Validate table and column references
                if not self._validate_table_references(statement):
                    return False, "SQL references disallowed tables or columns"

                # Validate function usage
                if not self._validate_function_usage(statement):
                    return False, "SQL uses disallowed functions"

        except Exception as e:
            return False, f"SQL validation error: {str(e)}"

        return True, "SQL is safe"

    def _contains_dangerous_operations(self, statement) -> bool:
        """Check for dangerous SQL operations."""
        sql_str = str(statement).upper()

        # Check for DDL/DML operations
        dangerous_keywords = [
            "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER",
            "TRUNCATE", "EXEC", "EXECUTE", "UNION", "UNION ALL"
        ]

        return any(keyword in sql_str for keyword in dangerous_keywords)

    def _validate_table_references(self, statement) -> bool:
        """Validate that all table and column references are whitelisted."""
        def check_references(node):
            if isinstance(node, sqlglot.expressions.Table):
                table_name = node.name.lower()
                if table_name not in self.ALLOWED_SCHEMA:
                    return False
            elif isinstance(node, sqlglot.expressions.Column):
                # Extract table and column names
                if hasattr(node, 'table') and node.table:
                    table_name = node.table.lower()
                    if table_name not in self.ALLOWED_SCHEMA:
                        return False

                if hasattr(node, 'this') and isinstance(node.this, str):
                    column_name = node.this.lower()
                    # If we have a table reference, check the column is allowed for that table
                    if hasattr(node, 'table') and node.table:
                        table_name = node.table.lower()
                        if column_name not in self.ALLOWED_SCHEMA.get(table_name, []):
                            return False
                    else:
                        # If no table specified, check if column exists in any allowed table
                        found = False
                        for table_cols in self.ALLOWED_SCHEMA.values():
                            if column_name in table_cols:
                                found = True
                                break
                        if not found:
                            return False

            # Recursively check child nodes
            for child in node.args.values():
                if isinstance(child, list):
                    for item in child:
                        if hasattr(item, 'args'):
                            if not check_references(item):
                                return False
                elif hasattr(child, 'args'):
                    if not check_references(child):
                        return False

            return True

        return check_references(statement)

    def _validate_function_usage(self, statement) -> bool:
        """Validate that only whitelisted functions are used."""
        def check_functions(node):
            if isinstance(node, sqlglot.expressions.Anonymous):
                func_name = str(node.this).upper()
                if func_name not in self.ALLOWED_FUNCTIONS:
                    return False
            elif isinstance(node, sqlglot.expressions.Func):
                func_name = node.this.upper() if hasattr(node, 'this') else ""
                if func_name not in self.ALLOWED_FUNCTIONS:
                    return False

            # Recursively check child nodes
            for child in node.args.values():
                if isinstance(child, list):
                    for item in child:
                        if hasattr(item, 'args'):
                            if not check_functions(item):
                                return False
                elif hasattr(child, 'args'):
                    if not check_functions(child):
                        return False

            return True

        return check_functions(statement)

    def _generate_date_filter(self, date_from: Optional[datetime] = None,
                             date_to: Optional[datetime] = None) -> str:
        """Generate date filter clause."""
        filters = []

        if date_from:
            filters.append(f"transaction_date >= '{date_from.strftime('%Y-%m-%d')}'")
        if date_to:
            filters.append(f"transaction_date <= '{date_to.strftime('%Y-%m-%d')}'")

        return " AND ".join(filters) if filters else "1=1"

    def _select_query_template(self, query_type: str, parameters: Dict[str, Any]) -> str:
        """Select appropriate query template based on query type."""
        template = self.QUERY_TEMPLATES.get(query_type)
        if not template:
            return None

        # Replace placeholders in template
        date_filter = self._generate_date_filter(
            parameters.get('date_from'),
            parameters.get('date_to')
        )

        sql = template.format(
            date_filter=date_filter,
            limit=parameters.get('limit', 100)
        )

        return sql

    def _classify_query_intent(self, query: str) -> str:
        """Classify query intent to select appropriate template."""
        query_lower = query.lower()

        # Simple keyword-based classification
        if any(word in query_lower for word in ['total', 'sum', 'spend', 'spent']):
            if 'income' in query_lower or 'revenue' in query_lower or 'earned' in query_lower:
                return 'total_income'
            else:
                return 'total_spend'

        if any(word in query_lower for word in ['monthly', 'month', 'trend']):
            if 'income' in query_lower:
                return 'income_by_month'
            else:
                return 'spend_by_month'

        if any(word in query_lower for word in ['vendor', 'merchant', 'company']):
            return 'top_vendors'

        if 'category' in query_lower:
            return 'spend_by_category'

        if any(word in query_lower for word in ['count', 'number', 'how many']):
            return 'transaction_count'

        if 'average' in query_lower:
            return 'average_transaction'

        if any(word in query_lower for word in ['recent', 'latest', 'last']):
            return 'recent_transactions'

        if 'anomal' in query_lower:
            return 'anomalies_count'

        # Default fallback
        return 'recent_transactions'

    def generate_sql(self, query: str, parameters: Dict[str, Any] = None) -> Tuple[str, str]:
        """Generate safe SQL from natural language query."""
        if parameters is None:
            parameters = {}

        # Classify query intent
        intent = self._classify_query_intent(query)

        # Try to use template first
        template_sql = self._select_query_template(intent, parameters)
        if template_sql:
            # Validate the template-generated SQL
            is_safe, error_msg = self._validate_sql_safety(template_sql)
            if is_safe:
                return template_sql, intent

        # If template doesn't work or isn't safe, generate custom SQL
        # For now, we'll use a simple approach - in a real implementation,
        # this would use an LLM to generate SQL based on the schema whitelist

        # Fallback: use a safe default query
        default_sql = f"""
            SELECT t.*, v.name as vendor_name
            FROM transactions t
            LEFT JOIN vendors v ON t.vendor_id = v.id
            WHERE {self._generate_date_filter(parameters.get('date_from'), parameters.get('date_to'))}
            ORDER BY t.transaction_date DESC
            LIMIT {parameters.get('limit', 50)}
        """

        is_safe, error_msg = self._validate_sql_safety(default_sql)
        if not is_safe:
            raise ValueError(f"Generated SQL failed safety check: {error_msg}")

        return default_sql, "custom"

    def execute_query(self, query: str, parameters: Dict[str, Any] = None) -> Dict[str, Any]:
        """Execute a validated SQL query and return results."""
        start_time = time.time()

        try:
            # Generate and validate SQL
            sql, intent = self.generate_sql(query, parameters or {})

            # Execute the query
            result = self.db.execute(text(sql))
            rows = result.fetchall()
            columns = result.keys()

            # Convert to list of dicts
            results = [
                dict(zip(columns, row))
                for row in rows
            ]

            execution_time = (time.time() - start_time) * 1000

            # Log the query
            nlq_query = NLQQuery(
                user_query=query,
                generated_sql=sql,
                parameters=json.dumps(parameters or {}),
                execution_time_ms=execution_time,
                result_count=len(results),
                executed_successfully=True
            )
            self.db.add(nlq_query)
            self.db.commit()

            return {
                "success": True,
                "sql": sql,
                "intent": intent,
                "results": results,
                "execution_time_ms": execution_time,
                "result_count": len(results)
            }

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000

            # Log the failed query
            nlq_query = NLQQuery(
                user_query=query,
                generated_sql=getattr(e, 'sql', ''),
                parameters=json.dumps(parameters or {}),
                execution_time_ms=execution_time,
                error_message=str(e),
                executed_successfully=False
            )
            self.db.add(nlq_query)
            self.db.commit()

            return {
                "success": False,
                "error": str(e),
                "execution_time_ms": execution_time
            }

    def get_query_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent query history."""
        queries = self.db.query(NLQQuery).order_by(
            NLQQuery.created_at.desc()
        ).limit(limit).all()

        return [
            {
                "id": str(q.id),
                "user_query": q.user_query,
                "generated_sql": q.generated_sql,
                "execution_time_ms": q.execution_time_ms,
                "result_count": q.result_count,
                "executed_successfully": q.executed_successfully,
                "created_at": q.created_at.isoformat(),
                "error_message": q.error_message
            }
            for q in queries
        ]

    def __del__(self):
        """Cleanup database session."""
        if hasattr(self, 'db') and self.db:
            self.db.close()
