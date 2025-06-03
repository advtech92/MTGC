# mtg_api.py
import requests
import sqlite3
import os
from models import Card

SCRYFALL_SEARCH_URL = "https://api.scryfall.com/cards/search"
SCRYFALL_CARD_URL   = "https://api.scryfall.com/cards/named"

CACHE_DB_PATH = os.path.join("data", "cards_cache.sqlite")

def init_cache_db():
    """Create local SQLite DB (if not exists) with a simple table for cards."""
    os.makedirs(os.path.dirname(CACHE_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(CACHE_DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS cards (
            id TEXT PRIMARY KEY,
            name TEXT UNIQUE,
            json_data TEXT
        )
    """)
    conn.commit()
    conn.close()

def get_card_by_name(name: str, use_cache: bool = True) -> Card | None:
    """
    1. If use_cache is True, check SQLite for card JSON. 
    2. If not found, call Scryfall named endpoint, store JSON in cache, then return Card.
    """
    if use_cache:
        conn = sqlite3.connect(CACHE_DB_PATH)
        c = conn.cursor()
        c.execute("SELECT json_data FROM cards WHERE name = ?", (name.lower(),))
        row = c.fetchone()
        if row:
            import json
            data = json.loads(row[0])
            conn.close()
            return Card.from_scryfall_json(data)
        conn.close()

    # Not in cache (or no cache). Fetch from Scryfall by exact name.
    params = {"exact": name}
    res = requests.get(SCRYFALL_CARD_URL, params=params)
    if res.status_code != 200:
        return None  # card not found or API error
    data = res.json()

    # Insert into cache
    if use_cache:
        conn = sqlite3.connect(CACHE_DB_PATH)
        c = conn.cursor()
        import json
        c.execute(
            "INSERT OR IGNORE INTO cards (id, name, json_data) VALUES (?, ?, ?)",
            (data["id"], data["name"].lower(), json.dumps(data))
        )
        conn.commit()
        conn.close()

    return Card.from_scryfall_json(data)

def search_cards(query: str, use_cache: bool = False) -> list[Card]:
    """
    Use Scryfall’s search endpoint. Returns up to 175 cards by default.
    query examples:
      - "name:Lightning Bolt"
      - "type:creature cmc<=2"
      - "c:red c:creature"  (red creatures)
    """
    params = {"q": query, "unique": "cards", "order": "name", "dir": "asc"}
    res = requests.get(SCRYFALL_SEARCH_URL, params=params)
    if res.status_code != 200:
        return []
    data = res.json()
    card_list = [Card.from_scryfall_json(card) for card in data.get("data", [])]
    return card_list
