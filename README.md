
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

## Architecture

This application consists of two main components:
- **Backend (FastAPI)**: Python-based API server running on port 8000
- **Frontend (Next.js)**: React-based web application running on port 8080

## Quick Start

### Automated Setup (Recommended)

The easiest way to get started is using the provided startup script:

```bash
# Make the script executable
chmod +x startup.sh

# Run the startup script
./startup.sh
```

This script will:
1. Check prerequisites (Python, Node.js, PostgreSQL, MongoDB)
2. Create environment files from examples
3. Install backend and frontend dependencies
4. Run database migrations
5. Start both services

To stop the application:
```bash
./stop.sh
```

### Manual Setup

#### Prerequisites

- Python 3.9 or higher
- Node.js 18 or higher
- PostgreSQL 12 or higher
- MongoDB 4.4 or higher (for authentication)

#### 1. Backend Setup

```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file from example
cp env.example .env
# Edit .env with your database credentials and API keys

# Run database migrations
alembic upgrade head

# Start the backend server (port 8000)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The backend API will be available at `http://localhost:8000` with interactive OpenAPI documentation at `/docs`.

#### 2. Frontend Setup

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Create .env.local file from example
cp env.local.example .env.local
# Edit .env.local with your MongoDB credentials and API keys

# Start the frontend server (port 8080)
npm run dev
```

The frontend will be available at `http://localhost:8080`.

### Environment Configuration

#### Backend (.env)

Copy `env.example` to `.env` and configure:

```bash
# Database
DB_USER=postgres
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432
DB_NAME=cashflow

# LLM API Keys
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key

# QuickBooks OAuth
QUICKBOOKS_CLIENT_ID=your_client_id
QUICKBOOKS_CLIENT_SECRET=your_client_secret
QUICKBOOKS_REDIRECT_URI=http://localhost:8000/api/quickbooks/callback
QUICKBOOKS_ENVIRONMENT=sandbox

# CORS
ALLOWED_ORIGINS=http://localhost:8080,http://localhost:3000
```

#### Frontend (.env.local)

Copy `frontend/env.local.example` to `frontend/.env.local` and configure:

```bash
# Backend API
NEXT_PUBLIC_API_URL=http://localhost:8000

# MongoDB
MONGODB_URI=mongodb://localhost:27017/cashflow
MONGODB_DATABASE=cashflow

# Brevo Email
BREVO_API_KEY=your_brevo_key
BREVO_SENDER=Your Company Name
BREVO_FROM_EMAIL_ID=noreply@yourcompany.com

# JWT
JWT_SECRET=your_jwt_secret_minimum_32_characters
```

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

### Production Deployment

For production deployment, use the provided `nginx.conf.example` as a reference to configure a reverse proxy:

```bash
# Copy and customize nginx configuration
cp nginx.conf.example /etc/nginx/sites-available/cashflow
ln -s /etc/nginx/sites-available/cashflow /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

### Docker

```bash
# Build backend image
docker build -t cashflow-api .
docker run -p 8000:8000 -e DATABASE_URL=... -e OPENAI_API_KEY=... cashflow-api

# Build frontend image (in frontend directory)
cd frontend
docker build -t cashflow-frontend .
docker run -p 8080:8080 cashflow-frontend
```

### Production Considerations

- Use a production WSGI server (Gunicorn + Uvicorn) for the backend
- Enable database connection pooling
- Set up proper logging and monitoring
- Consider Redis for caching query results
- Implement rate limiting and authentication
- Use environment-specific configuration files
- Enable HTTPS with SSL certificates
- Set `ENVIRONMENT=production` in backend .env

## Troubleshooting

### Backend Issues

**Port 8000 already in use:**
```bash
# Find and kill the process using port 8000
lsof -ti:8000 | xargs kill -9
```

**Database connection errors:**
- Ensure PostgreSQL is running: `pg_isready`
- Check credentials in `.env` file
- Verify database exists: `psql -l`

**Migration errors:**
```bash
# Reset migrations (development only)
alembic downgrade base
alembic upgrade head
```

### Frontend Issues

**Port 8080 already in use:**
```bash
# Find and kill the process using port 8080
lsof -ti:8080 | xargs kill -9
```

**MongoDB connection errors:**
- Ensure MongoDB is running: `mongosh --eval "db.runCommand({ ping: 1 })"`
- Check `MONGODB_URI` in `frontend/.env.local`

**API connection errors:**
- Verify backend is running on port 8000
- Check `NEXT_PUBLIC_API_URL` in `frontend/.env.local`
- Ensure CORS is configured correctly in backend

### Common Issues

**CORS errors:**
- Add your frontend URL to `ALLOWED_ORIGINS` in backend `.env`
- Restart the backend server after changing CORS settings

**Environment variables not loading:**
- Ensure `.env` files are in the correct locations
- Restart both servers after changing environment variables
- Check that variable names start with `NEXT_PUBLIC_` for client-side Next.js variables

**Logs location:**
- Backend logs: `backend.log` (when using startup.sh)
- Frontend logs: `frontend.log` (when using startup.sh)

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## License

MIT License - see LICENSE file for details.
