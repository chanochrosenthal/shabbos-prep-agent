import json, sys, pathlib
from types import SimpleNamespace as NS
sys.path.insert(0, str(pathlib.Path(__file__).parents[1] / "src"))
from shabbos_prep import agent, ics


class FakeClient:
    """Scripted stand-in for the Token Factory client: first a tool call, then a JSON plan."""
    def __init__(self):
        self.calls = 0
        self.chat = NS(completions=NS(create=self.create))

    def create(self, model, messages, **kw):
        self.calls += 1
        if self.calls == 1:
            tc = NS(id="t1", function=NS(name="get_shabbos_times",
                                          arguments=json.dumps({"city": "Lakewood", "date": "2026-10-30"})),
                    model_dump=lambda: {"id": "t1", "type": "function",
                                        "function": {"name": "get_shabbos_times", "arguments": "{}"}})
            return NS(choices=[NS(message=NS(content="", tool_calls=[tc]))])
        tool_msg = [m for m in messages if m["role"] == "tool"][0]
        times = json.loads(tool_msg["content"])
        candles = [i for i in times["items"] if i["category"] == "candles"][0]["date"]
        plan = {"location": times["location"], "candle_lighting": candles, "havdalah": None,
                "parsha": None, "warnings": [],
                "tasks": [{"start": "2026-10-30T15:00:00-04:00", "end": "2026-10-30T15:45:00-04:00",
                           "title": "Kugel in oven", "who": "Chanoch", "note": ""}]}
        return NS(choices=[NS(message=NS(content="```json\n" + json.dumps(plan) + "\n```", tool_calls=None))])


def test_plan_uses_real_candle_time(monkeypatch):
    monkeypatch.setattr(agent.hebcal, "shabbos_times", lambda **k: {
        "location": "Lakewood, New Jersey, USA",
        "items": [{"category": "candles", "title": "Candle lighting: 5:38pm",
                   "date": "2026-10-30T17:38:00-04:00"}]})
    agent.TOOL_IMPLS["get_shabbos_times"] = agent.hebcal.shabbos_times
    trace = []
    p = agent.plan("plan my friday in lakewood", client=FakeClient(), trace=trace)
    assert p["candle_lighting"] == "2026-10-30T17:38:00-04:00"
    assert trace[0]["tool"] == "get_shabbos_times"


def test_ics_export():
    out = ics.plan_to_ics({"tasks": [{"start": "2026-10-30T15:00:00-04:00",
                                      "end": "2026-10-30T15:45:00-04:00", "title": "Kugel"}]})
    assert "DTSTART:20261030T190000Z" in out and out.count("BEGIN:VEVENT") == 1


def test_tool_error_is_returned_to_model(monkeypatch):
    def boom(**k): raise ValueError("Unknown city")
    agent.TOOL_IMPLS["get_shabbos_times"] = boom
    c = FakeClient()
    try:
        agent.plan("x", client=c)
    except Exception:
        pass
    assert c.calls >= 1


def test_date_context_points_to_coming_friday():
    import datetime as dt
    from shabbos_prep.agent import _date_context
    assert "2026-10-30" in _date_context(dt.date(2026, 10, 29))   # Thu -> next day
    assert "2026-10-30" in _date_context(dt.date(2026, 10, 30))   # Fri -> same day
    assert "2026-11-06" in _date_context(dt.date(2026, 10, 31))   # Sat -> next week


def test_ground_overrides_model_times_and_warns():
    from shabbos_prep.agent import _ground
    trace = [{"tool": "get_shabbos_times", "args": {}, "result": {
        "location": "Lakewood, New Jersey, USA",
        "items": [{"category": "candles", "title": "Candle lighting: 5:38pm",
                   "date": "2026-10-30T17:38:00-04:00"},
                  {"category": "parashat", "title": "Parashat Lech-Lecha", "date": "2026-10-31"}]}}]
    p = {"candle_lighting": "2026-10-30T18:00:00-04:00", "tasks": [
        {"start": "2026-10-30T17:00:00-04:00", "end": "2026-10-30T17:30:00-04:00", "title": "Urn"},
        {"start": "2025-08-29T13:00:00-04:00", "end": "2025-08-29T13:30:00-04:00", "title": "Soup"}]}
    out = _ground(p, trace)
    assert out["candle_lighting"] == "2026-10-30T17:38:00-04:00"
    assert out["parsha"] == "Lech-Lecha"
    assert any("Urn" in w for w in out["warnings"]) and any("Soup" in w for w in out["warnings"])
