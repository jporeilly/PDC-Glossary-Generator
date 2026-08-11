# Pentaho-branded icon + NSIS installer art.
#
# Default run (no args): the stock set - red app icon master
# (icon-source.png) plus red NSIS header/sidebar bitmaps.
#
# Course-seeded installer builds recolor the NSIS art per course:
#   python scripts/make-icons.py --nsis-only \
#       --accent "#16a34a" --title "Pentaho Analyst - BA Practitioner"
# (--nsis-only leaves the app icon untouched; the swirl/wordmark masks
# in src-tauri/icons/brand/ come from the classic Pentaho logo with
# the Hitachi tagline stripped.)
#
# After changing the app icon master, regenerate the full set with:
#   npx @tauri-apps/cli icon src-tauri/icons/icon-source.png
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import argparse
import os

parser = argparse.ArgumentParser()
parser.add_argument("--accent", default="#CC0000", help="background color for the NSIS art")
parser.add_argument("--title", default="PDC Glossary Generator",
                    help="product title for the sidebar (split on ' - ')")
parser.add_argument("--strapline", default="Build a governed business glossary",
                    help="one line under the product title on the sidebar")
parser.add_argument("--nsis-only", action="store_true", help="only regenerate the NSIS bitmaps")
# The per-app badge on the app icon. The suite shares the red swirl; the badge
# is what tells the three taskbar pins apart at 24 px: Glossary = a governed
# term TAG, Insights = a bar CHART, Policy = a SHIELD with a check.
parser.add_argument("--badge", default="tag", choices=["tag", "chart", "shield", "none"])
parser.add_argument("--badge-color", default="#16A34A",
                    help="badge circle colour (this app: glossary green)")
args = parser.parse_args()

repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
scr = os.path.join(repo, "src-tauri", "icons", "brand")
icons = os.path.join(repo, "src-tauri", "icons")

PENTAHO_RED = (204, 0, 0)
PENTAHO_RED_DARK = (150, 0, 0)
WHITE = (255, 255, 255)

accent_hex = args.accent.lstrip("#")
ACCENT = tuple(int(accent_hex[i : i + 2], 16) for i in (0, 2, 4))
ACCENT_DARK = tuple(int(c * 0.62) for c in ACCENT)

swirl_a = Image.open(os.path.join(scr, "swirl_mask.png"))
wm_a = Image.open(os.path.join(scr, "wordmark_mask.png"))

def colorize(alpha, color, scale):
    tw, th = int(alpha.width * scale), int(alpha.height * scale)
    if scale > 2:
        big = alpha.resize((tw * 2, th * 2), Image.LANCZOS)
        r = max(2, scale * 0.9)
        big = big.filter(ImageFilter.GaussianBlur(r))
        big = big.point(lambda v: max(0, min(255, int((v - 116) * 4.2))))
        big = big.filter(ImageFilter.GaussianBlur(3))
        a = big.resize((tw, th), Image.LANCZOS)
    else:
        a = alpha.resize((tw, th), Image.LANCZOS)
    out = Image.new("RGBA", (tw, th), color + (0,))
    out.putalpha(a)
    return out

# ---------------- per-app badge glyphs -------------------------
def draw_badge(img, S, kind, color_hex):
    """A coloured circle in the lower-right with a simple white glyph.

    Pure shapes, no text: the badge must read at 16-24 px, where a letter is
    mush. A white ring separates the circle from the red field behind it."""
    if kind == "none":
        return
    c = tuple(int(color_hex.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    cx, cy, r = int(S * 0.735), int(S * 0.735), int(S * 0.205)
    ring = int(S * 0.024)
    d = ImageDraw.Draw(img)
    d.ellipse([cx - r - ring, cy - r - ring, cx + r + ring, cy + r + ring],
              fill=(255, 255, 255, 255))
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=c + (255,))

    if kind == "chart":
        # Four bars, the app's own sidebar mark: heights 10/13/7/9.
        heights = [10, 13, 7, 9]
        unit = (r * 1.24) / 13
        bw = int(r * 0.24)
        gap = int(r * 0.13)
        total_w = 4 * bw + 3 * gap
        x = cx - total_w // 2
        base = cy + int(r * 0.62)
        for h in heights:
            top = base - int(h * unit)
            d.rounded_rectangle([x, top, x + bw, base], radius=bw // 3,
                                fill=(255, 255, 255, 255))
            x += bw + gap
    elif kind == "shield":
        # Shield outline as a polygon (curves approximated), check inside.
        w, h = r * 1.30, r * 1.46
        pts = [(0.0, -0.50), (0.30, -0.42), (0.46, -0.38), (0.46, -0.02),
               (0.40, 0.18), (0.24, 0.36), (0.0, 0.50), (-0.24, 0.36),
               (-0.40, 0.18), (-0.46, -0.02), (-0.46, -0.38), (-0.30, -0.42)]
        d.polygon([(cx + px * w, cy + py * h) for px, py in pts],
                  fill=(255, 255, 255, 255))
        lw = int(r * 0.16)
        chk = [(cx - w * 0.22, cy + h * 0.00), (cx - w * 0.05, cy + h * 0.16),
               (cx + w * 0.26, cy - h * 0.18)]
        d.line(chk, fill=c + (255,), width=lw, joint="curve")
        for px, py in (chk[0], chk[2]):
            d.ellipse([px - lw / 2, py - lw / 2, px + lw / 2, py + lw / 2], fill=c + (255,))
    else:  # tag
        # A governed-term tag: rounded square rotated 45 deg, hole punched in
        # the badge colour. Drawn on its own layer so the rotation stays crisp.
        side = int(r * 1.18)
        layer = Image.new("RGBA", (side * 2, side * 2), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        ld.rounded_rectangle([side // 2, side // 2, side // 2 + side, side // 2 + side],
                             radius=side // 5, fill=(255, 255, 255, 255))
        layer = layer.rotate(45, resample=Image.BICUBIC, expand=False)
        img.alpha_composite(layer, (cx - side, cy - side))
        hole = int(r * 0.14)
        hx, hy = cx, cy - int(r * 0.46)
        d.ellipse([hx - hole, hy - hole, hx + hole, hy + hole], fill=c + (255,))


# ---------------- 1024 icon (always Pentaho red) ----------------
if not args.nsis_only:
    S = 2048
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * 0.19), fill=255)
    bg = Image.new("RGBA", (S, S), PENTAHO_RED + (255,))
    shade = Image.new("L", (1, S))
    for y in range(S):
        shade.putpixel((0, y), int(28 * (y / S)))
    dark = Image.new("RGBA", (S, S), PENTAHO_RED_DARK + (255,))
    bg = Image.composite(dark, bg, shade.resize((S, S)))
    img.paste(bg, (0, 0), mask)

    sw = colorize(swirl_a, WHITE, (S * 0.72) / swirl_a.width)
    # Nudged up-left so the badge owns the lower-right corner.
    img.alpha_composite(sw, (int((S - sw.width) / 2 - S * 0.03),
                             int((S - sw.height) / 2 - S * 0.03)))
    draw_badge(img, S, args.badge, args.badge_color)
    img = img.resize((1024, 1024), Image.LANCZOS)
    img.save(os.path.join(icons, "icon-source.png"))

# ---------------- NSIS header 150x57 ----------------
SS = 8
W, H = 150 * SS, 57 * SS
hdr = Image.new("RGB", (W, H), ACCENT)
sw = colorize(swirl_a, WHITE, (H * 0.74) / swirl_a.height)
wmark = colorize(wm_a, WHITE, (W * 0.54) / wm_a.width)
MARGIN = 0.06
hdr.paste(wmark, (int(W * MARGIN), int((H - wmark.height) / 2)), wmark)
# Right margin computed to MATCH the left, rather than a fixed x that happened
# to leave the swirl flush against the edge: it was pasted at 71% and is ~28%
# wide, so it ran to 99%. Deriving the position from the mark's actual width
# keeps the two margins equal whatever the scale factor above becomes.
hdr.paste(sw, (W - int(W * MARGIN) - sw.width, int((H - sw.height) / 2)), sw)
hdr.resize((150, 57), Image.LANCZOS).save(os.path.join(icons, "nsis-header.bmp"), "BMP")

# ---------------- NSIS sidebar 164x314 ----------------
SS = 8
W, H = 164 * SS, 314 * SS
side = Image.new("RGB", (W, H), ACCENT)
grad = Image.new("L", (1, H))
for y in range(H):
    grad.putpixel((0, y), int(70 * (1 - y / H)))
side = Image.composite(Image.new("RGB", (W, H), ACCENT_DARK), side, grad.resize((W, H)))
d = ImageDraw.Draw(side)
sw = colorize(swirl_a, WHITE, (W * 0.54) / swirl_a.width)
# The sidebar swirl wears the app badge, same composition as the app
# icon (the header's swirl lands ~42 px tall, glyph mush - left plain).
L = int(sw.width / 0.72)
tile = Image.new("RGBA", (L, L), (0, 0, 0, 0))
tile.alpha_composite(sw, (int((L - sw.width) / 2 - L * 0.03),
                          int((L - sw.height) / 2 - L * 0.03)))
draw_badge(tile, L, args.badge, args.badge_color)
side.paste(tile, (int((W - L) / 2), int(H * 0.11) - (L - sw.height) // 2), tile)
wmark = colorize(wm_a, WHITE, (W * 0.74) / wm_a.width)
side.paste(wmark, (int((W - wmark.width) / 2), int(H * 0.455)), wmark)
try:
    f_med = ImageFont.truetype(r"C:\Windows\Fonts\segoeui.ttf", int(W * 0.088))
    f_sml = ImageFont.truetype(r"C:\Windows\Fonts\segoeui.ttf", int(W * 0.070))
except OSError:
    f_med = f_sml = ImageFont.load_default()

def centered(dr, y, text, font, fill):
    bb = dr.textbbox((0, 0), text, font=font)
    dr.text(((W - (bb[2] - bb[0])) / 2 - bb[0], y), text, font=font, fill=fill)

def fit_font(text, max_w, size):
    """Shrink from `size` until `text` fits in max_w pixels."""
    while size > int(W * 0.05):
        f = ImageFont.truetype(r"C:\Windows\Fonts\segoeui.ttf", size)
        bb = ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox((0, 0), text, font=f)
        if bb[2] - bb[0] <= max_w:
            return f
        size = int(size * 0.92)
    return ImageFont.truetype(r"C:\Windows\Fonts\segoeui.ttf", size)

soft = tuple(min(255, int(c * 0.35 + 255 * 0.65)) for c in ACCENT)
if args.title:
    # The product title (split on " - ") under the wordmark, then the
    # strapline. PCM's copy says "Workshop lab guide" here; this is a
    # different product and saying so is the whole point of regenerating
    # the art rather than copying PCM's bitmaps.
    lines = [p.strip() for p in args.title.split(" - ") if p.strip()][:2]
    y = H * 0.585
    for line in lines:
        f = fit_font(line, int(W * 0.88), int(W * 0.085))
        centered(d, y, line, f, WHITE)
        y += H * 0.055
    f_str = fit_font(args.strapline, int(W * 0.90), int(W * 0.070))
    centered(d, y + H * 0.020, args.strapline, f_str, soft)
else:
    centered(d, H * 0.60, "Glossary Generator", f_med, WHITE)
    f_str = fit_font(args.strapline, int(W * 0.90), int(W * 0.070))
    centered(d, H * 0.695, args.strapline, f_str, soft)

# NSIS stretches this bitmap to fill the welcome-page control
# (FitToField), so the canvas must be EXACTLY the nominal 164x314 -
# padding it taller gets the whole design vertically squashed, and any
# decorative bar at the bottom edge reads as a stray band once the
# control's bevel is drawn under it. Learned both the hard way.
side.resize((164, 314), Image.LANCZOS).save(os.path.join(icons, "nsis-sidebar.bmp"), "BMP")

print("done" + (" (nsis-only, accent %s)" % args.accent if args.nsis_only else ""))
