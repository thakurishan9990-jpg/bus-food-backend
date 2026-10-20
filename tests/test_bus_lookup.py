from datetime import datetime

import pytest

from app.models.dhaba import DhabaStatus
from app.models.route import Route
from app.models.stop import Stop
from app.services.bus_service import BUS_NOT_FOUND, IST


def _hm(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(IST).strftime("%H:%M")


# ---- bus lookup ----

@pytest.mark.parametrize("typed", ["uk07pa1187", "UK07 PA 1187", "PA 1187", "  uk07 pa  1187 "])
def test_bus_number_variants_find_the_same_bus(seeded_client, typed):
    resp = seeded_client.get(f"/buses/{typed}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["bus"]["bus_number"] == "UK07 PA 1187"
    assert body["bus"]["bus_number_key"] == "UK07PA1187"
    assert body["route"]["code"] == "DL-234"


def test_unknown_bus_returns_404_with_the_ticket_hint(seeded_client):
    resp = seeded_client.get("/buses/XX99")

    assert resp.status_code == 404
    assert resp.json() == {"detail": BUS_NOT_FOUND}
    assert BUS_NOT_FOUND == (
        "No bus found with that number. Check the number on your ticket, for example UK07 PA 1187."
    )


def test_partial_number_matching_several_buses_is_not_guessed(seeded_client):
    resp = seeded_client.get("/buses/UK07")  # many buses share this prefix

    assert resp.status_code == 404
    assert "More than one bus" in resp.json()["detail"]


def test_route_buses_are_sorted_by_departure_with_delay(seeded_client):
    buses = seeded_client.get("/routes/DL-234/buses").json()

    assert [b["departs"] for b in buses] == sorted(b["departs"] for b in buses)
    uk07 = next(b for b in buses if b["bus_number"] == "UK07 PA 1187")
    assert (uk07["departs"], uk07["delay_minutes"]) == ("08:00:00", 15)


def test_routes_list_counts(seeded_client):
    routes = {r["code"]: r for r in seeded_client.get("/routes").json()}

    assert len(routes) == 8
    assert sum(r["bus_count"] for r in routes.values()) == 32
    assert sum(r["stop_count"] for r in routes.values()) == 39
    assert sum(r["dhaba_count"] for r in routes.values()) == 284


# ---- arrival and cut-off maths ----

def test_meerut_arrival_and_cutoff_for_uk07_pa_1187(seeded_client):
    """Departs 08:00, running 15 min late; Meerut is 159 min out; slowest kitchen there takes 18 min."""
    stops = seeded_client.get("/buses/UK07 PA 1187/stops").json()["stops"]
    meerut = stops[0]

    assert meerut["name"] == "Meerut"
    assert _hm(meerut["scheduled"]) == "10:39"
    assert _hm(meerut["expected_arrival"]) == "10:54"
    assert _hm(meerut["order_cutoff"]) == "10:26"  # 10:54 - 18 min prep - 10 min buffer


def test_cutoff_uses_the_slowest_live_kitchen(seeded_client, seeded_session):
    # Block Meerut's 18-minute kitchen(s); the cut-off moves to the next slowest.
    meerut = seeded_session.query(Stop).join(Stop.route).filter(Route.code == "DL-234", Stop.sequence_order == 1).one()
    meerut_dhabas = meerut.dhabas
    slowest = max(d.avg_prep_time_minutes for d in meerut_dhabas)
    for d in meerut_dhabas:
        if d.avg_prep_time_minutes == slowest:
            d.status = DhabaStatus.BLOCKED
    seeded_session.commit()
    next_slowest = max(d.avg_prep_time_minutes for d in meerut_dhabas if d.status == DhabaStatus.ACTIVE)

    timing = seeded_client.get("/buses/UK07 PA 1187/stops").json()["stops"][0]
    arrival = datetime.fromisoformat(timing["expected_arrival"])
    cutoff = datetime.fromisoformat(timing["order_cutoff"])
    assert (arrival - cutoff).total_seconds() / 60 == next_slowest + 10
