"""Export a plan to an .ics calendar so the household gets phone reminders before Shabbos."""
from __future__ import annotations
import datetime as dt
import uuid


def _fmt(ts: str) -> str:
    t = dt.datetime.fromisoformat(ts).astimezone(dt.timezone.utc)
    return t.strftime("%Y%m%dT%H%M%SZ")


def plan_to_ics(plan: dict) -> str:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//shabbos-prep-agent//EN"]
    for task in plan.get("tasks", []):
        start = task["start"]
        end = task.get("end") or start
        lines += ["BEGIN:VEVENT", f"UID:{uuid.uuid4()}@shabbos-prep-agent",
                  f"DTSTAMP:{_fmt(dt.datetime.now(dt.timezone.utc).isoformat())}",
                  f"DTSTART:{_fmt(start)}", f"DTEND:{_fmt(end)}",
                  "SUMMARY:" + task["title"].replace("\n", " "),
                  "DESCRIPTION:" + task.get("note", "").replace("\n", " "),
                  "BEGIN:VALARM", "TRIGGER:-PT10M", "ACTION:DISPLAY",
                  "DESCRIPTION:" + task["title"], "END:VALARM", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
