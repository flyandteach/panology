"""Site layout: places the hub's zones on a rectangular lot and draws them as SVG.

Coordinates are metres. x runs along the store frontage, y runs away from the
store (y = 0 is the store side). Order from the store outward: public setback,
operations building (loading under cover), airside apron with the pad grid,
fence, public setback. The battery room sits at the side of the apron, held
apart from the building and pads by the separation distance.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from html import escape


@dataclass
class Rect:
    name: str
    x: float
    y: float
    w: float
    h: float
    kind: str

    @property
    def x2(self) -> float:
        return self.x + self.w

    @property
    def y2(self) -> float:
        return self.y + self.h

    @property
    def area(self) -> float:
        return self.w * self.h


@dataclass
class Layout:
    site_w: float
    site_d: float
    required_w: float
    required_d: float
    fits: bool
    pad_side_m: float
    pad_pitch_m: float
    cols: int
    rows: int
    barrier: bool
    barrier_to_pad_m: float  # fence/barrier to the centre of the nearest pad
    rects: list[Rect] = field(default_factory=list)
    corridor_headings: list[float] = field(default_factory=list)  # degrees clockwise from "away from store"
    pad_label: str = "Pad"

    def get(self, name: str) -> Rect:
        return next(r for r in self.rects if r.name == name)

    @property
    def pads(self) -> list[Rect]:
        return [r for r in self.rects if r.kind == "pad"]

    def to_svg(self, px_per_m: float = 8.0) -> str:
        return render_svg(self, px_per_m)


def plan_layout(
    site_w: float,
    site_d: float,
    pads: int,
    span_m: float,
    pad_size_factor: float,
    pad_separation_factor: float,
    fence_buffer_factor: float,
    public_setback_m: float,
    building_depth_m: float,
    battery_side_m: float,
    battery_separation_m: float,
    barrier: bool,
    building_label: str = "Operations building (covered loading)",
) -> Layout:
    pad_side = pad_size_factor * span_m
    gap = pad_separation_factor * span_m
    pitch = pad_side + gap
    buffer = fence_buffer_factor * span_m
    sb = public_setback_m

    battery_block = battery_side_m + battery_separation_m
    avail_w = site_w - 2 * sb - 2 * buffer - battery_block
    cols = max(1, min(pads, math.floor((avail_w + gap) / pitch)))
    rows = math.ceil(pads / cols)

    grid_w = cols * pitch - gap
    grid_d = rows * pitch - gap
    fence_w = 2 * buffer + grid_w + battery_block
    # The battery room needs its own depth if it is taller than the pad grid. It is held
    # apart from the building and pads; it can sit against the fence.
    apron_d = max(2 * buffer + grid_d, battery_separation_m + battery_side_m)
    required_w = max(2 * sb + fence_w, 2 * sb + 1)
    required_d = sb + building_depth_m + apron_d + sb

    rects = [Rect("Public setback / walkway buffer", 0, 0, max(site_w, required_w), sb, "setback")]
    # Centre the hub along the frontage when the site has room to spare.
    fence_x = sb + max(0.0, (site_w - required_w) / 2)
    rects.append(Rect(building_label, fence_x, sb, fence_w, building_depth_m, "building"))
    apron_y = sb + building_depth_m
    rects.append(Rect("Airside apron (fenced)", fence_x, apron_y, fence_w, apron_d, "apron"))

    grid_x = fence_x + buffer
    grid_y = apron_y + buffer
    for i in range(pads):
        r, c = divmod(i, cols)
        rects.append(Rect(f"Pad {i + 1}", grid_x + c * pitch, grid_y + r * pitch, pad_side, pad_side, "pad"))

    bat_x = grid_x + grid_w + battery_separation_m
    bat_y = apron_y + battery_separation_m
    rects.append(Rect("Battery charging / storage room", bat_x, bat_y, battery_side_m, battery_side_m, "battery"))

    return Layout(
        site_w=site_w,
        site_d=site_d,
        required_w=required_w,
        required_d=required_d,
        fits=required_w <= site_w and required_d <= site_d,
        pad_side_m=pad_side,
        pad_pitch_m=pitch,
        cols=cols,
        rows=rows,
        barrier=barrier,
        barrier_to_pad_m=buffer + pad_side / 2,
        rects=rects,
    )


_FILL = {
    "setback": "#e8eef5",
    "building": "#c9b99a",
    "apron": "#d9dde2",
    "pad": "#4a7fb5",
    "battery": "#d0573a",
}


def render_svg(layout: Layout, px_per_m: float = 8.0) -> str:
    margin = 30.0
    world_w = max(layout.site_w, layout.required_w)
    world_d = max(layout.site_d, layout.required_d)
    w = world_w * px_per_m + 2 * margin
    h = world_d * px_per_m + 2 * margin + 30

    def sx(x: float) -> float:
        return margin + x * px_per_m

    def sy(y: float) -> float:
        # Store side at the bottom of the drawing.
        return margin + (world_d - y) * px_per_m

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {h:.0f}" '
        f'font-family="sans-serif" font-size="11">',
        f'<rect x="0" y="0" width="{w:.0f}" height="{h:.0f}" fill="#ffffff"/>',
    ]
    for r in layout.rects:
        fill = _FILL.get(r.kind, "#cccccc")
        out.append(
            f'<rect x="{sx(r.x):.1f}" y="{sy(r.y2):.1f}" width="{r.w * px_per_m:.1f}" '
            f'height="{r.h * px_per_m:.1f}" fill="{fill}" stroke="#333" stroke-width="0.8">'
            f"<title>{escape(r.name.replace('Pad', layout.pad_label))}</title></rect>"
        )
        if r.kind == "pad":
            out.append(
                f'<text x="{sx(r.x + r.w / 2):.1f}" y="{sy(r.y + r.h / 2) + 4:.1f}" fill="#fff" '
                f'text-anchor="middle">{escape(r.name.split()[-1])}</text>'
            )
        elif r.kind in ("building", "battery", "setback"):
            label = "Battery room" if r.kind == "battery" else r.name
            out.append(
                f'<text x="{sx(r.x) + 4:.1f}" y="{sy(r.y2) + 13:.1f}" fill="#111">{escape(label)}</text>'
            )

    apron = layout.get("Airside apron (fenced)")
    if layout.barrier:
        # Barrier on the three airside fence lines facing away from the store.
        pts = [(apron.x, apron.y), (apron.x, apron.y2), (apron.x2, apron.y2), (apron.x2, apron.y)]
        path = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y in pts)
        out.append(f'<polyline points="{path}" fill="none" stroke="#2e7d32" stroke-width="4"/>')
    else:
        out.append(
            f'<rect x="{sx(apron.x):.1f}" y="{sy(apron.y2):.1f}" width="{apron.w * px_per_m:.1f}" '
            f'height="{apron.h * px_per_m:.1f}" fill="none" stroke="#555" stroke-dasharray="4 3"/>'
        )

    # Departure / arrival corridors from the apron centre; straight away from the store if none given.
    cx = sx(apron.x + apron.w / 2)
    cy = sy(apron.y + apron.h / 2)
    reach = max(apron.w, apron.h) / 2 * px_per_m + 20
    for rel in layout.corridor_headings or [0.0]:
        t = math.radians(rel)
        x2, y2 = cx + reach * math.sin(t), cy - reach * math.cos(t)
        out.append(
            f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="#6a1b9a" stroke-width="2" marker-end="url(#arrow)"/>'
        )
    out.insert(
        1,
        '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="4" refY="4" orient="auto">'
        '<path d="M0,0 L8,4 L0,8 z" fill="#6a1b9a"/></marker></defs>',
    )

    site_stroke = "#2e7d32" if layout.fits else "#c62828"
    out.append(
        f'<rect x="{sx(0):.1f}" y="{sy(layout.site_d):.1f}" width="{layout.site_w * px_per_m:.1f}" '
        f'height="{layout.site_d * px_per_m:.1f}" fill="none" stroke="{site_stroke}" stroke-width="2" '
        f'stroke-dasharray="8 4"><title>Available site</title></rect>'
    )
    out.append(f'<text x="{margin:.0f}" y="{h - 24:.0f}" fill="#111">Store / parking side at bottom. '
               f'Purple arrows: departure / arrival corridors.</text>')
    out.append(f'<text x="{margin:.0f}" y="{h - 8:.0f}" fill="#111">Green line: noise barrier. '
               f'Dashed outline: available site (red if the hub does not fit).</text>')
    out.append("</svg>")
    return "\n".join(out)
