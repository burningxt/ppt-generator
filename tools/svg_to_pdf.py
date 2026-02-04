#!/usr/bin/env python3
import os
import sys
from pathlib import Path

try:
    from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter, QPainter
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtCore import QSize, QRectF, QMarginsF, QPointF, QSizeF
    from PySide6.QtWidgets import QApplication

    USE_PYSIDE = True
except ImportError:
    USE_PYSIDE = False
    print("Warning: PySide6 not found. PDF quality may be low.")

# Import project utilities for dimension extraction
sys.path.insert(0, str(Path(__file__).parent))
try:
    from project_utils import get_svg_dimensions
except ImportError:

    def get_svg_dimensions(path):
        return None, None


def svg_to_pdf_pyside(project_dir, source="final"):
    # Need a QApplication instance for Qt elements
    app = QApplication.instance() or QApplication(sys.argv)

    project_path = Path(project_dir)
    svg_dir = project_path / ("svg_final" if source == "final" else "svg_output")

    if not svg_dir.exists():
        print(f"Error: {svg_dir} does not exist.")
        return

    svg_files = sorted(svg_dir.glob("*.svg"))
    if not svg_files:
        print(f"No SVG files found in {svg_dir}")
        return

    # Detect dimensions from the first file
    sw, sh = get_svg_dimensions(svg_files[0])
    if not sw or not sh:
        print(
            f"  [WARN] Could not detect dimensions from {svg_files[0].name}, using default 1280x720"
        )
        sw, sh = 1280, 720
    else:
        print(f"  [INFO] Detected dimensions: {sw}x{sh}")

    output_pdf = project_path / f"{project_path.name}.pdf"

    writer = QPdfWriter(str(output_pdf))
    writer.setResolution(72)  # 72 DPI means 1 unit = 1 point = 1 px

    # Create page size and layout
    # For custom dimensions, it's safest to define the size exactly and use Portrait
    # to avoid Qt's automatic orientation swapping logic.
    page_size = QPageSize(QSizeF(sw, sh), QPageSize.Unit.Point)

    layout = QPageLayout()
    layout.setPageSize(page_size)
    layout.setOrientation(QPageLayout.Orientation.Portrait)  # Direct mapping
    layout.setMargins(QMarginsF(0, 0, 0, 0))

    # Explicitly set the page layout on the writer
    if not writer.setPageLayout(layout):
        print("  [WARN] Failed to set page layout, falling back to setPageSize")
        writer.setPageSize(page_size)

    painter = QPainter(writer)

    for i, svg_file in enumerate(svg_files):
        print(f"Processing {svg_file.name}...")

        # Check dimensions for each page to handle mixed orientations if needed
        psw, psh = get_svg_dimensions(svg_file)
        if psw and psh and (psw != sw or psh != sh):
            print(f"  [INFO] Page {i + 1} has different dimensions: {psw}x{psh}")
            # Note: QPdfWriter doesn't easily support mixed page sizes in a single layout
            # without resetting layout between pages, which can be tricky.
            # For now, we scale to fit the first page's size to keep it simple and consistent.
            render_rect = QRectF(0, 0, sw, sh)
        else:
            render_rect = QRectF(0, 0, sw, sh)

        if i > 0:
            writer.newPage()

        renderer = QSvgRenderer(str(svg_file))
        if not renderer.isValid():
            print(f"  [ERROR] Invalid SVG: {svg_file.name}")
            continue

        # Draw the SVG to the page
        renderer.render(painter, render_rect)

    painter.end()
    print(f"Successfully saved high-quality PDF to {output_pdf}")


if __name__ == "__main__":
    if not USE_PYSIDE:
        print("Please install PySide6: uv pip install PySide6")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("Usage: python tools/svg_to_pdf.py <project_dir> [source]")
    else:
        project_dir = sys.argv[1]
        source = sys.argv[2] if len(sys.argv) > 2 else "final"
        svg_to_pdf_pyside(project_dir, source)
