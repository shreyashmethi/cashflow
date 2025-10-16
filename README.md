
# Cash Flow Analysis & Visualization Tool

An AI-powered financial data analysis and visualization API that processes bank statements, invoices, and other financial documents to provide insights, anomaly detection, and natural language querying capabilities.

## Features

- **Document Processing**: Parse CSV, Excel, PDF, and other document formats
- **Vendor Resolution**: Automatic vendor name normalization and deduplication
- **Data Validation**: Comprehensive transaction validation and anomaly detection
- **Natural Language Queries**: Safe SQL generation from natural language questions
- **Financial Summarization**: KPI calculation and trend analysis
- **Visualization Data**: Generate data for charts and dashboards
- **Anomaly Detection**: Statistical outlier detection using z-score and IQR methods

## Quick Start

### Installation

```bash
pip install -r requirements.txt
```

### Environment Setup

Set your database URL and API keys:

```bash
export DATABASE_URL="postgresql://username:password@localhost:5432/cashflow"
export OPENAI_API_KEY="your-openai-key"
```

### Database Setup

```bash
# Run migrations
python -m alembic upgrade head

# Create database extension
psql $DATABASE_URL -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### Start the API

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000` with interactive OpenAPI documentation at `/docs`.

## API Endpoints

### Transaction Management

#### Parse Transactions from File
```http
POST /api/parse-transactions
Content-Type: multipart/form-data

# Upload a CSV, Excel, or PDF file
```

**Response:**
```json
{
  "filename": "transactions.csv",
  "transactions_saved": 150,
  "vendors_resolved": 45,
  "duplicates_found": 3,
  "metadata": {
    "file_type": "csv",
    "total_raw_records": 153,
    "normalized_records": 150
  }
}
```

#### Get Transactions
```http
GET /api/transactions?limit=100&offset=0&vendor_id=uuid&category=expense&date_from=2024-01-01&date_to=2024-12-31
```

#### Validate Transactions
```http
POST /api/validate-transactions
Content-Type: application/json

{
  "transactions": [
    {
      "transaction_date": "2024-01-15T10:30:00Z",
      "amount": -45.67,
      "vendor": "Starbucks Coffee",
      "category": "expense",
      "description": "Coffee purchase"
    }
  ]
}
```

**Response:**
```json
{
  "total_transactions": 1,
  "valid_transactions": 1,
  "invalid_transactions": 0,
  "results": [
    {
      "index": 0,
      "is_valid": true,
      "errors": [],
      "warnings": []
    }
  ],
  "summary": {
    "common_errors": [],
    "common_warnings": [],
    "error_rate": 0.0,
    "warning_rate": 0.0
  },
  "duplicates": [],
  "anomalies": []
}
```

### Analytics & Insights

#### Natural Language Query
```http
POST /api/query
Content-Type: application/json

{
  "query": "What was the total spending on groceries last month?",
  "date_from": "2024-01-01",
  "date_to": "2024-01-31",
  "limit": 100
}
```

**Response:**
```json
{
  "success": true,
  "sql": "SELECT SUM(amount) as total FROM transactions WHERE amount < 0 AND category = 'groceries' AND transaction_date >= '2024-01-01' AND transaction_date <= '2024-01-31'",
  "intent": "total_spend",
  "results": [
    {"total": -1250.75}
  ],
  "execution_time_ms": 45.2,
  "result_count": 1
}
```

#### Generate Summary
```http
POST /api/summarize
Content-Type: application/json

{
  "date_from": "2024-01-01",
  "date_to": "2024-01-31",
  "include_anomalies": true
}
```

**Response:**
```json
{
  "period": {
    "from": "2024-01-01T00:00:00",
    "to": "2024-01-31T23:59:59",
    "days": 31
  },
  "kpis": {
    "total_income": 5000.0,
    "total_expenses": 3250.75,
    "net_cashflow": 1749.25,
    "total_transactions": 45,
    "average_transaction": 181.85,
    "unique_vendors": 23
  },
  "trends": {
    "monthly_breakdown": [
      {
        "month": "2024-01",
        "income": 5000.0,
        "expenses": 3250.75,
        "net": 1749.25
      }
    ],
    "trends": {
      "income_trend": "stable",
      "expense_trend": "increasing",
      "income_change_percent": 2.1,
      "expense_change_percent": 15.3
    }
  },
  "top_vendors": [
    {
      "vendor": "Amazon",
      "total_spent": -450.0,
      "transaction_count": 12
    }
  ],
  "categories": [
    {
      "category": "groceries",
      "total_spent": -800.0,
      "transaction_count": 15,
      "percentage": 24.6
    }
  ],
  "summary_text": "## Financial Summary\n**Total Income:** $5,000.00\n**Total Expenses:** $3,250.75\n..."
}
```

#### Get Visualization Data
```http
POST /api/visualize-data
Content-Type: application/json

{
  "chart_type": "bar",
  "date_from": "2024-01-01",
  "date_to": "2024-01-31",
  "group_by": "month",
  "category": "expense"
}
```

**Response:**
```json
{
  "chart_type": "bar",
  "title": "Top Spending Vendors - Expense Category (Jan 2024 - Jan 2024)",
  "data": [
    {"vendor": "Amazon", "amount": 450.0, "count": 12},
    {"vendor": "Starbucks", "amount": 125.0, "count": 8}
  ],
  "labels": ["Amazon", "Starbucks"],
  "metadata": {
    "date_range": {
      "from": "2024-01-01T00:00:00",
      "to": "2024-01-31T23:59:59"
    },
    "filters": {
      "category": "expense",
      "group_by": "month"
    }
  }
}
```

#### Anomaly Detection
```http
POST /api/run-anomaly-scan
Content-Type: application/json

{
  "date_from": "2024-01-01",
  "date_to": "2024-01-31",
  "persist_results": true
}
```

**Response:**
```json
{
  "total_scanned": 150,
  "anomalies_found": 3,
  "anomalies": [
    {
      "vendor_id": "uuid",
      "anomaly_type": "z_score_outlier",
      "severity": "high",
      "description": "Unusual expense amount ($1,200.00) for vendor - 3.2 standard deviations from mean",
      "expected_value": 150.0,
      "actual_value": 1200.0,
      "confidence": 0.85
    }
  ],
  "scan_time_ms": 125.5
}
```

#### Get Anomalies
```http
GET /api/anomalies?limit=50&severity=high&resolved=false
```

## Supported File Types

- **CSV**: Transaction data in comma-separated format
- **Excel**: .xlsx and .xls files with transaction data
- **PDF**: Bank statements and invoices (requires vision capability)
- **Images**: Scanned receipts and documents (requires vision capability)
- **Word/HTML**: Text-based financial documents

## Configuration

### Environment Variables

```bash
# Database
DATABASE_URL=postgresql://username:password@localhost:5432/cashflow

# LLM Providers
OPENAI_API_KEY=your-openai-key
ANTHROPIC_API_KEY=your-anthropic-key

# Optional: Model overrides
OPENAI_MODEL=gpt-4o
ANTHROPIC_MODEL=claude-3-5-sonnet-20240620
```

### Application Configuration

The system uses dataclasses for configuration. Key settings:

```python
from app.config import PipelineConfig, LLMConfig, VisionConfig

config = PipelineConfig(
    llm=LLMConfig(
        provider="gpt",  # or "claude"
        model="gpt-4o",
        enable_vision=True,
        temperature=0.0
    ),
    vision=VisionConfig(
        strategy="auto",  # auto, full_document, page_by_page, off
        max_pages_full=15,
        dpi=180
    )
)
```

## Architecture

### Database Schema

The system uses PostgreSQL with the following core tables:

- **transactions**: Financial transaction records
- **vendors**: Normalized vendor information
- **statements**: Metadata about source files
- **anomalies**: Detected anomalies and issues
- **nlq_queries**: Log of natural language queries

### Services

- **FileParser**: Parses and normalizes transaction data from files
- **VendorService**: Handles vendor resolution and deduplication
- **ValidationService**: Validates transactions and detects issues
- **NLQService**: Safe natural language to SQL conversion
- **SummarizeService**: Generates financial summaries and KPIs
- **VisualizationService**: Creates data for charts and visualizations
- **AnomalyService**: Detects statistical anomalies

### Security

- **SQL Injection Prevention**: Uses parameterized queries and sqlglot parsing
- **Schema Whitelisting**: Only allows access to predefined tables and columns
- **Input Validation**: Comprehensive Pydantic schemas for all endpoints
- **Rate Limiting**: Ready for implementation via middleware

## Development

### Running Tests

```bash
pytest tests/
```

### Database Migrations

```bash
# Generate new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

### API Documentation

Visit `/docs` when the server is running for interactive OpenAPI documentation.

## Deployment

### Docker

```bash
docker build -t cashflow-api .
docker run -p 8000:8000 -e DATABASE_URL=... -e OPENAI_API_KEY=... cashflow-api
```

### Production Considerations

- Use a production WSGI server (Gunicorn + Uvicorn)
- Enable database connection pooling
- Set up proper logging and monitoring
- Consider Redis for caching query results
- Implement rate limiting and authentication

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## License

MIT License - see LICENSE file for details.
