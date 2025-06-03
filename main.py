# main.py
import os
import io
import subprocess, shlex
import requests
import winsound
import webbrowser
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
import tkinter.font as tkfont
from PIL import Image, ImageTk

from mtg_api import init_cache_db, get_card_by_name, search_cards
from deck_manager import save_deck as dm_save_deck, load_deck, list_saved_decks
from collection_manager import load_collection, save_collection
from battle_simulator import simulate_match, record_manual_result, load_match_history
from models import Deck, Card

# ──────────────────────────────────────────────────────────────────────────────
# VERSIONING (build number from Git commits, fallback __version__)
# ──────────────────────────────────────────────────────────────────────────────
MAJOR = 1
MINOR = 2
__version__ = f"{MAJOR}.{MINOR}.0"   # fallback if not in a Git repo
GITHUB_REPO = "YourUsername/YourRepo"  # ← replace with your GitHub "owner/repo"


def get_local_version() -> str:
    """
    Return "<MAJOR>.<MINOR>.<commit_count>" by running:
        git rev-list --count HEAD
    Fallback to __version__ if Git fails.
    """
    try:
        p = subprocess.run(
            shlex.split("git rev-list --count HEAD"),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
            text=True
        )
        build = p.stdout.strip()
        return f"{MAJOR}.{MINOR}.{build}"
    except Exception:
        return __version__


def check_for_updates(local_version: str, repo: str) -> None:
    """
    Fetch GitHub’s latest release (tag_name), compare to local_version.
    If GitHub’s is newer, prompt to open the Releases page.
    """
    api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        resp = requests.get(api_url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        tag = data.get("tag_name", "").lstrip("v")
    except Exception:
        return

    def to_tuple(v: str):
        nums = [int(x) for x in v.split(".") if x.isdigit()]
        return tuple(nums)

    try:
        if to_tuple(tag) > to_tuple(local_version):
            ans = messagebox.askyesno(
                "Update Available",
                f"A newer version ({tag}) is available on GitHub.\n"
                f"You’re running {local_version}.\n\n"
                "Would you like to view the Releases page?"
            )
            if ans:
                webbrowser.open(
                    data.get("html_url", f"https://github.com/{repo}/releases/latest")
                )
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────────────────────
# MTGDeckBuilder GUI
# ──────────────────────────────────────────────────────────────────────────────
class MTGDeckBuilder(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MTG Deck Builder")
        self.geometry("1200x750")

        # Ensure data folders/files
        init_cache_db()
        _ = load_collection()
        _ = load_match_history()

        # Theme tracking
        self.theme = tk.StringVar(value="dark")

        # Current deck
        self.current_deck: Deck | None = None

        # Caches
        self.card_cache: dict[str, Card] = {}  # name → Card
        self.search_images: dict[str, ImageTk.PhotoImage] = {}
        self.coll_images: dict[str, dict[str, ImageTk.PhotoImage]] = {
            tab: {} for tab in ["All", "Black", "White", "Red", "Green", "Blue", "Unmarked", "Tokens"]
        }
        self.deck_images: dict[str, dict[str, ImageTk.PhotoImage]] = {
            tab: {} for tab in ["All", "Black", "White", "Red", "Green", "Blue", "Unmarked", "Tokens"]
        }
        self.preview_photo: ImageTk.PhotoImage | None = None
        self.color_icon_images: dict[str, ImageTk.PhotoImage] = {}

        # Build UI
        self._load_color_icons()
        self._load_sounds()
        self._build_widgets()
        self._layout_widgets()
        self.apply_theme()

        # After 1 second, check for updates
        local_ver = get_local_version()
        self.after(1000, lambda: check_for_updates(local_ver, GITHUB_REPO))

    # -----------------------------------------------------------------------------
    # Preload W/U/B/R/G icons
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
    # Ensure sounds folder
    # -----------------------------------------------------------------------------
    def _load_sounds(self):
        sound_folder = os.path.join("assets", "sounds")
        os.makedirs(sound_folder, exist_ok=True)

    # -----------------------------------------------------------------------------
    # Build all widgets (including Combobox for autocomplete)
    # -----------------------------------------------------------------------------
    def _build_widgets(self):
        # Deck controls (top)
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

        # Collection panel with tabs (left)
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
            tree.bind("<<TreeviewSelect>>", self._on_coll_select)
            tree.pack(fill="both", expand=True, side="left", padx=(4,0), pady=4)
            scroll.pack(fill="y", side="left", padx=(0,4), pady=4)
            self.coll_notebook.add(frame, text=tab_name)
            self.coll_tabs[tab_name] = frame
            self.coll_trees[tab_name] = tree
            self.coll_scrolls[tab_name] = scroll
        self.remove_from_coll_btn = ttk.Button(self.coll_frame, text="Remove from Collection", command=self._on_remove_from_collection)
        self.coll_qty_label = ttk.Label(self.coll_frame, text="Qty:")
        self.coll_qty_spin = ttk.Spinbox(self.coll_frame, from_=1, to=1000, width=6)
        self.coll_set_qty_btn = ttk.Button(self.coll_frame, text="Set Quantity", command=self._on_set_coll_qty)

        # Right side: Search panel + Deck panel + Preview
        self.right_frame = ttk.Frame(self)

        # Search / Add Cards
        self.search_frame = ttk.LabelFrame(self.right_frame, text="Search / Add Cards", padding=8)
        self.search_entry = ttk.Combobox(self.search_frame, width=30)
        self.search_entry.set("")
        self.search_entry.bind("<<ComboboxSelected>>", lambda e: self._on_autocomplete_select())
        self.search_entry.bind("<KeyRelease>", lambda e: self._update_autocomplete())
        self.search_entry.bind("<FocusIn>", lambda e: self.search_entry.select_range(0, tk.END))
        self.search_btn = ttk.Button(self.search_frame, text="Search", command=self._on_perform_search)
        self.results_tree = ttk.Treeview(self.search_frame, height=12, columns=("info",), show="tree")
        self.results_scroll = ttk.Scrollbar(self.search_frame, orient="vertical", command=self.results_tree.yview)
        self.results_tree.configure(yscrollcommand=self.results_scroll.set)
        self.results_tree.bind("<<TreeviewSelect>>", self._on_result_select)
        self.add_qty_label = ttk.Label(self.search_frame, text="Qty:")
        self.add_qty_spin = ttk.Spinbox(self.search_frame, from_=1, to=20, width=5)
        self.add_qty_spin.set("1")
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
            tree.bind("<<TreeviewSelect>>", self._on_deck_select)
            tree.pack(fill="both", expand=True, side="left", padx=(4,0), pady=4)
            scroll.pack(fill="y", side="left", padx=(0,4), pady=4)
            self.deck_notebook.add(frame, text=tab_name)
            self.deck_tabs[tab_name] = frame
            self.deck_trees[tab_name] = tree
            self.deck_scrolls[tab_name] = scroll
        self.remove_card_btn = ttk.Button(self.deck_view_frame, text="Remove Selected", command=self._on_remove_selected)
        self.deck_qty_label = ttk.Label(self.deck_view_frame, text="Qty:")
        self.deck_qty_spin = ttk.Spinbox(self.deck_view_frame, from_=1, to=1000, width=6)
        self.deck_set_qty_btn = ttk.Button(self.deck_view_frame, text="Set Quantity", command=self._on_set_deck_qty)

        # Card preview (bottom)
        self.preview_frame = ttk.LabelFrame(self, text="Card Preview", padding=8)
        self.card_image_label = ttk.Label(self.preview_frame)
        self.color_icons_frame = ttk.Frame(self.preview_frame)

    # -----------------------------------------------------------------------------
    # Layout everything with pack() and grid()
    # -----------------------------------------------------------------------------
    def _layout_widgets(self):
        # Deck controls
        self.deck_frame.pack(fill="x", padx=10, pady=(10,5))
        self.new_deck_btn.grid(row=0, column=0, padx=4, pady=4)
        self.load_deck_btn.grid(row=0, column=1, padx=4, pady=4)
        self.save_deck_btn.grid(row=0, column=2, padx=4, pady=4)
        self.smart_build_btn.grid(row=0, column=3, padx=4, pady=4)
        self.simulate_btn.grid(row=0, column=4, padx=4, pady=4)
        self.record_btn.grid(row=0, column=5, padx=4, pady=4)
        self.theme_toggle.grid(row=0, column=6, padx=20, pady=4)
        self.deck_name_label.grid(row=0, column=7, padx=10, pady=4, sticky="w")

        # Collection panel
        self.coll_frame.pack(fill="y", side="left", padx=(10,5), pady=5)
        self.coll_frame.configure(width=280)
        self.coll_notebook.pack(fill="both", expand=True, padx=4, pady=4)
        self.remove_from_coll_btn.pack(fill="x", padx=4, pady=(4,4))
        qty_frame_c = ttk.Frame(self.coll_frame)
        qty_frame_c.pack(fill="x", padx=4, pady=(0,10))
        self.coll_qty_label.pack(in_=qty_frame_c, side="left")
        self.coll_qty_spin.pack(in_=qty_frame_c, side="left", padx=(4,10))
        self.coll_set_qty_btn.pack(in_=qty_frame_c, side="left")

        # Right side: search + deck
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
        self.remove_card_btn.pack(fill="x", padx=4, pady=(4,4))
        qty_frame_d = ttk.Frame(self.deck_view_frame)
        qty_frame_d.pack(fill="x", padx=4, pady=(0,10))
        self.deck_qty_label.pack(in_=qty_frame_d, side="left")
        self.deck_qty_spin.pack(in_=qty_frame_d, side="left", padx=(4,10))
        self.deck_set_qty_btn.pack(in_=qty_frame_d, side="left")

        # Preview panel
        self.preview_frame.pack(fill="x", padx=10, pady=(0,10))
        self.preview_frame.columnconfigure(0, weight=1)
        self.preview_frame.rowconfigure(0, weight=1)
        self.card_image_label.grid(row=0, column=0, padx=4, pady=4)
        self.color_icons_frame.grid(row=1, column=0, padx=4, pady=(4,8))

        # Populate collection + deck
        self._refresh_collection()
        self._refresh_deck()

    # -----------------------------------------------------------------------------
    # Apply VSCode Dark+ or Light theme
    # -----------------------------------------------------------------------------
    def apply_theme(self):
        mode = self.theme.get()
        style = ttk.Style()
        style.theme_use("clam")

        if mode == "dark":
            bg = "#1e1e1e"; fg = "#d4d4d4"; panel = "#252526"
            entry_bg = "#3c3c3c"; entry_fg = "#d4d4d4"; select_bg = "#264f78"
            btn_bg = "#0e639c"; btn_fg = "#ffffff"
        else:
            bg = "#ffffff"; fg = "#000000"; panel = "#f0f0f0"
            entry_bg = "#ffffff"; entry_fg = "#000000"; select_bg = "#cce5ff"
            btn_bg = "#007acc"; btn_fg = "#ffffff"

        style.configure("TLabelframe", background=panel, foreground=fg)
        style.configure("TLabelframe.Label", background=panel, foreground=fg)
        style.configure("TLabel", background=bg, foreground=fg)
        style.configure("TButton", background=btn_bg, foreground=btn_fg)
        style.map("TButton",
                  background=[("active", "#005a9e")] if mode=="dark" else [("active", "#0057e7")])
        style.configure("TCheckbutton", background=panel, foreground=fg)

        style.configure("Treeview",
                        background=entry_bg, foreground=entry_fg,
                        fieldbackground=entry_bg, selectbackground=select_bg, rowheight=48)
        style.map("Treeview", background=[("selected", select_bg)])
        style.configure("TEntry", fieldbackground=entry_bg, foreground=entry_fg)
        style.configure("TSpinbox", fieldbackground=entry_bg, foreground=entry_fg)
        style.configure("TCombobox", fieldbackground=entry_bg, foreground=entry_fg)

        self.configure(background=bg)
        for frame in [self.deck_frame, self.coll_frame, self.search_frame,
                      self.deck_view_frame, self.preview_frame, self.right_frame]:
            frame.configure(style="TLabelframe")

    # -----------------------------------------------------------------------------
    # Autocomplete: update Combobox values as user types
    # -----------------------------------------------------------------------------
    def _update_autocomplete(self):
        text = self.search_entry.get().strip()
        if len(text) < 2:
            return
        # Fetch up to 10 matching card names
        try:
            results = search_cards(text + "*",)  # wildcard to get broader matches
        except Exception:
            return
        names = [c.name for c in results[:10]]
        # Update the Combobox dropdown
        self.search_entry["values"] = names
        # If there are suggestions, open the dropdown
        if names:
            self.search_entry.event_generate("<Down>")

    # -----------------------------------------------------------------------------
    # When the user selects from autocomplete dropdown
    # -----------------------------------------------------------------------------
    def _on_autocomplete_select(self):
        selected = self.search_entry.get().strip()
        if not selected:
            return
        # Fetch full Card and preview it
        card = self.card_cache.get(selected) or get_card_by_name(selected)
        if not card:
            return
        self.card_cache[card.name] = card
        self._show_preview(card)

    # -----------------------------------------------------------------------------
    # Perform a normal “Search” (when user clicks Search)
    # -----------------------------------------------------------------------------
    def _on_perform_search(self):
        play_sound("click")
        query = self.search_entry.get().strip()
        if not query:
            return

        self.results_tree.delete(*self.results_tree.get_children())
        self.search_images.clear()

        try:
            results = search_cards(query)
        except Exception:
            results = []
        if not results:
            return

        for idx, card in enumerate(results):
            self.card_cache[card.name] = card
            img = None
            if card.image_url:
                try:
                    resp = requests.get(card.image_url, timeout=5)
                    resp.raise_for_status()
                    pil = Image.open(io.BytesIO(resp.content))
                    pil.thumbnail((80,120), Image.LANCZOS)
                    img = ImageTk.PhotoImage(pil)
                    self.search_images[card.name] = img
                except Exception:
                    img = None

            display = f"{card.name} ● {card.mana_cost or ''} ● {card.type_line} [{card.rarity}]"
            if img:
                self.results_tree.insert("", "end", iid=str(idx), text=display, image=img)
            else:
                self.results_tree.insert("", "end", iid=str(idx), text=display)

        self._clear_preview()

    # -----------------------------------------------------------------------------
    # When a search result is clicked → preview it
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
    # Show full image + color icons in preview
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
                image.thumbnail((250,350), Image.LANCZOS)
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
    # Add to Collection (silent, cache thumbnails automatically)
    # -----------------------------------------------------------------------------
    def _on_add_to_collection(self):
        play_sound("click")
        coll = load_collection()
        sel = self.results_tree.selection()
        if not sel:
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

        # Clear the search box so user can type another name
        self.search_entry.set("")
        self.search_entry.focus_set()
        self.results_tree.delete(*self.results_tree.get_children())
        self._clear_preview()

    # -----------------------------------------------------------------------------
    # Add to Deck (silent)
    # -----------------------------------------------------------------------------
    def _on_add_to_deck(self):
        play_sound("click")
        if not self.current_deck:
            return
        sel = self.results_tree.selection()
        if not sel:
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
            return
        self.card_cache[card.name] = card

        self.current_deck.add_card(card.name, qty)
        self.deck_name_label.config(text=f"Deck: {self.current_deck.name} ({self.current_deck.total_cards()} cards)")
        self._refresh_deck()

    # -----------------------------------------------------------------------------
    # Remove selected from collection
    # -----------------------------------------------------------------------------
    def _on_remove_from_collection(self):
        play_sound("click")
        current_tab = self.coll_notebook.tab(self.coll_notebook.select(), "text")
        tree = self.coll_trees[current_tab]
        sel = tree.selection()
        if not sel:
            return
        iid = sel[0]
        display = tree.item(iid, "text")
        _, name_part = display.split("×", 1)
        card_name = name_part.strip()

        coll = load_collection()
        if card_name in coll:
            del coll[card_name]
            save_collection(coll)
            self._refresh_collection()

    # -----------------------------------------------------------------------------
    # When a collection card is selected → populate spinbox
    # -----------------------------------------------------------------------------
    def _on_coll_select(self, event):
        current_tab = self.coll_notebook.tab(self.coll_notebook.select(), "text")
        tree = self.coll_trees[current_tab]
        sel = tree.selection()
        if not sel:
            return
        iid = sel[0]
        display = tree.item(iid, "text")
        qty_str, _ = display.split("×", 1)
        try:
            self.coll_qty_spin.set(qty_str.strip())
        except Exception:
            self.coll_qty_spin.set("1")

    # -----------------------------------------------------------------------------
    # Set quantity in collection (inline)
    # -----------------------------------------------------------------------------
    def _on_set_coll_qty(self):
        play_sound("click")
        current_tab = self.coll_notebook.tab(self.coll_notebook.select(), "text")
        tree = self.coll_trees[current_tab]
        sel = tree.selection()
        if not sel:
            return
        iid = sel[0]
        display = tree.item(iid, "text")
        _, name_part = display.split("×", 1)
        card_name = name_part.strip()

        try:
            new_qty = int(self.coll_qty_spin.get())
            if new_qty < 1:
                raise ValueError
        except Exception:
            new_qty = 1

        coll = load_collection()
        coll[card_name] = new_qty
        save_collection(coll)
        self._refresh_collection()

    # -----------------------------------------------------------------------------
    # Refresh the entire collection (all tabs) + autofit columns
    # -----------------------------------------------------------------------------
    def _refresh_collection(self):
        coll = load_collection()
        buckets = {tn: [] for tn in self.coll_trees}
        for name, qty in coll.items():
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

        for tab_name, tree in self.coll_trees.items():
            tree.delete(*tree.get_children())
            # Do NOT clear self.coll_images[tab_name]; reuse cached thumbnails
            fnt_spec = ttk.Style().lookup("Treeview", "font")
            if fnt_spec:
                fnt = tkfont.Font(font=fnt_spec)
            else:
                fnt = tkfont.nametofont("TkDefaultFont")

            max_width = 0
            for idx, (card_name, qty) in enumerate(sorted(buckets[tab_name], key=lambda x: x[0].lower())):
                card = self.card_cache.get(card_name)
                img = None
                if card and card.thumbnail_url:
                    if card_name not in self.coll_images[tab_name]:
                        try:
                            resp = requests.get(card.thumbnail_url, timeout=5)
                            resp.raise_for_status()
                            pil = Image.open(io.BytesIO(resp.content))
                            pil.thumbnail((24,36), Image.LANCZOS)
                            img_obj = ImageTk.PhotoImage(pil)
                            self.coll_images[tab_name][card_name] = img_obj
                        except Exception:
                            pass
                    img = self.coll_images[tab_name].get(card_name)

                display = f"{qty}× {card_name}"
                if img:
                    tree.insert("", "end", iid=str(idx), text=display, image=img)
                    text_w = fnt.measure(display)
                    total_w = text_w + 24 + 10
                else:
                    tree.insert("", "end", iid=str(idx), text=display)
                    total_w = fnt.measure(display) + 10

                if total_w > max_width:
                    max_width = total_w

            tree.column("#0", width=max_width)

    # -----------------------------------------------------------------------------
    # New Deck
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
    # Load Deck
    # -----------------------------------------------------------------------------
    def _on_load_deck(self):
        play_sound("click")
        choices = list_saved_decks()
        if not choices:
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

    # -----------------------------------------------------------------------------
    # Save Deck
    # -----------------------------------------------------------------------------
    def _on_save_deck(self):
        play_sound("click")
        if not self.current_deck:
            return
        dm_save_deck(self.current_deck)

    # -----------------------------------------------------------------------------
    # When a deck card is selected → preview + set spinbox
    # -----------------------------------------------------------------------------
    def _on_deck_select(self, event):
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
        qty_str, name_part = parts
        card_name = name_part.strip()
        if card_name.endswith("⚠"):
            card_name = card_name[:-1].strip()

        try:
            self.deck_qty_spin.set(qty_str.strip())
        except Exception:
            self.deck_qty_spin.set("1")

        card = self.card_cache.get(card_name) or get_card_by_name(card_name)
        if not card:
            return
        self.card_cache[card.name] = card
        self._show_preview(card)

    # -----------------------------------------------------------------------------
    # Set quantity in deck (inline)
    # -----------------------------------------------------------------------------
    def _on_set_deck_qty(self):
        play_sound("click")
        if not self.current_deck:
            return
        current_tab = self.deck_notebook.tab(self.deck_notebook.select(), "text")
        tree = self.deck_trees[current_tab]
        sel = tree.selection()
        if not sel:
            return
        iid = sel[0]
        display = tree.item(iid, "text")
        parts = display.split("×", 1)
        if len(parts) != 2:
            return
        _, name_part = parts
        card_name = name_part.strip()
        if card_name.endswith("⚠"):
            card_name = card_name[:-1].strip()

        try:
            new_qty = int(self.deck_qty_spin.get())
            if new_qty < 1:
                raise ValueError
        except Exception:
            new_qty = 1

        self.current_deck.cards[card_name] = new_qty
        self.deck_name_label.config(text=f"Deck: {self.current_deck.name} ({self.current_deck.total_cards()} cards)")
        self._refresh_deck()

    # -----------------------------------------------------------------------------
    # Remove selected from deck
    # -----------------------------------------------------------------------------
    def _on_remove_selected(self):
        play_sound("click")
        if not self.current_deck:
            return
        current_tab = self.deck_notebook.tab(self.deck_notebook.select(), "text")
        tree = self.deck_trees[current_tab]
        sel = tree.selection()
        if not sel:
            return
        iid = sel[0]
        display = tree.item(iid, "text")
        parts = display.split("×", 1)
        if len(parts) != 2:
            return
        _, name_part = parts
        card_name = name_part.strip()
        if card_name.endswith("⚠"):
            card_name = card_name[:-1].strip()

        if card_name in self.current_deck.cards:
            del self.current_deck.cards[card_name]
        self.deck_name_label.config(text=f"Deck: {self.current_deck.name} ({self.current_deck.total_cards()} cards)")
        self._refresh_deck()
        self._clear_preview()

    # -----------------------------------------------------------------------------
    # Refresh the deck tabs + autofit
    # -----------------------------------------------------------------------------
    def _refresh_deck(self):
        if not self.current_deck:
            for tree in self.deck_trees.values():
                tree.delete(*tree.get_children())
            return

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

        for tab_name, tree in self.deck_trees.items():
            tree.delete(*tree.get_children())
            self.deck_images[tab_name].clear()
            fnt_spec = ttk.Style().lookup("Treeview", "font")
            if fnt_spec:
                fnt = tkfont.Font(font=fnt_spec)
            else:
                fnt = tkfont.nametofont("TkDefaultFont")

            max_width = 0
            for idx, (card_name, qty) in enumerate(sorted(buckets[tab_name], key=lambda x: x[0].lower())):
                card = self.card_cache.get(card_name)
                img = None
                if card and card.thumbnail_url:
                    if card_name not in self.deck_images[tab_name]:
                        try:
                            resp = requests.get(card.thumbnail_url, timeout=5)
                            resp.raise_for_status()
                            pil = Image.open(io.BytesIO(resp.content))
                            pil.thumbnail((24,36), Image.LANCZOS)
                            img_obj = ImageTk.PhotoImage(pil)
                            self.deck_images[tab_name][card_name] = img_obj
                        except Exception:
                            pass
                    img = self.deck_images[tab_name].get(card_name)

                flag = ""
                if card and qty > 1 and not is_land(card):
                    flag = " ⚠"
                display = f"{qty}× {card_name}{flag}"
                if img:
                    tree.insert("", "end", iid=str(idx), text=display, image=img)
                    text_w = fnt.measure(display)
                    total_w = text_w + 24 + 10
                else:
                    tree.insert("", "end", iid=str(idx), text=display)
                    total_w = fnt.measure(display) + 10

                if total_w > max_width:
                    max_width = total_w

            tree.column("#0", width=max_width)

    # -----------------------------------------------------------------------------
    # Clear card preview
    # -----------------------------------------------------------------------------
    def _clear_preview(self):
        self.card_image_label.config(image="", text="")
        for w in self.color_icons_frame.winfo_children():
            w.destroy()
        self.preview_photo = None

    # -----------------------------------------------------------------------------
    # Simulate Battle
    # -----------------------------------------------------------------------------
    def _on_simulate_battle(self):
        play_sound("click")
        choices = list_saved_decks()
        if len(choices) < 2:
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
            return

        wins1, wins2, ties = simulate_match(deck1, deck2, iterations=1000)
        messagebox.showinfo(
            "Simulation Complete",
            f"Results (1000 games):\n\n"
            f"{d1} wins: {wins1}\n"
            f"{d2} wins: {wins2}\n"
            f"Ties: {ties}"
        )

    # -----------------------------------------------------------------------------
    # Record Result
    # -----------------------------------------------------------------------------
    def _on_record_result(self):
        play_sound("click")
        choices = list_saved_decks()
        if not choices:
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
            return

        record_manual_result(deck_name, opponent, result.upper())


# ──────────────────────────────────────────────────────────────────────────────
# Launch the app
# ──────────────────────────────────────────────────────────────────────────────
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
