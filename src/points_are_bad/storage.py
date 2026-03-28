from __future__ import annotations

import json
import os

DATA_FILE = os.environ.get("POINTS_DATA_FILE", "points_are_bad_data.json")


def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return json.load(f)
    return {"players": [], "races": []}


def save_data(data: dict) -> None:
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)
