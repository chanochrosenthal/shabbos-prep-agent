---
title: Shabbos Prep Agent
emoji: 🕯️
sdk: gradio
app_file: app.py
license: mit
---

# Shabbos Prep Agent

An AI agent that plans an observant family's Friday **backwards from the real candle-lighting time**,
powered by **NVIDIA Nemotron** models on **Nebius Token Factory**.

Every Friday, observant households race a hard, moving deadline: candle lighting. It shifts every
week and differs by city. After it, cooking, driving, phones and lights are off-limits for 25 hours.
Shabbos Prep Agent takes a plain-English description of your Friday (city, guests, menu, kids, work
hours, customs), fetches the real times, and returns a time-stamped plan, a short family message, and
an `.ics` file so everyone's phone pings before each step.

## How it uses Nebius + NVIDIA
| Step | Model (Token Factory) | Why |
|---|---|---|
| Tool-calling planner | `nvidia/nemotron-3-super-120b-a12b` | Multi-step reasoning: calls `get_shabbos_times` / `get_zmanim`, then back-schedules tasks with buffers |
| Family message | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | Fast, cheap everyday call for the short summary |

All inference is a runtime call to the Token Factory OpenAI-compatible API
(`https://api.tokenfactory.nebius.com/v1/`). Model IDs are configurable via `PLANNER_MODEL` / `FAST_MODEL`
(you can switch the planner to Nemotron 3 Ultra for harder plans, e.g. a two-day Yom Tov).

## Run locally
```bash
git clone https://github.com/chanochrosenthal/shabbos-prep-agent && cd shabbos-prep-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export NEBIUS_API_KEY=...   # from https://tokenfactory.nebius.com
python app.py               # opens http://localhost:7860
pytest -q                   # offline tests (scripted model, no key needed)
```

## Architecture
```
User text ──► Nemotron 3 Super (Token Factory) ──tool calls──► Hebcal.com (times, parsha, Yom Tov)
                     │  JSON plan (tasks w/ ISO times)
                     ├──► Nemotron 3 Nano ──► family message
                     └──► .ics export (10-min alarms)
```
- `src/shabbos_prep/agent.py` – tool-calling loop, model routing, JSON plan contract
- `src/shabbos_prep/hebcal.py` – polite Hebcal client (cached)
- `src/shabbos_prep/ics.py` – calendar export
- `src/shabbos_prep/app.py` – Gradio UI (also runs as a Hugging Face Space)

## Privacy
No accounts, no database. Your request is sent to Nebius Token Factory for inference and only the city
is sent to Hebcal. Nothing is stored server-side.

## Relationship to earlier work
The author previously built `shabbos-zmanim-mcp` (an MCP server for voice assistants). This is a
**new repository**: the agent, planner, model routing, UI and calendar export were written during the
Nebius x NVIDIA submission period.

## Attribution
Times: Hebcal.com (CC BY 4.0). Locations: GeoNames (CC BY 4.0). Not a halachic authority — ask your Rav.
Not affiliated with Nebius, NVIDIA or Hebcal.
