# main.py
import os
import io
import requests
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from PIL import Image, ImageTk

from mtg_api import init_cache_db, get_card_by_name, search_cards
from deck_manager import save_deck as dm_save_deck, load_deck, list_saved_decks
from collection_manager import load_collection, save_collection, list_collection
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
        self.geometry("1000x650")

        # Ensure necessary folders/files exist
        init_cache_db()
        _ = load_collection()  # ensure collection file/folder

        # Currently loaded Deck (or None)
        self.current_deck: Deck | None = None

        # In-memory cache: card_name → Card object (so we don't re-fetch repeatedly)
        self.card_cache: dict[str, Card] = {}

        # Hold references to PhotoImage objects so they don’t get garbage-collected
        self.preview_photo: ImageTk.PhotoImage | None = None
        self.color_icon_images: dict[str, ImageTk.PhotoImage] = {}

        # Build the UI
        self._load_color_icons()
        self._build_widgets()
        self._layout_widgets()

    # -----------------------------------------------------------------------------
    # Pre-load color icon images from local `assets/icons`
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
                self.color_icon_images[symbol] = None

    # -----------------------------------------------------------------------------
    # Create all widgets
    # -----------------------------------------------------------------------------
    def _build_widgets(self):
        # -- Deck Controls -------------------------------------------------------
        self.deck_frame = ttk.LabelFrame(self, text="Deck Controls", padding=10)
        self.new_deck_btn = ttk.Button(self.deck_frame, text="New Deck", command=self.new_deck)
        self.load_deck_btn = ttk.Button(self.deck_frame, text="Load Deck", command=self.load_deck)
        self.save_deck_btn = ttk.Button(self.deck_frame, text="Save Deck", command=self.save_deck)
        self.smart_build_btn = ttk.Button(self.deck_frame, text="Smart Build Deck", command=self.smart_build_deck)
        self.deck_name_label = ttk.Label(self.deck_frame, text="(no deck loaded)")

        # -- A container for the two main panels (Search vs. Deck) -------------
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
        self.add_to_deck_btn = ttk.Button(self.search_frame, text="Add to Deck", command=self.add_card_to_deck)
        self.add_to_coll_btn = ttk.Button(self.search_frame, text="Add to Collection", command=self.add_card_to_collection)

        # -- Card Preview (image + color icons) --------------------------------
        self.preview_frame = ttk.LabelFrame(self.search_frame, text="Card Preview", padding=10)
        self.card_image_label = ttk.Label(self.preview_frame)
        self.color_icons_frame = ttk.Frame(self.preview_frame)

        # -- Deck Contents -----------------------------------------------------
        self.deck_view_frame = ttk.LabelFrame(self.content_frame, text="Deck Contents", padding=10)
        self.deck_list = tk.Listbox(self.deck_view_frame, height=20, width=40)
        self.deck_scroll = ttk.Scrollbar(self.deck_view_frame, orient="vertical", command=self.deck_list.yview)
        self.deck_list.configure(yscrollcommand=self.deck_scroll.set)
        self.deck_list.bind("<<ListboxSelect>>", self.on_deck_select)

        self.remove_card_btn = ttk.Button(self.deck_view_frame, text="Remove Selected", command=self.remove_selected)

        # -- Collection Controls (view your collection) ------------------------
        self.coll_frame = ttk.LabelFrame(self, text="Collection Controls", padding=10)
        self.view_coll_btn = ttk.Button(self.coll_frame, text="View Collection", command=self.view_collection)

    # -----------------------------------------------------------------------------
    # Arrange everything in the proper geometry (pack/grid)
    # -----------------------------------------------------------------------------
    def _layout_widgets(self):
        # 1) Top: Deck controls (packed)
        self.deck_frame.pack(fill="x", padx=10, pady=5)
        self.new_deck_btn.grid(row=0, column=0, padx=5, pady=5)
        self.load_deck_btn.grid(row=0, column=1, padx=5, pady=5)
        self.save_deck_btn.grid(row=0, column=2, padx=5, pady=5)
        self.smart_build_btn.grid(row=0, column=3, padx=5, pady=5)
        self.deck_name_label.grid(row=0, column=4, padx=10, pady=5, sticky="w")

        # 2) Just below: Collection controls (packed)
        self.coll_frame.pack(fill="x", padx=10, pady=(0,5))
        self.view_coll_btn.pack(padx=5, pady=5, anchor="w")

        # 3) Middle: content_frame (packed)
        self.content_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.content_frame.columnconfigure(0, weight=1)
        self.content_frame.columnconfigure(1, weight=0)
        self.content_frame.rowconfigure(0, weight=1)

        # --- Left panel: Search / Add / Collection (gridded inside content_frame) ---
        self.search_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.search_frame.columnconfigure(0, weight=1)
        self.search_frame.rowconfigure(1, weight=1)

        self.search_entry.grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.search_btn.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        self.results_list.grid(row=1, column=0, columnspan=3, padx=(5, 0), pady=5, sticky="nsew")
        self.result_scroll.grid(row=1, column=3, sticky="ns", pady=5)

        self.add_qty_label.grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.add_qty_spin.grid(row=2, column=1, padx=5, pady=5, sticky="w")
        self.add_to_deck_btn.grid(row=2, column=2, padx=5, pady=5, sticky="w")
        self.add_to_coll_btn.grid(row=2, column=3, padx=5, pady=5, sticky="w")

        # Preview frame sits below everything in the search_frame
        self.preview_frame.grid(row=3, column=0, columnspan=4, padx=5, pady=10, sticky="nsew")
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
    # Create a brand-new Deck
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
    # Smart-build a 60-card deck based on user’s color choice & archetype
    # -----------------------------------------------------------------------------
    def smart_build_deck(self):
        # 1) Ask for colors
        color_input = simpledialog.askstring(
            "Smart Build: Colors",
            "Enter 1–3 colors (e.g. R G) separated by spaces:",
            parent=self
        )
        if not color_input:
            return
        colors = [c.strip().upper() for c in color_input.split() if c.strip().upper() in {"W","U","B","R","G"}]
        if not 1 <= len(colors) <= 3:
            messagebox.showerror("Invalid Colors", "You must pick 1–3 of W, U, B, R, G.")
            return

        # 2) Ask for archetype
        archetype = simpledialog.askstring(
            "Smart Build: Archetype",
            "Enter archetype (Aggro, Control, Midrange):",
            parent=self
        )
        if not archetype:
            return
        archetype = archetype.strip().lower()
        if archetype not in {"aggro", "control", "midrange"}:
            messagebox.showerror("Invalid Archetype", "Must be 'Aggro', 'Control', or 'Midrange'.")
            return

        # 3) Build a name for the new deck
        deck_name = f"{archetype.capitalize()} {'/'.join(colors)} Auto"
        deck = Deck(name=deck_name)

        # 4) Determine land count & creature/spell counts
        #    We’ll do a 24-land / 24-spells / 12-utility split.
        land_count = 24
        spells_count = 36  # creatures+noncreatures
        # For simplicity, creatures vs. noncreature split:
        if archetype == "aggro":
            creature_target = 24
            noncreature_target = 12
        elif archetype == "midrange":
            creature_target = 18
            noncreature_target = 18
        else:  # control
            creature_target = 12
            noncreature_target = 24

        # 5) Fetch lands: basic lands for each color, split evenly.
        per_color = land_count // len(colors)
        extra = land_count % len(colors)
        for idx, col in enumerate(colors):
            qty = per_color + (1 if idx < extra else 0)
            # Basic Land names in MTG: “Plains”, “Island”, “Swamp”, “Mountain”, “Forest”
            map_basic = {"W": "Plains", "U": "Island", "B": "Swamp", "R": "Mountain", "G": "Forest"}
            land_name = map_basic[col]
            deck.add_card(land_name, qty)

        # 6) Fetch creatures using Scryfall search
        #    Example query: “c:R type:creature cmc<=3” for aggro; adjust for other archetypes.
        creature_query = f"c:{''.join(colors)} type:creature"
        if archetype == "aggro":
            creature_query += " cmc<=3"
        elif archetype == "midrange":
            creature_query += " cmc<=4"
        else:  # control
            creature_query += " cmc<=5"

        creatures = search_cards(creature_query)
        creatures = [c for c in creatures if set(c.colors).issubset(set(colors))]
        # Take up to creature_target distinct names
        used = set()
        added = 0
        for c in creatures:
            if added >= creature_target:
                break
            if c.name not in used:
                deck.add_card(c.name, 1)
                used.add(c.name)
                added += 1

        # 7) Fetch noncreature spells: instants & sorceries
        noncre_query = f"c:{''.join(colors)} (type:instant or type:sorcery)"
        if archetype == "aggro":
            noncre_query += " cmc<=3"
        elif archetype == "midrange":
            noncre_query += " cmc<=4"
        else:  # control
            noncre_query += " cmc>=3"

        noncre = search_cards(noncre_query)
        noncre = [c for c in noncre if set(c.colors).issubset(set(colors))]
        added_non = 0
        for c in noncre:
            if added_non >= noncreature_target:
                break
            if c.name not in used:
                deck.add_card(c.name, 1)
                used.add(c.name)
                added_non += 1

        # 8) If we still need cards (e.g., not enough results), pad with any multi-color or colorless
        total_cards = sum(deck.cards.values())
        if total_cards < 60:
            fill_needed = 60 - total_cards
            filler = search_cards("type:creature cmc<=3")  # cheap catch-all
            for c in filler:
                if c.name not in used:
                    deck.add_card(c.name, 1)
                    used.add(c.name)
                    fill_needed -= 1
                    if fill_needed == 0:
                        break

        # 9) Assign to current_deck and refresh UI
        self.current_deck = deck
        self.deck_name_label.config(text=f"Deck: {deck.name} ({deck.total_cards()} cards)")
        self._refresh_deck_list()
        self._clear_preview()
        messagebox.showinfo("Smart Build Complete", f"Created deck '{deck.name}' with {deck.total_cards()} cards.")

    # -----------------------------------------------------------------------------
    # View your existing Collection in a pop-up window
    # -----------------------------------------------------------------------------
    def view_collection(self):
        coll = load_collection()
        if not coll:
            messagebox.showinfo("Collection", "Your collection is empty.")
            return

        # Build a Toplevel window
        top = tk.Toplevel(self)
        top.title("Your Collection")
        top.geometry("400x500")

        lbl = ttk.Label(top, text="Card Name – Quantity", font=("TkDefaultFont", 12, "bold"))
        lbl.pack(pady=(10,5))

        listbox = tk.Listbox(top, width=50, height=20)
        listbox.pack(fill="both", expand=True, padx=10, pady=5)

        # Sort alphabetically
        for name, qty in sorted(coll.items(), key=lambda x: x[0].lower()):
            listbox.insert(tk.END, f"{qty}× {name}")

        def remove_selected():
            sel = listbox.curselection()
            if not sel:
                return
            idx = sel[0]
            entry = listbox.get(idx)
            qty_str, name_part = entry.split("×", 1)
            card_name = name_part.strip()
            # Remove entirely (or prompt for qty) — here, we remove all copies
            del coll[card_name]
            save_collection(coll)
            listbox.delete(idx)

        btn = ttk.Button(top, text="Remove Selected Card", command=remove_selected)
        btn.pack(pady=(5,10))

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

        # Cache Card objects
        for card in results:
            self.card_cache[card.name] = card

        for card in results:
            display = f"{card.name}  •  {card.mana_cost or ''}  •  {card.type_line}  [{card.rarity}]"
            self.results_list.insert(tk.END, display)

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
    # Add selected card (with qty) to the current Deck
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
    # Add selected card (with qty) to your Collection (no deck required)
    # -----------------------------------------------------------------------------
    def add_card_to_collection(self):
        coll = load_collection()
        sel = self.results_list.curselection()
        if not sel:
            messagebox.showwarning("Add to Collection", "Select a card first.")
            return
        index = sel[0]
        display = self.results_list.get(index)
        card_name = display.split("  •  ")[0].strip()

        try:
            qty = int(self.add_qty_spin.get())
        except ValueError:
            messagebox.showerror("Invalid Quantity", "Enter a valid number.")
            return

        # Increment in collection
        coll[card_name] = coll.get(card_name, 0) + qty
        save_collection(coll)
        messagebox.showinfo("Collection", f"Added {qty}× '{card_name}' to your collection.")

    # -----------------------------------------------------------------------------
    # When a deck entry is selected, preview its image + colors
    # -----------------------------------------------------------------------------
    def on_deck_select(self, event):
        sel = self.deck_list.curselection()
        if not sel or not self.current_deck:
            return
        index = sel[0]
        entry = self.deck_list.get(index)
        # Format: "Qty× CardName ⚠?" or "Qty× CardName"
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

        self.current_deck.remove_card(card_name, qty)
        total = self.current_deck.total_cards()
        self.deck_name_label.config(text=f"Deck: {self.current_deck.name} ({total} cards)")
        self._refresh_deck_list()
        self._clear_preview()

    # -----------------------------------------------------------------------------
    # Repopulate deck_list, marking non-land duplicates with “⚠”
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
    # Warn if color icons are missing
    missing = [s for s in ["W","U","B","R","G"] if not os.path.isfile(os.path.join("assets","icons",f"{s}.png"))]
    if missing:
        print(f"Warning: Missing color icon(s) for {missing} in assets/icons/. Cards will still load.")
    app = MTGDeckBuilder()
    app.mainloop()
