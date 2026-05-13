---
name: monte-carlo-explainer
description: How to explain Monte Carlo forecasting for software delivery so a non-statistician can act on it.
version: 1.0
author: dvhthomas@gmail.com
tags: [flow, monte-carlo, forecasting, flow-coach]
---

Monte Carlo forecasting for software delivery answers two questions:

1. **"When will we be done with these N items?"** → date forecast
2. **"How many items can we ship by date X?"** → item-count forecast

Both use the same input — historical throughput — and the same method — random sampling. The `flowmetrics` MCP tool implements both as `flowmetrics_when_done(...)` and `flowmetrics_how_many(...)`.

## How it works (in two paragraphs the user can act on)

You take your recent throughput history (say, the last 12 weeks of items completed per week). You roll that history like a die — randomly pick a week's throughput; that's "this week's sample." Roll again for next week. Keep rolling until either (a) you've used up your remaining items, in which case record the date, or (b) you've reached your target date, in which case record the item count.

Run that simulation 10,000 times. You now have 10,000 dates (or item counts). Take the **50th-percentile** = "median forecast." Take the **85th-percentile** = "85% confidence we ship by here or earlier." Take the **95th** = "stretch forecast." That triple is the Monte Carlo result.

## Why this beats story-point velocity forecasting

- **It uses actual throughput, not estimates.** Story-point velocity multiplies one estimate (points per sprint) by another estimate (points per story). Monte Carlo multiplies one measurement (items per week) by an assumed scope (count of remaining items).
- **It produces a probability distribution, not a point estimate.** "We'll ship in 4 weeks" is a lie; "50% chance by 3.5 weeks, 85% by 5.5 weeks" is honest.
- **It works on the team you have.** Throughput reflects all the real-world friction — meetings, on-call, sick days, scope creep. Story-point velocity pretends those don't exist.

## When the user asks for a forecast

1. **Make sure they have ≥ 11 weeks of throughput data.** Less than that and the sample is too small to be honest about. Tell them so; offer to do it anyway with a confidence caveat.
2. **Ask whether they want a date forecast or an item-count forecast.** They are different questions.
3. **Quote three percentiles** — p50, p85, p95. Never a single number. If they push for one, give them p85 and note the others.
4. **Be honest about scope volatility.** Monte Carlo assumes the scope is fixed. If scope changes mid-flight, the forecast changes. This is a feature, not a bug — it makes scope-vs-deadline trade-offs visible.

## Calling the tool

Use `flowmetrics_when_done(repo, items, since)` for "when will N items be done." Use `flowmetrics_how_many(repo, by_date, since)` for "how many items by date X." Both return structured forecasts; cite the tool call per [[cite-sources]].

If `flowmetrics` is unavailable (e.g. not installed in this environment), say so plainly: "Monte Carlo forecast requires the flowmetrics tool which isn't configured here. The cycle-time and throughput numbers from gh-velocity are still useful for back-of-envelope sanity checks." Don't fabricate a forecast.

## What Monte Carlo is NOT

- **Not a "this will definitely happen by X" guarantee.** It's a probability.
- **Not a substitute for breaking work into doable chunks.** A 10-item scope with one giant story still gives a wide distribution.
- **Not magic.** If throughput drops, the forecast slips. The model is honest about this; people sometimes aren't.
- **Not a way to commit a team to a deadline.** It's a way to *inform* commitment. Use the p85 as the commitment if you must; quote p50 internally so the team knows what's likely.

## Common questions and how to answer

- *"Just give me one date."* → "p85 is <date>. p50 is <earlier date>; we'll likely hit it. p95 is <later>; that's the worst-case stretch."
- *"Our throughput will improve next sprint."* → "Maybe. The forecast uses observed throughput; if you have new evidence, we can re-run with a recent window. Want me to re-forecast on the last 4 weeks instead of 12?"
- *"Why is the spread so wide?"* → "High variability in past throughput. Look at the histogram — if there are weeks of 0 and weeks of 8, the spread will be wide. Smoothing comes from reducing variability, not increasing speed."
- *"Can you forecast with story points instead?"* → "Monte Carlo over story points is doable but less reliable than over throughput, because point estimates have their own variance you're now multiplying through. If you have a strong reason, we can; otherwise throughput-based is better."
