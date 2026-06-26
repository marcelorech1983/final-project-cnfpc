import os
import sqlite3
import requests
import zipfile
import shutil
import logging
import csv
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DATA_URL ="https://download.data.public.lu/resources/horaires-et-arrets-des-transport-publics-gtfs/20250718-071118/gtfs-20250717-20250817.zip"
DOWNLOAD_FOLDER = os.environ.get("GTFS_DOWNLOAD_FOLDER", "data/gtfs_dl")
DB_PATH = os.environ.get("TRANSPORT_DB_PATH", "data/transport_data.db")
LOG_FILE = os.environ.get("COLLECT_LOG_FILE", "logs/gtfs_update.log")

# Expected tables and their merge/replace keys
VALID_GTFS_TABLES = {
    "agency", "calendar", "calendar_dates", "frequencies", "routes", "shapes",
    "stop_times", "stops", "transfers", "trips"
}

DELETION_KEYS = {
    "agency": "agency_id",
    "calendar": "service_id",
    "calendar_dates": "service_id",
    "frequencies": "trip_id",
    "routes": "route_id",
    "shapes": "shape_id",
    "stop_times": "trip_id",
    "stops": "stop_id",
    "transfers": "from_stop_id",
    "trips": "trip_id"
}

os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")

def get_latest_feed_url():
    return DATA_URL  # TODO: scrape for the newest feed version instead of a fixed URL

def download_feed(url):
    os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
    local_zip = os.path.join(DOWNLOAD_FOLDER, os.path.basename(url))
    if os.path.exists(local_zip):
        logging.info(f"Feed already exists locally: {local_zip}")
        return None
    logging.info(f"Downloading GTFS from: {url}")
    r = requests.get(url, stream=True)
    r.raise_for_status()
    with open(local_zip, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)
    logging.info("Download complete.")
    return local_zip

def extract_and_import(zip_path):
    tmp_folder = os.path.join(DOWNLOAD_FOLDER, "tmp")
    if os.path.exists(tmp_folder):
        shutil.rmtree(tmp_folder)
    os.makedirs(tmp_folder)

    with zipfile.ZipFile(zip_path, 'r') as z:
        z.extractall(tmp_folder)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys=OFF;")
    cursor = conn.cursor()

    for fname in os.listdir(tmp_folder):
        if not fname.endswith(".txt"):
            continue

        table = fname.replace(".txt", "").lower().strip()

        if table not in VALID_GTFS_TABLES:
            logging.warning(f"Skipped: {fname} (unrecognized table)")
            continue

        path = os.path.join(tmp_folder, fname)
        logging.info(f"Starting import: {table}")

        with open(path, encoding="utf-8") as f:
            reader = csv.reader(f)
            headers = next(reader)
            headers = [h.strip() for h in headers]
            columns = ', '.join([f"{col} TEXT" for col in headers])
            insert_query = f"INSERT INTO temp_{table} ({', '.join(headers)}) VALUES ({','.join(['?'] * len(headers))})"
            rows = list(reader)

        cursor.execute(f"DROP TABLE IF EXISTS temp_{table}")
        cursor.execute(f"CREATE TABLE temp_{table} ({columns})")
        cursor.executemany(insert_query, rows)

        if table in DELETION_KEYS:
            key = DELETION_KEYS[table]
            try:
                cursor.execute(f"""
                    DELETE FROM {table}
                    WHERE {key} IN (
                        SELECT DISTINCT {key} FROM temp_{table}
                    )
                """)
                logging.info(f"Old records removed from table {table} based on '{key}'")
            except sqlite3.OperationalError as e:
                logging.warning(f"Error applying delete filter by key {key} on table {table}: {e}")
        else:
            logging.warning(f"No deletion key defined for {table}, old rows were not removed")

        cursor.execute(f"INSERT INTO {table} SELECT * FROM temp_{table}")
        cursor.execute(f"DROP TABLE temp_{table}")
        conn.commit()
        logging.info(f"{table} imported successfully. Rows inserted: {len(rows)}")

    conn.close()
    shutil.rmtree(tmp_folder)
    logging.info("GTFS import finished successfully.")

def main():
    logging.info("==== Starting automated GTFS update ====")
    url = get_latest_feed_url()
    zip_path = download_feed(url)
    if zip_path:
        extract_and_import(zip_path)
    else:
        logging.info("No new feed detected.")
    logging.info("==== Process finished ====")

if __name__ == "__main__":
    main()
