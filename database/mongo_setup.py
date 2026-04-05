from pymongo import MongoClient
from pymongo.errors import PyMongoError
from dotenv import load_dotenv
import os


def main() -> None:
    load_dotenv()

    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
    db_name = os.getenv("MONGO_DB_NAME", "dsfst")

    try:
        client = MongoClient(mongo_uri)
        db = client[db_name]

        # Create collections if they do not exist
        existing_collections = db.list_collection_names()

        required_collections = ["experiments", "logs", "users"]

        for collection_name in required_collections:
            if collection_name not in existing_collections:
                db.create_collection(collection_name)
                print(f"Created collection: {collection_name}")
            else:
                print(f"Collection already exists: {collection_name}")

        # Create indexes
        db["experiments"].create_index("experiment_id", unique=True)
        db["logs"].create_index("log_id", unique=True)
        db["logs"].create_index("experiment_id")
        db["users"].create_index("user_id", unique=True)
        db["users"].create_index("email", unique=True)

        print(f"\nMongoDB setup completed successfully for database: {db_name}")

    except PyMongoError as error:
        print(f"MongoDB setup failed: {error}")

    finally:
        client.close()


if __name__ == "__main__":
    main()