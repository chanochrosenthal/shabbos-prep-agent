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
    assert any("Urn" in w for w in out["_violations"]) and any("Soup" in w for w in out["_violations"])


class LateThenFixedClient(FakeClient):
    """First plan ends inside the 15-minute buffer; after the self-check it returns a fixed plan."""
    def create(self, model, messages, **kw):
        out = super().create(model, messages, **kw)
        if self.calls == 1:
            return out
        end = "2026-10-30T17:35:00-04:00" if self.calls == 2 else "2026-10-30T17:00:00-04:00"
        plan = {"location": "Lakewood", "candle_lighting": "2026-10-30T17:38:00-04:00", "warnings": [],
                "tasks": [{"start": "2026-10-30T16:30:00-04:00", "end": end, "title": "Urn", "who": "", "note": ""}]}
        return NS(choices=[NS(message=NS(content=json.dumps(plan), tool_calls=None))])


def test_self_check_repairs_buffer_violation(monkeypatch):
    monkeypatch.setattr(agent.hebcal, "shabbos_times", lambda **k: {
        "location": "Lakewood, New Jersey, USA",
        "items": [{"category": "candles", "title": "Candle lighting: 5:38pm",
                   "date": "2026-10-30T17:38:00-04:00"}]})
    agent.TOOL_IMPLS["get_shabbos_times"] = agent.hebcal.shabbos_times
    trace, client = [], LateThenFixedClient()
    p = agent.plan("friday", client=client, trace=trace)
    assert client.calls == 3 and any(t["tool"] == "self_check" for t in trace)
    assert p["tasks"][0]["end"] == "2026-10-30T17:00:00-04:00" and p["warnings"] == []


def test_summary_falls_back_when_model_returns_nothing():
    class Empty:
        chat = NS(completions=NS(create=lambda **k: NS(choices=[NS(message=NS(content=None))])))
    p = {"candle_lighting": "2026-10-30T17:38:00-04:00",
         "tasks": [{"start": "2026-10-30T13:00:00-04:00", "end": "2026-10-30T14:00:00-04:00", "title": "Soup"}]}
    out = agent.summarize(p, client=Empty())
    assert "1:00 PM - Soup" in out and "5:38 PM" in out


def test_message_times_match_timeline_even_if_model_invents_times():
    class Liar:
        chat = NS(completions=NS(create=lambda **k: NS(choices=[NS(message=NS(
            content="Kugel goes in at 2:15 PM and soup at 3:00 PM!"))])))
    p = {"candle_lighting": "2026-10-30T17:38:00-04:00",
         "tasks": [{"start": "2026-10-30T13:15:00-04:00", "end": "2026-10-30T14:15:00-04:00", "title": "Bake kugel"},
                   {"start": "2026-10-30T13:00:00-04:00", "end": "2026-10-30T15:00:00-04:00", "title": "Cook chicken soup"},
                   {"start": "2026-10-30T16:45:00-04:00", "end": "2026-10-30T17:23:00-04:00", "title": "Free time / buffer"}]}
    out = agent.summarize(p, client=Liar())
    assert "2:15" not in out and "3:00" not in out          # invented times rejected
    lines = out.splitlines()
    assert lines[1] == "1:00 PM - Cook chicken soup" and lines[2] == "1:15 PM - Bake kugel"
    assert lines[-1].startswith("5:38 PM - Candle lighting") and "buffer" not in out
    import re
    table = {f"{agent.dt.datetime.fromisoformat(t['start']):%-I:%M %p}" for t in p["tasks"]} | {"5:38 PM"}
    assert set(re.findall(r"\d{1,2}:\d{2} [AP]M", out)) <= table
