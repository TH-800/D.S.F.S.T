from pymongo import MongoClient
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from dotenv import load_dotenv
from datetime import datetime, UTC
import os
import uuid


def insert_mongo_sample_data() -> None:
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
    db_name = os.getenv("MONGO_DB_NAME", "dsfst")

    client = None

    try:
        client = MongoClient(mongo_uri)
        db = client[db_name]

        now = datetime.now(UTC)

        experiment_id = str(uuid.uuid4())
        log_id = str(uuid.uuid4())

        experiment = {
            "experiment_id": experiment_id,
            "name": "CPU Stress Test",
            "failure_type": "cpu_stress",
            "target_container": "service-a",
            "parameters": {
                "cpu_load_percent": 80,
                "duration_seconds": 60
            },
            "status": "created",
            "created_at": now,
            "started_at": None,
            "ended_at": None
        }

        user = {
            "user_id": str(uuid.uuid4()),
            "name": "Mayank Surani",
            "email": "mayank@example.com",
            "role": "developer",
            "created_at": now
        }

        log = {
            "log_id": log_id,
            "experiment_id": experiment_id,
            "event_type": "info",
            "message": "Experiment created successfully",
            "timestamp": now
        }

        db["experiments"].update_one(
            {"experiment_id": experiment_id},
            {"$set": experiment},
            upsert=True
        )

        db["users"].update_one(
            {"email": user["email"]},
            {"$set": user},
            upsert=True
        )

        db["logs"].update_one(
            {"log_id": log_id},
            {"$set": log},
            upsert=True
        )

        print("✅ Inserted/updated MongoDB sample data successfully.")

    except Exception as error:
        print(f"❌ MongoDB insert failed: {error}")

    finally:
        if client:
            client.close()


def insert_influx_sample_data() -> None:
    url = os.getenv("INFLUXDB_URL", "http://localhost:8086")
    token = os.getenv("INFLUXDB_TOKEN", "")
    org = os.getenv("INFLUXDB_ORG", "dsfst-org")
    bucket = os.getenv("INFLUXDB_BUCKET", "dsfst-bucket")

    if not token:
        print("⚠️ InfluxDB token not found. Skipping InfluxDB sample data.")
        return

    client = None

    try:
        client = InfluxDBClient(url=url, token=token, org=org)
        write_api = client.write_api(write_options=SYNCHRONOUS)

        now = datetime.now(UTC)

        points = [
            Point("cpu")
            .tag("container_id", "service-a")
            .field("cpu_usage_percent", 76.5)
            .time(now, WritePrecision.NS),

            Point("memory")
            .tag("container_id", "service-a")
            .field("memory_used_mb", 512.0)
            .field("memory_percent", 62.3)
            .time(now, WritePrecision.NS),

            Point("network")
            .tag("container_id", "service-a")
            .field("latency_ms", 120.5)
            .field("packet_loss_percent", 0.5)
            .field("throughput_kbps", 2048.0)
            .time(now, WritePrecision.NS)
        ]

        write_api.write(bucket=bucket, org=org, record=points)

        print("✅ Inserted InfluxDB sample data successfully.")

    except Exception as error:
        print(f"❌ InfluxDB insert failed: {error}")

    finally:
        if client:
            client.close()


def main() -> None:
    load_dotenv()

    insert_mongo_sample_data()
    insert_influx_sample_data()


if __name__ == "__main__":
    main()