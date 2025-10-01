import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

API_KEY = "dev-key"

def test_list_books():
    response = client.get("/books?q=orwell&year_from=1930&year_to=1950&page=1&page_size=10")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert isinstance(data["items"], list)

def test_get_book_valid():
    response = client.get("/books/170")
    assert response.status_code in [200, 404]

def test_get_book_invalid():
    response = client.get("/books/999999")
    assert response.status_code == 404


def test_post_rating_valid():
    payload = {"user_id": 2001, "book_id": 170, "rating": 5}
    response = client.post("/ratings", headers={"x-api-key": API_KEY}, json=payload)
    assert response.status_code in [200, 201]
    data = response.json()
    assert "status" in data

def test_post_rating_invalid_key():
    payload = {"user_id": 2001, "book_id": 170, "rating": 5}
    response = client.post("/ratings", headers={"x-api-key": "wrong-key"}, json=payload)
    assert response.status_code == 401

def test_post_rating_invalid_value():
    payload = {"user_id": 2001, "book_id": 170, "rating": 6}  # invalid >5
    response = client.post("/ratings", headers={"x-api-key": API_KEY}, json=payload)
    assert response.status_code == 422  # validation error


def test_get_books_by_author():
    response = client.get("/authors/orwell/books")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data


def test_list_tags():
    response = client.get("/tags?page=1&page_size=10")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data

def test_health():
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data

def test_metrics():
    response = client.get("/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "total_requests" in data