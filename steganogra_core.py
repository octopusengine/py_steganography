from __future__ import annotations

import hashlib
import random

from lib.bitmap_font import FONT_9x13, FONT_H, FONT_W

try:
    from PIL import Image, ImageDraw
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


PRINT_W = 1240   # px
PRINT_H = 1754   # px

# font_scale → (subpixel_print_scale, char_w_logical, char_h_logical)
# subpixel_print_scale: print pixels per one subpixel
# Logical grid: COLS = PRINT_W // (2 * sp), ROWS = PRINT_H // (2 * sp)
FONT_CONFIGS = {
    1: dict(sp=4, cw=10, ch=15),   # small
    2: dict(sp=3, cw=20, ch=29),   # medium
    3: dict(sp=2, cw=30, ch=43),   # large
    4: dict(sp=2, cw=40, ch=57),   # extra large
}

# ─────────────────────────────────────────────────────────────────────────────
# Shared 2-of-4 visual crypto patterns and deterministic key stream.
# ─────────────────────────────────────────────────────────────────────────────
PATTERNS = [
    [True, True, False, False],
    [False, False, True, True],
    [True, False, True, False],
    [False, True, False, True],
]


def _sha256_bit_stream(key: str):
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    while True:
        for byte in digest:
            for shift in range(7, -1, -1):
                yield bool((byte >> shift) & 1)
        digest = hashlib.sha256(digest).digest()


def _pattern_stream_from_key(key: str):
    bits = _sha256_bit_stream(key)
    while True:
        index = (int(next(bits)) << 1) | int(next(bits))
        yield PATTERNS[index]


def deterministic_noise_layer(key: str, cols, rows, block_size=1):
    bs = 2 * block_size
    pw, ph = cols * bs, rows * bs
    layer = [[False] * pw for _ in range(ph)]
    patterns = _pattern_stream_from_key(key)

    def put(r, c, pattern):
        pr, pc = r * bs, c * bs
        qs = block_size
        quadrants = [(0, 0), (0, qs), (qs, 0), (qs, qs)]
        for qi, (dr0, dc0) in enumerate(quadrants):
            value = pattern[qi]
            for dr in range(qs):
                for dc in range(qs):
                    layer[pr + dr0 + dr][pc + dc0 + dc] = value

    for r in range(rows):
        for c in range(cols):
            put(r, c, next(patterns))

    return layer

# ─────────────────────────────────────────────────────────────────────────────
# Render text into a logical grid.
# ─────────────────────────────────────────────────────────────────────────────
def render_text_to_grid(text, cols, rows, font_scale=1):
    """
    font_scale: integer scale applied to every glyph pixel.
    char_w = (FONT_W + 1) * font_scale   (+1 spacing column)
    char_h = (FONT_H + 2) * font_scale   (+2 spacing rows)
    """
    grid = [[False] * cols for _ in range(rows)]
    cw = (FONT_W + 1) * font_scale
    ch = (FONT_H + 2) * font_scale

    text = text.upper()
    max_per_line = max(1, (cols - 2) // cw)

    # Word wrap.
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
        row0 = start_row + li * ch + font_scale  # +1 top spacing row
        total_w = len(line) * cw
        start_col = max(1, (cols - total_w) // 2)

        for ci, ch_char in enumerate(line):
            bitmap = FONT_9x13.get(ch_char, FONT_9x13.get(' ', [0]*FONT_H))
            for gy in range(FONT_H):
                row_bits = bitmap[gy]
                for gx in range(FONT_W):
                    if row_bits & (1 << (FONT_W - 1 - gx)):
                        # Scale each glyph pixel to font_scale x font_scale.
                        for sy in range(font_scale):
                            for sx in range(font_scale):
                                gr = row0 + gy * font_scale + sy
                                gc = start_col + ci * cw + gx * font_scale + sx
                                if 0 <= gr < rows and 0 <= gc < cols:
                                    grid[gr][gc] = True
    return grid


# ─────────────────────────────────────────────────────────────────────────────
# Load an image into a logical grid.
# ─────────────────────────────────────────────────────────────────────────────
def image_to_grid(path, cols, rows, threshold=128):
    """
    Load a PNG/JPG, convert it to grayscale, threshold it, and fit it to cols x rows.
    Black pixel (< threshold) -> True, white -> False.
    The image is proportionally letterboxed into cols x rows.
    """
    from PIL import Image as PILImage
    img = PILImage.open(path).convert('L')   # grayscale 0-255

    # Proportional fit into the target grid.
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
# Naor-Shamir steganographic encoder.
# block_size: 1 = standard 2x2, 2 = doubled 4x4, 4 = quadrupled 8x8.
# Every logical pixel becomes a (2*block_size) x (2*block_size) subpixel block.
# Larger blocks are more tolerant of imperfect physical alignment.
# ─────────────────────────────────────────────────────────────────────────────
def encode_visual_stego(src1, src2, hidden, cols, rows, block_size=1):
    """Return (layer1, layer2).
    Physical size of each layer: cols*(2*block_size) x rows*(2*block_size)."""
    bs = 2 * block_size          # macroblock side length
    pw, ph = cols * bs, rows * bs
    L1 = [[False] * pw for _ in range(ph)]
    L2 = [[False] * pw for _ in range(ph)]

    # Fill macroblock quadrants. Each quadrant is block_size x block_size.
    # p contains 4 bool values in TL, TR, BL, BR order.
    def put(layer, r, c, p):
        pr, pc = r * bs, c * bs
        qs = block_size  # side length of one quadrant
        quadrants = [(0, 0), (0, qs), (qs, 0), (qs, qs)]
        for qi, (dr0, dc0) in enumerate(quadrants):
            val = p[qi]
            for dr in range(qs):
                for dc in range(qs):
                    layer[pr + dr0 + dr][pc + dc0 + dc] = val

    for r in range(rows):
        for c in range(cols):
            s1, s2, h = src1[r][c], src2[r][c], hidden[r][c]

            if h:   # hidden BLACK -> OR must produce 4/4
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
            else:   # hidden WHITE -> OR must produce 3/4
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
# Pure visual cryptography (original Naor-Shamir scheme).
# Layers look like random noise with no visible text.
# block_size: 1 = standard 2x2, 2 = doubled 4x4, 4 = quadrupled 8x8.
#   White secret pixel: both layers share the same 2 quadrants -> OR = 2/4 gray.
#   Black secret pixel: layers have complementary quadrants -> OR = 4/4 black.
# ─────────────────────────────────────────────────────────────────────────────
def encode_visual_crypto(hidden, cols, rows, block_size=1, layer2_key=None):
    """
    Pure 2-of-2 visual cryptography.
    Returns (layer1, layer2); each layer looks like random noise.
    The secret image appears only after OR overlay.
    Physical size: cols*(2*block_size) x rows*(2*block_size).
    """
    bs = 2 * block_size
    pw, ph = cols * bs, rows * bs
    L1 = [[False] * pw for _ in range(ph)]
    L2 = [[False] * pw for _ in range(ph)]

    def put(layer, r, c, p):
        pr, pc = r * bs, c * bs
        qs = block_size
        quadrants = [(0, 0), (0, qs), (qs, 0), (qs, qs)]
        for qi, (dr0, dc0) in enumerate(quadrants):
            val = p[qi]
            for dr in range(qs):
                for dc in range(qs):
                    layer[pr + dr0 + dr][pc + dc0 + dc] = val

    deterministic_patterns = _pattern_stream_from_key(layer2_key) if layer2_key is not None else None

    for r in range(rows):
        for c in range(cols):
            if deterministic_patterns is not None:
                p2 = list(next(deterministic_patterns))
                p1 = [not value for value in p2] if hidden[r][c] else list(p2)
                put(L1, r, c, p1)
                put(L2, r, c, p2)
                continue

            # Randomly choose the pattern for layer 1.
            pat_idx = random.randint(0, 3)
            p1 = PATTERNS[pat_idx]

            if hidden[r][c]:
                # Black pixel -> OR = 4/4, so layer 2 is the complement of layer 1.
                p2 = [not x for x in p1]
            else:
                # White pixel -> OR < 4/4, so layer 2 uses another random non-complement pattern.
                # The complement would produce OR=4/4 (black), which is not wanted.
                # The remaining 3 patterns all produce OR=2/4 or 3/4, never 4/4.
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
# Export to PNG (Pillow).
# ─────────────────────────────────────────────────────────────────────────────
def export_png(layer, sp_scale, path, dpi=150):
    """Save a layer as PNG. Every subpixel is sp_scale x sp_scale print pixels."""
    ph = len(layer)
    pw = len(layer[0])
    W = pw * sp_scale
    H = ph * sp_scale
    img = Image.new("1", (W, H), 1)   # 1-bit, white
    draw = ImageDraw.Draw(img)
    for r in range(ph):
        for c in range(pw):
            if layer[r][c]:
                x0, y0 = c * sp_scale, r * sp_scale
                draw.rectangle([x0, y0, x0 + sp_scale - 1, y0 + sp_scale - 1], fill=0)
    img.save(path, dpi=(dpi, dpi))


# ─────────────────────────────────────────────────────────────────────────────
# GUI preview canvas dimensions (screen-scaled).
# ─────────────────────────────────────────────────────────────────────────────
PREVIEW_W = 310   # preview width in px
PREVIEW_H = 440   # preview height in px

