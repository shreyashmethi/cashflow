# AI/ML Tasks for Cash Flow Analysis Tool

This document outlines the AI/ML responsibilities and deliverables for the Cash Flow Analysis & Visualization Tool.

## Task List

### AI/ML Modules
- [ ] Transaction parsing/normalization engine.
- [ ] Anomaly detection logic.
- [ ] NLQ (Natural Language Query) interpreter.
- [ ] Summarization layer.

### API Layer
- [ ] Implement API Endpoints:
    - [ ] `POST /api/parse-transactions`
    - [ ] `POST /api/validate-transactions`
    - [ ] `POST /api/query`
    - [ ] `POST /api/summarize`
    - [ ] `POST /api/visualize-data`
    - [ ] `GET /api/health`
- [ ] Generate Swagger/OpenAPI documentation.

### Database Schema & Configuration
- [ ] Design and implement normalized schema for:
    - [ ] transactions
    - [ ] statements
    - [ ] vendors
    - [ ] anomalies
    - [ ] NLQ queries
    - [ ] embeddings
- [ ] Provide partitioning and indexing guidance.

### Testing & Validation
- [ ] Create parsing tests with provided sample files.
- [ ] Create NLQ correctness checks.

### Documentation
- [ ] Write API usage guide.
- [ ] Create a data schema reference document.

---

## Project Specifications

### Needs (Resources & Keys)
- **LLM & Embeddings**:
    - API keys for LLM provider (e.g., OpenAI, Anthropic, or local deployment).
    - API keys for embeddings provider (OpenAI embeddings or open-source equivalent).
- **Storage & Database**:
    - Access to PostgreSQL (with `pgvector` extension enabled).
    - S3-compatible object storage for raw PDF/CSV files (AWS S3, MinIO, or equivalent).
    - Redis (for caching query/visualization results).
- **Infrastructure & Orchestration**:
    - Containerized environment (Docker/Kubernetes).
    - Message broker (Kafka or RabbitMQ) for background parsing jobs.
    - CI/CD access (GitHub Actions or GitLab CI).

### Preferences
- **Database**: PostgreSQL with partitioning on `posting_date`, vector search via `pgvector`, OLAP supplement with ClickHouse/BigQuery if scale demands.
- **Storage**: S3 (or MinIO) for raw files, Redis for caching.
- **Stack**: Python 3.11+, FastAPI, SQLAlchemy, Prefect for orchestration.
- **Parsing tools**: `pdfplumber`/`pdfminer`/Tika + OCR fallback (Tesseract).
- **ML Toolkit**: LangChain + LLM provider (OpenAI or Anthropic).
- **Deployment**: Docker/Kubernetes, CI/CD via GitHub Actions.
