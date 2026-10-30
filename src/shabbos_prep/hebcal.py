"""Thin, polite Hebcal.com client (free, no key, CC BY 4.0)."""
from __future__ import annotations
import datetime as dt
import functools
import httpx

BASE = "https://www.hebcal.com"
UA = {"User-Agent": "shabbos-prep-agent/0.1 (+https://github.com/chanochrosenthal)"}

# A few common community cities -> GeoNames ids (Hebcal accepts geonameid).
CITIES = {
    "lakewood": 5100280, "lakewood nj": 5100280, "brooklyn": 5110302,
    "new york": 5128581, "monsey": 5127315,
    "baltimore": 4347778, "chicago": 4887398,
    "los angeles": 5368361, "miami beach": 4164143, "toronto": 6167865,
    "london": 2643743, "jerusalem": 281184, "bnei brak": 295514,
}


def _geoid(city: str) -> int:
    key = city.strip().lower().replace(",", "")
    for name, gid in CITIES.items():
        if key == name or key.startswith(name):
            return gid
    raise ValueError(f"Unknown city '{city}'. Known: {', '.join(sorted(set(CITIES)))}")


@functools.lru_cache(maxsize=128)
def _get(path: str, params: tuple) -> dict:
    r = httpx.get(f"{BASE}{path}", params=dict(params), headers=UA, timeout=15)
    r.raise_for_status()
    return r.json()


def shabbos_times(city: str, date: str | None = None, candle_minutes: int = 18) -> dict:
    """Candle lighting, havdalah, parsha and any Yom Tov for the week containing `date`."""
    d = dt.date.fromisoformat(date) if date else dt.date.today()
    p = {"cfg": "json", "geonameid": _geoid(city), "M": "on", "b": candle_minutes,
         "gy": d.year, "gm": d.month, "gd": d.day}
    data = _get("/shabbat", tuple(sorted(p.items())))
    out = {"location": data.get("location", {}).get("title"), "items": []}
    for it in data.get("items", []):
        if it["category"] in ("candles", "havdalah", "parashat", "holiday"):
            out["items"].append({"category": it["category"], "title": it["title"], "date": it["date"]})
    out["attribution"] = "Hebcal.com (CC BY 4.0)"
    return out


def zmanim(city: str, date: str | None = None) -> dict:
    """Halachic times (alos, sunrise, sof zman shema, chatzos, plag, sunset, tzeis) for a day."""
    d = date or dt.date.today().isoformat()
    data = _get("/zmanim", (("cfg", "json"), ("date", d), ("geonameid", _geoid(city))))
    keep = ["alotHaShachar", "sunrise", "sofZmanShma", "sofZmanTfilla", "chatzot",
            "minchaGedola", "plagHaMincha", "sunset", "tzeit7083deg"]
    return {"location": data.get("location", {}).get("title"), "date": d,
            "times": {k: data.get("times", {}).get(k) for k in keep},
            "attribution": "Hebcal.com (CC BY 4.0)"}
