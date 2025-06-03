# main.py
import os
import io
import requests
import winsound
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from PIL import Image, ImageTk

from mtg_api import init_cache_db, get_card_by_name, search_cards
from deck_manager import save_deck as dm_save_deck, load_deck, list_saved_decks
from collection_manager import load_collection, save_collection
from battle_simulator import simulate_match, record_manual_result, load_match_history
from models import Deck, Card

# -----------------------------------------------------------------------------
# Helper to detect lands
# -----------------------------------------------------------------------------
def is_land(card: Card) -> bool:
    return "Land" in card.type_line

# -----------------------------------------------------------------------------
# Play a custom WAV whenever you want (falls back if missing)
# -----------------------------------------------------------------------------
def play_sound(sound_name: str):
    path = os.path.join("assets", "sounds", f"{sound_name}.wav")
    if os.path.isfile(path):
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)

# -----------------------------------------------------------------------------
# Main Application Window
# -----------------------------------------------------------------------------
class MTGDeckBuilder(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MTG Deck Builder")
        self.geometry("1200x750")

        # Ensure necessary folders/files exist
        init_cache_db()
        _ = load_collection()       # ensure collection file
        _ = load_match_history()    # ensure match history file

        # Track theme: "dark" or "light"
        self.theme = tk.StringVar(value="dark")

        # Currently loaded Deck
        self.current_deck: Deck | None = None

        # In-memory cache: card_name → Card object
        self.card_cache: dict[str, Card] = {}

        # Keep references to PhotoImage to avoid garbage-collection
        self.thumbnail_images: dict[str, ImageTk.PhotoImage] = {}
        self.preview_photo: ImageTk.PhotoImage | None = None
        self.color_icon_images: dict[str, ImageTk.PhotoImage] = {}

        # Build & layout UI
        self._load_color_icons()
        self._load_sounds()
        self._build_widgets()
        self._layout_widgets()
        self.apply_theme()  # start in VSCode-style dark

    # -----------------------------------------------------------------------------
    # Pre-load color icons (W/U/B/R/G)
    # -----------------------------------------------------------------------------
    def _load_color_icons(self):
        icon_folder = os.path.join("assets", "icons")
        for symbol in ["W", "U", "B", "R", "G"]:
            path = os.path.join(icon_folder, f"{symbol}.png")
            if os.path.isfile(path):
                img = Image.open(path).resize((20, 20), Image.LANCZOS)
                self.color_icon_images[symbol] = ImageTk.PhotoImage(img)
            else:
                self.color_icon_images[symbol] = None

    # -----------------------------------------------------------------------------
    # Ensure sound folder exists
    # -----------------------------------------------------------------------------
    def _load_sounds(self):
        sound_folder = os.path.join("assets", "sounds")
        os.makedirs(sound_folder, exist_ok=True)
        # Place click.wav and error.wav there if you have them.

    # -----------------------------------------------------------------------------
    # Create all widgets
    # -----------------------------------------------------------------------------
    def _build_widgets(self):
        # --- Top row: Deck controls + theme toggle ---
        self.deck_frame = ttk.LabelFrame(self, text="Deck Controls", padding=8)
        self.new_deck_btn = ttk.Button(self.deck_frame, text="New Deck", command=self._on_new_deck)
        self.load_deck_btn = ttk.Button(self.deck_frame, text="Load Deck", command=self._on_load_deck)
        self.save_deck_btn = ttk.Button(self.deck_frame, text="Save Deck", command=self._on_save_deck)
        self.smart_build_btn = ttk.Button(self.deck_frame, text="Smart Build Deck", command=self._on_smart_build)
        self.simulate_btn = ttk.Button(self.deck_frame, text="Simulate Battle", command=self._on_simulate_battle)
        self.record_btn = ttk.Button(self.deck_frame, text="Record Result", command=self._on_record_result)
        self.deck_name_label = ttk.Label(self.deck_frame, text="(no deck loaded)")
        self.theme_toggle = ttk.Checkbutton(
            self.deck_frame,
            text="Light Mode",
            variable=self.theme,
            onvalue="light",
            offvalue="dark",
            command=self.apply_theme
        )

        # --- Collection panel with tabs (left) ---
        self.coll_frame = ttk.LabelFrame(self, text="Your Collection", padding=8)
        self.coll_notebook = ttk.Notebook(self.coll_frame)
        self.coll_tabs = {}
        self.coll_trees = {}
        self.coll_scrolls = {}
        for tab_name in ["All", "Black", "White", "Red", "Green", "Blue", "Unmarked", "Tokens"]:
            frame = ttk.Frame(self.coll_notebook)
            tree = ttk.Treeview(frame, height=20, columns=("info",), show="tree")
            scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=scroll.set)
            tree.pack(fill="both", expand=True, side="left", padx=(4,0), pady=4)
            scroll.pack(fill="y", side="left", padx=(0,4), pady=4)
            self.coll_notebook.add(frame, text=tab_name)
            self.coll_tabs[tab_name] = frame
            self.coll_trees[tab_name] = tree
            self.coll_scrolls[tab_name] = scroll
        self.remove_from_coll_btn = ttk.Button(self.coll_frame, text="Remove from Collection", command=self._on_remove_from_collection)

        # --- Right side: Search panel + Deck panel + Preview ---
        self.right_frame = ttk.Frame(self)
        # Search / Add Cards
        self.search_frame = ttk.LabelFrame(self.right_frame, text="Search / Add Cards", padding=8)
        self.search_entry = ttk.Entry(self.search_frame, width=30)
        self.search_btn = ttk.Button(self.search_frame, text="Search", command=self._on_perform_search)
        self.search_entry.bind("<Return>", lambda e: self._on_perform_search())
        self.results_tree = ttk.Treeview(self.search_frame, height=12, columns=("info",), show="tree")
        self.results_scroll = ttk.Scrollbar(self.search_frame, orient="vertical", command=self.results_tree.yview)
        self.results_tree.configure(yscrollcommand=self.results_scroll.set)
        self.results_tree.bind("<<TreeviewSelect>>", self._on_result_select)
        self.add_qty_label = ttk.Label(self.search_frame, text="Qty:")
        self.add_qty_spin = ttk.Spinbox(self.search_frame, from_=1, to=20, width=5)
        self.add_qty_spin.set("1")
        # Swap these two so that Add to Collection is on the left
        self.add_to_coll_btn = ttk.Button(self.search_frame, text="Add to Collection", command=self._on_add_to_collection)
        self.add_to_deck_btn = ttk.Button(self.search_frame, text="Add to Deck", command=self._on_add_to_deck)

        # Deck panel with tabs
        self.deck_view_frame = ttk.LabelFrame(self.right_frame, text="Deck Contents", padding=8)
        self.deck_notebook = ttk.Notebook(self.deck_view_frame)
        self.deck_tabs = {}
        self.deck_trees = {}
        self.deck_scrolls = {}
        for tab_name in ["All", "Black", "White", "Red", "Green", "Blue", "Unmarked", "Tokens"]:
            frame = ttk.Frame(self.deck_notebook)
            tree = ttk.Treeview(frame, height=20, columns=("info",), show="tree")
            scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=scroll.set)
            tree.pack(fill="both", expand=True, side="left", padx=(4,0), pady=4)
            scroll.pack(fill="y", side="left", padx=(0,4), pady=4)
            self.deck_notebook.add(frame, text=tab_name)
            self.deck_tabs[tab_name] = frame
            self.deck_trees[tab_name] = tree
            self.deck_scrolls[tab_name] = scroll
            tree.bind("<<TreeviewSelect>>", self._on_deck_select)
        self.remove_card_btn = ttk.Button(self.deck_view_frame, text="Remove Selected", command=self._on_remove_selected)

        # Card preview (bottom)
        self.preview_frame = ttk.LabelFrame(self, text="Card Preview", padding=8)
        self.card_image_label = ttk.Label(self.preview_frame)
        self.color_icons_frame = ttk.Frame(self.preview_frame)

    # -----------------------------------------------------------------------------
    # Arrange everything with pack() and grid()
    # -----------------------------------------------------------------------------
    def _layout_widgets(self):
        # --- Deck controls (top) ---
        self.deck_frame.pack(fill="x", padx=10, pady=(10, 5))
        self.new_deck_btn.grid(row=0, column=0, padx=4, pady=4)
        self.load_deck_btn.grid(row=0, column=1, padx=4, pady=4)
        self.save_deck_btn.grid(row=0, column=2, padx=4, pady=4)
        self.smart_build_btn.grid(row=0, column=3, padx=4, pady=4)
        self.simulate_btn.grid(row=0, column=4, padx=4, pady=4)
        self.record_btn.grid(row=0, column=5, padx=4, pady=4)
        self.theme_toggle.grid(row=0, column=6, padx=20, pady=4)
        self.deck_name_label.grid(row=0, column=7, padx=10, pady=4, sticky="w")

        # --- Collection panel (left) ---
        self.coll_frame.pack(fill="y", side="left", padx=(10,5), pady=5)
        self.coll_frame.configure(width=250)
        self.coll_notebook.pack(fill="both", expand=True, padx=4, pady=4)
        self.remove_from_coll_btn.pack(fill="x", padx=4, pady=(4,10))

        # --- Right side: search + deck ---
        self.right_frame.pack(fill="both", expand=True, side="left", padx=(5,10), pady=5)
        self.right_frame.columnconfigure(0, weight=1)
        self.right_frame.columnconfigure(1, weight=1)
        self.right_frame.rowconfigure(0, weight=1)

        # Search panel
        self.search_frame.grid(row=0, column=0, sticky="nsew", padx=(0,5))
        self.search_frame.columnconfigure(0, weight=1)
        self.search_frame.rowconfigure(1, weight=1)

        self.search_entry.grid(row=0, column=0, padx=4, pady=4, sticky="w")
        self.search_btn.grid(row=0, column=1, padx=4, pady=4, sticky="w")

        self.results_tree.grid(row=1, column=0, columnspan=2, padx=(4,0), pady=4, sticky="nsew")
        self.results_scroll.grid(row=1, column=2, sticky="ns", pady=4)

        self.add_qty_label.grid(row=2, column=0, padx=4, pady=(4,10), sticky="w")
        self.add_qty_spin.grid(row=2, column=1, padx=4, pady=(4,10), sticky="w")
        self.add_to_coll_btn.grid(row=2, column=2, padx=4, pady=(4,10), sticky="w")
        self.add_to_deck_btn.grid(row=2, column=3, padx=4, pady=(4,10), sticky="w")

        # Deck panel
        self.deck_view_frame.grid(row=0, column=1, sticky="nsew", padx=(5,0))
        self.deck_view_frame.columnconfigure(0, weight=1)
        self.deck_view_frame.rowconfigure(0, weight=1)

        self.deck_notebook.pack(fill="both", expand=True, padx=4, pady=4)
        self.remove_card_btn.pack(fill="x", padx=4, pady=(4,10))

        # Preview panel (bottom)
        self.preview_frame.pack(fill="x", padx=10, pady=(0,10))
        self.preview_frame.columnconfigure(0, weight=1)
        self.preview_frame.rowconfigure(0, weight=1)
        self.card_image_label.grid(row=0, column=0, padx=4, pady=4)
        self.color_icons_frame.grid(row=1, column=0, padx=4, pady=(4,8))

        # Populate both Collection and Deck initially
        self._refresh_collection()
        self._refresh_deck()

    # -----------------------------------------------------------------------------
    # Apply either “VSCode Dark+” or Light theme
    # -----------------------------------------------------------------------------
    def apply_theme(self):
        mode = self.theme.get()  # "dark" or "light"
        style = ttk.Style()
        style.theme_use("clam")

        if mode == "dark":
            # VSCode Dark+ approximate palette
            bg = "#1e1e1e"
            fg = "#d4d4d4"
            panel = "#252526"
            entry_bg = "#3c3c3c"
            entry_fg = "#d4d4d4"
            select_bg = "#264f78"
            btn_bg = "#0e639c"
            btn_fg = "#ffffff"
        else:
            # Standard light
            bg = "#ffffff"
            fg = "#000000"
            panel = "#f0f0f0"
            entry_bg = "#ffffff"
            entry_fg = "#000000"
            select_bg = "#cce5ff"
            btn_bg = "#007acc"
            btn_fg = "#ffffff"

        # Configure styles
        style.configure("TLabelframe", background=panel, foreground=fg)
        style.configure("TLabelframe.Label", background=panel, foreground=fg)
        style.configure("TLabel", background=bg, foreground=fg)
        style.configure("TButton", background=btn_bg, foreground=btn_fg)
        style.map("TButton",
                  background=[("active", "#005a9e")] if mode=="dark" else [("active", "#0057e7")])
        style.configure("TCheckbutton", background=panel, foreground=fg)

        style.configure("Treeview",
                        background=entry_bg, foreground=entry_fg,
                        fieldbackground=entry_bg, selectbackground=select_bg, rowheight=36)
        style.map("Treeview", background=[("selected", select_bg)])
        style.configure("TEntry", fieldbackground=entry_bg, foreground=entry_fg)
        style.configure("TSpinbox", fieldbackground=entry_bg, foreground=entry_fg)

        # Re-color all frames
        self.configure(background=bg)
        for frame in [self.deck_frame, self.coll_frame, self.search_frame,
                      self.deck_view_frame, self.preview_frame, self.right_frame]:
            frame.configure(style="TLabelframe")

    # -----------------------------------------------------------------------------
    # “New Deck” callback
    # -----------------------------------------------------------------------------
    def _on_new_deck(self):
        play_sound("click")
        name = simpledialog.askstring("New Deck", "Enter deck name:", parent=self)
        if not name:
            return
        self.current_deck = Deck(name=name)
        self.deck_name_label.config(text=f"Deck: {name} (0 cards)")
        self._refresh_deck()
        self._clear_preview()

    # -----------------------------------------------------------------------------
    # “Load Deck” callback
    # -----------------------------------------------------------------------------
    def _on_load_deck(self):
        play_sound("click")
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
            self._refresh_deck()
            self._clear_preview()
        else:
            play_sound("error")
            messagebox.showerror("Error", f"Deck '{name}' not found.")

    # -----------------------------------------------------------------------------
    # “Save Deck” callback
    # -----------------------------------------------------------------------------
    def _on_save_deck(self):
        play_sound("click")
        if not self.current_deck:
            messagebox.showwarning("Save Deck", "No deck loaded.")
            return
        dm_save_deck(self.current_deck)
        messagebox.showinfo("Save Deck", f"Deck '{self.current_deck.name}' saved.")

    # -----------------------------------------------------------------------------
    # “Smart Build Deck” callback
    # -----------------------------------------------------------------------------
    def _on_smart_build(self):
        play_sound("click")
        color_input = simpledialog.askstring(
            "Smart Build: Colors",
            "Enter 1–3 colors (e.g. R G) separated by spaces:",
            parent=self
        )
        if not color_input:
            return
        colors = [c.strip().upper() for c in color_input.split() if c.strip().upper() in {"W","U","B","R","G"}]
        if not 1 <= len(colors) <= 3:
            play_sound("error")
            messagebox.showerror("Invalid Colors", "You must pick 1–3 of W, U, B, R, G.")
            return

        history = load_match_history()
        archetypes = ["Aggro", "Midrange", "Control"]
        best_arch = None
        best_rate = -1.0
        combo = "/".join(colors)
        for arch in archetypes:
            total = wins = 0
            for record in history:
                dn = record.get("deck", "")
                if dn.startswith(arch) and combo in dn:
                    res = record.get("result", "")
                    if res in ("W","L"):
                        total += 1
                        if res == "W":
                            wins += 1
            if total > 0:
                rate = wins / total
                if rate > best_rate:
                    best_rate = rate
                    best_arch = arch

        if best_arch:
            confirm = messagebox.askokcancel(
                "Choose Archetype",
                f"Based on history, {best_arch} {combo} has win rate {best_rate:.0%}.\nUse it?"
            )
            if confirm:
                archetype = best_arch.lower()
            else:
                archetype = None
        else:
            archetype = None

        if not archetype:
            arch_input = simpledialog.askstring(
                "Smart Build: Archetype",
                "Enter archetype (Aggro, Control, Midrange):",
                parent=self
            )
            if not arch_input:
                return
            arch_input = arch_input.strip().lower()
            if arch_input not in {"aggro", "control", "midrange"}:
                play_sound("error")
                messagebox.showerror("Invalid Archetype", "Must be 'Aggro', 'Control', or 'Midrange'.")
                return
            archetype = arch_input

        deck_name = f"{archetype.capitalize()} {combo} Auto"
        deck = Deck(name=deck_name)

        land_count = 24
        if archetype == "aggro":
            creature_target = 24; noncreature_target = 12
        elif archetype == "midrange":
            creature_target = 18; noncreature_target = 18
        else:
            creature_target = 12; noncreature_target = 24

        per_color = land_count // len(colors)
        extra = land_count % len(colors)
        basic_map = {"W":"Plains","U":"Island","B":"Swamp","R":"Mountain","G":"Forest"}
        for idx, col in enumerate(colors):
            qty = per_color + (1 if idx < extra else 0)
            deck.add_card(basic_map[col], qty)

        creature_query = f"c:{''.join(colors)} type:creature"
        if archetype == "aggro":
            creature_query += " cmc<=3"
        elif archetype == "midrange":
            creature_query += " cmc<=4"
        else:
            creature_query += " cmc<=5"
        creatures = search_cards(creature_query)
        creatures = [c for c in creatures if set(c.colors).issubset(set(colors))]
        used = set(); added = 0
        for c in creatures:
            if added >= creature_target:
                break
            if c.name not in used:
                deck.add_card(c.name, 1)
                used.add(c.name); added += 1

        noncre_query = f"c:{''.join(colors)} (type:instant or type:sorcery)"
        if archetype == "aggro":
            noncre_query += " cmc<=3"
        elif archetype == "midrange":
            noncre_query += " cmc<=4"
        else:
            noncre_query += " cmc>=3"
        noncre = search_cards(noncre_query)
        noncre = [c for c in noncre if set(c.colors).issubset(set(colors))]
        added_non = 0
        for c in noncre:
            if added_non >= noncreature_target:
                break
            if c.name not in used:
                deck.add_card(c.name, 1)
                used.add(c.name); added_non += 1

        total_cards = sum(deck.cards.values())
        if total_cards < 60:
            fill_needed = 60 - total_cards
            filler = search_cards("type:creature cmc<=3")
            for c in filler:
                if c.name not in used:
                    deck.add_card(c.name,1)
                    used.add(c.name)
                    fill_needed -=1
                    if fill_needed==0: break

        self.current_deck = deck
        self.deck_name_label.config(text=f"Deck: {deck.name} ({deck.total_cards()} cards)")
        self._refresh_deck()
        self._clear_preview()
        messagebox.showinfo("Smart Build Complete", f"Created deck '{deck.name}' with {deck.total_cards()} cards.")

    # -----------------------------------------------------------------------------
    # Refresh the entire collection (all tabs)
    # -----------------------------------------------------------------------------
    def _refresh_collection(self):
        coll = load_collection()
        # Prepare a dict: tab_name → list of (name, qty)
        buckets = {tn: [] for tn in self.coll_trees}
        for name, qty in coll.items():
            # Fetch Card object (cache or API)
            card = self.card_cache.get(name) or get_card_by_name(name)
            if card:
                self.card_cache[card.name] = card
                colors = card.colors
                is_token = "Token" in card.type_line
            else:
                colors = []
                is_token = False

            # Every card goes into "All"
            buckets["All"].append((name, qty))

            # Color-specific tabs
            for col, tab in [("B", "Black"), ("W", "White"),
                             ("R", "Red"), ("G", "Green"), ("U", "Blue")]:
                if col in colors:
                    buckets[tab].append((name, qty))

            # Unmarked = no colors
            if not colors and not is_token:
                buckets["Unmarked"].append((name, qty))

            # Tokens tab
            if is_token:
                buckets["Tokens"].append((name, qty))

        # Now update each Treeview
        for tab_name, tree in self.coll_trees.items():
            tree.delete(*tree.get_children())
            for idx, (card_name, qty) in enumerate(sorted(buckets[tab_name], key=lambda x: x[0].lower())):
                display = f"{qty}× {card_name}"
                tree.insert("", "end", iid=str(idx), text=display)

    # -----------------------------------------------------------------------------
    # “Remove from Collection” callback
    # -----------------------------------------------------------------------------
    def _on_remove_from_collection(self):
        play_sound("click")
        # Determine which tab is currently selected
        current_tab = self.coll_notebook.tab(self.coll_notebook.select(), "text")
        tree = self.coll_trees[current_tab]
        sel = tree.selection()
        if not sel:
            return
        iid = sel[0]
        display = tree.item(iid, "text")
        qty_str, name_part = display.split("×", 1)
        card_name = name_part.strip()

        coll = load_collection()
        if card_name in coll:
            del coll[card_name]
            save_collection(coll)
            self._refresh_collection()

    # -----------------------------------------------------------------------------
    # “Search” callback
    # -----------------------------------------------------------------------------
    def _on_perform_search(self):
        play_sound("click")
        query = self.search_entry.get().strip()
        if not query:
            return

        self.results_tree.delete(*self.results_tree.get_children())
        self.thumbnail_images.clear()

        results = search_cards(query)
        if not results:
            messagebox.showinfo("Search", "No cards found.")
            return

        for idx, card in enumerate(results):
            self.card_cache[card.name] = card
            thumb = None
            if card.thumbnail_url:
                try:
                    resp = requests.get(card.thumbnail_url, timeout=5)
                    resp.raise_for_status()
                    img = Image.open(io.BytesIO(resp.content))
                    img.thumbnail((40, 60), Image.LANCZOS)
                    thumb = ImageTk.PhotoImage(img)
                except Exception:
                    thumb = None

            display_text = f"{card.name} ● {card.mana_cost or ''} ● {card.type_line} [{card.rarity}]"
            if thumb:
                self.thumbnail_images[card.name] = thumb
                self.results_tree.insert(
                    "", "end", iid=str(idx),
                    text=display_text, image=thumb
                )
            else:
                self.results_tree.insert(
                    "", "end", iid=str(idx),
                    text=display_text
                )

        self._clear_preview()

    # -----------------------------------------------------------------------------
    # When a search result is selected → preview it
    # -----------------------------------------------------------------------------
    def _on_result_select(self, event):
        sel = self.results_tree.selection()
        if not sel:
            return
        iid = sel[0]
        display = self.results_tree.item(iid, "text")
        card_name = display.split(" ● ")[0].strip()

        card = self.card_cache.get(card_name) or get_card_by_name(card_name)
        if not card:
            return
        self.card_cache[card.name] = card
        self._show_preview(card)

    # -----------------------------------------------------------------------------
    # Show full image + color pips in preview
    # -----------------------------------------------------------------------------
    def _show_preview(self, card: Card):
        for w in self.color_icons_frame.winfo_children():
            w.destroy()

        x = 0
        for symbol in card.colors:
            icon = self.color_icon_images.get(symbol)
            if icon:
                lbl = ttk.Label(self.color_icons_frame, image=icon)
                lbl.image = icon
                lbl.grid(row=0, column=x, padx=2)
                x += 1

        if card.image_url:
            try:
                resp = requests.get(card.image_url, timeout=10)
                resp.raise_for_status()
                img_data = resp.content
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
    # “Add to Deck” callback
    # -----------------------------------------------------------------------------
    def _on_add_to_deck(self):
        play_sound("click")
        if not self.current_deck:
            messagebox.showwarning("Add Card", "Create or load a deck first.")
            return
        sel = self.results_tree.selection()
        if not sel:
            messagebox.showwarning("Add Card", "Select a card from search results.")
            return
        iid = sel[0]
        display = self.results_tree.item(iid, "text")
        card_name = display.split(" ● ")[0].strip()

        try:
            qty = int(self.add_qty_spin.get())
            if qty < 1:
                raise ValueError
        except Exception:
            qty = 1

        card = self.card_cache.get(card_name) or get_card_by_name(card_name)
        if not card:
            play_sound("error")
            messagebox.showerror("Error", f"Card '{card_name}' not found.")
            return
        self.card_cache[card.name] = card

        self.current_deck.add_card(card.name, qty)
        self.deck_name_label.config(text=f"Deck: {self.current_deck.name} ({self.current_deck.total_cards()} cards)")
        self._refresh_deck()

    # -----------------------------------------------------------------------------
    # “Add to Collection” callback
    # -----------------------------------------------------------------------------
    def _on_add_to_collection(self):
        play_sound("click")
        coll = load_collection()
        sel = self.results_tree.selection()
        if not sel:
            messagebox.showwarning("Add to Collection", "Select a card first.")
            return
        iid = sel[0]
        display = self.results_tree.item(iid, "text")
        card_name = display.split(" ● ")[0].strip()

        try:
            qty = int(self.add_qty_spin.get())
            if qty < 1:
                raise ValueError
        except Exception:
            qty = 1

        coll[card_name] = coll.get(card_name, 0) + qty
        save_collection(coll)
        self._refresh_collection()
        messagebox.showinfo("Collection", f"Added {qty}× '{card_name}' to your collection.")

    # -----------------------------------------------------------------------------
    # “Deck” selection callback → preview
    # -----------------------------------------------------------------------------
    def _on_deck_select(self, event):
        # Determine which tab is selected
        current_tab = self.deck_notebook.tab(self.deck_notebook.select(), "text")
        tree = self.deck_trees[current_tab]
        sel = tree.selection()
        if not sel or not self.current_deck:
            return
        iid = sel[0]
        display = tree.item(iid, "text")
        parts = display.split("×", 1)
        if len(parts) != 2:
            return
        card_name = parts[1].strip()
        if card_name.endswith("⚠"):
            card_name = card_name[:-1].strip()

        card = self.card_cache.get(card_name) or get_card_by_name(card_name)
        if not card:
            return
        self.card_cache[card.name] = card
        self._show_preview(card)

    # -----------------------------------------------------------------------------
    # “Remove Selected” from deck callback
    # -----------------------------------------------------------------------------
    def _on_remove_selected(self):
        play_sound("click")
        current_tab = self.deck_notebook.tab(self.deck_notebook.select(), "text")
        tree = self.deck_trees[current_tab]
        sel = tree.selection()
        if not sel or not self.current_deck:
            return
        iid = sel[0]
        display = tree.item(iid, "text")
        parts = display.split("×", 1)
        if len(parts) != 2:
            return
        try:
            qty = int(parts[0].strip())
        except ValueError:
            return
        card_name = parts[1].strip()
        if card_name.endswith("⚠"):
            card_name = card_name[:-1].strip()

        self.current_deck.remove_card(card_name, qty)
        self.deck_name_label.config(text=f"Deck: {self.current_deck.name} ({self.current_deck.total_cards()} cards)")
        self._refresh_deck()
        self._clear_preview()

    # -----------------------------------------------------------------------------
    # Refresh deck tabs
    # -----------------------------------------------------------------------------
    def _refresh_deck(self):
        if not self.current_deck:
            for tree in self.deck_trees.values():
                tree.delete(*tree.get_children())
            return

        # Prepare buckets similar to collection
        buckets = {tn: [] for tn in self.deck_trees}
        for name, qty in self.current_deck.cards.items():
            card = self.card_cache.get(name) or get_card_by_name(name)
            if card:
                self.card_cache[card.name] = card
                colors = card.colors
                is_token = "Token" in card.type_line
            else:
                colors = []
                is_token = False

            buckets["All"].append((name, qty))
            for col, tab in [("B", "Black"), ("W", "White"),
                             ("R", "Red"), ("G", "Green"), ("U", "Blue")]:
                if col in colors:
                    buckets[tab].append((name, qty))
            if not colors and not is_token:
                buckets["Unmarked"].append((name, qty))
            if is_token:
                buckets["Tokens"].append((name, qty))

        # Update each deck Treeview
        for tab_name, tree in self.deck_trees.items():
            tree.delete(*tree.get_children())
            for idx, (card_name, qty) in enumerate(sorted(buckets[tab_name], key=lambda x: x[0].lower())):
                card = self.card_cache.get(card_name)
                flag = ""
                if card and qty > 1 and not is_land(card):
                    flag = " ⚠"
                display = f"{qty}× {card_name}{flag}"
                tree.insert("", "end", iid=str(idx), text=display)

    # -----------------------------------------------------------------------------
    # Clear card preview
    # -----------------------------------------------------------------------------
    def _clear_preview(self):
        self.card_image_label.config(image="", text="")
        for w in self.color_icons_frame.winfo_children():
            w.destroy()
        self.preview_photo = None

    # -----------------------------------------------------------------------------
    # “Simulate Battle” callback
    # -----------------------------------------------------------------------------
    def _on_simulate_battle(self):
        play_sound("click")
        choices = list_saved_decks()
        if len(choices) < 2:
            messagebox.showinfo("Simulate Battle", "Need at least two saved decks.")
            return

        d1 = simpledialog.askstring(
            "Simulate Battle: Deck 1",
            f"Available: {', '.join(choices)}\nEnter deck 1 name:",
            parent=self
        )
        if not d1 or d1 not in choices:
            return
        deck1 = load_deck(d1)
        if not deck1:
            play_sound("error")
            messagebox.showerror("Error", f"Deck '{d1}' not found.")
            return

        d2 = simpledialog.askstring(
            "Simulate Battle: Deck 2",
            f"Available: {', '.join(choices)}\nEnter deck 2 name:",
            parent=self
        )
        if not d2 or d2 not in choices:
            return
        deck2 = load_deck(d2)
        if not deck2:
            play_sound("error")
            messagebox.showerror("Error", f"Deck '{d2}' not found.")
            return

        wins1, wins2, ties = simulate_match(deck1, deck2, iterations=1000)
        msg = (f"Simulation results (1000 games):\n\n"
               f"{d1} wins: {wins1}\n"
               f"{d2} wins: {wins2}\n"
               f"Ties: {ties}")
        messagebox.showinfo("Simulation Complete", msg)

    # -----------------------------------------------------------------------------
    # “Record Result” callback
    # -----------------------------------------------------------------------------
    def _on_record_result(self):
        play_sound("click")
        choices = list_saved_decks()
        if not choices:
            messagebox.showinfo("Record Result", "No saved decks to record.")
            return

        deck_name = simpledialog.askstring(
            "Record Result: Deck",
            f"Available: {', '.join(choices)}\nEnter deck name:",
            parent=self
        )
        if not deck_name or deck_name not in choices:
            return

        opponent = simpledialog.askstring(
            "Record Result: Opponent Deck (optional)",
            "Enter opponent deck name (or leave blank):",
            parent=self
        )
        if opponent is None:
            return

        result = simpledialog.askstring(
            "Record Result: Outcome",
            "Enter result (W for win, L for loss, T for tie):",
            parent=self
        )
        if not result or result.upper() not in {"W","L","T"}:
            play_sound("error")
            messagebox.showerror("Invalid Result", "Result must be W, L, or T.")
            return

        record_manual_result(deck_name, opponent, result.upper())
        messagebox.showinfo("Record Result", f"Recorded {result.upper()} for '{deck_name}' vs '{opponent}'.")

# -----------------------------------------------------------------------------
# Launch the app
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    missing_icons = [s for s in ["W","U","B","R","G"]
                     if not os.path.isfile(os.path.join("assets","icons",f"{s}.png"))]
    if missing_icons:
        print(f"Warning: Missing color icon(s) for {missing_icons} in assets/icons/. Cards will still load.")

    missing_sounds = []
    for nm in ["click","error"]:
        if not os.path.isfile(os.path.join("assets","sounds", f"{nm}.wav")):
            missing_sounds.append(nm)
    if missing_sounds:
        print(f"Warning: Missing sound(s) for {missing_sounds} in assets/sounds/. Default OS beep may appear.")

    app = MTGDeckBuilder()
    app.mainloop()
