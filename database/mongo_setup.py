from pymongo import MongoClient
from pymongo.errors import PyMongoError
from dotenv import load_dotenv
import os


def main() -> None:
    """
    Initialize the MongoDB database used by D.S.F.S.T.

    This script:
    - Connects to MongoDB using environment configuration.
    - Creates required collections if they do not already exist.
    - Creates indexes used by the application.
    - Can be safely executed multiple times.
    """

    load_dotenv()

    mongo_uri = os.getenv(
        "MONGO_URI",
        "mongodb://localhost:27017/"
    )

    db_name = os.getenv(
        "MONGO_DB_NAME",
        "dsfst"
    )

    client = None

    try:

        client = MongoClient(
            mongo_uri,
            serverSelectionTimeoutMS=5000
        )

        client.admin.command("ping")

        db = client[db_name]

        print(f"Connected to MongoDB: {db_name}")


        existing_collections = db.list_collection_names()

        required_collections = [
            "experiments",
            "logs",
            "users",
            "virtual_machines",
            "saved_presets"
        ]

        for collection_name in required_collections:
            if collection_name not in existing_collections:
                db.create_collection(collection_name)
                print(f"Created collection: {collection_name}")
            else:
                print(f"Collection already exists: {collection_name}")


        db["experiments"].create_index(
            "experiment_id",
            unique=True
        )


        db["logs"].create_index(
            "log_id",
            unique=True
        )

        db["logs"].create_index(
            "experiment_id"
        )


        db["users"].create_index(
            "user_id",
            unique=True
        )

        db["users"].create_index(
            "email",
            unique=True
        )


        vm_collection = db["virtual_machines"]

        vm_collection.create_index(
            "vm_id",
            unique=True
        )

        vm_collection.create_index(
            "name",
            unique=True
        )

        vm_collection.create_index(
            "ip"
        )

        vm_collection.create_index(
            "status"
        )

        print("VM Registry indexes configured successfully.")


        preset_collection = db["saved_presets"]

        preset_collection.create_index(
            "preset_id",
            unique=True
        )

        preset_collection.create_index(
            "name",
            unique=True
        )

        preset_collection.create_index(
            "failure_type"
        )

        preset_collection.create_index(
            "created_by"
        )

        print("Saved Presets indexes configured successfully.")


        print("\nAvailable MongoDB collections:")

        for collection_name in sorted(db.list_collection_names()):
            print(f" - {collection_name}")

        print(
            f"\nMongoDB setup completed successfully "
            f"for database: {db_name}"
        )

    except PyMongoError as error:
        print(f"MongoDB setup failed: {error}")
        raise

    finally:
        # Always close the MongoDB client when setup finishes
        if client is not None:
            client.close()


if __name__ == "__main__":
    main()