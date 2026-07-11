# py_steganography
basic visual cryptography and steganography

## Credits

Parts of this project were inspired by the work of:
- https://github.com/code21acoma

---

Documentation for a visual cryptography and steganography program. The program creates two separate layers that reveal hidden text or an image after printing and physical alignment, or after digital overlay inside the application.

## Principle

Steganogra is based on visual cryptography: the hidden information is not decrypted by calculation, but by overlaying two image layers.

Each point of the secret image is converted into a small block of black and white subpixels. The program creates two layers so that:

- a single layer does not reveal the full secret content,
- the exact overlay of both layers produces a readable result,
- black points in the secret image become darker after overlay than white points.

The overlay uses OR logic: if a point is black in at least one layer, it is black in the final image. This makes it possible to print the layers on transparent film and read the message without any additional software.

## Two Modes

### Visual Cryptography

In this mode, you enter only the secret text or secret image. The program creates two layers from it. Each layer looks like random noise on its own, and the hidden message appears only after the two layers are overlaid.

This mode is useful when the individual layers should not look like readable images.

### Visual Steganography

In this mode, the layers have their own visible content while also hiding a third piece of content together.

It uses three inputs:

- text or image for layer 1,
- text or image for layer 2,
- secret text or image revealed after overlay.

This mode is useful for demonstrations, games, teaching materials, or situations where the individual layers should look like ordinary images.

## Running the Program

The easiest way to run the program on Windows:

```bat
spustit.bat
```

You can also run it directly:

```bash
python steganogra_app.py
```

The application requires Python and the libraries listed in `requirements.txt`, mainly `PyQt6` and `Pillow`.

## Create Layers Tab

This tab is used to create new layers.

1. Choose a mode: `Vizualni kryptografie` or `Vizualni steganografie`.
2. Choose the pixel block size: `1x`, `2x`, or `3x`.
3. Enter text, or select an image with the `Obrazek` button.
4. Set the font size and text position.
5. Click `Generovat`.
6. Check layer 1, layer 2, and the overlay result in the previews.
7. If needed, move layer 2 with the mouse or arrow keys.
8. Export the result as PNG or PDF.

### Pixel Size

The pixel block size determines how fine or robust the image will be:

| Option | Advantage | Disadvantage |
| --- | --- | --- |
| `1x (4x4 px)` | finest image detail | requires very accurate alignment |
| `2x (8x8 px)` | good compromise and default | less detail than `1x` |
| `3x (16x16 px)` | best for manual overlay | coarser image |

For first tests and ordinary printing, `2x` or `3x` is usually the practical choice.

### Layer 2 Source

In visual cryptography mode, layer 2 can be generated in two ways:

- `Random noise` creates a new random layer every time.
- `Deterministic key` creates layer 2 from a SHA-256 hash stream derived from the entered word or password.

With the same key, resolution, and pixel size, layer 2 is identical. Different secrets can then produce different layer 1 files that are readable with that same keyed layer 2.

### Text and Images

Each input field can contain text. Instead of text, you can select an image. The program converts the image into a black-and-white grid and fits it to the layer size.

The `X` button next to an input removes the selected image and returns the field to text input.

### Text Position

Text can be placed:

- horizontally left, centered, or right,
- vertically top, centered, or bottom,
- with fine adjustment using the `X` and `Y` values.

The `Vycentrovat` button moves the text back to the center.

## Export

### PNG Export

The `Export PNG` button saves three files into the selected folder:

- `vrstva1.png`,
- `vrstva2.png`,
- `vysledek.png`.

The files `vrstva1.png` and `vrstva2.png` are intended for printing or further work. The `vysledek.png` file is a control preview of the overlay without offset.

### PDF Export

The `Export PDF` button creates a PDF containing the source layers. This is useful especially for printing, because PDF preserves page size more reliably and is easier to share.

The output is prepared as A4 at 150 DPI in landscape orientation.

## Check Overlay Tab

This tab is used to check existing layers.

Workflow:

1. Next to `Vrstva 1`, click `Otevrit` and select the first image.
2. Next to `Vrstva 2`, click `Otevrit` and select the second image.
3. Click `Zobrazit prekryti`.
4. Move layer 2 with the mouse or arrow keys until the result is readable.
5. Use `Ulozit vysledek` to save the current overlay.

Overlay checking is useful when working with scanned layers, layers from another source, or when searching for the correct alignment.

## Printing Tips

- Print both layers with the same printer settings.
- Avoid automatic page fitting if it changes the scale.
- For the best result, print on transparent film.
- If you use paper, place a strong light source behind the sheets.
- For manual overlay, use a larger pixel block, for example `3x`.
- If the secret message does not appear, the most common cause is misalignment or different print scaling.

## Security Note

Visual cryptography is excellent for demonstrating secret sharing and for simple physical hiding of messages. Practical security still depends on how the layers are created, stored, printed, and delivered. If the content is truly sensitive, do not store both layers in the same place and do not send them through the same channel.

## Typical Workflow

1. Prepare a short secret text or a simple black-and-white image.
2. Choose the mode and pixel size in the program.
3. Generate the layers.
4. Check the overlay preview.
5. Export PNG or PDF.
6. Print both layers.
7. Overlay them and fine-tune the alignment.

Simple, high-contrast content works best: large letters, short words, QR codes, symbols, and silhouettes.

