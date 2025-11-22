import os
from typing import List, Dict, Any

DAT_DIR = "/app/docs/Information"


def parse_trips() -> List[Dict[str, Any]]:
    trips = []
    with open(os.path.join(DAT_DIR, "FILE1.DAT"), "r") as f:
        lines = f.readlines()

    num_drom = 0
    start_idx = 0

    for i, line in enumerate(lines):
        if line.strip() == "[NumOfDrom]":
            num_drom = int(lines[i + 1].strip())
        if line.strip() == "[ListOfDrom]":
            start_idx = i + 1
            break

    trip_count = 0
    for line in lines[start_idx:]:
        if trip_count >= num_drom:
            break
        if line.strip().startswith("["):
            break
        if line.strip():
            parts = line.split()
            if len(parts) >= 11:
                start_time = parts[8]
                end_time = parts[9]

                start_hour = int(start_time[:2]) % 24
                start_min = int(start_time[2:])
                end_hour = int(end_time[:2]) % 24
                end_min = int(end_time[2:])

                trip = {
                    "id": parts[0],
                    "start_station": parts[1],
                    "end_station": parts[2],
                    "start_time": f"{start_hour:02d}:{start_min:02d}",
                    "end_time": f"{end_hour:02d}:{end_min:02d}",
                    "start_minutes": start_hour * 60 + start_min,
                    "end_minutes": (
                        end_hour * 60 + end_min
                        if end_hour * 60 + end_min > start_hour * 60 + start_min
                        else (end_hour * 60 + end_min) + 24 * 60
                    ),
                }
                trips.append(trip)
                trip_count += 1

    return trips


def parse_drivers() -> List[Dict[str, Any]]:
    return []


def parse_travel_matrix() -> Dict[str, Any]:
    matrix = {}
    for file in ["FILE3.DAT", "FILE4.DAT"]:
        with open(os.path.join(DAT_DIR, file), "r") as f:
            lines = f.readlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line == "[Joints]":
                i += 1
                break
            i += 1
        for line in lines[i:]:
            if line.strip():
                parts = line.split()
                if len(parts) >= 3:
                    key = f"{parts[0]}-{parts[1]}"
                    matrix[key] = int(parts[2])
    return matrix
