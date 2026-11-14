"""Wekelijks hardlooprapport uit Strava.

Haalt je hardloopactiviteiten op via de Strava API, berekent het weekrapport
(afstand, tempo, hartslag, doelen, trend, voorspelde 5/10 km), stuurt een
pushmelding via ntfy en schrijft docs/data/report.json voor de webversie.

Omgevingsvariabelen (GitHub Secrets):
  STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET  - van je Strava API-app
  STRAVA_REFRESH_TOKEN                    - eerste refresh token (scripts/get_token.py)
  TOKEN_KEY                               - willekeurige lange tekst; versleutelt de
                                            vernieuwde refresh token in state/
  NTFY_TOPIC                              - je (geheime) ntfy-topic
Optioneel:
  NTFY_SERVER        (standaard https://ntfy.sh)
  DOEL_KM_WEEK       (standaard 5)
  PUBLISH_HEARTRATE  ("true" om hartslag ook in de openbare webversie te zetten)
  PAGES_URL          (link die de melding opent)
  FORCE_RUN          ("true" om de tijdcheck over te slaan)
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

TZ = ZoneInfo("Europe/Amsterdam")
ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "state" / "strava_token.enc"
REPORT_FILE = ROOT / "docs" / "data" / "report.json"
API = "https://www.strava.com/api/v3"
RUN_TYPES = {"Run", "TrailRun", "VirtualRun"}
MIJL_M = 1609.34


# ---------- opmaak ----------

def fmt_tijd(sec: float | None) -> str | None:
    if sec is None:
        return None
    s = int(round(sec))
    h, rest = divmod(s, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_km(v: float) -> str:
    return f"{v:.1f}".replace(".", ",")


def riegel(t1: float, d1: float, d2: float) -> float:
    """Riegel (1981): T2 = T1 * (D2/D1)^1.06."""
    return t1 * (d2 / d1) ** 1.06


# ---------- token-opslag ----------

def _fernet():
    from cryptography.fernet import Fernet

    key = os.environ.get("TOKEN_KEY")
    if not key:
        return None
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest()))


def laad_refresh_token() -> str:
    f = _fernet()
    if f and STATE_FILE.exists():
        try:
            return f.decrypt(STATE_FILE.read_bytes()).decode()
        except Exception:
            print("Waarschuwing: opgeslagen token niet te ontsleutelen, gebruik secret.", file=sys.stderr)
    tok = os.environ.get("STRAVA_REFRESH_TOKEN")
    if not tok:
        sys.exit("STRAVA_REFRESH_TOKEN ontbreekt.")
    return tok


def bewaar_refresh_token(tok: str) -> None:
    f = _fernet()
    if not f:
        print("Waarschuwing: TOKEN_KEY ontbreekt; vernieuwde refresh token wordt niet bewaard.", file=sys.stderr)
        return
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_bytes(f.encrypt(tok.encode()))


def access_token() -> str:
    r = requests.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": os.environ["STRAVA_CLIENT_ID"],
            "client_secret": os.environ["STRAVA_CLIENT_SECRET"],
            "grant_type": "refresh_token",
            "refresh_token": laad_refresh_token(),
        },
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    # Strava kan een nieuwe refresh token geven; de oude werkt dan niet meer.
    bewaar_refresh_token(data["refresh_token"])
    return data["access_token"]


# ---------- Strava ophalen ----------

def haal_lopen(token: str, vanaf: date) -> list[dict]:
    h = {"Authorization": f"Bearer {token}"}
    after = int(datetime(vanaf.year, vanaf.month, vanaf.day, tzinfo=TZ).timestamp())
    acts, page = [], 1
    while True:
        r = requests.get(f"{API}/athlete/activities", headers=h,
                         params={"after": after, "per_page": 100, "page": page}, timeout=30)
        r.raise_for_status()
        batch = r.json()
        acts += batch
        if len(batch) < 100:
            break
        page += 1
    lopen = []
    for a in acts:
        if a.get("sport_type", a.get("type")) not in RUN_TYPES or not a.get("distance"):
            continue
        d = requests.get(f"{API}/activities/{a['id']}", headers=h, timeout=30)
        d.raise_for_status()
        det = d.json()
        lopen.append(normaliseer(det))
    return lopen


def normaliseer(a: dict) -> dict:
    """Strava-activiteit -> compacte rij (afstand in meters, tijden in seconden)."""
    be = {b.get("name"): b.get("elapsed_time") for b in a.get("best_efforts") or []}
    return {
        "id": str(a["id"]),
        "datum": a["start_date_local"][:10],
        "afstand_m": a["distance"],
        "beweegtijd_s": a["moving_time"],
        "totaaltijd_s": a["elapsed_time"],
        "hartslag": round(a["average_heartrate"]) if a.get("has_heartrate") and a.get("average_heartrate") else None,
        "snelste_1k_s": be.get("1k"),
        "snelste_mijl_s": be.get("1 mile"),
    }


# ---------- rapport ----------

def maandag(d: date) -> date:
    return d - timedelta(days=d.weekday())


def bouw_rapport(lopen: list[dict], vandaag: date, doel_km: float, met_hartslag: bool) -> dict:
    deze_ma = maandag(vandaag)
    weken = []
    for i in range(11, -1, -1):
        start = deze_ma - timedelta(weeks=i)
        rij = [l for l in lopen if maandag(date.fromisoformat(l["datum"])) == start]
        weken.append({"week_start": start.isoformat(),
                      "km": round(sum(l["afstand_m"] for l in rij) / 1000, 2),
                      "lopen": len(rij)})
    deze, vorige = weken[-1], weken[-2]
    vol4, vol8 = weken[-5:-1], weken[-9:-1]
    reeks = 0
    for w in reversed(weken if deze["lopen"] else weken[:-1]):
        if not w["lopen"]:
            break
        reeks += 1

    def rij_uit(l: dict) -> dict:
        km = l["afstand_m"] / 1000
        r = {
            "id": l["id"], "datum": l["datum"], "afstand_km": round(km, 2),
            "beweegtijd": fmt_tijd(l["beweegtijd_s"]),
            "tempo": fmt_tijd(l["beweegtijd_s"] / km), "tempo_s": round(l["beweegtijd_s"] / km),
            "tempo_incl_stops": fmt_tijd(l["totaaltijd_s"] / km), "tempo_incl_s": round(l["totaaltijd_s"] / km),
            "snelste_1k": fmt_tijd(l["snelste_1k_s"]),
        }
        if met_hartslag:
            r["hartslag"] = l["hartslag"]
        return r

    alle = sorted(lopen, key=lambda l: l["datum"])
    rijen = [rij_uit(l) for l in alle]
    deze_rijen = [r for r in rijen if maandag(date.fromisoformat(r["datum"])) == deze_ma]
    eerdere = [r for r in rijen if maandag(date.fromisoformat(r["datum"])) < deze_ma][-3:]

    trend = None
    if deze_rijen and eerdere:
        nu = sum(r["tempo_s"] for r in deze_rijen) / len(deze_rijen)
        toen = sum(r["tempo_s"] for r in eerdere) / len(eerdere)
        trend = round(nu - toen)  # negatief = sneller

    mijlen = [l["snelste_mijl_s"] for l in lopen if l.get("snelste_mijl_s")]
    beste_mijl = min(mijlen) if mijlen else None
    voorspelling = None
    if beste_mijl:
        voorspelling = {
            "basis": f"snelste mijl laatste 12 weken: {fmt_tijd(beste_mijl)}",
            "5k": fmt_tijd(riegel(beste_mijl, MIJL_M, 5000)),
            "10k": fmt_tijd(riegel(beste_mijl, MIJL_M, 10000)),
        }

    laatste = rijen[-1] if rijen else None
    if laatste:
        volgende = round(min(laatste["afstand_km"] + 0.5, laatste["afstand_km"] * 1.1), 1)
        if (vandaag - date.fromisoformat(laatste["datum"])).days > 14:
            volgende = round(laatste["afstand_km"], 1)
        advies = f"Volgend weekend: {fmt_km(volgende)} km rustig en zonder stoppen."
    else:
        advies = "Volgend weekend: begin met 3 km rustig."

    return {
        "gegenereerd": datetime.now(TZ).isoformat(timespec="minutes"),
        "week_start": deze_ma.isoformat(),
        "doel_km_week": doel_km,
        "deze_week": {"km": deze["km"], "lopen": deze["lopen"], "runs": deze_rijen},
        "vorige_week_km": vorige["km"],
        "gem_km_4w": round(sum(w["km"] for w in vol4) / 4, 1),
        "weken_met_loop_8w": sum(1 for w in vol8 if w["lopen"]),
        "reeks_weken": reeks,
        "doel_afstand_gehaald": deze["km"] >= doel_km,
        "doel_regelmaat_gehaald": deze["lopen"] >= 1,
        "tempo_trend_s": trend,
        "voorspelling": voorspelling,
        "advies": advies,
        "weken": weken,
        "lopen": rijen,
    }


def bericht(rap: dict) -> tuple[str, str]:
    d = rap["deze_week"]
    doel = rap["doel_km_week"]
    if d["lopen"]:
        titel = f"Hardlopen: {fmt_km(d['km'])} km deze week"
    else:
        titel = "Hardlopen: geen loop deze week"
    regels = []
    for r in d["runs"]:
        hr = f", hartslag {r['hartslag']}" if r.get("hartslag") else ""
        regels.append(f"• {r['datum']}: {fmt_km(r['afstand_km'])} km, {r['tempo']}/km "
                      f"(incl. stops {r['tempo_incl_stops']}/km){hr}")
    regels.append(f"Doel {fmt_km(doel)} km: {'gehaald' if rap['doel_afstand_gehaald'] else 'niet gehaald'} · "
                  f"regelmaat: {'gehaald' if rap['doel_regelmaat_gehaald'] else 'niet gehaald'}")
    regels.append(f"Vorige week {fmt_km(rap['vorige_week_km'])} km · gem. 4 weken {fmt_km(rap['gem_km_4w'])} km · "
                  f"{rap['weken_met_loop_8w']}/8 weken gelopen · reeks {rap['reeks_weken']}")
    if rap["tempo_trend_s"] is not None:
        t = rap["tempo_trend_s"]
        regels.append(f"Tempo: {abs(t)} s/km {'sneller' if t < 0 else 'langzamer'} dan vorige 3 lopen"
                      if t else "Tempo: gelijk aan vorige 3 lopen")
    if rap["voorspelling"]:
        v = rap["voorspelling"]
        regels.append(f"Voorspelling (Riegel): 5 km {v['5k']}, 10 km {v['10k']}")
    regels.append(rap["advies"])
    return titel, "\n".join(regels)


def stuur_ntfy(titel: str, tekst: str) -> None:
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        print("NTFY_TOPIC ontbreekt; geen melding verstuurd.", file=sys.stderr)
        return
    payload = {"topic": topic, "title": titel, "message": tekst, "tags": ["runner"]}
    if os.environ.get("PAGES_URL"):
        payload["click"] = os.environ["PAGES_URL"]
    r = requests.post(os.environ.get("NTFY_SERVER", "https://ntfy.sh"), json=payload, timeout=30)
    r.raise_for_status()


def main() -> None:
    nu = datetime.now(TZ)
    # De workflow draait op twee UTC-tijden; alleen de run om 20:xx Nederlandse tijd telt.
    if os.environ.get("GITHUB_EVENT_NAME") == "schedule" and os.environ.get("FORCE_RUN") != "true" and nu.hour != 20:
        print(f"Overgeslagen: {nu:%H:%M} Europe/Amsterdam is niet 20:xx.")
        return
    vandaag = nu.date()
    token = access_token()
    lopen = haal_lopen(token, maandag(vandaag) - timedelta(weeks=11))
    rap = bouw_rapport(lopen, vandaag,
                       float(os.environ.get("DOEL_KM_WEEK") or 5),
                       os.environ.get("PUBLISH_HEARTRATE", "").lower() == "true")
    titel, tekst = bericht(bouw_rapport(lopen, vandaag, rap["doel_km_week"], True))
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(json.dumps(rap, ensure_ascii=False, indent=2), encoding="utf-8")
    print(titel)
    print(tekst)
    stuur_ntfy(titel, tekst)


if __name__ == "__main__":
    main()
