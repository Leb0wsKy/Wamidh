"""3D figures for the report, Section 5 (node and radio link).

python docs/figures/src/node_and_relief_3d.py
-> docs/figures/fig_node_3d.{png,svg}, docs/figures/fig_relief_los.{png,svg}
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import rasterio  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402
from pyproj import Transformer  # noqa: E402
from rasterio.windows import from_bounds  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
FIG = REPO / "docs" / "figures"
EMBER, INK = "#B3261E", "#1A1A19"
TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32632", always_xy=True)


def cuboid(ax, origin, size, face, edge=INK, lw=0.5):
    x, y, z = origin
    dx, dy, dz = size
    v = np.array(
        [
            [x, y, z],
            [x + dx, y, z],
            [x + dx, y + dy, z],
            [x, y + dy, z],
            [x, y, z + dz],
            [x + dx, y, z + dz],
            [x + dx, y + dy, z + dz],
            [x, y + dy, z + dz],
        ]
    )
    faces = [
        [v[i] for i in f]
        for f in (
            [0, 1, 2, 3],
            [4, 5, 6, 7],
            [0, 1, 5, 4],
            [1, 2, 6, 5],
            [2, 3, 7, 6],
            [3, 0, 4, 7],
        )
    ]
    ax.add_collection3d(
        Poly3DCollection(faces, facecolors=face, edgecolors=edge, linewidths=lw)
    )


def cuboid_faces(origin, size):
    x, y, z = origin
    dx, dy, dz = size
    v = np.array(
        [
            [x, y, z],
            [x + dx, y, z],
            [x + dx, y + dy, z],
            [x, y + dy, z],
            [x, y, z + dz],
            [x + dx, y, z + dz],
            [x + dx, y + dy, z + dz],
            [x, y + dy, z + dz],
        ]
    )
    return [
        [v[i] for i in f]
        for f in (
            [0, 1, 2, 3],
            [4, 5, 6, 7],
            [0, 1, 5, 4],
            [1, 2, 6, 5],
            [2, 3, 7, 6],
            [3, 0, 4, 7],
        )
    ]


def disc(centre, r, n=20):
    """A disc in the x-z plane (on the enclosure's front face)."""
    cx, cy, cz = centre
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return [[cx + r * np.cos(a), cy, cz + r * np.sin(a)] for a in t]


def cylinder(ax, cx, cy, z0, z1, r, color, axis="z"):
    t = np.linspace(0, 2 * np.pi, 24)
    h = np.linspace(z0, z1, 2)
    tt, hh = np.meshgrid(t, h)
    if axis == "z":
        ax.plot_surface(
            cx + r * np.cos(tt), cy + r * np.sin(tt), hh, color=color, linewidth=0
        )
    else:  # along -y (pointing out of the enclosure front)
        ax.plot_surface(
            cx + r * np.cos(tt), hh, cy + r * np.sin(tt), color=color, linewidth=0
        )


def node_figure() -> None:
    fig = plt.figure(figsize=(6.4, 4.6))
    # Draw in the order written (back to front), so the front-face windows stay visible.
    ax = fig.add_subplot(projection="3d", computed_zorder=False)
    # Pole, 2 m (units: metres).
    cylinder(ax, 0.0, 0.0, 0.0, 2.0, 0.03, "#9A9A96")
    # IP67 enclosure (electronics, LiFePO4 cell) and the louvred radiation shield over the vented
    # BME688 chamber.
    polys, colors = [], []
    polys += cuboid_faces((-0.12, -0.10, 1.45), (0.24, 0.12, 0.30))
    colors += ["#E8E6E1"] * 6
    for k in range(4):
        polys += cuboid_faces((-0.08, -0.12, 1.25 + 0.045 * k), (0.16, 0.14, 0.012))
        colors += ["#F7F6F3"] * 6
    ax.add_collection3d(
        Poly3DCollection(polys, facecolors=colors, edgecolors=INK, linewidths=0.5)
    )
    # Camera lens and IR flame window on the front face, drawn after the box.
    windows = [
        disc((0.06, -0.103, 1.66), 0.028),
        disc((0.06, -0.104, 1.66), 0.012),
        disc((-0.06, -0.103, 1.66), 0.02),
    ]
    ax.add_collection3d(
        Poly3DCollection(
            windows,
            facecolors=["#2B2B29", "#6F8FB8", EMBER],
            edgecolors=INK,
            linewidths=0.5,
        )
    )
    # 1 W solar panel above, tilted south.
    panel = np.array(
        [
            [-0.17, -0.18, 1.90],
            [0.17, -0.18, 1.90],
            [0.17, 0.06, 2.02],
            [-0.17, 0.06, 2.02],
        ]
    )
    ax.add_collection3d(
        Poly3DCollection([panel], facecolors="#22324F", edgecolors=INK, linewidths=0.6)
    )
    ax.plot([0, 0], [0, -0.06], [1.75, 1.95], color="#9A9A96", lw=2)
    # LoRa antenna (868 MHz) on the side.
    ax.plot(
        [0.13, 0.13], [-0.04, -0.04], [1.70, 2.25], color=INK, lw=2.2, clip_on=False
    )
    ax.set_xlim(-0.35, 0.35)
    ax.set_ylim(-0.3, 0.3)
    ax.set_zlim(0.55, 2.3)  # the lower pole is plain; crop it so the node reads larger
    ax.set_box_aspect((0.7, 0.6, 1.75), zoom=1.45)
    ax.view_init(elev=14, azim=-62)
    ax.set_axis_off()
    fig.subplots_adjust(left=0.28, right=0.72, top=1.0, bottom=0.0)
    fig.canvas.draw()
    # Callouts in 2D: each part's 3D position projected on the image, labels in two clean columns.
    from mpl_toolkits.mplot3d import proj3d

    callouts = [  # (part position), (label x, y in figure fraction), text, alignment
        ((0.0, -0.06, 1.98), (0.02, 0.80), "1 W solar panel", "left"),
        (
            (-0.12, -0.10, 1.60),
            (0.02, 0.56),
            "IP67 enclosure:\nESP32-S3, SX1262,\nLiFePO$_4$ cell",
            "left",
        ),
        ((0.0, 0.0, 0.85), (0.02, 0.18), "2 m pole near a track", "left"),
        ((0.13, -0.04, 2.22), (0.68, 0.90), "LoRa antenna, 868 MHz", "left"),
        ((0.06, -0.12, 1.66), (0.68, 0.56), "camera, wakes in ALERT", "left"),
        ((-0.06, -0.12, 1.66), (0.68, 0.68), "IR flame window", "left"),
        (
            (0.0, -0.12, 1.32),
            (0.68, 0.38),
            "radiation shield over\nthe BME688 chamber",
            "left",
        ),
    ]
    for (x, y, z), (fx, fy), text, ha in callouts:
        px, py, _ = proj3d.proj_transform(x, y, z, ax.get_proj())
        ax.annotate(
            text,
            xy=(px, py),
            xycoords="data",
            xytext=(fx, fy),
            textcoords="figure fraction",
            ha=ha,
            va="center",
            fontsize=10,
            color=INK,
            annotation_clip=False,
            arrowprops=dict(
                arrowstyle="-", color="#5B5A56", lw=0.7, shrinkA=2, shrinkB=1
            ),
        )
    for ext in ("png", "svg"):
        # Full canvas: the tight box of a 3D axes leaves out callouts placed beside it.
        from matplotlib.transforms import Bbox

        fig.savefig(
            FIG / f"fig_node_3d.{ext}",
            bbox_inches=Bbox([[0, 0], list(fig.get_size_inches())]),
        )
    plt.close(fig)


# --- relief and line of sight -----------------------------------------------------------------


def pick_gateway() -> tuple[dict, list[dict]]:
    """The gateway serving the most nodes, and its two nearest nodes."""
    gws = json.loads(
        (REPO / "web/public/placement/gateways.geojson").read_text("utf-8")
    )["features"]
    nodes = json.loads(
        (REPO / "web/public/placement/nodes.geojson").read_text("utf-8")
    )["features"]
    gw = max(gws, key=lambda f: f["properties"]["nodes_assigned"])
    gid = gw["properties"]["gateway_id"]
    gx, gy = TO_UTM.transform(*gw["geometry"]["coordinates"][:2])
    mine = [f for f in nodes if f["properties"].get("gateway_id") == gid]
    mine.sort(
        key=lambda f: np.hypot(
            *(
                np.subtract(
                    TO_UTM.transform(*f["geometry"]["coordinates"][:2]), (gx, gy)
                )
            )
        )
    )
    return gw, mine[:2]


def sight_clear(dem, transform, a_xy, b_xy) -> bool:
    """The placement model's own test (placement.viewshed): 2 m node antenna, 10 m mast, 4/3 Earth."""
    import sys

    sys.path.insert(0, str(REPO / "placement" / "src"))
    from placement.viewshed import line_of_sight

    inv = ~transform
    ca, ra = inv * a_xy
    cb, rb = inv * b_xy
    return bool(
        line_of_sight(
            dem,
            abs(transform.a),
            (int(ra), int(ca)),
            (int(rb), int(cb)),
            2.0,
            10.0,
            4 / 3,
        )
    )


def relief_figure() -> None:
    gw, nodes = pick_gateway()
    gx, gy = TO_UTM.transform(*gw["geometry"]["coordinates"][:2])
    pts = [TO_UTM.transform(*f["geometry"]["coordinates"][:2]) for f in nodes]
    xs = [gx] + [p[0] for p in pts]
    ys = [gy] + [p[1] for p in pts]
    pad = 700
    bounds = (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)
    with rasterio.open(REPO / "data/raw/gee/kroumirie_terrain.tif") as src:
        win = from_bounds(*bounds, transform=src.transform)
        dem = src.read(1, window=win).astype(float)
        tr = src.window_transform(win)
    step = max(1, dem.shape[0] // 120)
    rows, cols = np.mgrid[0 : dem.shape[0] : step, 0 : dem.shape[1] : step]
    X = tr.c + (cols + 0.5) * tr.a
    Y = tr.f + (rows + 0.5) * tr.e
    Z = dem[::step, ::step]

    def ground(x, y):
        c, r = ~tr * (x, y)
        return float(dem[int(r), int(c)])

    fig = plt.figure(figsize=(6.6, 4.6))
    ax = fig.add_subplot(
        projection="3d", computed_zorder=False
    )  # draw marks above the surface
    ax.plot_surface(
        (X - gx) / 1000,
        (Y - gy) / 1000,
        Z,
        cmap="terrain",
        linewidth=0,
        antialiased=True,
        alpha=0.9,
        rstride=1,
        cstride=1,
        vmin=Z.min() - 150,
        vmax=Z.max() + 50,
        zorder=1,
    )
    g_top = ground(gx, gy) + 10
    ax.plot(
        [0, 0], [0, 0], [ground(gx, gy), g_top + 25], color=INK, lw=3, zorder=10
    )  # mast (drawn taller)
    ax.scatter(
        [0], [0], [g_top + 25], color=INK, s=34, marker="^", depthshade=False, zorder=11
    )
    ax.text(
        0,
        0,
        g_top + 110,
        f"gateway {gw['properties']['gateway_id']}, {gw['properties']['elevation_m']:.0f} m",
        fontsize=10,
        ha="center",
        zorder=12,
        bbox=dict(facecolor="white", edgecolor="none", alpha=0.8, pad=1),
    )
    for f, (x, y) in zip(nodes, pts, strict=True):
        z0 = ground(x, y)
        clear = sight_clear(dem, tr, (x, y), (gx, gy))
        ax.plot(
            [(x - gx) / 1000] * 2,
            [(y - gy) / 1000] * 2,
            [z0, z0 + 40],
            color=EMBER,
            lw=2.5,
            zorder=10,
        )
        ax.scatter(
            [(x - gx) / 1000],
            [(y - gy) / 1000],
            [z0 + 40],
            color=EMBER,
            s=26,
            depthshade=False,
            zorder=11,
        )
        ax.plot(
            [(x - gx) / 1000, 0],
            [(y - gy) / 1000, 0],
            [z0 + 40, g_top + 25],
            color="#1B5E20" if clear else EMBER,
            lw=1.6,
            ls="--",
            zorder=10,
        )
        d = np.hypot(x - gx, y - gy) / 1000
        ax.text(
            (x - gx) / 1000,
            (y - gy) / 1000,
            z0 - 120,
            f"sensor {f['properties']['node_id']}\n{d:.1f} km, {'clear' if clear else 'blocked'}",
            fontsize=9,
            ha="center",
            va="top",
            color=INK,
            zorder=12,
            bbox=dict(facecolor="white", edgecolor="none", alpha=0.8, pad=1),
        )
    ax.set_xlabel("east (km)", fontsize=9, labelpad=-2)
    ax.set_ylabel("north (km)", fontsize=9, labelpad=-2)
    ax.set_zlabel("elevation (m)", fontsize=9, labelpad=-2)
    ax.tick_params(labelsize=6, pad=-1)
    ax.set_box_aspect((np.ptp(X) / 1000, np.ptp(Y) / 1000, 1.0))
    ax.view_init(elev=28, azim=-60)
    fig.tight_layout()
    for ext in ("png", "svg"):
        fig.savefig(FIG / f"fig_relief_los.{ext}")
    plt.close(fig)


def trim_png(path: Path, margin: int = 24) -> None:
    """3D axes keep wide white margins even with a tight bounding box: crop them."""
    from PIL import Image, ImageChops

    im = Image.open(path).convert("RGB")
    bbox = ImageChops.difference(im, Image.new("RGB", im.size, "white")).getbbox()
    if bbox:
        l, t, r, b = bbox
        im.crop(
            (
                max(l - margin, 0),
                max(t - margin, 0),
                min(r + margin, im.width),
                min(b + margin, im.height),
            )
        ).save(path)


def main() -> None:
    plt.style.use(str(FIG / "wamidh.mplstyle"))
    node_figure()
    relief_figure()
    for name in ("fig_node_3d", "fig_relief_los"):
        trim_png(FIG / f"{name}.png")
    print("written fig_node_3d and fig_relief_los")


if __name__ == "__main__":
    main()
