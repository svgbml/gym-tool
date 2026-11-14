"""Test de rapportberekening met echte loopdata (Strava, okt-nov 2026)."""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from weekrapport import bericht, bouw_rapport, fmt_tijd, riegel  # noqa: E402

LOPEN = [
    {"id": "20445334499", "datum": "2026-10-04", "afstand_m": 3594.1, "beweegtijd_s": 1116,
     "totaaltijd_s": 1243, "hartslag": None, "snelste_1k_s": 291, "snelste_mijl_s": 472},
    {"id": "20817075972", "datum": "2026-11-01", "afstand_m": 4122.1, "beweegtijd_s": 1309,
     "totaaltijd_s": 1584, "hartslag": None, "snelste_1k_s": 290, "snelste_mijl_s": 487},
    {"id": "20894843762", "datum": "2026-11-07", "afstand_m": 3503.9, "beweegtijd_s": 1074,
     "totaaltijd_s": 1692, "hartslag": 141, "snelste_1k_s": 365, "snelste_mijl_s": 649},
]


def test_riegel():
    assert fmt_tijd(riegel(472, 1609.34, 5000)) == "26:10"


def test_week_zonder_loop():
    r = bouw_rapport(LOPEN, date(2026, 11, 14), 5, False)
    assert r["deze_week"]["lopen"] == 0
    assert r["vorige_week_km"] == 3.5
    assert r["gem_km_4w"] == 1.9
    assert r["weken_met_loop_8w"] == 3
    assert r["reeks_weken"] == 2
    assert "hartslag" not in r["lopen"][-1]
    assert r["voorspelling"]["5k"] == "26:10"


def test_week_met_loop():
    r = bouw_rapport(LOPEN, date(2026, 11, 8), 5, True)
    assert r["deze_week"]["km"] == 3.5
    assert r["doel_regelmaat_gehaald"] and not r["doel_afstand_gehaald"]
    assert r["deze_week"]["runs"][0]["hartslag"] == 141
    assert r["deze_week"]["runs"][0]["tempo_incl_stops"] == "8:03"
    titel, tekst = bericht(r)
    assert "3,5 km" in titel and "hartslag 141" in tekst
