# models.py
from dataclasses import dataclass, field
from typing import Optional, List

@dataclass
class Card:
    """Represents an MTG card (subset of Scryfall’s data), including color identity."""
    id: str
    name: str
    mana_cost: Optional[str]
    type_line: str
    oracle_text: Optional[str]
    set_name: str
    rarity: str
    image_url: Optional[str]
    colors: List[str]  # e.g. ["R"], ["W","U"], or [] for colorless

    @classmethod
    def from_scryfall_json(cls, data: dict) -> "Card":
        return cls(
            id=data["id"],
            name=data["name"],
            mana_cost=data.get("mana_cost"),
            type_line=data["type_line"],
            oracle_text=data.get("oracle_text"),
            set_name=data["set_name"],
            rarity=data["rarity"],
            image_url=data.get("image_uris", {}).get("normal"),
            colors=data.get("colors", []),
        )

@dataclass
class Deck:
    """Keeps track of cards and quantities in a deck."""
    name: str
    cards: dict[str, int] = field(default_factory=dict)
    # Example: {"Lightning Bolt": 4, "Island": 24, ...}

    def add_card(self, card_name: str, qty: int = 1):
        self.cards[card_name] = self.cards.get(card_name, 0) + qty

    def remove_card(self, card_name: str, qty: int = 1):
        if card_name in self.cards:
            new_qty = self.cards[card_name] - qty
            if new_qty > 0:
                self.cards[card_name] = new_qty
            else:
                del self.cards[card_name]

    def total_cards(self) -> int:
        return sum(self.cards.values())

    def to_dict(self) -> dict:
        return {"name": self.name, "cards": self.cards}

    @classmethod
    def from_dict(cls, data: dict) -> "Deck":
        deck = cls(name=data["name"])
        deck.cards = data["cards"]
        return deck
