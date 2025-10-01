# syntax=docker/dockerfile:1.4
FROM python:3.11-slim

# Set working directory
WORKDIR /code

# Install system dependencies
RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*

# Copy only requirements first for caching
COPY requirements.txt .

# Enable pip cache for faster rebuilds
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project
COPY . .

# Expose FastAPI port
EXPOSE 8000

# CMD: Wait for Mongo + ingest + start FastAPI
CMD ["bash", "-c", "python ingest/ingest.py && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
