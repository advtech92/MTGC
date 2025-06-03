# battle_simulator.py
import random
import json
import os

# Basic land names for simplicity:
BASIC_LANDS = {"Plains", "Island", "Swamp", "Mountain", "Forest"}

# Path for manual match history
MATCH_HISTORY_FILE = os.path.join("data", "match_history.json")

def _deck_to_list(deck):
    """
    Convert Deck.cards (dict of name: qty) into a flat list of card names.
    """
    card_list = []
    for name, qty in deck.cards.items():
        card_list.extend([name] * qty)
    return card_list

def simulate_hand(deck, hand_size=7):
    """
    Simulate drawing an opening hand from the deck.
    Returns True if the hand has between 2 and 5 lands (inclusive), else False.
    """
    deck_list = _deck_to_list(deck)
    if len(deck_list) < hand_size:
        return False
    hand = random.sample(deck_list, hand_size)
    land_count = sum(1 for card in hand if card in BASIC_LANDS)
    return 2 <= land_count <= 5

def simulate_match(deck1, deck2, iterations=1000):
    """
    Simulate a match between deck1 and deck2 over 'iterations' games.
    For each game, both decks draw an opening hand; if one hits the land range
    and the other doesn't, that deck wins; if both hit or both miss, it's a tie.
    Returns (wins1, wins2, ties).
    """
    wins1 = wins2 = ties = 0
    for _ in range(iterations):
        result1 = simulate_hand(deck1)
        result2 = simulate_hand(deck2)
        if result1 and not result2:
            wins1 += 1
        elif result2 and not result1:
            wins2 += 1
        else:
            ties += 1
    return wins1, wins2, ties

def load_match_history():
    """
    Load manual match history from JSON. Returns a list of records:
      [{"deck": "DeckName", "opponent": "OppName", "result": "W"|"L"|"T"}, ...]
    If file doesn't exist, returns [].
    """
    if not os.path.isdir(os.path.dirname(MATCH_HISTORY_FILE)):
        os.makedirs(os.path.dirname(MATCH_HISTORY_FILE), exist_ok=True)
    if not os.path.isfile(MATCH_HISTORY_FILE):
        return []
    try:
        with open(MATCH_HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []

def save_match_history(history):
    """
    Save the list of match records to disk.
    """
    if not os.path.isdir(os.path.dirname(MATCH_HISTORY_FILE)):
        os.makedirs(os.path.dirname(MATCH_HISTORY_FILE), exist_ok=True)
    with open(MATCH_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)

def record_manual_result(deck_name, opponent_name, result):
    """
    Append a manual result to match history. 'result' should be "W", "L", or "T".
    """
    history = load_match_history()
    history.append({"deck": deck_name, "opponent": opponent_name, "result": result})
    save_match_history(history)
