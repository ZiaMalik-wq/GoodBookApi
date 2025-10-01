# GoodBooks API

A **FastAPI** REST API for books, ratings, and tags based on the [GoodBooks-10k dataset](https://github.com/zygmuntz/goodbooks-10k). The API uses **MongoDB** as the backend and is fully **Dockerized** for easy deployment.

## Features

- CRUD-like endpoints for **books, authors, tags, ratings, and to-read lists**  
- **Protected POST /ratings** with API key  
- Optional endpoints implemented:  
  - `/healthz` – service health check (Mongo ping)  
  - `/metrics` – request counters and latency  
  - Rate limiting: 60 requests/min per IP  
- Pagination, sorting, and filtering for lists  
- JSON logging of requests with latency  

## Project Structure

```
GoodBook/
├─ app/                # FastAPI application
│  └─ main.py          # API endpoints
├─ ingest/             # CSV -> MongoDB ingestion scripts
│  └─ ingest.py
├─ Dockerfile          # Docker image build instructions
├─ docker-compose.yml  # Multi-container setup (API + MongoDB)
├─ requirements.txt    # Python dependencies
├─ .env                # Environment variables (not committed)
├─ README.md
└─ .gitignore
```

## Setup

1. **Clone the repository**:

```bash
git clone https://github.com/ZiaMalik-wq/GoodBookApi.git
cd GoodBook
```

2. **Create `.env`** (example):

```text
MONGO_URI=mongodb://goodbooks_db:27017
DB_NAME=goodbooks
INGEST_MODE=sample
BATCH_SIZE=1000
API_KEY=dev-key
```

3. **Docker & Docker Compose** must be installed on your machine.

## Running the API with Docker

1. **Build Docker images**:

```powershell
docker compose build
```

2. **Start API and MongoDB**:

```powershell
docker compose up
```

3. **Ingest sample data** (from the ingest container):

```powershell
docker compose run --rm api python ingest/ingest.py
```

4. **Access API**:

- Swagger docs: [http://localhost:8000/docs](http://localhost:8000/docs)  
- Example endpoint:

```powershell
Invoke-RestMethod "http://localhost:8000/books?q=orwell&year_from=1930&year_to=1950&page=1&page_size=10"
```

- Protected endpoint example:

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/ratings" `
  -Method Post `
  -Headers @{ "x-api-key" = "dev-key" } `
  -Body (@{ "user_id" = 2001; "book_id" = 170; "rating" = 5 } | ConvertTo-Json) `
  -ContentType "application/json"
```

## Key Design Decisions

- **MongoDB Schema**: Separate collections for `books`, `ratings`, `tags`, `book_tags`, and `to_read` for simplicity and query efficiency.  
- **Indexes**:
  - `books`: `book_id`, `title+authors` (text search), `average_rating`  
  - `ratings`: `user_id+book_id` unique, `book_id`  
  - `tags`: `tag_id`, `tag_name`  
  - `book_tags`: `goodreads_book_id`, `tag_id`  
  - `to_read`: `user_id+book_id` unique  
- **Rate Limiting**: Basic in-memory per-IP counter (60 requests/min) to prevent abuse.  
- **Health and Metrics**: `/healthz` pings MongoDB; `/metrics` aggregates request count and average latency.  
- **Ingestion**: Idempotent CSV ingestion via `ingest.py`, with batching for large datasets.  
- **API Key**: Simple header `x-api-key` for protected endpoints like `/ratings`.  

## Testing Endpoints

- List books:

```powershell
Invoke-RestMethod "http://localhost:8000/books?q=orwell&year_from=1930&year_to=1950&page=1&page_size=10"
```

- Create/update rating (protected):

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/ratings" `
  -Method Post `
  -Headers @{ "x-api-key" = "dev-key" } `
  -Body (@{ "user_id" = 2001; "book_id" = 170; "rating" = 5 } | ConvertTo-Json) `
  -ContentType "application/json"
```

- Health check:

```powershell
Invoke-RestMethod "http://localhost:8000/healthz"
```

- Metrics:

```powershell
Invoke-RestMethod "http://localhost:8000/metrics"
```

## Notes

- `.venv` and `.env` are **ignored** in `.gitignore` to avoid committing sensitive data.  
- Docker ensures a reproducible environment for both API and MongoDB.  
- Pagination defaults: `page=1`, `page_size=10` (max 100).