from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

from wamidh_sim.camera import CameraModel, Vision, camera_from_config
from wamidh_sim.classifier import fire_probability
from wamidh_sim.sensors import Readings

TUNIS = ZoneInfo("Africa/Tunis")
DAY = datetime(2026, 7, 20, 14, 0, tzinfo=UTC)  # 15:00 in Tunis
NIGHT = datetime(2026, 7, 20, 1, 0, tzinfo=UTC)  # 02:00 in Tunis


def camera() -> CameraModel:
    return CameraModel(seed=1, daylight=(time(6, 30), time(19, 30)), tz=TUNIS)


def test_by_day_it_sees_smoke_but_not_clean_air() -> None:
    cam = camera()
    assert cam.look(DAY, smoke=0.0, flame=False).prob < 0.1
    seen = cam.look(DAY, smoke=0.6, flame=False)
    assert seen.prob > 0.8 and seen.night is False


def test_at_night_smoke_alone_is_invisible_but_a_nearby_fire_is_seen() -> None:
    cam = camera()
    smoke_only = cam.look(NIGHT, smoke=0.5, flame=False)
    assert smoke_only.prob < 0.1 and smoke_only.night is True
    assert cam.look(NIGHT, smoke=0.9, flame=False).prob > 0.8
    assert cam.look(NIGHT, smoke=0.2, flame=True).prob > 0.8


def test_daylight_uses_tunis_time_not_utc() -> None:
    cam = camera()
    assert cam.is_day(datetime(2026, 7, 20, 5, 45, tzinfo=UTC))  # 06:45 in Tunis
    assert not cam.is_day(datetime(2026, 7, 20, 18, 45, tzinfo=UTC))  # 19:45 in Tunis


def test_camera_from_config() -> None:
    cam = camera_from_config(
        {"timezone": "Africa/Tunis", "daylight_local": ["06:30", "19:30"]}, seed=3
    )
    assert cam.is_day(DAY) and not cam.is_day(NIGHT)


def test_visible_fire_raises_the_fire_probability_and_its_absence_by_day_lowers_it() -> None:
    r = Readings(gas_ratio=0.62, temp_c=36.0, rh_pct=30.0, flame=False, battery_v=4.0)
    alone = fire_probability(r)

    assert fire_probability(r, Vision(prob=0.95, night=False)) > alone
    assert fire_probability(r, Vision(prob=0.02, night=False)) < alone


def test_at_night_seeing_nothing_does_not_argue_against_a_fire() -> None:
    # Smoke is invisible at night: an empty night image is not evidence of "no fire".
    r = Readings(gas_ratio=0.62, temp_c=30.0, rh_pct=40.0, flame=False, battery_v=3.8)

    assert fire_probability(r, Vision(prob=0.02, night=True)) == fire_probability(r)
