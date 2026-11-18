import gzip
from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Point, box

from zones.clusters import cluster_buildings
from zones.names import name_zones
from zones.population import zone_population
from zones.risk import zone_risk
from zones.towers import TowerFormatError, link_towers, parse_towers

UTM = "EPSG:32632"
X0, Y0 = 470_000.0, 4_070_000.0  # a point in Kroumirie, metres


def houses(cx: float, cy: float, n: int, spacing: float = 30.0) -> list:
    """n small square houses on a line, `spacing` m apart."""
    return [box(cx + k * spacing, cy, cx + k * spacing + 10, cy + 10) for k in range(n)]


def test_clusters_two_groups_drop_isolated() -> None:
    footprints = gpd.GeoDataFrame(
        geometry=houses(X0, Y0, 8) + houses(X0 + 3000, Y0, 6) + houses(X0 + 1500, Y0 + 2000, 1),
        crs=UTM,
    )

    zones = cluster_buildings(footprints, eps_m=150, min_buildings=5, buffer_m=60, simplify_m=10)

    assert sorted(zones["building_count"]) == [6, 8]  # the lone house is not a zone
    assert zones.crs == UTM
    assert all(
        z.contains(Point(X0 + 5, Y0 + 5)) for z in zones.geometry if z.distance(Point(X0, Y0)) == 0
    )


def test_name_nearest_place_and_douar_fallback() -> None:
    zones = gpd.GeoDataFrame(
        geometry=[box(X0, Y0, X0 + 200, Y0 + 200), box(X0 + 9000, Y0, X0 + 9200, Y0 + 200)], crs=UTM
    )
    places = gpd.GeoDataFrame(
        {"name": ["ملولة", "عين دراهم"], "fclass": ["village", "town"]},
        geometry=[Point(X0 + 500, Y0), Point(X0 + 15000, Y0)],
        crs=UTM,
    )

    named = name_zones(zones, places, radius_m=2000)

    assert named[0] == {"name": "ملولة", "near": "ملولة"}
    assert named[1] == {"name": None, "near": "عين دراهم"}  # too far: a douar near the town


def test_population_sum_inside_outline(tmp_path: Path) -> None:
    # 10 x 10 grid of 100 m pixels with 3 people each, in UTM for simplicity.
    raster = tmp_path / "pop.tif"
    with rasterio.open(
        raster,
        "w",
        driver="GTiff",
        width=10,
        height=10,
        count=1,
        dtype="float32",
        crs=UTM,
        transform=from_origin(X0, Y0 + 1000, 100, 100),
        nodata=-99999,
    ) as r:
        data = np.full((10, 10), 3.0, dtype="float32")
        data[0, 0] = -99999  # nodata must not count
        r.write(data, 1)
    zones = gpd.GeoDataFrame(
        geometry=[box(X0, Y0 + 800, X0 + 300, Y0 + 1000)], crs=UTM
    )  # 3 x 2 pixels

    assert zone_population(zones, raster) == [20]  # 5 valid pixels x 3 = 15, rounded to 10


def test_risk_level_from_toy_raster(tmp_path: Path) -> None:
    raster = tmp_path / "susc.tif"
    with rasterio.open(
        raster,
        "w",
        driver="GTiff",
        width=20,
        height=20,
        count=2,
        dtype="float32",
        crs=UTM,
        transform=from_origin(X0, Y0 + 2000, 100, 100),
        nodata=np.nan,
    ) as r:
        pct = np.full((20, 20), np.nan, dtype="float32")
        pct[0:3, 0:3] = 85.0  # forest close to zone A (top-left)
        pct[17:20, 17:20] = 40.0  # forest close to zone B (bottom-right)
        r.write(np.zeros((20, 20), dtype="float32"), 1)
        r.write(pct, 2)
    zones = gpd.GeoDataFrame(
        geometry=[
            box(X0 + 400, Y0 + 1400, X0 + 500, Y0 + 1500),  # A: within 1 km of the 85s
            box(X0 + 1500, Y0 + 100, X0 + 1600, Y0 + 200),  # B: near the 40s
            box(X0 + 900, Y0 + 900, X0 + 950, Y0 + 950),
        ],  # C: no forest within 300 m
        crs=UTM,
    )

    levels = zone_risk(zones, raster, ring_m=1000, high=80, medium=60)
    assert levels[0] == ("high", 85.0)
    assert levels[1] == ("low", 40.0)
    assert zone_risk(zones.iloc[[2]], raster, ring_m=300, high=80, medium=60) == [("none", None)]


ROWS = [
    "GSM,605,2,101,1001,0,8.70,36.80,1500,12,1,1500000000,1600000000,0",
    "LTE,605,3,202,2002,0,8.72,36.81,800,5,1,1500000000,1600000000,0",
    "UMTS,605,1,303,3003,0,10.10,36.80,2000,9,1,1500000000,1600000000,0",  # Tunis: outside
]
HEADER = (
    "radio,mcc,net,area,cell,unit,lon,lat,range,samples,changeable,created,updated,averageSignal"
)


@pytest.mark.parametrize("with_header", [True, False])
def test_parse_towers_with_and_without_header(tmp_path: Path, with_header: bool) -> None:
    path = tmp_path / "605.csv.gz"
    with gzip.open(path, "wt") as f:
        f.write("\n".join(([HEADER] if with_header else []) + ROWS) + "\n")

    towers = parse_towers(path, bbox=(8.6, 36.7, 8.9, 36.9), pad_m=5000)

    assert list(towers["id"]) == ["605-2-101-1001", "605-3-202-2002"]
    assert list(towers["radio"]) == ["GSM", "LTE"]
    assert list(towers["range_m"]) == [1500, 800]


def test_parse_towers_bad_format_fails_clearly(tmp_path: Path) -> None:
    path = tmp_path / "605.csv.gz"
    with gzip.open(path, "wt") as f:
        f.write("this is not,a tower file\n1,2\n")

    with pytest.raises(TowerFormatError, match="OpenCelliD"):
        parse_towers(path, bbox=(8.6, 36.7, 8.9, 36.9), pad_m=5000)


def test_zone_towers_intersection_then_nearest() -> None:
    zones = gpd.GeoDataFrame(
        geometry=[box(X0, Y0, X0 + 100, Y0 + 100), box(X0 + 20000, Y0, X0 + 20100, Y0 + 100)],
        crs=UTM,
    )
    towers = gpd.GeoDataFrame(
        {"id": ["near-a", "big", "far"], "range_m": [500, 3000, 400]},
        geometry=[Point(X0 + 300, Y0), Point(X0 + 2500, Y0), Point(X0 + 26000, Y0)],
        crs=UTM,
    )

    links = link_towers(zones, towers, min_range_m=300, max_range_m=10_000)

    assert links[0] == ["big", "near-a"]  # both circles reach zone A
    assert links[1] == ["far"]  # nothing reaches B: the nearest tower serves it


def test_settled_pixels_count_where_osm_has_no_buildings() -> None:
    # A village OSM has not mapped: only WorldPop cells (100 m apart) show it.
    pixels = [Point(X0 + 100 * i, Y0 + 100 * j) for i in range(3) for j in range(2)]
    mapped = houses(X0 + 5000, Y0, 6)
    elements = gpd.GeoDataFrame(
        {"kind": ["pixel"] * len(pixels) + ["building"] * len(mapped)},
        geometry=pixels + mapped,
        crs=UTM,
    )

    zones = cluster_buildings(elements, eps_m=150, min_buildings=5, buffer_m=60, simplify_m=10)

    assert len(zones) == 2  # the unmapped village is a zone too
    assert sorted(zones["building_count"]) == [0, 6]  # only OSM footprints count as buildings
