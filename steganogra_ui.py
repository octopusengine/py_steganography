from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QObject, QPoint, Qt, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QImage, QKeyEvent, QMouseEvent, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSplitter,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from steganogra_core import (
    HAS_PIL,
    PREVIEW_H,
    PREVIEW_W,
    PRINT_H,
    PRINT_W,
    encode_visual_crypto,
    encode_visual_stego,
    image_to_grid,
    or_layers,
    render_text_to_grid,
)


VER = "0.1 | 2026-06"
UI_PREVIEW_W = 300
UI_PREVIEW_H = 180
OUTPUT_W = 1752
OUTPUT_H = 1236
PDF_REGISTRATION_MARK_LINE_W = 2
PDF_REGISTRATION_MARK_ARM = 14
PDF_REGISTRATION_MARK_OFFSET = 5
PDF_LAYER_GAP = 82
PDF_LAYER_CAPTION_GAP = 6
PDF_LAYER_CAPTION_FONT_SIZE = 12
UI_FONT_CONFIGS = {
    1: 1,
    2: 2,
    3: 4,
}
PIXEL_MODES = {
    1: {"label": "1x (4x4 px)", "block_size": 2, "side": 4},
    2: {"label": "2x (8x8 px)", "block_size": 4, "side": 8},
    3: {"label": "3x (16x16 px)", "block_size": 8, "side": 16},
}


def _short_name(path: str, limit: int = 18) -> str:
    name = Path(path).name
    if len(name) <= limit:
        return name
    return f"{name[: limit - 3]}..."


def _bool_grid_to_pixmap(layer: list[list[bool]], max_w: int = UI_PREVIEW_W, max_h: int = UI_PREVIEW_H) -> QPixmap:
    height = len(layer)
    width = len(layer[0]) if height else 0
    if width <= 0 or height <= 0:
        return QPixmap()

    image = QImage(width, height, QImage.Format.Format_RGB32)
    white = QColor("#ffffff").rgb()
    black = QColor("#000000").rgb()
    for y, row in enumerate(layer):
        for x, value in enumerate(row):
            image.setPixel(x, y, black if value else white)

    scale = min(max_w / width, max_h / height)
    scaled_w = max(1, int(width * scale))
    scaled_h = max(1, int(height * scale))
    image = image.scaled(
        scaled_w,
        scaled_h,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    return QPixmap.fromImage(image)


def _png_to_bool_grid(path: str) -> list[list[bool]]:
    from PIL import Image as PILImage

    image = PILImage.open(path).convert("L")
    width, height = image.size
    pixels = image.load()
    return [[pixels[x, y] < 128 for x in range(width)] for y in range(height)]


def _save_bool_grid_native(layer: list[list[bool]], path: str) -> None:
    from PIL import Image as PILImage

    height = len(layer)
    width = len(layer[0])
    image = PILImage.new("1", (width, height), 1)
    pixels = image.load()
    for y, row in enumerate(layer):
        for x, value in enumerate(row):
            if value:
                pixels[x, y] = 0
    image.save(path)


def _layer_to_pil(layer: list[list[bool]], sp_scale: int, dpi: int = 150):
    from PIL import Image as PILImage
    from PIL import ImageDraw

    height = len(layer)
    width = len(layer[0])
    image = PILImage.new("1", (width * sp_scale, height * sp_scale), 1)
    draw = ImageDraw.Draw(image)
    for row_index, row in enumerate(layer):
        for col_index, value in enumerate(row):
            if value:
                x0 = col_index * sp_scale
                y0 = row_index * sp_scale
                draw.rectangle([x0, y0, x0 + sp_scale - 1, y0 + sp_scale - 1], fill=0)
    if image.size != (OUTPUT_W, OUTPUT_H):
        fitted = PILImage.new("1", (OUTPUT_W, OUTPUT_H), 1)
        src_x = max(0, (image.width - OUTPUT_W) // 2)
        src_y = max(0, (image.height - OUTPUT_H) // 2)
        crop = image.crop((src_x, src_y, min(image.width, src_x + OUTPUT_W), min(image.height, src_y + OUTPUT_H)))
        dst_x = max(0, (OUTPUT_W - crop.width) // 2)
        dst_y = max(0, (OUTPUT_H - crop.height) // 2)
        fitted.paste(crop, (dst_x, dst_y))
        image = fitted
    image.info["dpi"] = (dpi, dpi)
    return image


def _export_png(layer: list[list[bool]], sp_scale: int, path: str, dpi: int = 150) -> None:
    image = _layer_to_pil(layer, sp_scale, dpi)
    image.save(path, dpi=(dpi, dpi))


def _draw_pdf_registration_marks(
    draw,
    bounds: tuple[int, int, int, int],
    page_size: tuple[int, int],
    line_width: int = PDF_REGISTRATION_MARK_LINE_W,
) -> None:
    x, y, width, height = bounds
    page_w, page_h = page_size
    arm = min(PDF_REGISTRATION_MARK_ARM, max(4, min(width, height) // 12))
    offset = PDF_REGISTRATION_MARK_OFFSET
    centers = (
        (
            max(arm, x - offset - arm),
            max(arm, y - offset - arm),
        ),
        (
            min(page_w - arm - 1, x + width + offset + arm),
            min(page_h - arm - 1, y + height + offset + arm),
        ),
    )
    for cx, cy in centers:
        draw.line((cx - arm, cy, cx + arm, cy), fill=(0, 0, 0), width=line_width)
        draw.line((cx, cy - arm, cx, cy + arm), fill=(0, 0, 0), width=line_width)


def _export_sources_pdf(
    layer1: list[list[bool]],
    layer2: list[list[bool]],
    sp_scale: int,
    path: str,
    caption_line: str | None = None,
    dpi: int = 150,
) -> None:
    from PIL import Image as PILImage
    from PIL import ImageDraw
    from PIL import ImageFont

    page = PILImage.new("RGB", (PRINT_W, PRINT_H), "white")
    draw = ImageDraw.Draw(page)
    try:
        font = ImageFont.truetype("arial.ttf", PDF_LAYER_CAPTION_FONT_SIZE)
    except OSError:
        font = ImageFont.load_default()
    caption_gap = PDF_LAYER_CAPTION_GAP if caption_line else 0
    caption_h = 0
    if caption_line:
        text_bbox = draw.textbbox((0, 0), caption_line, font=font)
        caption_h = caption_gap + (text_bbox[3] - text_bbox[1])

    source_images = [
        _layer_to_pil(layer1, sp_scale, dpi).convert("RGB"),
        _layer_to_pil(layer2, sp_scale, dpi).convert("RGB"),
    ]
    margin = int(dpi * 0.75)  # roughly 1.9 cm at 150 DPI
    gap = PDF_LAYER_GAP
    content_w = PRINT_W - 2 * margin
    content_h = PRINT_H - 2 * margin
    max_item_h = (content_h - gap - 2 * caption_h) // 2
    prepared = []
    for image in source_images:
        scale = min(content_w / image.width, max_item_h / image.height)
        target_size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
        prepared_image = image.resize(target_size, PILImage.Resampling.LANCZOS)
        prepared.append(prepared_image)

    total_h = sum(image.height for image in prepared) + gap + len(prepared) * caption_h
    y = margin + max(0, (content_h - total_h) // 2)
    for image in prepared:
        x = margin + max(0, (content_w - image.width) // 2)
        page.paste(image, (x, y))
        _draw_pdf_registration_marks(draw, (x, y, image.width, image.height), page.size)
        if caption_line:
            draw.text((x, y + image.height + caption_gap), caption_line, fill=(80, 80, 80), font=font)
        y += image.height + caption_h + gap
    page.save(path, "PDF", resolution=float(dpi))


def _grid_bounds(grid: list[list[bool]]) -> tuple[int, int, int, int] | None:
    rows = len(grid)
    cols = len(grid[0]) if rows else 0
    top = rows
    left = cols
    bottom = -1
    right = -1
    for row_index, row in enumerate(grid):
        for col_index, value in enumerate(row):
            if value:
                top = min(top, row_index)
                left = min(left, col_index)
                bottom = max(bottom, row_index)
                right = max(right, col_index)
    if bottom < 0:
        return None
    return left, top, right, bottom


def _move_grid(
    grid: list[list[bool]],
    horizontal: str,
    vertical: str,
    offset_x: int,
    offset_y: int,
    margin: int = 2,
) -> list[list[bool]]:
    bounds = _grid_bounds(grid)
    if bounds is None:
        return grid

    cols = len(grid[0])
    rows = len(grid)
    left, top, right, bottom = bounds
    text_w = right - left + 1
    text_h = bottom - top + 1

    if horizontal == "left":
        target_left = margin
    elif horizontal == "right":
        target_left = cols - text_w - margin
    else:
        target_left = (cols - text_w) // 2

    if vertical == "top":
        target_top = margin
    elif vertical == "bottom":
        target_top = rows - text_h - margin
    else:
        target_top = (rows - text_h) // 2

    target_left += offset_x
    target_top += offset_y
    dx = target_left - left
    dy = target_top - top
    if dx == 0 and dy == 0:
        return grid

    moved = [[False] * cols for _ in range(rows)]
    for row_index, row in enumerate(grid):
        new_row = row_index + dy
        if not 0 <= new_row < rows:
            continue
        for col_index, value in enumerate(row):
            if not value:
                continue
            new_col = col_index + dx
            if 0 <= new_col < cols:
                moved[new_row][new_col] = True
    return moved


def _grid_from_input_spec(
    spec: dict[str, str | None],
    cols: int,
    rows: int,
    font_scale: int,
    horizontal: str,
    vertical: str,
    offset_x: int,
    offset_y: int,
) -> list[list[bool]]:
    path = spec.get("path")
    if path:
        return image_to_grid(str(path), cols, rows)
    text = str(spec.get("text") or "").strip() or "TEXT"
    grid = render_text_to_grid(text, cols, rows, font_scale)
    return _move_grid(grid, horizontal, vertical, offset_x, offset_y)


class GenerateWorker(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, params: dict[str, object]) -> None:
        super().__init__()
        self.params = params

    @pyqtSlot()
    def run(self) -> None:
        try:
            mode = str(self.params["mode"])
            fs = int(self.params["font_scale"])
            cols = int(self.params["cols"])
            rows = int(self.params["rows"])
            block_size = int(self.params["block_size"])
            pixel_side = int(self.params["pixel_side"])
            inputs = self.params["inputs"]
            if not isinstance(inputs, dict):
                raise TypeError("Invalid input specification.")
            horizontal = str(self.params["text_h_align"])
            vertical = str(self.params["text_v_align"])
            offset_x = int(self.params["text_offset_x"])
            offset_y = int(self.params["text_offset_y"])

            hidden = _grid_from_input_spec(
                inputs["eh"],
                cols,
                rows,
                fs,
                horizontal,
                vertical,
                offset_x,
                offset_y,
            )
            if mode == "crypto":
                layer1, layer2 = encode_visual_crypto(
                    hidden,
                    cols,
                    rows,
                    block_size=block_size,
                    layer2_key=self.params.get("layer2_key"),
                )
            else:
                src1 = _grid_from_input_spec(
                    inputs["e1"],
                    cols,
                    rows,
                    fs,
                    horizontal,
                    vertical,
                    offset_x,
                    offset_y,
                )
                src2 = _grid_from_input_spec(
                    inputs["e2"],
                    cols,
                    rows,
                    fs,
                    horizontal,
                    vertical,
                    offset_x,
                    offset_y,
                )
                layer1, layer2 = encode_visual_stego(
                    src1,
                    src2,
                    hidden,
                    cols,
                    rows,
                    block_size=block_size,
                )

            layer2_label = "key" if mode == "crypto" and self.params.get("layer2_key") else "random"
            size_text = (
                f"Print/export size: {OUTPUT_W} x {OUTPUT_H} px | "
                f"grid: {len(layer1[0])} x {len(layer1)} px | "
                f"pixel block: {pixel_side}x{pixel_side} (@150 DPI, landscape)"
                f" | layer 2: {layer2_label}"
            )
            self.finished.emit(
                {
                    "layer1": layer1,
                    "layer2": layer2,
                    "cols": cols,
                    "rows": rows,
                    "sp_scale": 1,
                    "size_text": size_text,
                }
            )
        except Exception as exc:
            self.failed.emit(str(exc))


class PreviewPanel(QFrame):
    def __init__(self, title: str, draggable: bool = False) -> None:
        super().__init__()
        self.setObjectName("PreviewPanel")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._drag_start: QPoint | None = None
        self._drag_begin_callback = None
        self._drag_callback = None
        self._drag_end_callback = None
        self._draggable = draggable

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("PreviewTitle")
        layout.addWidget(self.title_label)
        self.image_label = QLabel("Bez nahledu")
        self.image_label.setObjectName("PreviewImage")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(UI_PREVIEW_W, UI_PREVIEW_H)
        self.image_label.setCursor(Qt.CursorShape.OpenHandCursor if draggable else Qt.CursorShape.ArrowCursor)
        layout.addWidget(self.image_label, stretch=1)

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)

    def set_pixmap(self, pixmap: QPixmap) -> None:
        if pixmap.isNull():
            self.image_label.setText("Bez nahledu")
            self.image_label.setPixmap(QPixmap())
            return
        self.image_label.setText("")
        self.image_label.setPixmap(pixmap)

    def preview_size(self) -> tuple[int, int]:
        return (
            max(UI_PREVIEW_W, self.image_label.width() - 4),
            max(UI_PREVIEW_H, self.image_label.height() - 4),
        )

    def set_drag_handlers(self, move_callback, end_callback, begin_callback=None) -> None:
        self._drag_begin_callback = begin_callback
        self._drag_callback = move_callback
        self._drag_end_callback = end_callback

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._draggable and event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.position().toPoint()
            self.image_label.setCursor(Qt.CursorShape.ClosedHandCursor)
            if self._drag_begin_callback is not None:
                self._drag_begin_callback()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_start is not None and self._drag_callback is not None:
            delta = event.position().toPoint() - self._drag_start
            self._drag_callback(delta.x(), delta.y())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag_start is not None and event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = None
            self.image_label.setCursor(Qt.CursorShape.OpenHandCursor)
            if self._drag_end_callback is not None:
                self._drag_end_callback()
        super().mouseReleaseEvent(event)


class MainWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("py_steganogra | Qt6")
        self.resize(1260, 820)
        self.setMinimumSize(980, 660)

        self.layer1: list[list[bool]] | None = None
        self.layer2: list[list[bool]] | None = None
        self.cols = 0
        self.rows = 0
        self.sp_scale = 3
        self.offset_x = 0
        self.offset_y = 0
        self._drag_ox = 0
        self._drag_oy = 0
        self.img_path = {"e1": None, "e2": None, "eh": None}

        self._v_layer1: list[list[bool]] | None = None
        self._v_layer2: list[list[bool]] | None = None
        self._v_path1 = ""
        self._v_path2 = ""
        self._v_offset_x = 0
        self._v_offset_y = 0
        self._v_drag_ox = 0
        self._v_drag_oy = 0
        self._generate_thread: QThread | None = None
        self._generate_worker: GenerateWorker | None = None

        self._build_ui()
        self._apply_theme()
        QTimer.singleShot(300, self.generate)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self._tab_changed)
        self.tabs.addTab(self._build_create_tab(), "Create Layers")
        self.tabs.addTab(self._build_verify_tab(), "Overlay Check")
        root.addWidget(self.tabs, stretch=1)

    def _build_header(self, subtitle: str = "A4, 150 DPI, Naor-Shamir") -> QWidget:
        header = QWidget()
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Visual Steganography")
        title.setObjectName("AppTitle")
        layout.addWidget(title)
        version = QLabel(f"ver. {VER} | {subtitle}")
        version.setObjectName("Version")
        version.setMinimumWidth(0)
        version.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout.addWidget(version)
        layout.addStretch()
        return header

    def _build_create_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(8)

        left_panel = QWidget()
        left_panel.setMaximumWidth(620)
        left = QVBoxLayout(left_panel)
        left.setContentsMargins(8, 8, 8, 8)
        left.setSpacing(8)
        right_panel = QWidget()
        right_panel.setMinimumWidth(540)
        right = QVBoxLayout(right_panel)
        right.setContentsMargins(4, 4, 4, 4)
        right.setSpacing(4)

        left.addWidget(self._build_header())

        left.addWidget(self._build_settings_tabs(), stretch=1)

        hint = QLabel("Drag Layer 2 with the mouse, or use arrow keys for fine alignment.")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        hint.setMinimumWidth(0)
        hint.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        left.addWidget(hint)

        self.cv1 = PreviewPanel("Layer 1")
        self.cv2 = PreviewPanel("Layer 2 - drag", draggable=True)
        self.cvR = PreviewPanel("Result (OR overlay)")
        self.cv2.set_drag_handlers(self._drag_motion, self._drag_end, self._drag_begin)
        for panel in (self.cv1, self.cv2, self.cvR):
            right.addWidget(panel, stretch=1)

        status = QHBoxLayout()
        status.addWidget(QLabel("Layer 2 offset:"))
        self.offset_label = QLabel("X=0  Y=0")
        self.offset_label.setObjectName("Accent")
        status.addWidget(self.offset_label)
        self.size_label = QLabel("")
        self.size_label.setObjectName("Muted")
        reset_btn = QPushButton("Reset")
        reset_btn.clicked.connect(self.reset_offset)
        status.addWidget(reset_btn)
        status.addStretch()
        left.addLayout(status)
        self.size_label.setWordWrap(True)
        self.size_label.setMinimumWidth(0)
        self.size_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        left.addWidget(self.size_label)
        left.addStretch()

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([600, 650])
        splitter.splitterMoved.connect(lambda _pos, _index: self._draw_all())
        layout.addWidget(splitter, stretch=1)
        return tab

    def _build_settings_tabs(self) -> QTabWidget:
        tabs = QTabWidget()
        tabs.setObjectName("SettingsTabs")
        mode_box = self._build_mode_box()
        layer2_box = self._build_layer2_box()
        text_box = self._build_text_settings_box()
        input_box = self._build_input_box()

        inputs_tab = QWidget()
        inputs = QVBoxLayout(inputs_tab)
        inputs.setContentsMargins(6, 6, 6, 6)
        inputs.setSpacing(8)
        inputs.addWidget(input_box)
        self.generate_progress = QProgressBar()
        self.generate_progress.setRange(0, 100)
        self.generate_progress.setValue(0)
        self.generate_progress.setFormat("Ready")
        inputs.addWidget(self.generate_progress)
        inputs.addWidget(self._build_settings_summary_box())
        inputs.addStretch()

        settings_tab = QWidget()
        settings = QVBoxLayout(settings_tab)
        settings.setContentsMargins(6, 6, 6, 6)
        settings.setSpacing(8)
        settings.addWidget(mode_box)
        settings.addWidget(layer2_box)
        settings.addWidget(text_box)
        settings.addStretch()

        tabs.addTab(inputs_tab, "Inputs")
        tabs.addTab(settings_tab, "Settings")
        self._update_settings_summary()
        return tabs

    def _build_settings_summary_box(self) -> QGroupBox:
        box = QGroupBox("Settings")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(10, 10, 10, 10)
        self.settings_summary_label = QLabel("")
        self.settings_summary_label.setObjectName("Muted")
        self.settings_summary_label.setWordWrap(True)
        layout.addWidget(self.settings_summary_label)
        return box

    def _build_mode_box(self) -> QGroupBox:
        box = QGroupBox("Mode and Pixel Size")
        layout = QGridLayout(box)
        layout.setHorizontalSpacing(14)
        layout.setVerticalSpacing(8)

        self.mode_group = QButtonGroup(self)
        crypto = QRadioButton("Visual cryptography")
        crypto.setChecked(True)
        stego = QRadioButton("Visual steganography")
        self.mode_group.addButton(crypto, 0)
        self.mode_group.addButton(stego, 1)
        self.mode_group.idClicked.connect(lambda _id: self._on_mode_change())
        layout.addWidget(QLabel("Mode:"), 0, 0)
        layout.addWidget(crypto, 0, 1)
        layout.addWidget(stego, 0, 2)

        self.block_group = QButtonGroup(self)
        for col, (value, config) in enumerate(PIXEL_MODES.items(), start=1):
            button = QRadioButton(str(config["label"]))
            if value == 2:
                button.setChecked(True)
            self.block_group.addButton(button, value)
            layout.addWidget(button, 1, col)
        self.block_group.idClicked.connect(lambda _id: self._update_settings_summary())
        layout.addWidget(QLabel("Pixel:"), 1, 0)
        return box

    def _build_layer2_box(self) -> QGroupBox:
        box = QGroupBox("Layer 2")
        layout = QGridLayout(box)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(6)

        self.layer2_group = QButtonGroup(self)
        self.layer2_random = QRadioButton("Random noise")
        self.layer2_random.setChecked(True)
        self.layer2_keyed = QRadioButton("Deterministic key")
        self.layer2_group.addButton(self.layer2_random, 0)
        self.layer2_group.addButton(self.layer2_keyed, 1)
        self.layer2_group.idClicked.connect(lambda _id: self._on_layer2_mode_change())

        layout.addWidget(self.layer2_random, 0, 0, 1, 2)
        layout.addWidget(self.layer2_keyed, 1, 0, 1, 2)
        layout.addWidget(QLabel("Key:"), 2, 0)
        self.layer2_key = QLineEdit()
        self.layer2_key.setPlaceholderText("word or password")
        layout.addWidget(self.layer2_key, 2, 1)
        note = QLabel("Used in cryptography mode; the same key and resolution produce the same Layer 2.")
        note.setObjectName("Muted")
        note.setWordWrap(True)
        layout.addWidget(note, 3, 0, 1, 2)
        self._on_layer2_mode_change()
        return box

    def _build_input_box(self) -> QGroupBox:
        box = QGroupBox("Inputs")
        layout = QGridLayout(box)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(8)

        self.e1 = QLineEdit("STEGO")
        self.e2 = QLineEdit("FISH")
        self.eh = QLineEdit("12356")
        for edit in (self.e1, self.e2, self.eh):
            edit.setMaximumWidth(260)
        self._name_labels: dict[str, QLabel] = {}
        self._text_labels: dict[str, QLabel] = {}

        for row, (key, label, edit) in enumerate(
            [("e1", "Layer 1 text:", self.e1), ("e2", "Layer 2 text:", self.e2), ("eh", "Secret text:", self.eh)]
        ):
            text_label = QLabel(label)
            self._text_labels[key] = text_label
            layout.addWidget(text_label, row, 0)
            layout.addWidget(edit, row, 1)
            pick = QPushButton("Image")
            pick.setMaximumWidth(110)
            pick.clicked.connect(lambda _checked=False, slot=key: self._pick_image(slot))
            setattr(self, f"_pick_{key}", pick)
            layout.addWidget(pick, row, 2)
            clear = QPushButton("X")
            clear.setMaximumWidth(42)
            clear.setProperty("dangerButton", True)
            clear.clicked.connect(lambda _checked=False, slot=key: self._clear_image(slot))
            setattr(self, f"_clear_{key}", clear)
            layout.addWidget(clear, row, 3)
            name = QLabel("")
            name.setObjectName("Muted")
            self._name_labels[key] = name
            layout.addWidget(name, row, 4)

        actions = QHBoxLayout()
        self.generate_btn = QPushButton("Generate")
        self.generate_btn.setObjectName("PrimaryButton")
        self.generate_btn.clicked.connect(self.generate)
        actions.addWidget(self.generate_btn)
        self.export_btn = QPushButton("Export PNG")
        self.export_btn.clicked.connect(self.export_all)
        self.export_btn.setEnabled(HAS_PIL)
        actions.addWidget(self.export_btn)
        self.pdf_btn = QPushButton("Export PDF")
        self.pdf_btn.clicked.connect(self.export_pdf)
        self.pdf_btn.setEnabled(HAS_PIL)
        actions.addWidget(self.pdf_btn)
        actions.addStretch()
        layout.addLayout(actions, 3, 1, 1, 4)
        self._on_mode_change()
        self._update_settings_summary()
        return box

    def _build_text_settings_box(self) -> QGroupBox:
        box = QGroupBox("Font and Position")
        layout = QGridLayout(box)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(6)

        layout.addWidget(QLabel("Font size:"), 0, 0)
        font_row = QHBoxLayout()
        font_row.setSpacing(6)
        self.font_group = QButtonGroup(self)
        for value, label in [(1, "1"), (2, "2"), (3, "3")]:
            button = QRadioButton(label)
            button.setToolTip({1: "Small", 2: "Medium", 3: "Large"}[value])
            if value == 2:
                button.setChecked(True)
            self.font_group.addButton(button, value)
            font_row.addWidget(button)
        self.font_group.idClicked.connect(lambda _id: self._update_settings_summary())
        font_row.addStretch()
        layout.addLayout(font_row, 0, 1, 1, 3)

        layout.addWidget(QLabel("Position:"), 1, 0)
        self.text_h_align = QComboBox()
        self.text_h_align.addItem("Left", "left")
        self.text_h_align.addItem("Center", "center")
        self.text_h_align.addItem("Right", "right")
        self.text_h_align.setCurrentIndex(1)
        layout.addWidget(self.text_h_align, 1, 1)
        self.text_v_align = QComboBox()
        self.text_v_align.addItem("Top", "top")
        self.text_v_align.addItem("Center", "center")
        self.text_v_align.addItem("Bottom", "bottom")
        self.text_v_align.setCurrentIndex(1)
        layout.addWidget(self.text_v_align, 1, 2)

        layout.addWidget(QLabel("X"), 2, 0)
        self.text_offset_x = QSpinBox()
        self.text_offset_x.setRange(-999, 999)
        self.text_offset_x.setToolTip("Text offset in logical pixels")
        layout.addWidget(self.text_offset_x, 2, 1)
        layout.addWidget(QLabel("Y"), 2, 2)
        self.text_offset_y = QSpinBox()
        self.text_offset_y.setRange(-999, 999)
        self.text_offset_y.setToolTip("Text offset in logical pixels")
        layout.addWidget(self.text_offset_y, 2, 3)
        center_btn = QPushButton("Center")
        center_btn.clicked.connect(self._reset_text_position)
        layout.addWidget(center_btn, 3, 1, 1, 3)
        return box

    def _build_verify_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(8)

        left_panel = QWidget()
        left_panel.setMaximumWidth(620)
        left = QVBoxLayout(left_panel)
        left.setContentsMargins(8, 8, 8, 8)
        left.setSpacing(8)
        right_panel = QWidget()
        right_panel.setMinimumWidth(540)
        right = QVBoxLayout(right_panel)
        right.setContentsMargins(4, 4, 4, 4)
        right.setSpacing(4)

        left.addWidget(self._build_header("physical overlay check"))

        top = QGroupBox("Physical Overlay Check")
        grid = QGridLayout(top)
        self.v_path1_label = QLabel("")
        self.v_path1_label.setObjectName("Muted")
        self.v_path2_label = QLabel("")
        self.v_path2_label.setObjectName("Muted")
        grid.addWidget(QLabel("Layer 1:"), 0, 0)
        grid.addWidget(self.v_path1_label, 0, 1)
        pick1 = QPushButton("Open")
        pick1.clicked.connect(lambda: self._v_pick(1))
        grid.addWidget(pick1, 0, 2)
        grid.addWidget(QLabel("Layer 2:"), 1, 0)
        grid.addWidget(self.v_path2_label, 1, 1)
        pick2 = QPushButton("Open")
        pick2.clicked.connect(lambda: self._v_pick(2))
        grid.addWidget(pick2, 1, 2)
        compute = QPushButton("Show Overlay")
        compute.setObjectName("PrimaryButton")
        compute.clicked.connect(self._v_compute)
        grid.addWidget(compute, 0, 3)
        save = QPushButton("Save Result")
        save.clicked.connect(self._v_export)
        save.setEnabled(HAS_PIL)
        grid.addWidget(save, 1, 3)
        self.v_info_label = QLabel("Load both layers and click Show Overlay.")
        self.v_info_label.setObjectName("Muted")
        self.v_info_label.setWordWrap(True)
        grid.addWidget(self.v_info_label, 2, 0, 1, 4)
        left.addWidget(top)

        hint = QLabel("Drag Layer 2 with the mouse; arrow keys move the active tab by 1 px.")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        left.addWidget(hint)

        self.v_cv1 = PreviewPanel("Layer 1")
        self.v_cv2 = PreviewPanel("Layer 2 - drag", draggable=True)
        self.v_cvR = PreviewPanel("Result (OR overlay)")
        self.v_cv2.set_drag_handlers(self._v_drag_motion, self._v_drag_end, self._v_drag_begin)
        for panel in (self.v_cv1, self.v_cv2, self.v_cvR):
            right.addWidget(panel, stretch=1)

        status = QHBoxLayout()
        status.addWidget(QLabel("Layer 2 offset:"))
        self.v_offset_label = QLabel("X=0  Y=0")
        self.v_offset_label.setObjectName("Accent")
        status.addWidget(self.v_offset_label)
        reset = QPushButton("Reset")
        reset.clicked.connect(self._v_reset)
        status.addWidget(reset)
        status.addStretch()
        left.addLayout(status)
        left.addStretch()

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([620, 620])
        splitter.splitterMoved.connect(lambda _pos, _index: self._v_draw())
        layout.addWidget(splitter, stretch=1)
        return tab

    def _reset_text_position(self) -> None:
        self.text_h_align.setCurrentIndex(1)
        self.text_v_align.setCurrentIndex(1)
        self.text_offset_x.setValue(0)
        self.text_offset_y.setValue(0)

    def _mode(self) -> str:
        return "stego" if self.mode_group.checkedId() == 1 else "crypto"

    def _layer2_mode(self) -> str:
        return "key" if self.layer2_group.checkedId() == 1 else "random"

    def _pixel_config(self) -> dict[str, int | str]:
        checked = self.block_group.checkedId()
        return PIXEL_MODES.get(checked, PIXEL_MODES[2])

    def _settings_summary_text(self) -> str:
        mode = "crypto" if self._mode() == "crypto" else "stego"
        pixel = str(self._pixel_config()["label"])
        layer2 = "key" if self._mode() == "crypto" and self._layer2_mode() == "key" else "random"
        font_id = self.font_group.checkedId()
        if font_id not in UI_FONT_CONFIGS:
            font_id = 2
        return f"Settings: {mode} | pixel {pixel} | layer 2 {layer2} | font {font_id}"

    def _update_settings_summary(self) -> None:
        if hasattr(self, "settings_summary_label"):
            self.settings_summary_label.setText(self._settings_summary_text())

    def _set_generation_progress(self, active: bool, text: str) -> None:
        if not hasattr(self, "generate_progress"):
            return
        if active:
            self.generate_progress.setRange(0, 0)
            self.generate_progress.setFormat(text)
        else:
            self.generate_progress.setRange(0, 100)
            self.generate_progress.setValue(100)
            self.generate_progress.setFormat(text)
        if hasattr(self, "generate_btn"):
            self.generate_btn.setEnabled(not active)
        if hasattr(self, "export_btn"):
            self.export_btn.setEnabled(HAS_PIL and not active)
        if hasattr(self, "pdf_btn"):
            self.pdf_btn.setEnabled(HAS_PIL and not active)
        QApplication.processEvents()

    def _on_layer2_mode_change(self) -> None:
        is_crypto = self._mode() == "crypto"
        is_keyed = self._layer2_mode() == "key"
        self.layer2_random.setEnabled(is_crypto)
        self.layer2_keyed.setEnabled(is_crypto)
        self.layer2_key.setEnabled(is_crypto and is_keyed)
        self._update_settings_summary()
        if hasattr(self, "cv1"):
            self._update_preview_titles()

    def _update_preview_titles(self) -> None:
        if self._mode() == "stego":
            self.cv1.set_title("Layer 1 (text/image)")
            self.cv2.set_title("Layer 2 - drag")
        elif self._layer2_mode() == "key":
            self.cv1.set_title("Layer 1 (for key)")
            self.cv2.set_title("Layer 2 (deterministic noise)")
        else:
            self.cv1.set_title("Layer 1 (random noise)")
            self.cv2.set_title("Layer 2 - drag")

    def _on_mode_change(self) -> None:
        is_stego = self._mode() == "stego"
        for key in ("e1", "e2"):
            edit: QLineEdit = getattr(self, key)
            edit.setEnabled(is_stego and not self.img_path[key])
            getattr(self, f"_pick_{key}").setEnabled(is_stego)
            getattr(self, f"_clear_{key}").setEnabled(is_stego)
            self._text_labels[key].setEnabled(is_stego)
            self._name_labels[key].setEnabled(is_stego)
        self._text_labels["eh"].setText("Secret text:" if is_stego else "Secret text (only input):")
        self._on_layer2_mode_change()
        self._update_settings_summary()
        if hasattr(self, "cv1"):
            self._update_preview_titles()

    def _pick_image(self, key: str) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Select image ({key})",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;All files (*.*)",
        )
        if not path:
            return
        self.img_path[key] = path
        self._name_labels[key].setText(_short_name(path))
        getattr(self, key).setEnabled(False)

    def _clear_image(self, key: str) -> None:
        self.img_path[key] = None
        self._name_labels[key].setText("")
        if key == "eh" or self._mode() == "stego":
            getattr(self, key).setEnabled(True)

    def _get_grid(self, key: str, cols: int, rows: int, font_scale: int) -> list[list[bool]]:
        path = self.img_path[key]
        if path:
            try:
                return image_to_grid(path, cols, rows)
            except Exception as exc:
                QMessageBox.critical(self, "Image Load Error", f"Cannot load {path}:\n{exc}")
                return [[False] * cols for _ in range(rows)]
        text = getattr(self, key).text().strip() or "TEXT"
        grid = render_text_to_grid(text, cols, rows, font_scale)
        return _move_grid(
            grid,
            str(self.text_h_align.currentData() or "center"),
            str(self.text_v_align.currentData() or "center"),
            self.text_offset_x.value(),
            self.text_offset_y.value(),
        )

    def generate(self) -> None:
        if self._generate_thread is not None and self._generate_thread.isRunning():
            return
        ui_fs = self.font_group.checkedId()
        fs = UI_FONT_CONFIGS.get(ui_fs, 3)
        pixel_config = self._pixel_config()
        block_size = int(pixel_config["block_size"])
        pixel_side = int(pixel_config["side"])
        cols = OUTPUT_W // pixel_side
        rows = OUTPUT_H // pixel_side
        layer2_key = None
        if self._mode() == "crypto" and self._layer2_mode() == "key":
            layer2_key = self.layer2_key.text().strip()
            if not layer2_key:
                QMessageBox.warning(self, "Missing Key", "Enter a word or password for deterministic Layer 2.")
                return

        params = {
            "mode": self._mode(),
            "font_scale": fs,
            "cols": cols,
            "rows": rows,
            "block_size": block_size,
            "pixel_side": pixel_side,
            "layer2_key": layer2_key,
            "text_h_align": str(self.text_h_align.currentData() or "center"),
            "text_v_align": str(self.text_v_align.currentData() or "center"),
            "text_offset_x": self.text_offset_x.value(),
            "text_offset_y": self.text_offset_y.value(),
            "inputs": {
                "e1": {"path": self.img_path["e1"], "text": self.e1.text()},
                "e2": {"path": self.img_path["e2"], "text": self.e2.text()},
                "eh": {"path": self.img_path["eh"], "text": self.eh.text()},
            },
        }

        self._set_generation_progress(True, "Generating...")
        self._generate_thread = QThread(self)
        self._generate_worker = GenerateWorker(params)
        self._generate_worker.moveToThread(self._generate_thread)
        self._generate_thread.started.connect(self._generate_worker.run)
        self._generate_worker.finished.connect(self._generate_finished)
        self._generate_worker.failed.connect(self._generate_failed)
        self._generate_worker.finished.connect(self._generate_thread.quit)
        self._generate_worker.failed.connect(self._generate_thread.quit)
        self._generate_thread.finished.connect(self._generate_worker.deleteLater)
        self._generate_thread.finished.connect(self._generate_thread_finished)
        self._generate_thread.start()

    def _generate_finished(self, result: object) -> None:
        data = result if isinstance(result, dict) else {}
        self.layer1 = data.get("layer1")
        self.layer2 = data.get("layer2")
        self.cols = int(data.get("cols", 0))
        self.rows = int(data.get("rows", 0))
        self.sp_scale = int(data.get("sp_scale", 1))
        self.size_label.setText(str(data.get("size_text", "")))
        self.reset_offset()
        self._set_generation_progress(False, "Done")

    def _generate_failed(self, message: str) -> None:
        self._set_generation_progress(False, "Error")
        QMessageBox.critical(self, "Generation Error", message)

    def _generate_thread_finished(self) -> None:
        self._generate_thread = None
        self._generate_worker = None

    def _draw_all(self) -> None:
        if self.layer1 is None or self.layer2 is None:
            return
        merged = or_layers(self.layer1, self.layer2, self.offset_x, self.offset_y)
        w1, h1 = self.cv1.preview_size()
        w2, h2 = self.cv2.preview_size()
        wr, hr = self.cvR.preview_size()
        self.cv1.set_pixmap(_bool_grid_to_pixmap(self.layer1, w1, h1))
        self.cv2.set_pixmap(_bool_grid_to_pixmap(self.layer2, w2, h2))
        self.cvR.set_pixmap(_bool_grid_to_pixmap(merged, wr, hr))
        self.offset_label.setText(f"X={self.offset_x:+d}  Y={self.offset_y:+d}")

    def _preview_scale(self) -> float:
        if self.layer1 is None:
            return 1.0
        height = len(self.layer1)
        width = len(self.layer1[0])
        preview_w, preview_h = self.cv1.preview_size()
        return min(preview_w / width, preview_h / height)

    def _drag_motion(self, dx: int, dy: int) -> None:
        if self.layer1 is None:
            return
        scale = self._preview_scale()
        self.offset_x = self._drag_ox - int(dx / scale)
        self.offset_y = self._drag_oy - int(dy / scale)
        self._draw_all()

    def _drag_begin(self) -> None:
        self._drag_ox = self.offset_x
        self._drag_oy = self.offset_y

    def _drag_end(self) -> None:
        self._drag_ox = self.offset_x
        self._drag_oy = self.offset_y

    def _shift(self, dx: int, dy: int) -> None:
        self.offset_x += dx
        self.offset_y += dy
        self._drag_ox = self.offset_x
        self._drag_oy = self.offset_y
        self._draw_all()

    def reset_offset(self) -> None:
        self.offset_x = 0
        self.offset_y = 0
        self._drag_ox = 0
        self._drag_oy = 0
        self._draw_all()

    def export_all(self) -> None:
        if not HAS_PIL:
            QMessageBox.critical(self, "Error", "Pillow is not installed.\npip install pillow")
            return
        if self.layer1 is None or self.layer2 is None:
            QMessageBox.warning(self, "Warning", "Generate the images first.")
            return
        folder = QFileDialog.getExistingDirectory(self, "Select PNG Export Folder")
        if not folder:
            return
        p1 = os.path.join(folder, "layer1.png")
        p2 = os.path.join(folder, "layer2.png")
        pr = os.path.join(folder, "result.png")
        _export_png(self.layer1, self.sp_scale, p1)
        _export_png(self.layer2, self.sp_scale, p2)
        _export_png(or_layers(self.layer1, self.layer2, 0, 0), self.sp_scale, pr)
        pw = len(self.layer1[0]) * self.sp_scale
        ph = len(self.layer1) * self.sp_scale
        QMessageBox.information(
            self,
            "Export Complete",
            f"Saved to:\n{folder}\n\nlayer1.png\nlayer2.png\nresult.png\n\nSize: {pw} x {ph} px",
        )

    def export_pdf(self) -> None:
        if not HAS_PIL:
            QMessageBox.critical(self, "Error", "Pillow is not installed.\npip install pillow")
            return
        if self.layer1 is None or self.layer2 is None:
            QMessageBox.warning(self, "Warning", "Generate the images first.")
            return
        created_at = datetime.now()
        default_name = created_at.strftime("export_%y%m%d_%H%M.pdf")
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save PDF with Source Layers",
            default_name,
            "PDF (*.pdf)",
        )
        if not path:
            return
        font_size = self.font_group.checkedId()
        if font_size not in UI_FONT_CONFIGS:
            font_size = 2
        layer2_label = "key" if self._mode() == "crypto" and self._layer2_mode() == "key" else "random"
        caption_line = (
            f"{OUTPUT_W}x{OUTPUT_H} px | "
            f"font {font_size} {layer2_label} | "
            f"A4 150 dpi | {created_at.strftime('%Y-%m-%d %H:%M')}"
        )
        _export_sources_pdf(self.layer1, self.layer2, self.sp_scale, path, caption_line=caption_line)
        QMessageBox.information(self, "Export Complete", f"PDF saved:\n{path}")

    def _v_pick(self, which: int) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Select PNG layer {which}",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp);;All files (*.*)",
        )
        if not path:
            return
        if which == 1:
            self._v_path1 = path
            self.v_path1_label.setText(_short_name(path, 36))
        else:
            self._v_path2 = path
            self.v_path2_label.setText(_short_name(path, 36))

    def _v_compute(self) -> None:
        if not self._v_path1 or not self._v_path2:
            QMessageBox.warning(self, "Missing Files", "Load both layers.")
            return
        if not HAS_PIL:
            QMessageBox.critical(self, "Error", "Pillow is required to load PNG files.\npip install pillow")
            return
        try:
            self._v_layer1 = _png_to_bool_grid(self._v_path1)
            self._v_layer2 = _png_to_bool_grid(self._v_path2)
        except Exception as exc:
            QMessageBox.critical(self, "Load Error", str(exc))
            return
        h1 = len(self._v_layer1)
        w1 = len(self._v_layer1[0])
        h2 = len(self._v_layer2)
        w2 = len(self._v_layer2[0])
        self.v_info_label.setText(f"Layer 1: {w1}x{h1} px | Layer 2: {w2}x{h2} px")
        self._v_reset()

    def _v_draw(self) -> None:
        if self._v_layer1 is None or self._v_layer2 is None:
            return
        merged = or_layers(self._v_layer1, self._v_layer2, self._v_offset_x, self._v_offset_y)
        w1, h1 = self.v_cv1.preview_size()
        w2, h2 = self.v_cv2.preview_size()
        wr, hr = self.v_cvR.preview_size()
        self.v_cv1.set_pixmap(_bool_grid_to_pixmap(self._v_layer1, w1, h1))
        self.v_cv2.set_pixmap(_bool_grid_to_pixmap(self._v_layer2, w2, h2))
        self.v_cvR.set_pixmap(_bool_grid_to_pixmap(merged, wr, hr))
        self.v_offset_label.setText(f"X={self._v_offset_x:+d}  Y={self._v_offset_y:+d}")

    def _v_preview_scale(self) -> float:
        if self._v_layer1 is None:
            return 1.0
        height = len(self._v_layer1)
        width = len(self._v_layer1[0])
        preview_w, preview_h = self.v_cv1.preview_size()
        return min(preview_w / width, preview_h / height)

    def _v_drag_motion(self, dx: int, dy: int) -> None:
        if self._v_layer1 is None:
            return
        scale = self._v_preview_scale()
        self._v_offset_x = self._v_drag_ox - int(dx / scale)
        self._v_offset_y = self._v_drag_oy - int(dy / scale)
        self._v_draw()

    def _v_drag_begin(self) -> None:
        self._v_drag_ox = self._v_offset_x
        self._v_drag_oy = self._v_offset_y

    def _v_drag_end(self) -> None:
        self._v_drag_ox = self._v_offset_x
        self._v_drag_oy = self._v_offset_y

    def _v_shift(self, dx: int, dy: int) -> None:
        self._v_offset_x += dx
        self._v_offset_y += dy
        self._v_drag_ox = self._v_offset_x
        self._v_drag_oy = self._v_offset_y
        self._v_draw()

    def _v_reset(self) -> None:
        self._v_offset_x = 0
        self._v_offset_y = 0
        self._v_drag_ox = 0
        self._v_drag_oy = 0
        self._v_draw()

    def _v_export(self) -> None:
        if self._v_layer1 is None or self._v_layer2 is None:
            QMessageBox.warning(self, "Warning", "Load and show the overlay first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Overlay Result",
            "overlay_result.png",
            "PNG (*.png)",
        )
        if not path:
            return
        merged = or_layers(self._v_layer1, self._v_layer2, self._v_offset_x, self._v_offset_y)
        _save_bool_grid_native(merged, path)
        QMessageBox.information(self, "Saved", f"Result saved:\n{path}")

    def _tab_changed(self, _index: int) -> None:
        self.setFocus()

    def resizeEvent(self, event: object) -> None:
        super().resizeEvent(event)
        if getattr(self, "layer1", None) is not None:
            self._draw_all()
        if getattr(self, "_v_layer1", None) is not None:
            self._v_draw()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        moves = {
            Qt.Key.Key_Left: (-1, 0),
            Qt.Key.Key_Right: (1, 0),
            Qt.Key.Key_Up: (0, -1),
            Qt.Key.Key_Down: (0, 1),
        }
        move = moves.get(event.key())
        if move is None:
            super().keyPressEvent(event)
            return
        if self.tabs.currentIndex() == 0:
            self._shift(*move)
        else:
            self._v_shift(*move)

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                background: #121417;
                color: #e8e8e8;
                font-family: Segoe UI, Arial, sans-serif;
                font-size: 11pt;
            }
            QLabel#AppTitle {
                font-size: 15pt;
                font-weight: 700;
                color: #b56cff;
            }
            QLabel#Version, QLabel#Muted {
                color: #8b96a3;
            }
            QLabel#Accent, QLabel#PreviewTitle {
                color: #ff5c6c;
                font-weight: 700;
            }
            QGroupBox {
                border: 1px solid #333941;
                border-radius: 6px;
                margin-top: 10px;
                padding: 10px;
                font-weight: 600;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            QFrame#PreviewPanel {
                border: 1px solid #333941;
                border-radius: 6px;
                background: #151a20;
            }
            QLabel#PreviewImage {
                background: #0f1114;
                border: 1px solid #333941;
                border-radius: 5px;
                color: #8b96a3;
            }
            QPushButton {
                background: #26313d;
                border: 1px solid #3d4a57;
                border-radius: 5px;
                padding: 8px 10px;
                text-align: center;
            }
            QPushButton:hover {
                background: #314153;
            }
            QPushButton:disabled {
                color: #626b75;
                background: #1a1f25;
                border-color: #2c333a;
            }
            QPushButton#PrimaryButton {
                background: #5d2d46;
                border-color: #a54468;
                font-weight: 700;
            }
            QPushButton[dangerButton="true"] {
                background: #3a2428;
                border-color: #6b343d;
            }
            QLineEdit {
                background: #0f1114;
                border: 1px solid #333941;
                border-radius: 5px;
                padding: 6px;
                color: #e8e8e8;
            }
            QLineEdit:disabled {
                color: #626b75;
                background: #10151b;
            }
            QTabWidget::pane {
                border: 1px solid #333941;
                border-radius: 6px;
                top: -1px;
            }
            QTabBar::tab {
                background: #26313d;
                border: 1px solid #333941;
                padding: 8px 16px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
            }
            QTabBar::tab:selected {
                background: #151a20;
                color: #ff5c6c;
            }
            QRadioButton::indicator {
                width: 16px;
                height: 16px;
                border-radius: 8px;
                border: 2px solid #58616b;
                background: #1b2026;
            }
            QRadioButton::indicator:checked {
                border: 3px solid #58616b;
                background: #39ff14;
            }
            """
        )
