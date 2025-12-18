import json
import os
from pathlib import Path
from typing import List, Dict, Any

DATA_FILE = "/app/data.json"


def load_data() -> Dict[str, Any]:
    """Load the structured data from data.json"""
    try:
        local_path = Path(__file__).resolve().parent.parent / "data.json"
        if local_path.exists():
            with open(local_path, "r", encoding="utf-8") as f:
                return json.load(f)

        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print("Warning: data.json not found, falling back to DAT parsing")
        return {}


_data_cache = None


def get_data() -> Dict[str, Any]:
    """Get cached data or load from file"""
    global _data_cache
    if _data_cache is None:
        _data_cache = load_data()
    return _data_cache


def parse_trips() -> List[Dict[str, Any]]:
    """Get trips from the structured data"""
    data = get_data()
    return data.get("trips", [])


def parse_drivers() -> List[Dict[str, Any]]:
    """Get drivers/resources from the structured data"""
    data = get_data()
    return data.get("resources", [])


def parse_travel_matrix() -> Dict[str, Any]:
    """Get station transfer matrix from the structured data"""
    data = get_data()
    matrix = data.get("stationTransferMatrix", {}).get("matrix", [])
    result = {}
    for i, row in enumerate(matrix):
        for j, val in enumerate(row):
            if val != "NONE":
                result[f"{i}-{j}"] = 1 if val == "BREAK" else 2
    return result


def get_full_data() -> Dict[str, Any]:
    """Get the complete structured data"""
    return get_data()
