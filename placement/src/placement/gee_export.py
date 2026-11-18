"""Earth Engine export tasks for the raster layers (CLAUDE.md §6.1).

Study area (northern Tunisia) at `study_scale_m`:
  terrain   elevation, slope, aspect (SRTM 30 m, ee.Terrain)
  landcover fraction of each WorldCover class per output pixel (10 m -> mean)
  ndvi      Sentinel-2 L2A summer median NDVI, SCL cloud/shadow masked
  climate   ERA5-Land summer means: Tmax (degC), wind speed, u, v; mean annual precipitation

Pilot zone at `pilot_scale_m` (and WorldCover at native 10 m) for viewsheds and spread.

Everything is exported in EPSG:32632 so steps 03+ can use metric distances directly.
"""

from __future__ import annotations

from typing import Any

import ee

from placement.io import WORLDCOVER_CLASSES

# Sentinel-2 Scene Classification values to mask: saturated, shadow, cloud (med/high), cirrus, snow.
S2_SCL_MASK = [1, 3, 8, 9, 10, 11]


def _terrain() -> ee.Image:
    dem = ee.Image("USGS/SRTMGL1_003").select("elevation")
    return ee.Terrain.products(dem).select(["elevation", "slope", "aspect"]).toFloat()


def _landcover_fractions(scale_m: float, crs: str) -> ee.Image:
    lc = ee.ImageCollection("ESA/WorldCover/v200").first().select("Map")
    bands = [
        lc.eq(code).rename(f"lc_{name}").toFloat() for code, name in WORLDCOVER_CLASSES.items()
    ]
    return (
        ee.Image.cat(bands)
        .setDefaultProjection(lc.projection())
        .reduceResolution(reducer=ee.Reducer.mean(), maxPixels=1024)
        .reproject(crs=crs, scale=scale_m)
        .toFloat()
    )


def _ndvi(region: ee.Geometry, g: dict[str, Any]) -> ee.Image:
    y0, y1 = g["ndvi_year_range"]
    m0, m1 = g["ndvi_months"]

    def mask_and_ndvi(img: ee.Image) -> ee.Image:
        scl = img.select("SCL")
        clear = scl.remap(S2_SCL_MASK, [0] * len(S2_SCL_MASK), 1).eq(1)
        return img.normalizedDifference(["B8", "B4"]).rename("ndvi").updateMask(clear)

    col = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(region)
        .filter(ee.Filter.calendarRange(y0, y1, "year"))
        .filter(ee.Filter.calendarRange(m0, m1, "month"))
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", g["s2_max_cloudy_pct"]))
        .map(mask_and_ndvi)
    )
    return col.median().toFloat()


def _climate(season_months: list[int], g: dict[str, Any]) -> ee.Image:
    y0, y1 = g["climate_year_range"]
    era = ee.ImageCollection("ECMWF/ERA5_LAND/DAILY_AGGR").filter(
        ee.Filter.calendarRange(y0, y1, "year")
    )
    summer = era.filter(ee.Filter.calendarRange(min(season_months), max(season_months), "month"))

    tmax_c = summer.select("temperature_2m_max").mean().subtract(273.15).rename("tmax_c")
    u = summer.select("u_component_of_wind_10m").mean().rename("wind_u")
    v = summer.select("v_component_of_wind_10m").mean().rename("wind_v")
    # Mean of daily speeds computed from daily-mean u/v: underestimates gusts; relative use only.
    speed = (
        summer.map(
            lambda img: img.expression(
                "sqrt(u*u + v*v)",
                {
                    "u": img.select("u_component_of_wind_10m"),
                    "v": img.select("v_component_of_wind_10m"),
                },
            ).rename("wind_speed")
        )
        .mean()
        .rename("wind_speed_ms")
    )
    n_years = y1 - y0 + 1
    precip_mm = (
        era.select("total_precipitation_sum").sum().multiply(1000 / n_years).rename("precip_mm_yr")
    )
    return ee.Image.cat([tmax_c, speed, u, v, precip_mm]).toFloat()


def start_exports(cfg: dict[str, Any], project: str) -> list[str]:
    """Start all export tasks and return their descriptions."""
    ee.Initialize(project=project)
    g = cfg["download"]["gee"]
    crs = cfg["crs"]["metric"]
    study = ee.Geometry.Rectangle(cfg["study_area"]["bbox"], proj="EPSG:4326", geodesic=False)
    pilot = ee.Geometry.Rectangle(cfg["pilot_zone"]["bbox"], proj="EPSG:4326", geodesic=False)
    pilot_name = cfg["pilot_zone"]["name"]
    s_scale, p_scale = g["study_scale_m"], g["pilot_scale_m"]

    jobs: list[tuple[str, ee.Image, ee.Geometry, float]] = [
        ("study_terrain", _terrain(), study, s_scale),
        ("study_landcover", _landcover_fractions(s_scale, crs), study, s_scale),
        ("study_ndvi", _ndvi(study, g), study, s_scale),
        # ERA5-Land native ~11 km; export at 1 km so it resamples cleanly onto the grid.
        ("study_climate", _climate(cfg["fires"]["season_months"], g), study, 1000),
        (f"{pilot_name}_terrain", _terrain(), pilot, p_scale),
        (
            f"{pilot_name}_worldcover",
            ee.ImageCollection("ESA/WorldCover/v200").first().select("Map").toUint8(),
            pilot,
            10,
        ),
        (f"{pilot_name}_ndvi", _ndvi(pilot, g), pilot, p_scale),
    ]

    names = []
    for name, image, region, scale in jobs:
        task = ee.batch.Export.image.toDrive(
            image=image.clip(region),
            description=f"wamidh_{name}",
            folder=g["drive_folder"],
            fileNamePrefix=name,
            region=region,
            scale=scale,
            crs=crs,
            maxPixels=int(1e10),
            fileFormat="GeoTIFF",
        )
        task.start()
        names.append(f"wamidh_{name}")
    return names
