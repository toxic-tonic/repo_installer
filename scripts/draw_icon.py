"""Repo Installer brand icon: slate box, petrol arrow into it, neutral branch glyph.

Developer tool only (needs Pillow, not a runtime requirement):
    uv run --with pillow==11.3.0 python scripts/draw_icon.py custom_components/repo_installer/brand
"""
import sys
from PIL import Image, ImageDraw

N = 2048  # supersampled canvas
SLATE, SLATE_DARK, SLATE_LIGHT = (71, 85, 105, 255), (51, 65, 85, 255), (100, 116, 139, 255)
PETROL, GLYPH = (14, 116, 144, 255), (226, 232, 240, 255)

def P(x, y):
    return (round(x * N), round(y * N))

img = Image.new("RGBA", (N, N), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# open flaps (behind the arrow), tilted outwards
d.polygon([P(0.10, 0.50), P(0.30, 0.50), P(0.20, 0.33), P(0.02, 0.38)], fill=SLATE_LIGHT)
d.polygon([P(0.90, 0.50), P(0.70, 0.50), P(0.80, 0.33), P(0.98, 0.38)], fill=SLATE_LIGHT)

# arrow: shaft + head, pointing down into the box
d.rounded_rectangle([P(0.415, 0.03), P(0.585, 0.46)], radius=round(0.03 * N), fill=PETROL)
d.polygon([P(0.27, 0.40), P(0.73, 0.40), P(0.50, 0.66)], fill=PETROL)

# box body with darker rim
d.rounded_rectangle([P(0.10, 0.50), P(0.90, 0.97)], radius=round(0.06 * N), fill=SLATE)
d.rectangle([P(0.10, 0.50), P(0.90, 0.58)], fill=SLATE_DARK)
# re-draw arrow tip over the rim so it visibly enters the box
d.polygon([P(0.36, 0.50), P(0.64, 0.50), P(0.50, 0.66)], fill=PETROL)

# neutral branch glyph on the front: trunk with two nodes, side branch merging in
w = round(0.035 * N)
r = round(0.045 * N)
trunk_x, top_y, bot_y = 0.40, 0.70, 0.89
side = (0.62, 0.74)
d.line([P(trunk_x, top_y), P(trunk_x, bot_y)], fill=GLYPH, width=w)
d.line([P(*side), P(0.62, 0.80), P(trunk_x, 0.86)], fill=GLYPH, width=w, joint="curve")
for cx, cy in ((trunk_x, top_y), (trunk_x, bot_y), side):
    x, y = P(cx, cy)
    d.ellipse([x - r, y - r, x + r, y + r], fill=GLYPH)

# trim transparent border as the brands guidelines ask, keep it square
bbox = img.getbbox()
side_len = max(bbox[2] - bbox[0], bbox[3] - bbox[1])
sq = Image.new("RGBA", (side_len, side_len), (0, 0, 0, 0))
sq.paste(img.crop(bbox), ((side_len - (bbox[2] - bbox[0])) // 2,
                          (side_len - (bbox[3] - bbox[1])) // 2))
out = sys.argv[1]
for size, name in ((256, "icon.png"), (512, "icon@2x.png")):
    sq.resize((size, size), Image.LANCZOS).save(f"{out}/{name}", optimize=True)
print("ok", bbox)
