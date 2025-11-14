import re
import time
import json
import os
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from sqlalchemy.sql import select
import sqlglot
from app.core.database import SessionLocal
from app.models.nlq_query import NLQQuery

# LLM imports
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

class NLQService:
    """Service for safe natural language to SQL conversion with security guardrails."""

    # Schema whitelist - only allow these tables and columns
    ALLOWED_SCHEMA = {
        "transactions": [
            "id", "transaction_date", "vendor_id", "amount", "category",
            "normalized_description", "raw_description", "source", "source_type",
            "statement_id", "quickbooks_id", "quickbooks_connection_id",
            "quickbooks_sync_version", "created_at", "updated_at"
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

    # Allowed SQL functions and operators (using sqlglot class names)
    ALLOWED_FUNCTIONS = [
        # Aggregate functions
        "SUM", "COUNT", "AVG", "MIN", "MAX",
        # Date/Time functions
        "DATE_TRUNC", "DATETRUNC", "EXTRACT", "NOW", "CURRENT_DATE", "CURRENTDATE", 
        "CURRENT_TIMESTAMP", "CURRENTTIMESTAMP", "DATE", "INTERVAL",
        # String functions
        "UPPER", "LOWER", "LENGTH", "COALESCE", "TRIM", "CONCAT",
        # Math functions
        "ABS", "ROUND", "FLOOR", "CEIL",
        # Allow both uppercase and PascalCase variants
        "Sum", "Count", "Avg", "Min", "Max",
        "DateTrunc", "Extract", "Now", "CurrentDate", "CurrentTimestamp",
        "Upper", "Lower", "Coalesce", "Abs", "Round", "Trim", "Concat",
        "Floor", "Ceil", "Date", "Interval"
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
        "recent_transactions": "SELECT t.id, t.transaction_date, t.vendor_id, t.amount, t.category, t.normalized_description, v.name FROM transactions t LEFT JOIN vendors v ON t.vendor_id = v.id WHERE {date_filter} ORDER BY t.transaction_date DESC LIMIT {limit}",
        "anomalies_count": "SELECT COUNT(*) as count FROM anomalies WHERE {date_filter}",
        "unresolved_anomalies": "SELECT a.id, a.transaction_id, a.anomaly_type, a.severity, a.description, t.amount, v.name FROM anomalies a JOIN transactions t ON a.transaction_id = t.id LEFT JOIN vendors v ON t.vendor_id = v.id WHERE a.resolved_at IS NULL AND {date_filter} ORDER BY a.detected_at DESC"
    }

    def __init__(self, db: Session = None):
        self.db = db or SessionLocal()
        
        # Initialize LLM clients
        self.openai_client = None
        self.anthropic_client = None
        self.llm_provider = os.getenv("LLM_PROVIDER", "openai").lower()
        
        if OPENAI_AVAILABLE and os.getenv("OPENAI_API_KEY"):
            self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            print("[NLQ Debug] OpenAI client initialized")
        
        if ANTHROPIC_AVAILABLE and os.getenv("ANTHROPIC_API_KEY"):
            self.anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            print("[NLQ Debug] Anthropic client initialized")

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
        # Track table aliases (e.g., t, v, a) and column aliases (e.g., total_spent)
        table_aliases = {}
        column_aliases = set()
        
        def extract_aliases(node, in_select=False):
            """Extract table and column aliases from the query."""
            if isinstance(node, sqlglot.expressions.Table):
                table_name = node.name.lower()
                alias = node.alias if hasattr(node, 'alias') and node.alias else table_name
                if alias:
                    table_aliases[alias.lower()] = table_name
            elif isinstance(node, sqlglot.expressions.Alias) and in_select:
                # Extract column aliases (e.g., SUM(amount) AS total_spent)
                alias_name = str(node.alias).lower() if hasattr(node, 'alias') else ""
                if alias_name:
                    column_aliases.add(alias_name)
                    print(f"[NLQ Debug] Found column alias: {alias_name}")
            elif isinstance(node, sqlglot.expressions.Select):
                # Process SELECT expressions to find aliases
                if hasattr(node, 'expressions'):
                    for expr in node.expressions:
                        extract_aliases(expr, in_select=True)
            
            # Recursively check child nodes
            for child in node.args.values():
                if isinstance(child, list):
                    for item in child:
                        if hasattr(item, 'args'):
                            extract_aliases(item, in_select)
                elif hasattr(child, 'args'):
                    extract_aliases(child, in_select)
        
        # First pass: extract all aliases
        extract_aliases(statement)
        print(f"[NLQ Debug] Table aliases: {table_aliases}")
        print(f"[NLQ Debug] Column aliases: {column_aliases}")
        
        def check_references(node):
            if isinstance(node, sqlglot.expressions.Table):
                table_name = node.name.lower()
                print(f"[NLQ Debug] Checking table: {table_name}")
                if table_name not in self.ALLOWED_SCHEMA:
                    print(f"[NLQ Debug] Table {table_name} not in allowed schema")
                    return False
            elif isinstance(node, sqlglot.expressions.Column):
                # Skip validation for aliased columns (e.g., vendor_name as alias)
                # We only validate the source columns, not the result aliases
                column_name = str(node.this).lower() if hasattr(node, 'this') else ""
                
                # Get table reference (could be alias or actual table name)
                table_ref = None
                if hasattr(node, 'table') and node.table:
                    table_ref = str(node.table).lower()
                    # Resolve alias to actual table name
                    table_name = table_aliases.get(table_ref, table_ref)
                    
                    print(f"[NLQ Debug] Checking column: {table_name}.{column_name}")
                    
                    if table_name not in self.ALLOWED_SCHEMA:
                        print(f"[NLQ Debug] Table {table_name} not in allowed schema")
                        return False
                    
                    # Check if column exists in the table
                    if column_name and column_name not in self.ALLOWED_SCHEMA.get(table_name, []):
                        # Check if it's a wildcard (*)
                        if column_name != '*':
                            print(f"[NLQ Debug] Column {column_name} not in table {table_name}")
                            print(f"[NLQ Debug] Allowed columns: {self.ALLOWED_SCHEMA.get(table_name, [])}")
                            return False
                else:
                    # No table specified, check if column exists in any allowed table OR is an alias
                    if column_name and column_name != '*':
                        print(f"[NLQ Debug] Checking unqualified column: {column_name}")
                        
                        # Check if it's a column alias (e.g., total_spent in ORDER BY)
                        if column_name in column_aliases:
                            print(f"[NLQ Debug] Column {column_name} is an alias, skipping validation")
                            return True
                        
                        found = False
                        for table_cols in self.ALLOWED_SCHEMA.values():
                            if column_name in table_cols:
                                found = True
                                break
                        if not found:
                            print(f"[NLQ Debug] Unqualified column {column_name} not found in any table")
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
        # Operators and predicates that should be ignored (not actual functions)
        ALLOWED_OPERATORS = {
            "AND", "OR", "NOT", "EQ", "NEQ", "LT", "LTE", "GT", "GTE",
            "IN", "LIKE", "BETWEEN", "IS", "ISNULL", "NOTNULL",
            "ADD", "SUB", "MUL", "DIV", "MOD", "NEG",
            "ALIAS", "CAST", "CASE", "IF", "NULLIF",
            "PAREN", "PARENTHESIS", "BRACKET",
            "LITERAL", "BOOLEAN", "NULL", "STAR",
            "ORDER", "ORDERBY", "GROUP", "GROUPBY", "LIMIT", "OFFSET",
            "WHERE", "HAVING", "JOIN", "ON", "USING",
            "SELECT", "FROM", "TABLE", "COLUMN", "IDENTIFIER"
        }
        
        def check_functions(node):
            if isinstance(node, sqlglot.expressions.Anonymous):
                func_name = str(node.this).upper()
                print(f"[NLQ Debug] Found Anonymous function: {func_name}")
                if func_name not in self.ALLOWED_FUNCTIONS:
                    print(f"[NLQ Debug] Function {func_name} not in allowed list")
                    return False
            elif isinstance(node, sqlglot.expressions.Func):
                # Get the function class name (e.g., Sum, Count, Avg)
                func_name = node.__class__.__name__.upper()
                print(f"[NLQ Debug] Found Func: {func_name}")
                
                # Skip operators and SQL keywords
                if func_name in ALLOWED_OPERATORS:
                    print(f"[NLQ Debug] Skipping operator: {func_name}")
                elif func_name and func_name not in self.ALLOWED_FUNCTIONS:
                    print(f"[NLQ Debug] Function {func_name} not in allowed list")
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

    def _get_schema_description(self) -> str:
        """Generate a human-readable schema description for the LLM."""
        return """
Database Schema:

1. transactions table:
   - id (UUID): Unique transaction identifier
   - transaction_date (TIMESTAMP): When the transaction occurred
   - vendor_id (UUID): Foreign key to vendors table
   - amount (FLOAT): Transaction amount (negative for expenses, positive for income)
   - category (STRING): Transaction category (e.g., 'groceries', 'utilities', 'salary')
   - normalized_description (STRING): Cleaned transaction description
   - raw_description (TEXT): Original transaction description
   - source (STRING): Source of transaction data
   - source_type (STRING): Type of source ('upload', 'quickbooks', 'manual')
   - statement_id (UUID): Foreign key to statements table
   - quickbooks_id (STRING): QuickBooks transaction ID (if synced)
   - quickbooks_connection_id (UUID): Foreign key to quickbooks_connections
   - quickbooks_sync_version (STRING): Sync version for updates
   - created_at (TIMESTAMP): Record creation time
   - updated_at (TIMESTAMP): Last update time

2. vendors table:
   - id (UUID): Unique vendor identifier
   - name (STRING): Vendor name
   - normalized_name (STRING): Cleaned vendor name for matching
   - embedding (STRING): Vector embedding for similarity search
   - created_at (TIMESTAMP): Record creation time
   - updated_at (TIMESTAMP): Last update time

3. statements table:
   - id (UUID): Unique statement identifier
   - source_file (STRING): Original file name
   - period_start (TIMESTAMP): Statement period start
   - period_end (TIMESTAMP): Statement period end
   - account_type (STRING): Type of account (checking, savings, credit)
   - processed_at (TIMESTAMP): When statement was processed
   - created_at (TIMESTAMP): Record creation time

4. anomalies table:
   - id (UUID): Unique anomaly identifier
   - transaction_id (UUID): Foreign key to transactions
   - anomaly_type (STRING): Type of anomaly detected
   - severity (STRING): Severity level (low, medium, high, critical)
   - description (TEXT): Description of the anomaly
   - expected_value (FLOAT): Expected value
   - actual_value (FLOAT): Actual value found
   - confidence (FLOAT): Confidence score (0-1)
   - detected_at (TIMESTAMP): When anomaly was detected
   - resolved_at (TIMESTAMP): When anomaly was resolved (NULL if unresolved)
   - notes (TEXT): Additional notes

Important Notes:
- Negative amounts in transactions represent expenses
- Positive amounts represent income
- Use JOINs to get vendor names: LEFT JOIN vendors v ON t.vendor_id = v.id
- Always use proper date filters when date ranges are provided
- Use aggregate functions (SUM, COUNT, AVG) for summary queries
"""

    def _generate_sql_with_llm(self, query: str, parameters: Dict[str, Any]) -> str:
        """Use LLM to generate SQL from natural language query."""
        schema_desc = self._get_schema_description()
        
        # Build date filter context
        date_context = ""
        if parameters.get('date_from') or parameters.get('date_to'):
            date_context = "\n\nDate Range:"
            if parameters.get('date_from'):
                date_context += f"\n- From: {parameters['date_from'].strftime('%Y-%m-%d')}"
            if parameters.get('date_to'):
                date_context += f"\n- To: {parameters['date_to'].strftime('%Y-%m-%d')}"
        
        limit_context = f"\n\nResult Limit: {parameters.get('limit', 100)} rows"
        
        system_prompt = f"""You are a SQL expert. Generate a safe PostgreSQL query based on the user's natural language question.

{schema_desc}

Rules:
1. ONLY generate SELECT queries (no INSERT, UPDATE, DELETE, DROP, etc.)
2. Only use tables and columns from the schema above
3. Use proper JOINs when referencing multiple tables
4. Always include WHERE clauses for date filters if dates are provided
5. Use aggregate functions (SUM, COUNT, AVG) appropriately
6. Return ONLY the SQL query, no explanations
7. Use table aliases for readability (t for transactions, v for vendors, etc.)
8. For expense queries, filter where amount < 0
9. For income queries, filter where amount > 0
10. For "top" or "highest" queries, use ORDER BY DESC (descending)
11. For "bottom" or "lowest" queries, use ORDER BY ASC (ascending)
12. When user asks for "top X spends" or "largest transactions", they want individual transactions, NOT grouped/aggregated data
13. When user asks for "spending by category" or "total by vendor", THEN use GROUP BY with aggregation
14. Include vendor names when showing transactions (JOIN with vendors table)

Output ONLY the SQL query, nothing else."""

        user_prompt = f"""Generate a SQL query for this question: "{query}"{date_context}{limit_context}

SQL Query:"""

        try:
            if self.llm_provider == "anthropic" and self.anthropic_client:
                response = self.anthropic_client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=1024,
                    messages=[
                        {"role": "user", "content": f"{system_prompt}\n\n{user_prompt}"}
                    ]
                )
                sql = response.content[0].text.strip()
            elif self.openai_client:
                response = self.openai_client.chat.completions.create(
                    model="gpt-4-turbo-preview",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0,
                    max_tokens=1024
                )
                sql = response.choices[0].message.content.strip()
            else:
                raise ValueError("No LLM client available. Please set OPENAI_API_KEY or ANTHROPIC_API_KEY")
            
            # Clean up the SQL (remove markdown code blocks if present)
            sql = re.sub(r'^```sql\n', '', sql)
            sql = re.sub(r'^```\n', '', sql)
            sql = re.sub(r'\n```$', '', sql)
            sql = sql.strip()
            
            return sql
            
        except Exception as e:
            print(f"[NLQ Debug] LLM generation failed: {e}")
            raise ValueError(f"Failed to generate SQL with LLM: {str(e)}")

    def _generate_natural_language_response(self, query: str, sql: str, results: List[Dict], execution_time_ms: float) -> str:
        """Generate a natural language response from query results using LLM."""
        
        # Format results for LLM (limit to first 20 rows for context)
        results_summary = json.dumps(results[:20], indent=2, default=str)
        
        system_prompt = """You are a friendly financial assistant. Explain query results in natural, conversational language.

Guidelines:
1. Be concise and direct - get to the point quickly
2. Use everyday language, not technical jargon
3. Format currency with $ and commas (e.g., $1,234.56)
4. Focus on actionable insights, not obvious observations
5. Skip unnecessary explanations about data structure or query mechanics
6. Use a warm, helpful tone as if talking to a friend
7. For missing data (NULL vendors, etc.), just say "Unknown" or skip mentioning it
8. Keep responses under 3-4 sentences for simple queries
9. Don't explain why there are fewer results than expected - just show what you found"""

        user_prompt = f"""The user asked: "{query}"

Results ({len(results)} rows):
{results_summary}

Provide a brief, natural response (2-3 sentences max). Just tell them what they asked for - no explanations about the query or data structure."""

        try:
            if self.llm_provider == "anthropic" and self.anthropic_client:
                response = self.anthropic_client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=1024,
                    messages=[
                        {"role": "user", "content": f"{system_prompt}\n\n{user_prompt}"}
                    ]
                )
                return response.content[0].text.strip()
            elif self.openai_client:
                response = self.openai_client.chat.completions.create(
                    model="gpt-4-turbo-preview",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.7,
                    max_tokens=1024
                )
                return response.choices[0].message.content.strip()
            else:
                # Fallback to simple summary if no LLM available
                return self._generate_simple_summary(results)
                
        except Exception as e:
            print(f"[NLQ Debug] Natural language generation failed: {e}")
            return self._generate_simple_summary(results)
    
    def _generate_simple_summary(self, results: List[Dict]) -> str:
        """Generate a simple text summary without LLM."""
        if not results:
            return "No results found for your query."
        
        result_count = len(results)
        summary = f"Found {result_count} result{'s' if result_count != 1 else ''}."
        
        # Try to identify numeric columns and provide basic stats
        if results and len(results) > 0:
            first_row = results[0]
            for key, value in first_row.items():
                if isinstance(value, (int, float)) and 'count' in key.lower():
                    summary += f" {key}: {value}"
                elif isinstance(value, (int, float)) and 'total' in key.lower():
                    summary += f" {key}: ${value:,.2f}"
        
        return summary

    def generate_sql(self, query: str, parameters: Dict[str, Any] = None) -> Tuple[str, str]:
        """Generate safe SQL from natural language query using LLM."""
        if parameters is None:
            parameters = {}

        print(f"[NLQ Debug] Query: '{query}'")
        print(f"[NLQ Debug] Using LLM provider: {self.llm_provider}")

        # Generate SQL using LLM
        sql = self._generate_sql_with_llm(query, parameters)
        print(f"[NLQ Debug] Generated SQL:\n{sql}")

        # Validate the generated SQL
        is_safe, error_msg = self._validate_sql_safety(sql)
        if not is_safe:
            print(f"[NLQ Debug] SQL validation failed: {error_msg}")
            raise ValueError(f"Generated SQL failed safety check: {error_msg}")

        print(f"[NLQ Debug] SQL validation passed!")
        return sql, "llm_generated"

    def execute_query(self, query: str, parameters: Dict[str, Any] = None) -> Dict[str, Any]:
        """Execute a validated SQL query and return results with natural language response."""
        start_time = time.time()

        try:
            # Generate and validate SQL using LLM
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

            # Generate natural language response
            print(f"[NLQ Debug] Generating natural language response...")
            natural_language_response = self._generate_natural_language_response(
                query, sql, results, execution_time
            )
            print(f"[NLQ Debug] Natural language response generated!")

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
                "result_count": len(results),
                "natural_language_response": natural_language_response,
                "summary": natural_language_response  # Alias for backward compatibility
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
                "execution_time_ms": execution_time,
                "natural_language_response": f"I encountered an error while processing your query: {str(e)}"
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
