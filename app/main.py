import os
import time
import logging
from datetime import datetime, timedelta
from collections import defaultdict
from fastapi import FastAPI, HTTPException, Query, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pymongo import MongoClient
from dotenv import load_dotenv


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
logger = logging.getLogger("goodbooks")

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "goodbooks")
API_KEY = os.getenv("API_KEY", "dev-key")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

app = FastAPI(title="GoodBooks API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

RATE_LIMIT = 60
RATE_PERIOD = timedelta(minutes=1)
ip_request_log = defaultdict(list)
metrics_data = defaultdict(lambda: {"count": 0, "total_latency_ms": 0.0})

@app.middleware("http")
async def rate_and_metrics_middleware(request: Request, call_next):
    start_time = time.time()
    client_ip = request.client.host
    now = datetime.now()
    timestamps = ip_request_log[client_ip]
    ip_request_log[client_ip] = [t for t in timestamps if now - t < RATE_PERIOD]
    if len(ip_request_log[client_ip]) >= RATE_LIMIT:
        return JSONResponse(status_code=429, content={"detail": "Rate limit exceeded. Try again later."})
    ip_request_log[client_ip].append(now)
    try:
        response = await call_next(request)
    except Exception as e:
        logger.exception(f"Error while handling request {request.url.path}")
        raise
    duration_ms = (time.time() - start_time) * 1000
    path = request.url.path
    metrics_data[path]["count"] += 1
    metrics_data[path]["total_latency_ms"] += duration_ms
    logger.info(f"{request.method} {request.url.path} completed in {round(duration_ms, 2)}ms with status {response.status_code}")
    return response

def require_api_key(request: Request):
    key = request.headers.get("x-api-key")
    if key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

class RatingIn(BaseModel):
    user_id: int
    book_id: int
    rating: int = Field(ge=1, le=5)

@app.get("/healthz")
def healthz():
    try:
        client.admin.command("ping")
        return {"status": "ok", "mongo": "reachable"}
    except Exception as e:
        logger.error(f"MongoDB ping failed: {e}")
        return {"status": "fail", "mongo": "unreachable"}

@app.get("/metrics")
def get_metrics():
    metrics = {}
    for endpoint, data in metrics_data.items():
        avg_latency = data["total_latency_ms"] / max(1, data["count"])
        metrics[endpoint] = {"request_count": data["count"], "average_latency_ms": round(avg_latency, 2)}
    return metrics

@app.get("/")
def root():
    return {"message": "GoodBooks API is running"}

@app.get("/books")
def list_books(
    q: str | None = None,
    min_avg: float | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    sort: str = Query("avg", pattern="^(avg|ratings_count|year|title)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = 1,
    page_size: int = Query(10, le=100),
):
    filt = {}
    if q:
        filt["$or"] = [
            {"title": {"$regex": q, "$options": "i"}},
            {"authors": {"$regex": q, "$options": "i"}},
        ]
    if min_avg is not None:
        filt["average_rating"] = {"$gte": float(min_avg)}
    year_clause = {}
    if year_from is not None:
        year_clause["$gte"] = year_from
    if year_to is not None:
        year_clause["$lte"] = year_to
    if year_clause:
        filt["original_publication_year"] = year_clause

    sort_map = {
        "avg": "average_rating",
        "ratings_count": "ratings_count",
        "year": "original_publication_year",
        "title": "title",
    }
    direction = -1 if order == "desc" else 1

    total = db.books.count_documents(filt)
    cursor = (
        db.books.find(filt, {"_id": 0})
        .sort([(sort_map[sort], direction)])
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    items = list(cursor)

    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
    }

@app.get("/books/{book_id}")
def get_book(book_id: int):
    book = db.books.find_one({"book_id": book_id}, {"_id": 0})
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    return book

@app.get("/authors/{author}/books")
def get_books_by_author(author: str, page: int = 1, page_size: int = Query(10, le=100)):
    filt = {"authors": {"$regex": author, "$options": "i"}}
    total = db.books.count_documents(filt)
    cursor = (
        db.books.find(filt, {"_id": 0})
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    items = list(cursor)
    return {
        "items": items,
        "author": author,
        "page": page,
        "page_size": page_size,
        "total": total,
    }

@app.get("/books/{book_id}/tags")
def get_book_tags(book_id: int):
    book = db.books.find_one({"book_id": book_id}, {"_id": 0, "book_id": 1, "title": 1})
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    tag_links = list(db.book_tags.find({"goodreads_book_id": book_id}, {"_id": 0, "tag_id": 1, "count": 1}))
    if not tag_links:
        return {"book_id": book_id, "title": book["title"], "tags": []}

    tag_ids = [t["tag_id"] for t in tag_links]
    tag_map = {t["tag_id"]: t["tag_name"] for t in db.tags.find({"tag_id": {"$in": tag_ids}}, {"_id": 0})}

    tags = [
        {"tag_id": t["tag_id"], "tag_name": tag_map.get(t["tag_id"], ""), "count": t["count"]}
        for t in tag_links
    ]

    return {"book_id": book_id, "title": book["title"], "tags": tags}

@app.get("/books/{book_id}/recommendations")
def recommend_books(book_id: int, limit: int = 5):
    book = db.books.find_one(
        {"book_id": book_id},
        {"_id": 0, "book_id": 1, "goodreads_book_id": 1, "title": 1}
    )
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    tag_links = list(
        db.book_tags.find({"goodreads_book_id": book["goodreads_book_id"]}, {"_id": 0, "tag_id": 1})
    )
    if not tag_links:
        return {"book_id": book_id, "title": book["title"], "recommendations": []}

    tag_ids = [t["tag_id"] for t in tag_links]

    other_books = db.book_tags.aggregate([
        {"$match": {"tag_id": {"$in": tag_ids}, "goodreads_book_id": {"$ne": book["goodreads_book_id"]}}},
        {"$group": {"_id": "$goodreads_book_id", "score": {"$sum": 1}}},
        {"$sort": {"score": -1}},
        {"$limit": limit}
    ])

    rec_ids = [b["_id"] for b in other_books]
    rec_books = list(db.books.find({"goodreads_book_id": {"$in": rec_ids}}, {"_id": 0}))

    return {
        "book_id": book_id,
        "title": book["title"],
        "recommendations": rec_books
    }


@app.get("/tags")
def list_tags(page: int = 1, page_size: int = Query(10, le=100)):
    total = db.tags.count_documents({})
    cursor = (
        db.tags.find({}, {"_id": 0})
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    tags = list(cursor)

    for t in tags:
        count = db.book_tags.count_documents({"tag_id": t["tag_id"]})
        t["book_count"] = count

    return {
        "items": tags,
        "page": page,
        "page_size": page_size,
        "total": total,
    }


@app.get("/users/{user_id}/to-read")
def get_to_read(user_id: int, page: int = 1, page_size: int = Query(10, le=100)):
    filt = {"user_id": user_id}
    total = db.to_read.count_documents(filt)

    cursor = (
        db.to_read.find(filt, {"_id": 0, "book_id": 1})
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    to_read_items = list(cursor)

    book_ids = [item["book_id"] for item in to_read_items]
    books = list(db.books.find({"book_id": {"$in": book_ids}}, {"_id": 0}))

    return {
        "user_id": user_id,
        "items": books,
        "page": page,
        "page_size": page_size,
        "total": total,
    }

@app.get("/books/{book_id}/ratings/summary")
def get_ratings_summary(book_id: int):
    pipeline = [
        {"$match": {"book_id": book_id}},
        {"$group": {
            "_id": "$rating",
            "count": {"$sum": 1}
        }}
    ]

    results = list(db.ratings.aggregate(pipeline))

    if not results:
        raise HTTPException(status_code=404, detail="No ratings found for this book")

    histogram = {str(i): 0 for i in range(1, 6)}
    total = 0
    sum_ratings = 0

    for r in results:
        rating = r["_id"]
        count = r["count"]
        histogram[str(rating)] = count
        total += count
        sum_ratings += rating * count

    avg_rating = round(sum_ratings / total, 2)

    return {
        "book_id": book_id,
        "average_rating": avg_rating,
        "ratings_count": total,
        "histogram": histogram
    }

@app.post("/ratings", dependencies=[Depends(require_api_key)])
def upsert_rating(r: RatingIn):
    result = db.ratings.update_one(
        {"user_id": r.user_id, "book_id": r.book_id},
        {"$set": r.dict()},
        upsert=True
    )

    if result.upserted_id:
        return {"status": "created", "user_id": r.user_id, "book_id": r.book_id, "rating": r.rating}
    elif result.modified_count > 0:
        return {"status": "updated", "user_id": r.user_id, "book_id": r.book_id, "rating": r.rating}
    else:
        return {"status": "no_change", "user_id": r.user_id, "book_id": r.book_id, "rating": r.rating}


from fastapi.responses import JSONResponse

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled error for {request.url.path}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Please try again later."},
    )