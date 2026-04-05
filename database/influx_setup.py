from influxdb_client import InfluxDBClient
from dotenv import load_dotenv
import os


def main() -> None:
    load_dotenv()

    url = os.getenv("INFLUXDB_URL", "http://localhost:8086")
    token = os.getenv("INFLUXDB_TOKEN", "")
    org = os.getenv("INFLUXDB_ORG", "dsfst-org")
    bucket_name = os.getenv("INFLUXDB_BUCKET", "dsfst-bucket")

    if not token:
        print("InfluxDB token not found in .env")
        print("Please complete InfluxDB initial setup first and update INFLUXDB_TOKEN.")
        return

    client = None

    try:
        client = InfluxDBClient(url=url, token=token, org=org)
        buckets_api = client.buckets_api()

        existing_bucket = buckets_api.find_bucket_by_name(bucket_name)

        if existing_bucket:
            print(f"Bucket already exists: {bucket_name}")
        else:
            orgs_api = client.organizations_api()
            org_obj = orgs_api.find_organizations(org=org)

            if not org_obj:
                print(f"Organization '{org}' not found.")
                return

            buckets_api.create_bucket(bucket_name=bucket_name, org_id=org_obj[0].id)
            print(f"Created bucket: {bucket_name}")

        print("\nInfluxDB setup completed successfully.")

    except Exception as error:
        print(f"InfluxDB setup failed: {error}")

    finally:
        if client:
            client.close()


if __name__ == "__main__":
    main()