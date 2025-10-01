import os, time
import pandas as pd
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://goodbooks_db:27017")
DB_NAME = os.getenv("DB_NAME", "goodbooks")
INGEST_MODE = os.getenv("INGEST_MODE", "sample").strip().lower()
BATCH_SIZE = int(os.getenv("BATCH_SIZE", 1000))

# Wait for MongoDB to be ready
for attempt in range(10):
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
        client.server_info()
        print("MongoDB is ready")
        break
    except ServerSelectionTimeoutError:
        print(f"Waiting for MongoDB... attempt {attempt+1}")
        time.sleep(2)
else:
    raise Exception("MongoDB not reachable")

db = client[DB_NAME]

BASE_URL = "https://raw.githubusercontent.com/zygmuntz/goodbooks-10k/master/"

datasets = {
    "books": "samples/books.csv" if INGEST_MODE == "sample" else "books.csv",
    "ratings": "samples/ratings.csv" if INGEST_MODE == "sample" else "ratings.csv",
    "tags": "samples/tags.csv" if INGEST_MODE == "sample" else "tags.csv",
    "book_tags": "samples/book_tags.csv" if INGEST_MODE == "sample" else "book_tags.csv",
    "to_read": "samples/to_read.csv" if INGEST_MODE == "sample" else "to_read.csv",
}

def cast_types(collection, df):
    if collection == "books":
        df["book_id"] = df["book_id"].astype(int)
        df["goodreads_book_id"] = df["goodreads_book_id"].astype(int)
        df["original_publication_year"] = pd.to_numeric(df["original_publication_year"], errors="coerce").fillna(0).astype(int)
        df["average_rating"] = pd.to_numeric(df["average_rating"], errors="coerce").fillna(0).astype(float)
        df["ratings_count"] = pd.to_numeric(df["ratings_count"], errors="coerce").fillna(0).astype(int)
    elif collection == "ratings":
        df["user_id"] = df["user_id"].astype(int)
        df["book_id"] = df["book_id"].astype(int)
        df["rating"] = df["rating"].astype(int)
    elif collection == "tags":
        df["tag_id"] = df["tag_id"].astype(int)
    elif collection == "book_tags":
        df["goodreads_book_id"] = df["goodreads_book_id"].astype(int)
        df["tag_id"] = df["tag_id"].astype(int)
        df["count"] = df["count"].astype(int)
    elif collection == "to_read":
        df["user_id"] = df["user_id"].astype(int)
        df["book_id"] = df["book_id"].astype(int)
    return df

for collection, path in datasets.items():
    url = BASE_URL + path
    print(f"Ingesting {collection} from {url}")
    df = pd.read_csv(url)
    df = cast_types(collection, df)
    records = df.to_dict(orient="records")

    # Only insert if collection is empty
    if records and db[collection].count_documents({}) == 0:
        for i in range(0, len(records), BATCH_SIZE):
            batch = records[i:i+BATCH_SIZE]
            db[collection].insert_many(batch)

print("Ingestion complete")
