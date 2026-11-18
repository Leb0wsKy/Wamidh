from wamidh_sim.world import fires_put_out


def inc(id_: int, status: str, nodes: list[int]) -> dict:  # type: ignore[type-arg]
    return {"id": id_, "status": status, "node_ids": nodes}


def test_a_controlled_or_closed_incident_puts_out_its_fires_once() -> None:
    done: set[int] = set()
    incidents = [inc(1, "ON_SITE", [3]), inc(2, "UNDER_CONTROL", [2, 4]), inc(3, "CLOSED", [5])]

    assert fires_put_out(incidents, done) == [2, 4, 5]
    assert fires_put_out(incidents, done) == []  # remembered


def test_a_false_alarm_also_clears_the_air() -> None:
    assert fires_put_out([inc(7, "FALSE_ALARM", [1])], set()) == [1]


def test_a_rekindle_in_a_new_incident_is_not_put_out_by_the_old_one() -> None:
    done: set[int] = set()
    fires_put_out([inc(1, "CLOSED", [3])], done)

    assert fires_put_out([inc(1, "CLOSED", [3]), inc(2, "ACKNOWLEDGED", [3])], done) == []
