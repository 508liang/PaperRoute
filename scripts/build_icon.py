"""Render the original PaperRoute SVG into its Windows icon."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPainter
from PyQt5.QtSvg import QSvgRenderer
from PIL import Image

renderer = QSvgRenderer(str(ROOT / "assets" / "paperroute.svg"))
assert renderer.isValid()
image = QImage(256, 256, QImage.Format_ARGB32)
image.fill(Qt.transparent)
painter = QPainter(image)
renderer.render(painter)
painter.end()
png = ROOT / "assets" / "paperroute.png"
assert image.save(str(png))
with Image.open(png) as bitmap:
    bitmap.save(ROOT / "assets" / "paperroute.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("PaperRoute PNG and ICO generated")
