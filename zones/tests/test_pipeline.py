import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Point, box

from zones.pipeline import run

UTM = "EPSG:32632"
X0, Y0 = 470_000.0, 4_070_000.0


def _inputs(tmp: Path) -> dict:  # type: ignore[type-arg]
    houses = [box(X0 + 30 * k, Y0, X0 + 30 * k + 10, Y0 + 10) for k in range(8)]
    gpd.GeoDataFrame(geometry=houses, crs=UTM).to_crs("EPSG:4326").to_file(tmp / "buildings.gpkg")
    places = gpd.GeoDataFrame(
        {"name": ["ملولة"], "fclass": ["village"]}, geometry=[Point(X0 + 100, Y0 + 300)], crs=UTM
    )
    places.to_crs("EPSG:4326").to_file(tmp / "places.gpkg")
    with rasterio.open(
        tmp / "pop.tif",
        "w",
        driver="GTiff",
        width=40,
        height=40,
        count=1,
        dtype="float32",
        crs=UTM,
        transform=from_origin(X0 - 1000, Y0 + 1000, 50, 50),
        nodata=-99999,
    ) as r:
        r.write(np.full((40, 40), 2.0, dtype="float32"), 1)
    with rasterio.open(
        tmp / "susc.tif",
        "w",
        driver="GTiff",
        width=40,
        height=40,
        count=2,
        dtype="float32",
        crs=UTM,
        transform=from_origin(X0 - 1000, Y0 + 1000, 50, 50),
        nodata=np.nan,
    ) as r:
        r.write(np.zeros((40, 40), dtype="float32"), 1)
        r.write(np.full((40, 40), 90.0, dtype="float32"), 2)
    lon0, lat0 = gpd.GeoSeries([Point(X0, Y0)], crs=UTM).to_crs("EPSG:4326").iloc[0].coords[0]
    return {
        "bbox": [lon0 - 0.05, lat0 - 0.05, lon0 + 0.05, lat0 + 0.05],
        "inputs": {
            "buildings": str(tmp / "buildings.gpkg"),
            "places": str(tmp / "places.gpkg"),
            "worldpop": str(tmp / "pop.tif"),
            "susceptibility": str(tmp / "susc.tif"),
            "towers": str(tmp / "missing.csv.gz"),
        },
        "outputs": str(tmp / "out"),
        "clusters": {
            "eps_m": 150,
            "min_buildings": 5,
            "buffer_m": 60,
            "simplify_m": 10,
            "min_people_per_cell": 1000,
        },
        "names": {"radius_m": 2000, "place_classes": ["village"]},
        "risk": {"ring_m": 1000, "high": 80, "medium": 60},
        "towers": {"pad_m": 5000, "min_range_m": 300, "max_range_m": 10000},
    }


def test_pipeline_without_towers(tmp_path: Path) -> None:
    cfg = _inputs(tmp_path)

    summary = run(cfg, repo=Path("/"))

    zones = json.loads((tmp_path / "out" / "zones.geojson").read_text(encoding="utf-8"))
    (zone,) = zones["features"]
    props = zone["properties"]
    assert props["id"] == 1 and props["name"] == "ملولة" and props["building_count"] == 8
    assert props["population"] > 0 and props["risk_level"] == "high"
    assert props["tower_ids"] == []
    assert summary["towers"] == "not available"
    towers = json.loads((tmp_path / "out" / "towers.geojson").read_text(encoding="utf-8"))
    assert towers["features"] == []
