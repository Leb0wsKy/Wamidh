import numpy as np
import pandas as pd

from placement.fires import cluster_events, filter_detections, ignitions, normalise

FIRES_CFG = {
    "season_months": [5, 6, 7, 8, 9, 10],
    "viirs_min_confidence": ["n", "h"],
    "modis_min_confidence": 30,
    "min_frp_mw": 2.0,
}


def _raw(**overrides: list) -> pd.DataFrame:  # type: ignore[type-arg]
    base = {
        "latitude": [36.8],
        "longitude": [8.7],
        "acq_date": ["2020-07-15"],
        "acq_time": [130],
        "confidence": ["n"],
        "frp": [5.0],
        "daynight": ["D"],
        "type": [0],
    }
    base.update(overrides)
    n = max(len(v) for v in base.values())
    return pd.DataFrame({k: v * n if len(v) == 1 else v for k, v in base.items()})


def test_normalise_builds_utc_timestamp_from_hhmm() -> None:
    df = normalise(_raw(acq_time=[130, 1405]), source="VIIRS")

    assert df["time"].tolist() == [
        pd.Timestamp("2020-07-15 01:30", tz="UTC"),
        pd.Timestamp("2020-07-15 14:05", tz="UTC"),
    ]
    assert (df["source"] == "VIIRS").all()


def test_normalise_stores_confidence_as_text_so_sources_can_be_mixed() -> None:
    modis = normalise(_raw(confidence=[85]), source="MODIS")

    assert modis["confidence"].tolist() == ["85"]


def test_filter_keeps_confident_vegetation_fires_in_season() -> None:
    viirs = normalise(
        _raw(
            confidence=["l", "n", "h", "h", "h", "h"],
            frp=[5.0, 5.0, 5.0, 1.0, 5.0, 5.0],
            acq_date=["2020-07-15"] * 4 + ["2020-04-30", "2020-07-15"],
            type=[0, 0, 0, 0, 0, 2],
        ),
        source="VIIRS",
    )
    modis = normalise(_raw(confidence=[29, 30, 95]), source="MODIS")

    kept = filter_detections(pd.concat([viirs, modis], ignore_index=True), FIRES_CFG)

    # VIIRS: only 'n' and the first 'h' survive (low FRP, April, static source dropped).
    # MODIS: 30 and 95 survive.
    assert kept["source"].tolist() == ["VIIRS", "VIIRS", "MODIS", "MODIS"]


def test_cluster_links_detections_close_in_space_and_time() -> None:
    x = np.array([0.0, 800.0, 1600.0, 0.0, 5000.0])
    y = np.zeros(5)
    t = np.array([0.0, 1.0, 2.0, 10.0, 0.0])  # days

    labels = cluster_events(x, y, t, eps_m=1000, eps_days=3)

    # 0-1-2 chain into one fire; 3 is the same place 10 days later; 4 is 5 km away.
    assert labels[0] == labels[1] == labels[2]
    assert len({labels[0], labels[3], labels[4]}) == 3


def test_ignitions_keep_earliest_detection_of_each_event() -> None:
    df = pd.DataFrame(
        {
            "event_id": [0, 0, 0, 1],
            "time": pd.to_datetime(
                ["2020-07-02", "2020-07-01", "2020-07-01", "2020-08-01"], utc=True
            ),
            "frp": [50.0, 3.0, 9.0, 4.0],
            "x": [1.0, 2.0, 3.0, 4.0],
        }
    )

    ign = ignitions(df)

    # Event 0: two detections on the first day; the stronger one is the ignition proxy.
    assert ign.set_index("event_id")["x"].to_dict() == {0: 3.0, 1: 4.0}
    assert ign.set_index("event_id")["n_detections"].to_dict() == {0: 3, 1: 1}
