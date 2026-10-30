"""Gradio web UI (deployable as a free Hugging Face Space or any VM)."""
from __future__ import annotations
import json
import tempfile

import gradio as gr

from .agent import plan, summarize, PLANNER_MODEL, FAST_MODEL
from .ics import plan_to_ics

EXAMPLE = ("We're in Lakewood NJ. This Friday we have 8 guests. I finish work at 1 PM. "
           "Menu: challah (dough is made), chicken soup, roast, kugel. Two kids need baths. "
           "We light 18 minutes before sunset.")


def run(request: str):
    trace: list = []
    p = plan(request, trace=trace)
    msg = summarize(p)
    rows = [[t["start"][11:16], t["end"][11:16], t["title"], t.get("who", ""), t.get("note", "")]
            for t in p.get("tasks", [])]
    f = tempfile.NamedTemporaryFile("w", suffix=".ics", delete=False)
    f.write(plan_to_ics(p)); f.close()
    return msg, rows, f.name, json.dumps(trace, indent=2)


def build():
    with gr.Blocks(title="Shabbos Prep Agent") as demo:
        gr.Markdown(f"# Shabbos Prep Agent\nPlans Erev Shabbos backwards from real candle-lighting "
                    f"times. Planner: `{PLANNER_MODEL}` · Summary: `{FAST_MODEL}` on Nebius Token Factory.")
        req = gr.Textbox(label="Your Friday", value=EXAMPLE, lines=4)
        btn = gr.Button("Plan my Erev Shabbos", variant="primary")
        summary = gr.Textbox(label="Family message")
        table = gr.Dataframe(headers=["Start", "End", "Task", "Who", "Note"], wrap=True)
        ics = gr.File(label="Add to calendar (.ics)")
        with gr.Accordion("Agent trace (tool calls)", open=False):
            tr = gr.Code(language="json")
        btn.click(run, req, [summary, table, ics, tr])
        gr.Markdown("Times: Hebcal.com (CC BY 4.0). Not a halachic authority — ask your Rav.")
    return demo


if __name__ == "__main__":
    build().launch()
