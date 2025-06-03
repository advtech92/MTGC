# main.py
import os
import io
import requests
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from PIL import Image, ImageTk

from mtg_api import init_cache_db, get_card_by_name, search_cards
from deck_manager import save_deck as dm_save_deck, load_deck, list_saved_decks
from models import Deck, Card

# -----------------------------------------------------------------------------
# Helper to detect lands
# -----------------------------------------------------------------------------
def is_land(card: Card) -> bool:
    return "Land" in card.type_line

# -----------------------------------------------------------------------------
# Main Application Window
# -----------------------------------------------------------------------------
class MTGDeckBuilder(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MTG Deck Builder")
        self.geometry("1000x600")

        # Ensure cache DB exists
        init_cache_db()

        # Currently loaded Deck
        self.current_deck: Deck | None = None

        # Local in‐memory cache: card_name → Card object
        self.card_cache: dict[str, Card] = {}

        # Keep references to PhotoImage so they do not get garbage‐collected
        self.preview_photo: ImageTk.PhotoImage | None = None
        self.color_icon_images: dict[str, ImageTk.PhotoImage] = {}

        # Build UI components
        self._load_color_icons()
        self._build_widgets()
        self._layout_widgets()

    # -----------------------------------------------------------------------------
    # Pre‐load color icon images from local `assets/icons`
    # -----------------------------------------------------------------------------
    def _load_color_icons(self):
        """
        Expects five PNG files in assets/icons: W.png, U.png, B.png, R.png, G.png
        """
        icon_folder = os.path.join("assets", "icons")
        for symbol in ["W", "U", "B", "R", "G"]:
            path = os.path.join(icon_folder, f"{symbol}.png")
            if os.path.isfile(path):
                img = Image.open(path).resize((32, 32), Image.LANCZOS)
                self.color_icon_images[symbol] = ImageTk.PhotoImage(img)
            else:
                self.color_icon_images[symbol] = None  # missing icon silently

    # -----------------------------------------------------------------------------
    # Create all widgets
    # -----------------------------------------------------------------------------
    def _build_widgets(self):
        # -- Deck Controls -------------------------------------------------------
        self.deck_frame = ttk.LabelFrame(self, text="Deck Controls", padding=10)
        self.new_deck_btn = ttk.Button(self.deck_frame, text="New Deck", command=self.new_deck)
        self.load_deck_btn = ttk.Button(self.deck_frame, text="Load Deck", command=self.load_deck)
        self.save_deck_btn = ttk.Button(self.deck_frame, text="Save Deck", command=self.save_deck)
        self.deck_name_label = ttk.Label(self.deck_frame, text="(no deck loaded)")

        # -- A container for the two main panels (Search and Deck) -------------
        self.content_frame = ttk.Frame(self)

        # -- Search / Add Cards -----------------------------------------------
        self.search_frame = ttk.LabelFrame(self.content_frame, text="Search / Add Cards", padding=10)
        self.search_entry = ttk.Entry(self.search_frame, width=40)
        self.search_btn = ttk.Button(self.search_frame, text="Search", command=self.perform_search)

        self.results_list = tk.Listbox(self.search_frame, height=12, width=50)
        self.result_scroll = ttk.Scrollbar(self.search_frame, orient="vertical", command=self.results_list.yview)
        self.results_list.configure(yscrollcommand=self.result_scroll.set)
        self.results_list.bind("<<ListboxSelect>>", self.on_result_select)

        self.add_qty_label = ttk.Label(self.search_frame, text="Quantity:")
        self.add_qty_spin = ttk.Spinbox(self.search_frame, from_=1, to=20, width=5)
        self.add_card_btn = ttk.Button(self.search_frame, text="Add to Deck", command=self.add_card_to_deck)

        # -- Card Preview (image + color icons) --------------------------------
        self.preview_frame = ttk.LabelFrame(self.search_frame, text="Card Preview", padding=10)
        # Label to show the card image
        self.card_image_label = ttk.Label(self.preview_frame)
        # Frame to hold 0–5 color icons horizontally
        self.color_icons_frame = ttk.Frame(self.preview_frame)

        # -- Deck Contents -----------------------------------------------------
        self.deck_view_frame = ttk.LabelFrame(self.content_frame, text="Deck Contents", padding=10)
        self.deck_list = tk.Listbox(self.deck_view_frame, height=20, width=40)
        self.deck_scroll = ttk.Scrollbar(self.deck_view_frame, orient="vertical", command=self.deck_list.yview)
        self.deck_list.configure(yscrollcommand=self.deck_scroll.set)
        self.deck_list.bind("<<ListboxSelect>>", self.on_deck_select)

        self.remove_card_btn = ttk.Button(self.deck_view_frame, text="Remove Selected", command=self.remove_selected)

    # -----------------------------------------------------------------------------
    # Arrange everything in the proper geometry
    # -----------------------------------------------------------------------------
    def _layout_widgets(self):
        # 1) Top ─ Deck controls (packed)
        self.deck_frame.pack(fill="x", padx=10, pady=5)
        self.new_deck_btn.grid(row=0, column=0, padx=5, pady=5)
        self.load_deck_btn.grid(row=0, column=1, padx=5, pady=5)
        self.save_deck_btn.grid(row=0, column=2, padx=5, pady=5)
        self.deck_name_label.grid(row=0, column=3, padx=10, pady=5, sticky="w")

        # 2) Middle ─ content_frame (packed)
        self.content_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.content_frame.columnconfigure(0, weight=1)
        self.content_frame.columnconfigure(1, weight=0)
        self.content_frame.rowconfigure(0, weight=1)

        # --- Left panel: Search / Add Cards (gridded inside content_frame) ---
        self.search_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.search_frame.columnconfigure(0, weight=1)
        self.search_frame.rowconfigure(1, weight=1)

        self.search_entry.grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.search_btn.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        self.results_list.grid(row=1, column=0, columnspan=2, padx=(5, 0), pady=5, sticky="nsew")
        self.result_scroll.grid(row=1, column=2, sticky="ns", pady=5)

        self.add_qty_label.grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.add_qty_spin.grid(row=2, column=1, padx=5, pady=5, sticky="w")
        self.add_card_btn.grid(row=2, column=2, padx=5, pady=5, sticky="w")

        # Preview frame sits below everything in the search_frame
        self.preview_frame.grid(row=3, column=0, columnspan=3, padx=5, pady=10, sticky="nsew")
        self.preview_frame.columnconfigure(0, weight=1)
        self.preview_frame.rowconfigure(0, weight=1)

        self.card_image_label.grid(row=0, column=0, padx=5, pady=5)
        self.color_icons_frame.grid(row=1, column=0, padx=5, pady=5)

        # --- Right panel: Deck Contents (gridded inside content_frame) ---
        self.deck_view_frame.grid(row=0, column=1, sticky="nsew")
        self.deck_view_frame.columnconfigure(0, weight=1)
        self.deck_view_frame.rowconfigure(0, weight=1)

        self.deck_list.grid(row=0, column=0, padx=(5, 0), pady=5, sticky="nsew")
        self.deck_scroll.grid(row=0, column=1, sticky="ns", pady=5)
        self.remove_card_btn.grid(row=1, column=0, padx=5, pady=5, sticky="w")

    # -----------------------------------------------------------------------------
    # Create a brand‐new Deck
    # -----------------------------------------------------------------------------
    def new_deck(self):
        name = simpledialog.askstring("New Deck", "Enter deck name:", parent=self)
        if not name:
            return
        self.current_deck = Deck(name=name)
        self.deck_name_label.config(text=f"Deck: {name} (0 cards)")
        self._refresh_deck_list()
        self._clear_preview()

    # -----------------------------------------------------------------------------
    # Load a saved Deck from disk
    # -----------------------------------------------------------------------------
    def load_deck(self):
        choices = list_saved_decks()
        if not choices:
            messagebox.showinfo("Load Deck", "No saved decks found.")
            return

        name = simpledialog.askstring(
            "Load Deck",
            f"Available: {', '.join(choices)}\nEnter deck name:",
            parent=self
        )
        if not name:
            return
        deck = load_deck(name)
        if deck:
            self.current_deck = deck
            self.deck_name_label.config(text=f"Deck: {deck.name} ({deck.total_cards()} cards)")
            self._refresh_deck_list()
            self._clear_preview()
        else:
            messagebox.showerror("Error", f"Deck '{name}' not found.")

    # -----------------------------------------------------------------------------
    # Save current Deck to disk
    # -----------------------------------------------------------------------------
    def save_deck(self):
        if not self.current_deck:
            messagebox.showwarning("Save Deck", "No deck loaded.")
            return
        dm_save_deck(self.current_deck)
        messagebox.showinfo("Save Deck", f"Deck '{self.current_deck.name}' saved.")

    # -----------------------------------------------------------------------------
    # Perform a Scryfall search and populate the listbox
    # -----------------------------------------------------------------------------
    def perform_search(self):
        query = self.search_entry.get().strip()
        if not query:
            return
        self.results_list.delete(0, tk.END)
        results = search_cards(query)
        if not results:
            self.results_list.insert(tk.END, "(no results)")
            return

        # Cache Card objects in memory
        for card in results:
            self.card_cache[card.name] = card

        for card in results:
            display = f"{card.name}  •  {card.mana_cost or ''}  •  {card.type_line}  [{card.rarity}]"
            self.results_list.insert(tk.END, display)

        # Clear any old preview
        self._clear_preview()

    # -----------------------------------------------------------------------------
    # When a search result is selected, show color icons + preview image
    # -----------------------------------------------------------------------------
    def on_result_select(self, event):
        sel = self.results_list.curselection()
        if not sel:
            return
        index = sel[0]
        display = self.results_list.get(index)
        # Extract card name (everything before first "  •  ")
        card_name = display.split("  •  ")[0].strip()

        card = self.card_cache.get(card_name) or get_card_by_name(card_name)
        if not card:
            return
        self.card_cache[card.name] = card
        self._show_preview(card)

    # -----------------------------------------------------------------------------
    # Show a given Card’s image + its color icons
    # -----------------------------------------------------------------------------
    def _show_preview(self, card: Card):
        # 1) Display color icons
        for widget in self.color_icons_frame.winfo_children():
            widget.destroy()

        x = 0
        for symbol in card.colors:
            icon_img = self.color_icon_images.get(symbol)
            if icon_img:
                lbl = ttk.Label(self.color_icons_frame, image=icon_img)
                lbl.image = icon_img
                lbl.grid(row=0, column=x, padx=2)
                x += 1

        # 2) Fetch & display card image
        if card.image_url:
            try:
                response = requests.get(card.image_url, timeout=10)
                response.raise_for_status()
                img_data = response.content
                image = Image.open(io.BytesIO(img_data))
                # Resize to fit in ~250×350 area, preserving aspect ratio
                image.thumbnail((250, 350), Image.LANCZOS)
                photo = ImageTk.PhotoImage(image)
                self.preview_photo = photo
                self.card_image_label.config(image=photo, text="")
            except Exception:
                self.card_image_label.config(text="Could not load image", image="")
                self.preview_photo = None
        else:
            self.card_image_label.config(text="No image available", image="")
            self.preview_photo = None

    # -----------------------------------------------------------------------------
    # Clear preview panel (both icons & image)
    # -----------------------------------------------------------------------------
    def _clear_preview(self):
        self.card_image_label.config(image="", text="")
        for widget in self.color_icons_frame.winfo_children():
            widget.destroy()
        self.preview_photo = None

    # -----------------------------------------------------------------------------
    # Add the currently highlighted search‐result card into the deck
    # -----------------------------------------------------------------------------
    def add_card_to_deck(self):
        if not self.current_deck:
            messagebox.showwarning("Add Card", "Create or load a deck first.")
            return
        sel = self.results_list.curselection()
        if not sel:
            messagebox.showwarning("Add Card", "Select a card from search results.")
            return
        index = sel[0]
        display = self.results_list.get(index)
        card_name = display.split("  •  ")[0].strip()

        try:
            qty = int(self.add_qty_spin.get())
        except ValueError:
            messagebox.showerror("Invalid Quantity", "Enter a valid number.")
            return

        card = self.card_cache.get(card_name) or get_card_by_name(card_name)
        if not card:
            messagebox.showerror("Error", f"Card '{card_name}' not found.")
            return
        self.card_cache[card.name] = card

        self.current_deck.add_card(card.name, qty)
        total = self.current_deck.total_cards()
        self.deck_name_label.config(text=f"Deck: {self.current_deck.name} ({total} cards)")
        self._refresh_deck_list()

    # -----------------------------------------------------------------------------
    # When a deck entry is selected, also preview its image + colors
    # -----------------------------------------------------------------------------
    def on_deck_select(self, event):
        sel = self.deck_list.curselection()
        if not sel or not self.current_deck:
            return
        index = sel[0]
        entry = self.deck_list.get(index)
        # Format is "Qty× CardName [⚠]" or "Qty× CardName"
        parts = entry.split("×", 1)
        if len(parts) != 2:
            return
        _, rest = parts
        card_name = rest.strip()
        if card_name.endswith("⚠"):
            card_name = card_name[:-1].strip()

        card = self.card_cache.get(card_name) or get_card_by_name(card_name)
        if not card:
            return
        self.card_cache[card.name] = card
        self._show_preview(card)

    # -----------------------------------------------------------------------------
    # Remove the selected card (all copies) from the deck
    # -----------------------------------------------------------------------------
    def remove_selected(self):
        if not self.current_deck:
            return
        sel = self.deck_list.curselection()
        if not sel:
            return
        index = sel[0]
        entry = self.deck_list.get(index)
        parts = entry.split("×", 1)
        if len(parts) != 2:
            return
        qty_str, rest = parts
        try:
            qty = int(qty_str.strip())
        except ValueError:
            return
        card_name = rest.strip()
        if card_name.endswith("⚠"):
            card_name = card_name[:-1].strip()

        # Remove that many copies (which usually removes it entirely)
        self.current_deck.remove_card(card_name, qty)
        total = self.current_deck.total_cards()
        self.deck_name_label.config(text=f"Deck: {self.current_deck.name} ({total} cards)")
        self._refresh_deck_list()
        self._clear_preview()

    # -----------------------------------------------------------------------------
    # Repopulate deck_list, showing "⚠" next to any non‐land with qty > 1
    # -----------------------------------------------------------------------------
    def _refresh_deck_list(self):
        self.deck_list.delete(0, tk.END)
        if not self.current_deck:
            return
        for name, qty in self.current_deck.cards.items():
            card = self.card_cache.get(name) or get_card_by_name(name)
            if card:
                self.card_cache[card.name] = card
                flag = ""
                if qty > 1 and not is_land(card):
                    flag = " ⚠"
                display = f"{qty}× {card.name}{flag}"
            else:
                display = f"{qty}× {name}"
            self.deck_list.insert(tk.END, display)

# -----------------------------------------------------------------------------
# Launch the app
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    # Warn if icons folder is missing any color PNG
    missing = []
    for sym in ["W", "U", "B", "R", "G"]:
        if not os.path.isfile(os.path.join("assets", "icons", f"{sym}.png")):
            missing.append(sym)
    if missing:
        print(f"Warning: Missing color icon(s) for {missing} in assets/icons/.")
        print("The rest of the GUI will still load, but those icons won't appear.")
    app = MTGDeckBuilder()
    app.mainloop()
