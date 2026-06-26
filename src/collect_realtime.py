# collect_realtime.py
#
# Consolidated version of six near-identical fetch_departures_script_N.py files
# used during data collection. The original collection ran six copies in
# parallel, each covering a different slice of stop_ids (ranked by trip
# frequency), to fetch more stops per minute without exceeding the API's
# rate limits. This script keeps that same logic but takes the stop_id
# rank range as a parameter instead of having it hardcoded six times.
#
# Requires HAFAS_ACCESS_ID and HAFAS_BASE_URL environment variables (see
# .env.example). The base URL is not hardcoded here pending confirmation
# of whether HAFAS's terms of service allow publishing the endpoint.

import sqlite3
import requests
import time
import logging
import os
import argparse
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("HAFAS_ACCESS_ID")
if not API_KEY:
    raise RuntimeError("Missing HAFAS_ACCESS_ID environment variable. See .env.example.")

API_URL = os.environ.get("HAFAS_BASE_URL")
if not API_URL:
    raise RuntimeError("Missing HAFAS_BASE_URL environment variable. See .env.example.")

DB_PATH = os.environ.get("TRANSPORT_DB_PATH", "data/transport_data.db")
LOG_FILE = os.environ.get("COLLECT_LOG_FILE", "logs/collect_realtime.log")
SLEEP_BETWEEN_CALLS = 0.3
DB_RETRY_LIMIT = 3
DB_RETRY_DELAY = 2  # seconds

os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")


def get_ranked_stop_ids(rank_start, rank_end):
    logging.info(f"Ranking stop_ids by trip frequency, rank {rank_start}-{rank_end}.")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        WITH ranked_stops AS (
            SELECT
                stop_id,
                COUNT(DISTINCT trip_id) AS trip_count,
                RANK() OVER (ORDER BY COUNT(DISTINCT trip_id) DESC) AS rank
            FROM stop_times
            GROUP BY stop_id
        )
        SELECT stop_id FROM ranked_stops
        WHERE rank BETWEEN ? AND ?
        ORDER BY rank;
    """, (rank_start, rank_end))
    stop_ids = [row[0] for row in cursor.fetchall()]
    conn.close()
    logging.info(f"{len(stop_ids)} stop_ids selected.")
    return stop_ids


def get_stop_names(stop_ids):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT stop_id, stop_name FROM stops
        WHERE stop_id IN ({','.join(['?'] * len(stop_ids))})
    """, stop_ids)
    result = dict(cursor.fetchall())
    conn.close()
    return result


def fetch_departures_for_stop(stop_id):
    params = {
        "accessId": API_KEY,
        "id": stop_id,
        "format": "json"
    }
    try:
        response = requests.get(API_URL, params=params, timeout=10)
        response.raise_for_status()
        return response.json().get("Departure", [])
    except Exception as e:
        logging.error(f"Error fetching departures for stop {stop_id}: {e}")
        return []


def parse_departure(entry, stop_id, stop_name):
    planned_time = f"{entry.get('date')} {entry.get('time')}"
    real_time = None
    if entry.get("rtDate") and entry.get("rtTime"):
        real_time = f"{entry.get('rtDate')} {entry.get('rtTime')}"

    delay_minutes = None
    if planned_time and real_time:
        try:
            pt = datetime.strptime(planned_time, "%Y-%m-%d %H:%M:%S")
            rt = datetime.strptime(real_time, "%Y-%m-%d %H:%M:%S")
            delay_minutes = round((rt - pt).total_seconds() / 60, 1)
        except Exception:
            pass

    return (
        stop_id,
        stop_name,
        entry.get("line"),
        entry.get("direction"),
        entry.get("JourneyDetailRef", {}).get("ref"),
        planned_time,
        real_time,
        delay_minutes,
        entry.get("reachable"),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        entry.get("routeIdxFrom"),
        entry.get("routeIdxTo"),
        entry.get("ProductAtStop", {}).get("operator"),
        entry.get("ProductAtStop", {}).get("catOut"),
        entry.get("ProductAtStop", {}).get("catOutL")
    )


def save_departures_to_db(rows):
    for attempt in range(DB_RETRY_LIMIT):
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.executemany("""
                INSERT OR REPLACE INTO departures_live (
                    stop_id, stop_name, line, direction, trip_id,
                    planned_time, real_time, delay_minutes, reachable,
                    collected_at, route_index_from, route_index_to,
                    operator, category, transport_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, rows)
            conn.commit()
            conn.close()
            return
        except sqlite3.OperationalError as e:
            logging.warning(f"Error writing to database: {e}. Retrying ({attempt+1}/{DB_RETRY_LIMIT})...")
            time.sleep(DB_RETRY_DELAY)
    logging.error("Failed to write to the database after multiple retries.")


def main():
    parser = argparse.ArgumentParser(description="Fetch real-time departures for a range of ranked stop_ids.")
    parser.add_argument("--rank-start", type=int, default=1, help="First stop rank to fetch (default: 1)")
    parser.add_argument("--rank-end", type=int, default=2780, help="Last stop rank to fetch (default: 2780, covers all stops)")
    args = parser.parse_args()

    logging.info(f"==== Starting collection, ranks {args.rank_start}-{args.rank_end} ====")
    start = datetime.now()

    stop_ids = get_ranked_stop_ids(args.rank_start, args.rank_end)
    stop_names = get_stop_names(stop_ids)

    all_rows = []
    for i, stop_id in enumerate(stop_ids):
        stop_name = stop_names.get(stop_id, "")
        departures = fetch_departures_for_stop(stop_id)
        for entry in departures:
            row = parse_departure(entry, stop_id, stop_name)
            all_rows.append(row)
        logging.info(f"[{i+1}/{len(stop_ids)}] processed stop_id={stop_id}")
        time.sleep(SLEEP_BETWEEN_CALLS)

    save_departures_to_db(all_rows)
    end = datetime.now()
    logging.info(f"==== Collection finished. Start: {start}, End: {end}, Total rows: {len(all_rows)} ====")


if __name__ == "__main__":
    main()
