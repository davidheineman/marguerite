"""Build schedule.json from Stanford's Marguerite GTFS feed.

The live ETA API only lists buses already on their way, so the app uses this
timetable to fill in later departures. Rerun when the feed changes:

    python3 build_schedule.py
"""

import csv
import io
import json
import urllib.request
import zipfile
from collections import defaultdict

GTFS_URL = "https://transportation-forms.stanford.edu/google/google_transit.zip"

# GTFS route_id -> label used in index.html
ROUTES = {"19": "C", "20": "CL", "21": "P", "15": "X", "16": "Y", "4": "YE", "25": "YL"}
# GTFS stop_id (the # on the stop sign)
STOPS = {"18", "80", "96", "75", "103"}


def read(zf, name):
    with zf.open(name) as f:
        return list(csv.DictReader(io.TextIOWrapper(f, "utf-8-sig")))


def minutes(hms):
    h, m, _ = map(int, hms.split(":"))
    return h * 60 + m


def main():
    with urllib.request.urlopen(GTFS_URL, timeout=60) as resp:
        zf = zipfile.ZipFile(io.BytesIO(resp.read()))

    trips = {t["trip_id"]: t for t in read(zf, "trips.txt") if t["route_id"] in ROUTES}

    stop_times = defaultdict(list)
    for st in read(zf, "stop_times.txt"):
        if st["trip_id"] in trips:
            stop_times[st["trip_id"]].append(st)

    departures = defaultdict(list)
    used_services = set()
    for trip_id, sts in stop_times.items():
        sts.sort(key=lambda s: int(s["stop_sequence"]))
        trip = trips[trip_id]
        # ETA Spot identifies a trip by its start time, e.g. scheduleNumber "18:38:00-21".
        trip_start = minutes(sts[0]["departure_time"])
        # The last stop of a trip is a drop-off only.
        for st in sts[:-1]:
            if st["stop_id"] in STOPS and st["pickup_type"] != "1":
                departures[st["stop_id"]].append(
                    [ROUTES[trip["route_id"]], trip["service_id"], minutes(st["departure_time"]), trip_start]
                )
                used_services.add(trip["service_id"])

    for deps in departures.values():
        deps.sort(key=lambda d: d[2])

    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    services = {
        c["service_id"]: {
            "days": [int(c[d]) for d in days],
            "start": c["start_date"],
            "end": c["end_date"],
        }
        for c in read(zf, "calendar.txt")
        if c["service_id"] in used_services
    }
    exceptions = defaultdict(lambda: {"add": [], "remove": []})
    for cd in read(zf, "calendar_dates.txt"):
        if cd["service_id"] in used_services:
            key = "add" if cd["exception_type"] == "1" else "remove"
            exceptions[cd["date"]][key].append(cd["service_id"])

    out = {"services": services, "exceptions": exceptions, "departures": departures}
    with open("schedule.json", "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print({stop: len(d) for stop, d in departures.items()})


if __name__ == "__main__":
    main()
