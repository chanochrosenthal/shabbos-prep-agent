# Devpost submission — Nebius x NVIDIA Global AI Hackathon (paste-ready)

**Project name:** Shabbos Prep Agent

**Tagline (≤200 chars):** An AI agent that plans your Friday backwards from the real candle-lighting time — Nemotron on Nebius Token Factory turns "8 guests, I finish work at 1" into a timed plan and phone reminders.

**Track:** Best Apps and Agents

**Demo URL:** [HF Space URL, e.g. https://huggingface.co/spaces/chanochrosenthal/shabbos-prep-agent]
**Repo:** [https://github.com/chanochrosenthal/shabbos-prep-agent]
**Video (public YouTube, <3 min):** [YouTube URL]
**City event attended:** None

**Built with:** python, nvidia-nemotron, nemotron-3-super, nemotron-3-nano, nebius-token-factory, openai-sdk, gradio, hebcal-api, hugging-face-spaces, icalendar

## Inspiration
Every Friday, millions of observant Jewish households race a hard deadline that moves every week and
differs by city: candle lighting. After it, cooking, driving, phones and lights are off for 25 hours, so
anything not done is simply not done. In my own community (Lakewood, NJ) Friday is a logistics problem:
guests, a full menu, kids, a work day, and a sunset that comes at 4:15 in December. Existing apps tell you
*when* Shabbos starts. Nobody tells you *what to do, and when*, to be ready.

## What it does
You describe your Friday in plain English ("8 guests, I finish work at 1, soup, roast, kugel, two kids need
baths, we light 18 minutes before sunset"). The agent:
1. Calls real tools for the real times (candle lighting, havdalah, parsha, Yom Tov, zmanim) for your city.
2. Back-schedules every task from candle lighting with buffers (oven times, the urn and blech, timers,
   baths, table, a final 15-minute "everything off" margin).
3. Returns a time-stamped plan, a short message to forward to the family group chat, and an `.ics` file so
   every phone pings 10 minutes before each step.
4. Shows its work: an agent trace of every tool call it made.
It never guesses a time and never gives halachic rulings ("ask your Rav").

## How we built it
- **Nemotron 3 Super (`nvidia/nemotron-3-super-120b-a12b`) on Nebius Token Factory** is the planner: an
  OpenAI-compatible tool-calling loop (`get_shabbos_times`, `get_zmanim`) followed by a strict JSON plan.
- **Nemotron 3 Nano (`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`)** writes the family message: the fast,
  cheap everyday call, exactly the Super-for-reasoning / Nano-for-speed split the track recommends.
- Model IDs are env-configurable (e.g. `nvidia/Nemotron-3-Ultra-550b-a55b` as planner).
- **Hebcal.com** (free, CC BY 4.0) supplies the times; a cached client keeps us polite.
- **Gradio** UI hosted on Hugging Face Spaces; `.ics` export with alarms; pytest tests with a scripted model
  so the agent loop is tested offline.

## Challenges
- The model doesn't know today's date. In our first live run it confidently planned a Friday in 2025.
  Fix: we inject today's date and the coming Friday into the prompt, then a grounding step overwrites
  candle lighting, havdalah and parsha with the tool's real values and warns about any task that is
  on the wrong day or eats into the 15-minute buffer.
- Models still sometimes squeeze a task into the last 15 minutes. A self-check step now catches it,
  hands the violations back to Nemotron 3 Super, and shows the corrected plan.
- The summary model once invented a candle time; it now gets the verified time explicitly. Nano is a
  reasoning model, so a tight token cap could leave it with no answer; we give it room and keep a
  deterministic fallback message.
- Getting strict JSON back reliably after tool calls: a tight output contract plus a tolerant extractor.
- Time zones and DST (this hackathon ends the week clocks change): all times are ISO-8601 with offsets.
- Being useful without overstepping: the agent plans logistics but defers halachic questions.

## Accomplishments
- A real, end-to-end agent a family can use this Friday, with times that match Hebcal to the minute.
- Two-model routing: a full plan plus family message comes back in about 15-25 seconds.

## What we learned
Nemotron 3 Super is a strong tool-caller for structured planning; Nano is more than enough for short,
warm prose. Token Factory's OpenAI compatibility meant zero SDK changes.

## What's next
WhatsApp delivery and a Friday-morning check-in ("you're 20 minutes behind — move the kugel up"),
saved household profiles, Yom Tov meal-by-meal planning, and Hebrew/Yiddish output.

## Feedback on Nebius Token Factory and NVIDIA (draft — edit with your real experience)
- Onboarding: [note how long signup/billing/API key took; whether the promo code applied smoothly].
- API: OpenAI-compatible endpoint worked with the stock `openai` Python SDK; tool calling on Nemotron 3 Super
  [worked first try / needed X]. Suggestion: a cookbook example of tool calling + strict JSON with Nemotron.
- Model catalog: model IDs differ in casing (`nvidia/nemotron-3-super-120b-a12b` vs
  `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`); a consistent scheme and aliases would avoid 404s.
- Docs show two base URLs (`api.tokenfactory.nebius.com` and `api.tokenfactory.us-central1.nebius.com`);
  a sentence on when to use the regional one would help.
- Nemotron: [latency/quality notes from your test run].

## Is this an existing project?
No. It is a new repository written during the submission period. The author's earlier, separate project
(`shabbos-zmanim-mcp`, an MCP server for voice assistants) shares the domain only; no code was reused.
