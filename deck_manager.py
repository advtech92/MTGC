# deck_manager.py
import json
import os
from models import Deck

DECKS_DIR = "data/decks"

def save_deck(deck: Deck):
    os.makedirs(DECKS_DIR, exist_ok=True)
    filepath = os.path.join(DECKS_DIR, f"{deck.name}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(deck.to_dict(), f, indent=2)

def load_deck(name: str) -> Deck | None:
    filepath = os.path.join(DECKS_DIR, f"{name}.json")
    if not os.path.isfile(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Deck.from_dict(data)

def list_saved_decks() -> list[str]:
    if not os.path.isdir(DECKS_DIR):
        return []
    return [fname[:-5] for fname in os.listdir(DECKS_DIR) if fname.endswith(".json")]
