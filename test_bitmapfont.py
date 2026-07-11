from __future__ import annotations

from pathlib import Path

from lib.bitmap_font import FONT_9x13, FONT_H, FONT_W, get_glyph, glyph_to_text


SAMPLE_TEXT = "STEGO FONT 9X13 TEST 123!? +-:/()"
OUTPUT_DIR = Path("data_exp")


def test_font_dimensions() -> None:
    for char, glyph in FONT_9x13.items():
        assert len(glyph) == FONT_H, f"{char!r} has {len(glyph)} rows"
        for row_bits in glyph:
            assert 0 <= row_bits < (1 << FONT_W), f"{char!r} row exceeds {FONT_W} bits"


def test_glyph_lookup() -> None:
    assert get_glyph("a") == FONT_9x13["A"]
    assert get_glyph("") == FONT_9x13[" "]
    assert get_glyph("@") == FONT_9x13[" "]
    assert glyph_to_text("A").splitlines()[0] == "...##...."


def text_to_rows(text: str, on: str = "#", off: str = ".") -> list[str]:
    rows = [""] * FONT_H
    for char in text:
        glyph = get_glyph(char)
        for row_index, row_bits in enumerate(glyph):
            rows[row_index] += "".join(
                on if row_bits & (1 << (FONT_W - 1 - col)) else off
                for col in range(FONT_W)
            )
            rows[row_index] += off
    return [row.rstrip(off) for row in rows]


def write_ascii_preview(path: Path, text: str = SAMPLE_TEXT) -> None:
    rows = text_to_rows(text)
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def write_png_preview(path: Path, text: str = SAMPLE_TEXT, scale: int = 6) -> None:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return

    rows = text_to_rows(text, on="1", off="0")
    width = max(len(row) for row in rows) * scale
    height = FONT_H * scale
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    for y, row in enumerate(rows):
        for x, value in enumerate(row):
            if value == "1":
                draw.rectangle(
                    (x * scale, y * scale, (x + 1) * scale - 1, (y + 1) * scale - 1),
                    fill="black",
                )

    image.save(path)


def run_tests() -> None:
    test_font_dimensions()
    test_glyph_lookup()


def main() -> None:
    run_tests()
    OUTPUT_DIR.mkdir(exist_ok=True)
    txt_path = OUTPUT_DIR / "bitmapfont_preview.txt"
    png_path = OUTPUT_DIR / "bitmapfont_preview.png"

    write_ascii_preview(txt_path)
    write_png_preview(png_path)

    print("Bitmap font tests passed.")
    print(f"ASCII preview: {txt_path}")
    print(f"PNG preview:   {png_path}")


if __name__ == "__main__":
    main()
