# The animated Pentaho swirl used on the startup splash.
#
# Emitted as a VECTOR path rather than reusing the raster mask in
# src-tauri/icons/brand/, because the splash animates it: stroke-dashoffset
# draws it on, then it rotates. Neither is possible with a PNG, and at 78px on a
# high-DPI laptop the vector is sharper anyway.
#
# Reusable as-is. It depends on nothing in this app, so the same path (or the
# standalone SVG below) drops straight into Pentaho Content Manager or anything
# else that wants the mark moving rather than sitting still.
#
#   python scripts/make-swirl.py                  # print the path data
#   python scripts/make-swirl.py --svg swirl.svg  # standalone animated SVG
#   python scripts/make-swirl.py --inject <html>  # replace __SPIRAL__ in a file
#
# ASCII-only on purpose.
import argparse
import math

ap = argparse.ArgumentParser(description="Generate the animated Pentaho swirl.")
ap.add_argument("--turns", type=float, default=2.55, help="revolutions from centre to tip")
ap.add_argument("--steps", type=int, default=220, help="polyline resolution")
ap.add_argument("--r0", type=float, default=4.0, help="inner radius")
ap.add_argument("--r1", type=float, default=44.0, help="outer radius")
ap.add_argument("--colour", default="#cc0000", help="stroke colour")
ap.add_argument("--width", type=float, default=7.5, help="stroke width")
ap.add_argument("--no-pulses", action="store_true",
                help="omit the concentric pulse rings (mark only)")
ap.add_argument("--svg", help="write a standalone animated SVG here")
ap.add_argument("--inject", help="replace __SPIRAL__ in this file with the path data")
args = ap.parse_args()


def path_data():
    """Archimedean spiral: r grows linearly with angle.

    The opening starts at the top-left and sweeps clockwise, which is what makes
    it read as the Pentaho mark rather than a generic spiral.
    """
    pts = []
    for i in range(args.steps + 1):
        t = i / args.steps
        r = args.r0 + (args.r1 - args.r0) * t
        a = t * args.turns * 2 * math.pi - math.pi * 0.75
        pts.append((50 + r * math.cos(a), 50 + r * math.sin(a)))
    return "M %.2f %.2f " % pts[0] + " ".join("L %.2f %.2f" % p for p in pts[1:])


SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="128" height="128">
  <style>
    .swirl {{
      fill: none; stroke: {colour}; stroke-width: {width};
      stroke-linecap: round; stroke-linejoin: round;
      stroke-dasharray: 640; stroke-dashoffset: 640;
      animation: draw 2.2s cubic-bezier(.35,.6,.3,1) forwards,
                 spin 16s linear 2.2s infinite;
      transform-origin: 50% 50%;
    }}
    @keyframes draw {{ to {{ stroke-dashoffset: 0; }} }}
    @keyframes spin {{ to {{ transform: rotate(360deg); }} }}

    /* Pulses. `r` and `opacity` are animated rather than a transform, so no
       transform-origin is needed and it behaves identically inline, as an
       <img>, or as a CSS background. */
    .pulse {{
      fill: none; stroke: {colour}; stroke-width: 0.8;
      animation: pulse 3.2s ease-out infinite;
    }}
    .pulse:nth-of-type(2) {{ animation-delay: 1.05s; }}
    .pulse:nth-of-type(3) {{ animation-delay: 2.10s; }}
    @keyframes pulse {{
      0%   {{ r: 24; opacity: .75; }}
      100% {{ r: 96; opacity: 0; }}
    }}
  </style>
{pulses}  <path class="swirl" d="{d}"/>
</svg>
"""
d = path_data()

# Three identical rings; the stagger comes from :nth-of-type delays in the CSS
# above, so adding or removing one needs no other change.
RING = '  <circle class="pulse" cx="50" cy="50" r="24"/>'
PULSES = "\n".join([RING, RING, RING]) + "\n"

if args.svg:
    with open(args.svg, "w", encoding="utf-8", newline="") as f:
        f.write(SVG.format(colour=args.colour, width=args.width, d=d,
                           pulses="" if args.no_pulses else PULSES))
    print("wrote", args.svg)
elif args.inject:
    with open(args.inject, encoding="utf-8") as f:
        html = f.read()
    if "__SPIRAL__" not in html:
        raise SystemExit("no __SPIRAL__ placeholder in " + args.inject)
    with open(args.inject, "w", encoding="utf-8", newline="") as f:
        f.write(html.replace("__SPIRAL__", d))
    print("injected", len(d), "chars into", args.inject)
else:
    print(d)
