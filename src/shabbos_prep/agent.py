"""The agent: Nemotron on Nebius Token Factory, with Hebcal tools, plans Erev Shabbos backwards
from candle lighting and returns a structured, time-stamped task list.

Model routing (per the Nebius track guidance):
  * PLANNER_MODEL (Nemotron 3 Super) does the tool-calling and the reasoning-heavy plan.
  * FAST_MODEL   (Nemotron 3 Nano) writes the short, friendly WhatsApp-style summary.
"""
from __future__ import annotations
import datetime as dt
import json
import re
import os
from typing import Any, Callable

from . import hebcal

BASE_URL = os.environ.get("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/")
PLANNER_MODEL = os.environ.get("PLANNER_MODEL", "nvidia/nemotron-3-super-120b-a12b")
FAST_MODEL = os.environ.get("FAST_MODEL", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B")

SYSTEM = """You are Shabbos Prep Agent, a calm, practical planner for observant Jewish households.
Your job: turn the user's situation (city, guests, menu, kids, work hours, customs) into an
Erev Shabbos / Erev Yom Tov schedule that works BACKWARDS from candle lighting.
Rules:
- ALWAYS call get_shabbos_times first to get the real candle-lighting time. Never guess times.
- Call get_zmanim when the user asks about davening times or a weekday plan.
- Finish all melacha-type prep (cooking, hot water urn, blech/plata, lights/timers, tearing toilet
  paper, eruv check, phones off) with a buffer of at least 15 minutes before candle lighting.
- Menu items still need to be cooked unless the user says they are ready. Use realistic durations
  (roast 2-3 h, chicken soup 2 h, kugel 1 h bake, challah: shape, rise ~45 min, bake ~30 min) and
  start the longest cooks first; overlap hands-off oven/stove time with other tasks.
- Never schedule a task before the user says they are free, unless someone else does it.
- End with a "Light candles" task at the exact candle-lighting time.
- Respect the user's stated minhag; if unknown, use the times returned by the tool.
- Do not give halachic rulings; if a question needs a psak, say "ask your Rav".
Return ONLY JSON: {"location": str, "candle_lighting": ISO8601, "havdalah": ISO8601|null,
 "parsha": str|null, "tasks": [{"start": ISO8601 with offset, "end": ISO8601 with offset,
 "title": str, "who": str, "note": str}], "warnings": [str]}"""

TOOLS = [
    {"type": "function", "function": {
        "name": "get_shabbos_times",
        "description": "Candle lighting, havdalah, parsha and Yom Tov for the week of a date in a city.",
        "parameters": {"type": "object", "properties": {
            "city": {"type": "string"}, "date": {"type": "string", "description": "YYYY-MM-DD"},
            "candle_minutes": {"type": "integer", "description": "minutes before sunset, default 18"}},
            "required": ["city"]}}},
    {"type": "function", "function": {
        "name": "get_zmanim",
        "description": "Daily zmanim (alos, sunrise, sof zman shema, chatzos, plag, sunset, tzeis).",
        "parameters": {"type": "object", "properties": {
            "city": {"type": "string"}, "date": {"type": "string"}}, "required": ["city"]}}},
]

TOOL_IMPLS: dict[str, Callable[..., Any]] = {
    "get_shabbos_times": hebcal.shabbos_times,
    "get_zmanim": hebcal.zmanim,
}


def make_client():
    from openai import OpenAI
    key = os.environ.get("NEBIUS_API_KEY")
    if not key:
        raise RuntimeError("Set NEBIUS_API_KEY (Nebius Token Factory) to run the agent.")
    return OpenAI(base_url=BASE_URL, api_key=key)


def _extract_json(text: str) -> dict:
    text = text.strip()
    if "```" in text:
        text = text.split("```")[1].removeprefix("json").strip()
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1])


def _today() -> dt.date:
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo(os.environ.get("TZ_NAME", "America/New_York"))).date()
    except Exception:
        return dt.date.today()


def _date_context(today: dt.date | None = None) -> str:
    """Models don't know today's date; tell them, plus the coming Friday."""
    today = today or _today()
    friday = today + dt.timedelta(days=(4 - today.weekday()) % 7)
    return (f"\nToday is {today:%A %Y-%m-%d}. Unless the user names another date, plan for "
            f"Friday {friday.isoformat()} and pass date=\"{friday.isoformat()}\" to the tools.")


def _ground(plan_obj: dict, trace: list) -> dict:
    """Overwrite times with the tool's real values and flag anything that breaks the buffer."""
    for t in reversed(trace):
        if t["tool"] != "get_shabbos_times" or "items" not in t.get("result", {}):
            continue
        items = t["result"]["items"]
        by = {}
        for it in items:
            by.setdefault(it["category"], it)
        if "candles" in by:
            plan_obj["candle_lighting"] = by["candles"]["date"]
        if "havdalah" in by:
            plan_obj["havdalah"] = by["havdalah"]["date"]
        if "parashat" in by:
            plan_obj["parsha"] = by["parashat"]["title"].removeprefix("Parashat ")
        if t["result"].get("location"):
            plan_obj["location"] = t["result"]["location"]
        break
    warnings = plan_obj.setdefault("warnings", [])
    violations = plan_obj.setdefault("_violations", [])
    violations.clear()
    try:
        candles = dt.datetime.fromisoformat(plan_obj["candle_lighting"])
    except Exception:
        warnings.append("Could not verify candle-lighting time; check hebcal.com.")
        return plan_obj
    for task in plan_obj.get("tasks", []):
        try:
            end = dt.datetime.fromisoformat(task["end"])
        except Exception:
            continue
        if end.date() != candles.date():
            violations.append(f"'{task['title']}' is dated {end.date()}, not the Friday "
                              f"{candles.date()}.")
        elif end > candles - dt.timedelta(minutes=15) and "candle" not in task["title"].lower():
            violations.append(f"'{task['title']}' ends {end:%-I:%M %p}, less than 15 minutes "
                              f"before candle lighting ({candles:%-I:%M %p}).")
    return plan_obj


def plan(request: str, client=None, max_steps: int = 8, trace: list | None = None) -> dict:
    """Run the tool-calling loop and return the structured plan."""
    client = client or make_client()
    trace = trace if trace is not None else []
    messages = [{"role": "system", "content": SYSTEM + _date_context()},
                {"role": "user", "content": request}]
    revised = False
    for _ in range(max_steps):
        resp = client.chat.completions.create(model=PLANNER_MODEL, messages=messages,
                                              tools=TOOLS, temperature=0.2)
        msg = resp.choices[0].message
        if getattr(msg, "tool_calls", None):
            messages.append({"role": "assistant", "content": msg.content or "",
                             "tool_calls": [tc.model_dump() if hasattr(tc, "model_dump") else tc
                                            for tc in msg.tool_calls]})
            for tc in msg.tool_calls:
                args = json.loads(tc.function.arguments or "{}")
                try:
                    result = TOOL_IMPLS[tc.function.name](**args)
                except Exception as e:  # surface tool errors to the model so it can recover
                    result = {"error": str(e)}
                trace.append({"tool": tc.function.name, "args": args, "result": result})
                messages.append({"role": "tool", "tool_call_id": tc.id,
                                 "content": json.dumps(result)})
            continue
        result = _ground(_extract_json(msg.content or "{}"), trace)
        if result["_violations"] and not revised:
            # Self-check: hand the violations back to the planner once and ask for a fix.
            revised = True
            trace.append({"tool": "self_check", "args": {}, "result": {"violations": result["_violations"]}})
            messages.append({"role": "assistant", "content": msg.content or ""})
            messages.append({"role": "user", "content": "Your plan breaks these rules:\n- "
                             + "\n- ".join(result["_violations"])
                             + "\nReturn the corrected plan as JSON only. Same format."})
            continue
        result["warnings"] = result.get("warnings", []) + result.pop("_violations")
        return result
    raise RuntimeError("Agent did not finish within max_steps")


_TIME_RE = re.compile(r"\b\d{1,2}(:\d{2})?\s*([AaPp]\.?[Mm]\.?)|\b\d{1,2}:\d{2}\b")
_SKIP = ("buffer", "free time", "candle")


def _message_lines(plan_obj: dict, limit: int = 6) -> list[str]:
    """Time lines rendered in code straight from the timeline, so they always match the table."""
    rows = []
    for t in plan_obj.get("tasks", []):
        try:
            start = dt.datetime.fromisoformat(t["start"])
        except Exception:
            continue
        if any(k in t.get("title", "").lower() for k in _SKIP):
            continue
        rows.append((start, t["title"]))
    rows.sort(key=lambda r: r[0])
    lines = [f"{s:%-I:%M %p} - {title}" for s, title in rows[:limit]]
    try:
        c = dt.datetime.fromisoformat(plan_obj["candle_lighting"])
        lines.append(f"{c:%-I:%M %p} - Candle lighting. Good Shabbos!")
    except Exception:
        pass
    return lines


def _friendly_line(plan_obj: dict, client) -> str:
    """Fast model writes ONE warm opening sentence with no times; rejected if it contains any time."""
    slim = {"location": plan_obj.get("location"), "guests_and_tasks": [t.get("title") for t in plan_obj.get("tasks", [])]}
    for _ in range(2):  # the fast model occasionally returns empty content; retry once
        try:
            resp = client.chat.completions.create(
                model=FAST_MODEL, temperature=0.4, max_tokens=2048,
                messages=[{"role": "system", "content": "Write ONE warm, upbeat sentence (max 25 words) "
                           "opening an Erev Shabbos game plan for a family group chat. Do NOT mention any "
                           "clock times or numbers of minutes/hours. Plain text, at most one emoji."},
                          {"role": "user", "content": json.dumps(slim)}])
            text = (resp.choices[0].message.content or "").strip().splitlines()
            text = text[0].strip() if text else ""
            if text and not _TIME_RE.search(text):
                return text
        except Exception:
            pass
    return "Here's our Erev Shabbos game plan:"


def summarize(plan_obj: dict, client=None) -> str:
    """Family message: friendly opener from Nemotron Nano + time lines rendered in code from the timeline."""
    client = client or make_client()
    return "\n".join([_friendly_line(plan_obj, client)] + _message_lines(plan_obj))


def _fallback_summary(plan_obj: dict) -> str:
    """Deterministic message without the model."""
    return "\n".join(["Here's our Erev Shabbos game plan:"] + _message_lines(plan_obj))
