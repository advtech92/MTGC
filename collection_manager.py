# collection_manager.py

import os
import json

COLLECTION_FILE = os.path.join("data", "collection.json")

def load_collection() -> dict[str, int]:
    """
    Returns a dict of card_name → quantity in your collection.
    If the file doesn’t exist, returns an empty dict.
    """
    if not os.path.isdir(os.path.dirname(COLLECTION_FILE)):
        os.makedirs(os.path.dirname(COLLECTION_FILE), exist_ok=True)
    if not os.path.isfile(COLLECTION_FILE):
        return {}
    try:
        with open(COLLECTION_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {str(k): int(v) for k, v in data.items()}
    except json.JSONDecodeError:
        return {}

def save_collection(collection: dict[str, int]) -> None:
    """
    Writes your collection (card_name → quantity) to disk.
    """
    if not os.path.isdir(os.path.dirname(COLLECTION_FILE)):
        os.makedirs(os.path.dirname(COLLECTION_FILE), exist_ok=True)
    with open(COLLECTION_FILE, "w", encoding="utf-8") as f:
        json.dump(collection, f, indent=2)

def list_collection() -> list[tuple[str, int]]:
    """
    Returns a sorted list of (card_name, qty) from your collection.
    """
    coll = load_collection()
    return sorted(coll.items(), key=lambda x: x[0].lower())
