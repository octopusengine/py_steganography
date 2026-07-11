"""
Visual Steganography Tool  –  Naor & Shamir, 1994
Výstup: A4 @ 150 DPI (1240 × 1754 px na výšku)
GUI: náhled + posun vrstvy 2, volba velikosti fontu, export PNG
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import random
import os

from lib.bitmap_font import FONT_9x13, FONT_H, FONT_W

try:
    from PIL import Image, ImageDraw
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# ─────────────────────────────────────────────────────────────────────────────
# Barvy GUI
# ─────────────────────────────────────────────────────────────────────────────
BG      = "#1a1a2e"
PANEL   = "#16213e"
ACCENT  = "#0f3460"
RED     = "#e94560"
FG      = "#eaeaea"
CVBG    = "#2a2a3e"

# ─────────────────────────────────────────────────────────────────────────────
# Tiskové rozměry: A4 @ 150 DPI, na výšku
# ─────────────────────────────────────────────────────────────────────────────
PRINT_W = 1240   # px
PRINT_H = 1754   # px

# font_scale → (subpixel_print_scale, char_w_logical, char_h_logical)
# subpixel_print_scale: kolik tiskových px zabírá 1 subpixel
# Logická mřížka: COLS = PRINT_W // (2 * sp), ROWS = PRINT_H // (2 * sp)
FONT_CONFIGS = {
    1: dict(sp=4, cw=10, ch=15),   # malý
    2: dict(sp=3, cw=20, ch=29),   # střední
    3: dict(sp=2, cw=30, ch=43),   # velký
    4: dict(sp=2, cw=40, ch=57),   # extra velký
}
# ─────────────────────────────────────────────────────────────────────────────
# Vykreslení textu do logické mřížky
# ─────────────────────────────────────────────────────────────────────────────
def render_text_to_grid(text, cols, rows, font_scale=1):
    """
    font_scale: integer, zvětší každý glyf (bilinear scale).
    char_w = (FONT_W + 1) * font_scale   (+1 mezera)
    char_h = (FONT_H + 2) * font_scale   (+2 mezera)
    """
    grid = [[False] * cols for _ in range(rows)]
    cw = (FONT_W + 1) * font_scale
    ch = (FONT_H + 2) * font_scale

    text = text.upper()
    max_per_line = max(1, (cols - 2) // cw)

    # Zalamování
    lines = []
    words = text.split()
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        if len(test) <= max_per_line:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    if not lines:
        lines = [""]

    total_h = len(lines) * ch
    start_row = max(1, (rows - total_h) // 2)

    for li, line in enumerate(lines):
        row0 = start_row + li * ch + font_scale  # +1 mezera nahoře
        total_w = len(line) * cw
        start_col = max(1, (cols - total_w) // 2)

        for ci, ch_char in enumerate(line):
            bitmap = FONT_9x13.get(ch_char, FONT_9x13.get(' ', [0]*FONT_H))
            for gy in range(FONT_H):
                row_bits = bitmap[gy]
                for gx in range(FONT_W):
                    if row_bits & (1 << (FONT_W - 1 - gx)):
                        # škálujeme pixel font_scale × font_scale
                        for sy in range(font_scale):
                            for sx in range(font_scale):
                                gr = row0 + gy * font_scale + sy
                                gc = start_col + ci * cw + gx * font_scale + sx
                                if 0 <= gr < rows and 0 <= gc < cols:
                                    grid[gr][gc] = True
    return grid


# ─────────────────────────────────────────────────────────────────────────────
# Načtení obrázku → logická mřížka
# ─────────────────────────────────────────────────────────────────────────────
def image_to_grid(path, cols, rows, threshold=128):
    """
    Načte PNG/JPG, převede na stupně šedi, prahuje a škáluje na cols×rows.
    Černý pixel (< threshold) → True, bílý → False.
    Obrázek se proporcionálně vejde (letterbox) do cols×rows.
    """
    from PIL import Image as PILImage
    img = PILImage.open(path).convert('L')   # šedotón 0–255

    # Proporcionální fit do cílové mřížky
    iw, ih = img.size
    scale = min(cols / iw, rows / ih)
    nw = max(1, int(iw * scale))
    nh = max(1, int(ih * scale))
    img = img.resize((nw, nh), PILImage.LANCZOS)

    grid = [[False] * cols for _ in range(rows)]
    ox = (cols - nw) // 2
    oy = (rows - nh) // 2

    pixels = img.load()
    for r in range(nh):
        for c in range(nw):
            if pixels[c, r] < threshold:
                grid[oy + r][ox + c] = True
    return grid


# ─────────────────────────────────────────────────────────────────────────────
# Naor-Shamir steganografický kodér
# block_size: 1 = standardní 2×2, 2 = zdvojený 4×4, 4 = zečtyřnásobený 8×8
# Každý logický pixel → blok (2*block_size)×(2*block_size) subpixelů.
# Větší blok = tolerantnější vůči nepřesnému zarovnání při překrytí.
# ─────────────────────────────────────────────────────────────────────────────
def encode_visual_stego(src1, src2, hidden, cols, rows, block_size=1):
    """Vrací (layer1, layer2).
    Fyzická velikost každé vrstvy: cols*(2*block_size) × rows*(2*block_size)."""
    bs = 2 * block_size          # délka strany makrobloku
    pw, ph = cols * bs, rows * bs
    L1 = [[False] * pw for _ in range(ph)]
    L2 = [[False] * pw for _ in range(ph)]

    # put: vyplní čtvrtiny makrobloku (každá čtvrtina = block_size × block_size)
    # p = seznam 4 bool hodnot pro 4 čtvrtiny v pořadí TL, TR, BL, BR
    def put(layer, r, c, p):
        pr, pc = r * bs, c * bs
        qs = block_size  # čtverec jedné čtvrtiny
        quadrants = [(0, 0), (0, qs), (qs, 0), (qs, qs)]
        for qi, (dr0, dc0) in enumerate(quadrants):
            val = p[qi]
            for dr in range(qs):
                for dc in range(qs):
                    layer[pr + dr0 + dr][pc + dc0 + dc] = val

    for r in range(rows):
        for c in range(cols):
            s1, s2, h = src1[r][c], src2[r][c], hidden[r][c]

            if h:   # hidden BLACK → OR musí dát 4/4
                if s1 and s2:
                    m1 = random.randint(0, 3)
                    m2 = random.choice([x for x in range(4) if x != m1])
                    p1 = [True]*4; p1[m1] = False
                    p2 = [True]*4; p2[m2] = False
                elif s1 and not s2:
                    m1 = random.randint(0, 3)
                    p1 = [True]*4; p1[m1] = False
                    sec = random.choice([x for x in range(4) if x != m1])
                    p2 = [False]*4; p2[m1] = True; p2[sec] = True
                elif not s1 and s2:
                    m2 = random.randint(0, 3)
                    p2 = [True]*4; p2[m2] = False
                    sec = random.choice([x for x in range(4) if x != m2])
                    p1 = [False]*4; p1[m2] = True; p1[sec] = True
                else:
                    ch = random.sample(range(4), 2)
                    p1 = [False]*4; p2 = [False]*4
                    for i in range(4):
                        if i in ch: p1[i] = True
                        else:       p2[i] = True
            else:   # hidden WHITE → OR musí dát 3/4
                if s1 and s2:
                    m = random.randint(0, 3)
                    p1 = [True]*4; p1[m] = False; p2 = list(p1)
                elif s1 and not s2:
                    m1 = random.randint(0, 3)
                    p1 = [True]*4; p1[m1] = False
                    ones = [x for x in range(4) if x != m1]
                    p2 = [False]*4
                    for i in random.sample(ones, 2): p2[i] = True
                elif not s1 and s2:
                    m2 = random.randint(0, 3)
                    p2 = [True]*4; p2[m2] = False
                    ones = [x for x in range(4) if x != m2]
                    p1 = [False]*4
                    for i in random.sample(ones, 2): p1[i] = True
                else:
                    c1 = random.sample(range(4), 2)
                    shared = random.choice(c1)
                    rem = [x for x in range(4) if x not in c1]
                    extra = random.choice(rem)
                    p1 = [False]*4; p2 = [False]*4
                    for i in c1: p1[i] = True
                    p2[shared] = True; p2[extra] = True

            put(L1, r, c, p1)
            put(L2, r, c, p2)

    return L1, L2


# ─────────────────────────────────────────────────────────────────────────────
# Čistá vizuální kryptografie (Naor-Shamir originál)
# Vrstvy vypadají jako náhodný šum – žádný viditelný text
# block_size: 1 = standardní 2×2, 2 = zdvojený 4×4, 4 = zečtyřnásobený 8×8
#   Bílý pixel v tajném: obě vrstvy sdílí stejné 2 čtvrtiny → OR = 2/4 (šedá)
#   Černý pixel v tajném: vrstvy mají komplementární čtvrtiny → OR = 4/4 (černá)
# ─────────────────────────────────────────────────────────────────────────────
def encode_visual_crypto(hidden, cols, rows, block_size=1):
    """
    Čistá 2-ze-2 vizuální kryptografie.
    Vrací (layer1, layer2) — každý vypadá jako náhodný šum.
    Tajný obraz se odhalí teprve překrytím (OR).
    Fyzická velikost: cols*(2*block_size) × rows*(2*block_size).
    """
    bs = 2 * block_size
    pw, ph = cols * bs, rows * bs
    L1 = [[False] * pw for _ in range(ph)]
    L2 = [[False] * pw for _ in range(ph)]

    # Čtyři možné vzory — každý má přesně 2 ze 4 čtvrtin černé
    PATTERNS = [
        [True,  True,  False, False],
        [False, False, True,  True ],
        [True,  False, True,  False],
        [False, True,  False, True ],
    ]

    def put(layer, r, c, p):
        pr, pc = r * bs, c * bs
        qs = block_size
        quadrants = [(0, 0), (0, qs), (qs, 0), (qs, qs)]
        for qi, (dr0, dc0) in enumerate(quadrants):
            val = p[qi]
            for dr in range(qs):
                for dc in range(qs):
                    layer[pr + dr0 + dr][pc + dc0 + dc] = val

    for r in range(rows):
        for c in range(cols):
            # Náhodně vybereme vzor pro vrstvu 1
            pat_idx = random.randint(0, 3)
            p1 = PATTERNS[pat_idx]

            if hidden[r][c]:
                # Černý pixel → OR = 4/4 → vrstva 2 je komplement vrstvy 1
                p2 = [not x for x in p1]
            else:
                # Bílý pixel → OR < 4/4 → vrstva 2 je JINÝ náhodný vzor (ne komplement)
                # Komplement by dal OR=4/4 (černý výsledek) — to nechceme.
                # Zbývají 3 vzory (všechny dají OR=2/4 nebo 3/4, nikdy 4/4).
                complement = [not x for x in p1]
                candidates = [p for p in PATTERNS if p != complement]
                p2 = random.choice(candidates)

            put(L1, r, c, p1)
            put(L2, r, c, p2)

    return L1, L2


def or_layers(L1, L2, ox=0, oy=0):
    ph = len(L1); pw = len(L1[0])
    R = [[False]*pw for _ in range(ph)]
    for r in range(ph):
        for c in range(pw):
            v1 = L1[r][c]
            r2, c2 = r + oy, c + ox
            v2 = L2[r2][c2] if 0 <= r2 < ph and 0 <= c2 < pw else False
            R[r][c] = v1 or v2
    return R


# ─────────────────────────────────────────────────────────────────────────────
# Export do PNG (Pillow)
# ─────────────────────────────────────────────────────────────────────────────
def export_png(layer, sp_scale, path, dpi=150):
    """Uloží vrstvu jako PNG. Každý subpixel = sp_scale × sp_scale tiskových px."""
    ph = len(layer)
    pw = len(layer[0])
    W = pw * sp_scale
    H = ph * sp_scale
    img = Image.new("1", (W, H), 1)   # 1-bit, bílá
    draw = ImageDraw.Draw(img)
    for r in range(ph):
        for c in range(pw):
            if layer[r][c]:
                x0, y0 = c * sp_scale, r * sp_scale
                draw.rectangle([x0, y0, x0 + sp_scale - 1, y0 + sp_scale - 1], fill=0)
    img.save(path, dpi=(dpi, dpi))


# ─────────────────────────────────────────────────────────────────────────────
# GUI – náhledový canvas (škálovaný na obrazovce)
# ─────────────────────────────────────────────────────────────────────────────
PREVIEW_W = 310   # šířka náhledu v px
PREVIEW_H = 440   # výška náhledu v px

class StegoApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Vizuální Steganografie – A4 / 150 DPI")
        self.configure(bg=BG)
        self.resizable(True, True)

        self.layer1 = None
        self.layer2 = None
        self.cols = 0
        self.rows = 0
        self.sp_scale = 3

        self.offset_x = 0
        self.offset_y = 0
        self._drag_start = None
        self._drag_ox = 0
        self._drag_oy = 0

        self._img1 = self._img2 = self._imgR = None

        # Cesty k nahraným obrázkům (None = použij text)
        self.img_path = {'e1': None, 'e2': None, 'eh': None}

        # Velikost pixelového bloku: 1=2×2, 2=4×4, 4=8×8
        self.block_size = tk.IntVar(value=1)

        # Režim: "crypto" = čistá kryptografie, "stego" = steganografie
        self.mode = tk.StringVar(value="crypto")

        self._build_ui()
        self.after(300, self.generate)


    # ── UI ────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        # Nadpis
        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill='x', padx=14, pady=(10, 4))
        tk.Label(hdr, text="🔐 Vizuální Kryptografie & Steganografie",
                 bg=BG, fg=RED, font=("Helvetica", 18, "bold")).pack(side='left')
        tk.Label(hdr, text="A4 · 150 DPI · Naor & Shamir 1994",
                 bg=BG, fg="#556688", font=("Helvetica", 10)).pack(side='left', padx=10)

        # ── Záložky ──────────────────────────────────────────────────────────
        style = ttk.Style()
        style.theme_use('default')
        style.configure('TNotebook',          background=BG,    borderwidth=0)
        style.configure('TNotebook.Tab',      background=ACCENT, foreground=FG,
                        font=('Helvetica', 11, 'bold'), padding=[16, 6])
        style.map('TNotebook.Tab',
                  background=[('selected', PANEL)],
                  foreground=[('selected', RED)])

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill='both', expand=True, padx=10, pady=(0, 6))

        # Záložka 1 — tvorba
        self.tab_create = tk.Frame(self.nb, bg=BG)
        self.nb.add(self.tab_create, text="  ✏️  Tvorba vrstev  ")

        # Záložka 2 — kontrola
        self.tab_verify = tk.Frame(self.nb, bg=BG)
        self.nb.add(self.tab_verify, text="  🔍  Kontrola překrytí  ")

        self._build_create_tab(self.tab_create)
        self._build_verify_tab(self.tab_verify)

    def _build_create_tab(self, parent):
        """Původní obsah — tvorba vrstev."""

        # ── Přepínač režimu ──────────────────────────────────────────────────
        mode_frame = tk.Frame(parent, bg=PANEL, padx=12, pady=8)
        mode_frame.pack(fill='x', padx=6, pady=(6, 0))

        tk.Label(mode_frame, text="Režim:", bg=PANEL, fg=FG,
                 font=("Helvetica", 10, "bold")).pack(side='left', padx=(0, 10))

        rb_opts = dict(bg=PANEL, fg=FG, selectcolor=ACCENT,
                       activebackground=PANEL, activeforeground=RED,
                       font=("Helvetica", 10), cursor='hand2')

        tk.Radiobutton(mode_frame, text="🎲 Vizuální kryptografie  (vrstvy = náhodný šum, tajný text se odhalí překrytím)",
                       variable=self.mode, value="crypto",
                       command=self._on_mode_change, **rb_opts).pack(side='left', padx=(0, 20))

        tk.Radiobutton(mode_frame, text="🖼 Vizuální steganografie  (vrstvy nesou vlastní text + skrývají třetí)",
                       variable=self.mode, value="stego",
                       command=self._on_mode_change, **rb_opts).pack(side='left')

        # ── Velikost pixelového bloku ─────────────────────────────────────────
        pix_frame = tk.Frame(parent, bg=PANEL, padx=12, pady=6)
        pix_frame.pack(fill='x', padx=6, pady=(0, 0))

        tk.Label(pix_frame, text="Velikost pixelu:", bg=PANEL, fg=FG,
                 font=("Helvetica", 10, "bold")).pack(side='left', padx=(0, 10))

        rb_pix = dict(bg=PANEL, fg=FG, selectcolor=ACCENT,
                      activebackground=PANEL, activeforeground=RED,
                      font=("Helvetica", 10), cursor='hand2')

        tk.Radiobutton(pix_frame,
                       text="◼ 1× — standardní 2×2 px  (nejlepší kresba, nutné přesné zarovnání)",
                       variable=self.block_size, value=1, **rb_pix).pack(side='left', padx=(0, 16))
        tk.Radiobutton(pix_frame,
                       text="◼◼ 2× — zdvojený 4×4 px  (hrubší, tolerantnější)",
                       variable=self.block_size, value=2, **rb_pix).pack(side='left', padx=(0, 16))
        tk.Radiobutton(pix_frame,
                       text="◼◼◼◼ 4× — zečtyřnásobený 8×8 px  (nejhrubší, nejodolnější)",
                       variable=self.block_size, value=4, **rb_pix).pack(side='left')

        # ── Vstupní panel ────────────────────────────────────────────────────
        inp = tk.Frame(parent, bg=PANEL, padx=10, pady=8)
        inp.pack(fill='x', padx=6, pady=0)

        lbl_opts = dict(bg=PANEL, fg=FG, font=("Helvetica", 10))
        ent_opts = dict(font=("Helvetica", 11), width=22,
                        bg="#0d1b2e", fg=RED, insertbackground=RED,
                        relief='flat', bd=4)

        # Řádky pro steganografii (vrstva 1 + vrstva 2) — dynamicky skryté
        self._lbl_e1 = tk.Label(inp, text="Text Vrstvy 1:", **lbl_opts)
        self._lbl_e1.grid(row=0, column=0, sticky='e', padx=(6,3), pady=3)
        self.e1 = tk.Entry(inp, **ent_opts); self.e1.insert(0, "STEGO")
        self.e1.grid(row=0, column=1, padx=(0,4), pady=3)
        self._btn_img_e1 = tk.Button(inp, text="🖼", width=3,
            command=lambda: self._pick_image('e1'),
            bg=ACCENT, fg='white', relief='flat', cursor='hand2', font=("Helvetica",10))
        self._btn_img_e1.grid(row=0, column=2, padx=(0,8), pady=3)
        self._clr_e1 = tk.Button(inp, text="✕", width=2,
            command=lambda: self._clear_image('e1'),
            bg="#330011", fg='#aa4455', relief='flat', cursor='hand2', font=("Helvetica",9))
        self._clr_e1.grid(row=0, column=3, padx=(0,6), pady=3)
        self._iname_e1 = tk.Label(inp, text="", bg=PANEL, fg="#557799",
            font=("Helvetica", 8), width=14, anchor='w')
        self._iname_e1.grid(row=0, column=4, sticky='w', pady=3)

        self._lbl_e2 = tk.Label(inp, text="Text Vrstvy 2:", **lbl_opts)
        self._lbl_e2.grid(row=1, column=0, sticky='e', padx=(6,3), pady=3)
        self.e2 = tk.Entry(inp, **ent_opts); self.e2.insert(0, "RYBA")
        self.e2.grid(row=1, column=1, padx=(0,4), pady=3)
        self._btn_img_e2 = tk.Button(inp, text="🖼", width=3,
            command=lambda: self._pick_image('e2'),
            bg=ACCENT, fg='white', relief='flat', cursor='hand2', font=("Helvetica",10))
        self._btn_img_e2.grid(row=1, column=2, padx=(0,8), pady=3)
        self._clr_e2 = tk.Button(inp, text="✕", width=2,
            command=lambda: self._clear_image('e2'),
            bg="#330011", fg='#aa4455', relief='flat', cursor='hand2', font=("Helvetica",9))
        self._clr_e2.grid(row=1, column=3, padx=(0,6), pady=3)
        self._iname_e2 = tk.Label(inp, text="", bg=PANEL, fg="#557799",
            font=("Helvetica", 8), width=14, anchor='w')
        self._iname_e2.grid(row=1, column=4, sticky='w', pady=3)

        # Tajný text — vždy viditelný
        self._lbl_eh = tk.Label(inp, text="Tajný text:", **lbl_opts)
        self._lbl_eh.grid(row=2, column=0, sticky='e', padx=(6,3), pady=3)
        self.eh = tk.Entry(inp, **ent_opts); self.eh.insert(0, "CLAUDE")
        self.eh.grid(row=2, column=1, padx=(0,4), pady=3)
        self._btn_img_eh = tk.Button(inp, text="🖼", width=3,
            command=lambda: self._pick_image('eh'),
            bg=ACCENT, fg='white', relief='flat', cursor='hand2', font=("Helvetica",10))
        self._btn_img_eh.grid(row=2, column=2, padx=(0,8), pady=3)
        self._clr_eh = tk.Button(inp, text="✕", width=2,
            command=lambda: self._clear_image('eh'),
            bg="#330011", fg='#aa4455', relief='flat', cursor='hand2', font=("Helvetica",9))
        self._clr_eh.grid(row=2, column=3, padx=(0,6), pady=3)
        self._iname_eh = tk.Label(inp, text="", bg=PANEL, fg="#557799",
            font=("Helvetica", 8), width=14, anchor='w')
        self._iname_eh.grid(row=2, column=4, sticky='w', pady=3)

        # Volba velikosti fontu
        fnt_frame = tk.Frame(inp, bg=PANEL)
        fnt_frame.grid(row=0, column=5, rowspan=3, padx=(10, 6), sticky='ns')

        tk.Label(fnt_frame, text="Velikost fontu:", bg=PANEL, fg=FG,
                 font=("Helvetica", 10)).pack(anchor='w')

        self.font_var = tk.IntVar(value=2)
        font_names = {1: "Malý (×1)", 2: "Střední (×2)", 3: "Velký (×3)", 4: "Extra (×4)"}
        self.font_label = tk.Label(fnt_frame, text=font_names[2],
                                   bg=PANEL, fg=RED, font=("Helvetica", 10, "bold"))
        self.font_label.pack(anchor='w', pady=(0, 4))

        tk.Scale(fnt_frame, from_=1, to=4, orient='horizontal',
                 variable=self.font_var, length=160,
                 bg=PANEL, fg=FG, troughcolor=ACCENT,
                 highlightthickness=0, bd=0).pack()

        self.font_var.trace_add('write',
            lambda *_: self.font_label.config(text=font_names.get(self.font_var.get(), "")))

        # Tlačítka
        btn_frame = tk.Frame(inp, bg=PANEL)
        btn_frame.grid(row=0, column=6, rowspan=3, padx=(10, 4), sticky='ns')

        tk.Button(btn_frame, text="⚡ Vygenerovat", command=self.generate,
                  bg=RED, fg='white', font=("Helvetica", 11, "bold"),
                  relief='flat', padx=14, pady=8, cursor='hand2').pack(fill='x', pady=(0,6))

        if HAS_PIL:
            tk.Button(btn_frame, text="💾 Export PNG", command=self.export_all,
                      bg=ACCENT, fg='white', font=("Helvetica", 10, "bold"),
                      relief='flat', padx=14, pady=6, cursor='hand2').pack(fill='x')
        else:
            tk.Label(btn_frame, text="(pip install pillow\npro export PNG)",
                     bg=PANEL, fg="#666688", font=("Helvetica", 8),
                     justify='center').pack()

        # Hint
        self.hint_lbl = tk.Label(parent,
                 text="💡 Přetáhněte Vrstvu 2 myší přes Vrstvu 1, nebo použijte klávesy ← ↑ → ↓",
                 bg=BG, fg="#88aacc", font=("Helvetica", 10))
        self.hint_lbl.pack(pady=(4, 2))

        # Canvasy
        cvs_frame = tk.Frame(parent, bg=BG)
        cvs_frame.pack(fill='both', expand=True, padx=6, pady=4)

        self.cv1 = self._make_canvas(cvs_frame, "Vrstva 1", 0)
        self.cv2 = self._make_canvas(cvs_frame, "Vrstva 2 — přetáhni sem →", 1)
        self.cvR = self._make_canvas(cvs_frame, "Výsledek (OR překrytí)", 2)

        for i in range(3):
            cvs_frame.columnconfigure(i, weight=1)

        # Stavový řádek
        ctrl = tk.Frame(parent, bg=BG)
        ctrl.pack(fill='x', padx=6, pady=(0, 8))

        tk.Label(ctrl, text="Posun vrstvy 2:", bg=BG, fg=FG,
                 font=("Helvetica", 10)).pack(side='left')
        self.offset_lbl = tk.Label(ctrl, text="X=0  Y=0",
                                    bg=BG, fg=RED, font=("Helvetica", 10, "bold"))
        self.offset_lbl.pack(side='left', padx=8)

        self.size_lbl = tk.Label(ctrl, text="",
                                  bg=BG, fg="#557799", font=("Helvetica", 9))
        self.size_lbl.pack(side='left', padx=12)

        tk.Button(ctrl, text="↺ Resetovat", command=self.reset_offset,
                  bg=ACCENT, fg='white', relief='flat', padx=10, cursor='hand2').pack(side='left')

        # Drag na cv2
        self.cv2.bind("<ButtonPress-1>",   self._drag_start_ev)
        self.cv2.bind("<B1-Motion>",        self._drag_motion_ev)
        self.cv2.bind("<ButtonRelease-1>", self._drag_end_ev)

        # Klávesy (výchozí — záložka tvorby)
        self.bind("<Left>",  lambda e: self._shift(-1, 0))
        self.bind("<Right>", lambda e: self._shift( 1, 0))
        self.bind("<Up>",    lambda e: self._shift(0, -1))
        self.bind("<Down>",  lambda e: self._shift(0,  1))

        # Nastavení počátečního stavu widgetů
        self._on_mode_change()

    def _pick_image(self, key):
        """Otevře dialog pro výběr obrázku pro daný vstupní slot."""
        path = filedialog.askopenfilename(
            title=f"Vyberte obrázek ({key})",
            filetypes=[("Obrázky", "*.png *.jpg *.jpeg *.bmp *.gif *.webp"),
                       ("Všechny soubory", "*.*")])
        if not path:
            return
        self.img_path[key] = path
        fname = os.path.basename(path)
        short = fname if len(fname) <= 16 else fname[:13] + "..."
        lbl = getattr(self, f'_iname_{key}')
        lbl.config(text=f"📎 {short}", fg=RED)
        # Zašedni textové pole
        entry = getattr(self, key)
        entry.config(state='disabled', bg="#0a1020", fg="#334455")

    def _clear_image(self, key):
        """Odstraní vybraný obrázek a obnoví textové pole."""
        self.img_path[key] = None
        lbl = getattr(self, f'_iname_{key}')
        lbl.config(text="", fg="#557799")
        entry = getattr(self, key)
        # Obnov stav jen pokud je slot aktivní (stego e1/e2 závisí na režimu)
        if key in ('e1', 'e2') and self.mode.get() == 'crypto':
            return   # v crypto režimu zůstane disabled
        entry.config(state='normal', bg="#0d1b2e", fg=RED)

    def _get_grid(self, key, cols, rows, font_scale):
        """Vrátí logickou mřížku: z obrázku nebo z textu."""
        if self.img_path[key]:
            try:
                return image_to_grid(self.img_path[key], cols, rows)
            except Exception as ex:
                messagebox.showerror("Chyba načtení obrázku",
                    f"Nelze načíst {self.img_path[key]}:\n{ex}")
                return [[False]*cols for _ in range(rows)]
        else:
            entry = getattr(self, key)
            text = entry.get().strip() or "TEXT"
            return render_text_to_grid(text, cols, rows, font_scale)

    def _on_mode_change(self):
        """Zobrazí/skryje pole podle zvoleného režimu."""
        is_stego = self.mode.get() == "stego"
        fg_lbl = FG if is_stego else "#444466"

        for w in (self._lbl_e1, self._lbl_e2, self._btn_img_e1, self._btn_img_e2,
                  self._clr_e1, self._clr_e2, self._iname_e1, self._iname_e2):
            w.config(fg=fg_lbl if hasattr(w, 'config') else None)

        for key in ('e1', 'e2'):
            entry = getattr(self, key)
            if is_stego:
                # Aktivuj jen pokud nemá nahraný obrázek
                if not self.img_path[key]:
                    entry.config(state='normal', bg="#0d1b2e", fg=RED)
                btn = getattr(self, f'_btn_img_{key}')
                btn.config(state='normal')
                getattr(self, f'_clr_{key}').config(state='normal')
            else:
                entry.config(state='disabled', bg="#0a1020", fg="#334455")
                getattr(self, f'_btn_img_{key}').config(state='disabled')
                getattr(self, f'_clr_{key}').config(state='disabled')

        # Popis tajného textu
        self._lbl_eh.config(text="Tajný text:" if is_stego else "Tajný text (jediný vstup):")

        # Popis canvasů
        try:
            if is_stego:
                self.cv1.master.children['!label'].config(text="Vrstva 1 (s textem/obr.)")
                self.cv2.master.children['!label'].config(text="Vrstva 2 — přetáhni →")
            else:
                self.cv1.master.children['!label'].config(text="Vrstva 1 (náhodný šum)")
                self.cv2.master.children['!label'].config(text="Vrstva 2 — přetáhni →")
        except (KeyError, AttributeError):
            pass

    def _make_canvas(self, parent, title, col):
        f = tk.Frame(parent, bg=PANEL, bd=1, relief='solid')
        f.grid(row=0, column=col, padx=5, pady=4, sticky='nsew')
        tk.Label(f, text=title, bg=PANEL, fg="#99bbdd",
                 font=("Helvetica", 9, "bold")).pack(pady=(5, 1))
        cv = tk.Canvas(f, bg=CVBG, highlightthickness=1,
                       highlightbackground=ACCENT,
                       width=PREVIEW_W, height=PREVIEW_H, cursor='fleur')
        cv.pack(padx=6, pady=(0, 6))
        return cv

    # ── generování ────────────────────────────────────────────────────────────
    def generate(self):
        fs = self.font_var.get()
        cfg = FONT_CONFIGS[fs]
        self.sp_scale = cfg['sp']
        bs = self.block_size.get()   # 1, 2 nebo 4

        # Logická mřížka: přizpůsobíme tak, aby tisková velikost zůstala A4
        # Fyzická vrstva = cols*(2*bs) × rows*(2*bs) subpixelů
        # Tisk = fyzická × sp_scale px
        # Cíl: cols*(2*bs)*sp_scale ≈ PRINT_W → cols = PRINT_W // (2*bs*sp_scale)
        self.cols = PRINT_W // (2 * bs * cfg['sp'])
        self.rows = PRINT_H // (2 * bs * cfg['sp'])

        hidden = self._get_grid('eh', self.cols, self.rows, fs)

        if self.mode.get() == "crypto":
            self.layer1, self.layer2 = encode_visual_crypto(
                hidden, self.cols, self.rows, block_size=bs)
        else:
            src1 = self._get_grid('e1', self.cols, self.rows, fs)
            src2 = self._get_grid('e2', self.cols, self.rows, fs)
            self.layer1, self.layer2 = encode_visual_stego(
                src1, src2, hidden, self.cols, self.rows, block_size=bs)

        pw = len(self.layer1[0]) * self.sp_scale
        ph = len(self.layer1)    * self.sp_scale
        bs_px = 2 * bs
        self.size_lbl.config(
            text=f"Tisková velikost: {pw} × {ph} px  |  pixel blok: {bs_px}×{bs_px}  (@150 DPI ≈ A4)")

        self.reset_offset()

    def _draw_all(self):
        if self.layer1 is None:
            return

        ph_sub = len(self.layer1)      # rows*(2*bs)
        pw_sub = len(self.layer1[0])   # cols*(2*bs)

        self._img1 = self._layer_to_preview(self.layer1, ph_sub, pw_sub)
        self._img2 = self._layer_to_preview(self.layer2, ph_sub, pw_sub)
        merged = or_layers(self.layer1, self.layer2, self.offset_x, self.offset_y)
        self._imgR = self._layer_to_preview(merged, ph_sub, pw_sub)

        # Nastav velikost canvasů podle skutečné velikosti náhledu
        img_w = self._img1.width()
        img_h = self._img1.height()
        for cv, img in [(self.cv1, self._img1), (self.cv2, self._img2), (self.cvR, self._imgR)]:
            cv.config(width=img_w, height=img_h)
            cv.delete('all')
            cv.create_image(img_w // 2, img_h // 2, anchor='center', image=img)

        self.offset_lbl.config(text=f"X={self.offset_x:+d}  Y={self.offset_y:+d}")

    def _layer_to_preview(self, layer, ph, pw):
        """Převede bool mřížku na tk.PhotoImage škálovanou tak,
        aby se celý obraz vešel do PREVIEW_W × PREVIEW_H."""
        if HAS_PIL:
            from PIL import Image as PILImage
            # Sestavíme PIL obraz přímo z dat
            img_pil = PILImage.new("1", (pw, ph), 1)
            px = img_pil.load()
            for r in range(ph):
                for c in range(pw):
                    if layer[r][c]:
                        px[c, r] = 0
            # Float scale — vejde se celý obraz
            scale = min(PREVIEW_W / pw, PREVIEW_H / ph)
            nw = max(1, int(pw * scale))
            nh = max(1, int(ph * scale))
            img_pil = img_pil.resize((nw, nh), PILImage.LANCZOS)
            # Převod na RGB pro tk.PhotoImage
            img_rgb = img_pil.convert("RGB")
            tk_img = tk.PhotoImage(width=nw, height=nh)
            data = []
            px2 = img_rgb.load()
            for r in range(nh):
                row = []
                for c in range(nw):
                    v = px2[c, r]
                    row.append(f'#{v[0]:02x}{v[1]:02x}{v[2]:02x}')
                data.append(' '.join(row))
            tk_img.put(data)
            return tk_img
        else:
            # Fallback bez Pillow — celočíselné škálování
            sc = max(1, int(min(PREVIEW_W / pw, PREVIEW_H / ph)))
            nw, nh = pw * sc, ph * sc
            img = tk.PhotoImage(width=nw, height=nh)
            rows_data = []
            for r in range(ph):
                row = ['#000000' if layer[r][c] else '#ffffff' for c in range(pw)]
                row_str = ' '.join(s for s in row for _ in range(sc))
                rows_data.extend([row_str] * sc)
            img.put(rows_data)
            return img

    def _preview_scale(self):
        """Aktuální float scale náhledu tvorby (pro drag)."""
        if self.layer1 is None:
            return 1.0
        ph = len(self.layer1); pw = len(self.layer1[0])
        return min(PREVIEW_W / pw, PREVIEW_H / ph)

    # ── drag ──────────────────────────────────────────────────────────────────
    def _drag_start_ev(self, e):
        self._drag_start = (e.x, e.y)
        self._drag_ox = self.offset_x
        self._drag_oy = self.offset_y

    def _drag_motion_ev(self, e):
        if self._drag_start is None:
            return
        sc = self._preview_scale()
        dx = e.x - self._drag_start[0]
        dy = e.y - self._drag_start[1]
        self.offset_x = self._drag_ox - int(dx / sc)
        self.offset_y = self._drag_oy - int(dy / sc)
        self._draw_all()

    def _drag_end_ev(self, e):
        self._drag_start = None

    def _shift(self, dx, dy):
        self.offset_x += dx
        self.offset_y += dy
        self._draw_all()

    def reset_offset(self):
        self.offset_x = 0
        self.offset_y = 0
        self._draw_all()

    # ── export ────────────────────────────────────────────────────────────────
    def export_all(self):
        if not HAS_PIL:
            messagebox.showerror("Chyba", "Pillow není nainstalován.\npip install pillow")
            return
        if self.layer1 is None:
            messagebox.showwarning("Pozor", "Nejprve vygenerujte obrázky.")
            return

        folder = filedialog.askdirectory(title="Vyberte složku pro export PNG")
        if not folder:
            return

        sp = self.sp_scale
        p1 = os.path.join(folder, "vrstva1.png")
        p2 = os.path.join(folder, "vrstva2.png")
        pR = os.path.join(folder, "vysledek.png")

        export_png(self.layer1, sp, p1)
        export_png(self.layer2, sp, p2)
        merged = or_layers(self.layer1, self.layer2, 0, 0)
        export_png(merged, sp, pR)

        pw = len(self.layer1[0]) * sp
        ph = len(self.layer1)    * sp
        messagebox.showinfo("Export dokončen",
            f"Uloženo do:\n{folder}\n\n"
            f"• vrstva1.png\n• vrstva2.png\n• vysledek.png\n\n"
            f"Rozměry: {pw} × {ph} px  (A4 @ 150 DPI)")


    # ── Záložka 2: Kontrola překrytí ─────────────────────────────────────────
    def _build_verify_tab(self, parent):
        """Načte dvě PNG vrstvy a zobrazí jejich OR-překrytí."""

        # Stav kontrolního nástroje
        self._v_layer1  = None   # bool mřížka vrstvy 1
        self._v_layer2  = None   # bool mřížka vrstvy 2
        self._v_path1   = tk.StringVar(value="")
        self._v_path2   = tk.StringVar(value="")
        self._v_fullpath1 = ""
        self._v_fullpath2 = ""
        self._v_offset_x = 0
        self._v_offset_y = 0
        self._v_drag_start = None
        self._v_drag_ox = 0
        self._v_drag_oy = 0
        self._v_img1 = self._v_img2 = self._v_imgR = None

        # ── Horní panel — načítání souborů ───────────────────────────────────
        top = tk.Frame(parent, bg=PANEL, padx=12, pady=10)
        top.pack(fill='x', padx=6, pady=(8, 0))

        tk.Label(top, text="Kontrola fyzického překrytí dvou vrstev",
                 bg=PANEL, fg=RED, font=("Helvetica", 12, "bold")).grid(
                 row=0, column=0, columnspan=6, sticky='w', pady=(0, 8))

        ent_opts = dict(font=("Helvetica", 10), width=38,
                        bg="#0d1b2e", fg=RED, insertbackground=RED,
                        relief='flat', bd=3, state='readonly',
                        readonlybackground="#0d1b2e")
        lbl_opts = dict(bg=PANEL, fg=FG, font=("Helvetica", 10))

        # Vrstva 1
        tk.Label(top, text="Vrstva 1 (PNG):", **lbl_opts).grid(
            row=1, column=0, sticky='e', padx=(0, 6), pady=4)
        tk.Entry(top, textvariable=self._v_path1, **ent_opts).grid(
            row=1, column=1, padx=(0, 6), pady=4)
        tk.Button(top, text="📂 Otevřít", cursor='hand2',
                  bg=ACCENT, fg='white', relief='flat', padx=10,
                  command=lambda: self._v_pick(1)).grid(row=1, column=2, padx=(0, 16), pady=4)

        # Vrstva 2
        tk.Label(top, text="Vrstva 2 (PNG):", **lbl_opts).grid(
            row=2, column=0, sticky='e', padx=(0, 6), pady=4)
        tk.Entry(top, textvariable=self._v_path2, **ent_opts).grid(
            row=2, column=1, padx=(0, 6), pady=4)
        tk.Button(top, text="📂 Otevřít", cursor='hand2',
                  bg=ACCENT, fg='white', relief='flat', padx=10,
                  command=lambda: self._v_pick(2)).grid(row=2, column=2, padx=(0, 16), pady=4)

        # Tlačítka akce
        btn_frame = tk.Frame(top, bg=PANEL)
        btn_frame.grid(row=1, column=3, rowspan=2, padx=(0, 4), sticky='ns')

        tk.Button(btn_frame, text="⚡ Zobrazit překrytí",
                  bg=RED, fg='white', font=("Helvetica", 10, "bold"),
                  relief='flat', padx=12, pady=6, cursor='hand2',
                  command=self._v_compute).pack(fill='x', pady=(0, 5))

        if HAS_PIL:
            tk.Button(btn_frame, text="💾 Uložit výsledek",
                      bg=ACCENT, fg='white', font=("Helvetica", 10),
                      relief='flat', padx=12, pady=5, cursor='hand2',
                      command=self._v_export).pack(fill='x')

        # Info label
        self._v_info = tk.Label(top, text="Načtěte obě vrstvy a klikněte na Zobrazit překrytí.",
                                 bg=PANEL, fg="#88aacc", font=("Helvetica", 9),
                                 justify='left')
        self._v_info.grid(row=3, column=0, columnspan=6, sticky='w', pady=(6, 0))

        # ── Hint ─────────────────────────────────────────────────────────────
        tk.Label(parent,
                 text="💡 Přetáhněte Vrstvu 2 myší nebo použijte ← ↑ → ↓ pro jemné doladění zarovnání",
                 bg=BG, fg="#88aacc", font=("Helvetica", 10)).pack(pady=(6, 2))

        # ── Canvasy ───────────────────────────────────────────────────────────
        cvs = tk.Frame(parent, bg=BG)
        cvs.pack(fill='both', expand=True, padx=6, pady=4)

        self._v_cv1 = self._v_make_canvas(cvs, "Vrstva 1", 0)
        self._v_cv2 = self._v_make_canvas(cvs, "Vrstva 2 — přetáhni →", 1)
        self._v_cvR = self._v_make_canvas(cvs, "Výsledek (OR překrytí)", 2)
        for i in range(3):
            cvs.columnconfigure(i, weight=1)

        # ── Stavový řádek ─────────────────────────────────────────────────────
        ctrl = tk.Frame(parent, bg=BG)
        ctrl.pack(fill='x', padx=6, pady=(0, 8))

        tk.Label(ctrl, text="Posun vrstvy 2:", bg=BG, fg=FG,
                 font=("Helvetica", 10)).pack(side='left')
        self._v_offset_lbl = tk.Label(ctrl, text="X=0  Y=0",
                                       bg=BG, fg=RED, font=("Helvetica", 10, "bold"))
        self._v_offset_lbl.pack(side='left', padx=8)

        tk.Button(ctrl, text="↺ Resetovat", command=self._v_reset,
                  bg=ACCENT, fg='white', relief='flat', padx=10, cursor='hand2').pack(side='left')

        # Drag na cv2
        self._v_cv2.bind("<ButtonPress-1>",   self._v_drag_start)
        self._v_cv2.bind("<B1-Motion>",        self._v_drag_motion)
        self._v_cv2.bind("<ButtonRelease-1>", self._v_drag_end)

        # Klávesy (aktivní jen na záložce kontroly)
        self.nb.bind("<<NotebookTabChanged>>", self._on_tab_change)

    def _on_tab_change(self, event):
        """Přepne klávesové vazby podle aktivní záložky."""
        tab = self.nb.index(self.nb.select())
        self.unbind("<Left>"); self.unbind("<Right>")
        self.unbind("<Up>");   self.unbind("<Down>")
        if tab == 0:
            self.bind("<Left>",  lambda e: self._shift(-1, 0))
            self.bind("<Right>", lambda e: self._shift( 1, 0))
            self.bind("<Up>",    lambda e: self._shift(0, -1))
            self.bind("<Down>",  lambda e: self._shift(0,  1))
        else:
            self.bind("<Left>",  lambda e: self._v_shift(-1, 0))
            self.bind("<Right>", lambda e: self._v_shift( 1, 0))
            self.bind("<Up>",    lambda e: self._v_shift(0, -1))
            self.bind("<Down>",  lambda e: self._v_shift(0,  1))

    def _v_make_canvas(self, parent, title, col):
        f = tk.Frame(parent, bg=PANEL, bd=1, relief='solid')
        f.grid(row=0, column=col, padx=5, pady=4, sticky='nsew')
        tk.Label(f, text=title, bg=PANEL, fg="#99bbdd",
                 font=("Helvetica", 9, "bold")).pack(pady=(5, 1))
        cv = tk.Canvas(f, bg=CVBG, highlightthickness=1,
                       highlightbackground=ACCENT,
                       width=PREVIEW_W, height=PREVIEW_H, cursor='fleur')
        cv.pack(padx=6, pady=(0, 6))
        return cv

    # ── Načtení PNG vrstvy jako bool mřížky ──────────────────────────────────
    def _png_to_bool_grid(self, path):
        """Načte PNG (libovolné rozlišení) → bool mřížka. Práh 128."""
        from PIL import Image as PILImage
        img = PILImage.open(path).convert('L')
        w, h = img.size
        px = img.load()
        return [[px[c, r] < 128 for c in range(w)] for r in range(h)]

    def _v_pick(self, which):
        path = filedialog.askopenfilename(
            title=f"Vyberte PNG vrstvu {which}",
            filetypes=[("Obrázky", "*.png *.jpg *.jpeg *.bmp"), ("Vše", "*.*")])
        if not path:
            return
        if which == 1:
            self._v_path1.set(os.path.basename(path))
            self._v_fullpath1 = path
        else:
            self._v_path2.set(os.path.basename(path))
            self._v_fullpath2 = path

    def _v_compute(self):
        p1 = self._v_fullpath1
        p2 = self._v_fullpath2
        if not p1 or not p2:
            messagebox.showwarning("Chybí soubory", "Načtěte obě vrstvy.")
            return
        if not HAS_PIL:
            messagebox.showerror("Chyba", "Pro načítání PNG je nutný Pillow.\npip install pillow")
            return
        try:
            self._v_layer1 = self._png_to_bool_grid(p1)
            self._v_layer2 = self._png_to_bool_grid(p2)
        except Exception as ex:
            messagebox.showerror("Chyba načítání", str(ex))
            return

        h1, w1 = len(self._v_layer1), len(self._v_layer1[0])
        h2, w2 = len(self._v_layer2), len(self._v_layer2[0])
        self._v_info.config(
            text=f"Vrstva 1: {w1}×{h1} px   |   Vrstva 2: {w2}×{h2} px   |   Posun: přetáhni nebo šipky")

        self._v_reset()   # reset polohy + překreslení

    def _v_draw(self):
        if self._v_layer1 is None or self._v_layer2 is None:
            return
        h1 = len(self._v_layer1); w1 = len(self._v_layer1[0])
        h2 = len(self._v_layer2); w2 = len(self._v_layer2[0])

        self._v_img1 = self._layer_to_preview(self._v_layer1, h1, w1)
        self._v_img2 = self._layer_to_preview(self._v_layer2, h2, w2)

        merged = or_layers(self._v_layer1, self._v_layer2, self._v_offset_x, self._v_offset_y)
        self._v_imgR = self._layer_to_preview(merged, h1, w1)

        for cv, img in [(self._v_cv1, self._v_img1),
                         (self._v_cv2, self._v_img2),
                         (self._v_cvR, self._v_imgR)]:
            iw = img.width(); ih = img.height()
            cv.config(width=iw, height=ih)
            cv.delete('all')
            cv.create_image(iw // 2, ih // 2, anchor='center', image=img)

        self._v_offset_lbl.config(
            text=f"X={self._v_offset_x:+d}  Y={self._v_offset_y:+d}")

    def _v_preview_scale(self):
        if self._v_layer1 is None:
            return 1.0
        h = len(self._v_layer1); w = len(self._v_layer1[0])
        return min(PREVIEW_W / w, PREVIEW_H / h)

    def _v_reset(self):
        self._v_offset_x = 0
        self._v_offset_y = 0
        self._v_draw()

    def _v_shift(self, dx, dy):
        self._v_offset_x += dx
        self._v_offset_y += dy
        self._v_draw()

    def _v_drag_start(self, e):
        self._v_drag_start_pos = (e.x, e.y)
        self._v_drag_ox = self._v_offset_x
        self._v_drag_oy = self._v_offset_y

    def _v_drag_motion(self, e):
        if not hasattr(self, '_v_drag_start_pos') or self._v_drag_start_pos is None:
            return
        if self._v_layer1 is None:
            return
        sc = self._v_preview_scale()
        dx = e.x - self._v_drag_start_pos[0]
        dy = e.y - self._v_drag_start_pos[1]
        self._v_offset_x = self._v_drag_ox - int(dx / sc)
        self._v_offset_y = self._v_drag_oy - int(dy / sc)
        self._v_draw()

    def _v_drag_end(self, e):
        self._v_drag_start_pos = None

    def _v_export(self):
        if self._v_layer1 is None or self._v_layer2 is None:
            messagebox.showwarning("Pozor", "Nejprve načtěte a zobrazte překrytí.")
            return
        path = filedialog.asksaveasfilename(
            title="Uložit výsledek překrytí",
            defaultextension=".png",
            filetypes=[("PNG", "*.png")],
            initialfile="prekryti_vysledek.png")
        if not path:
            return
        merged = or_layers(self._v_layer1, self._v_layer2, self._v_offset_x, self._v_offset_y)
        # Uložíme v nativním rozlišení (1 bool px = 1 výstupní px)
        from PIL import Image as PILImage
        h = len(merged); w = len(merged[0])
        img = PILImage.new("1", (w, h), 1)
        px = img.load()
        for r in range(h):
            for c in range(w):
                if merged[r][c]:
                    px[c, r] = 0
        img.save(path)
        messagebox.showinfo("Uloženo", f"Výsledek uložen:\n{path}\n\nPosun: X={self._v_offset_x:+d}, Y={self._v_offset_y:+d}")


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    app = StegoApp()
    app.mainloop()

