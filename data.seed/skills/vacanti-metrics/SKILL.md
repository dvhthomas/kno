---
name: vacanti-metrics
description: Daniel Vacanti's four flow metrics — cycle time, throughput, WIP, WIP aging — with operational definitions and the rules that make them honest signals.
version: 1.0
author: dvhthomas@gmail.com
tags: [flow, vacanti, metrics, flow-coach]
---

Daniel Vacanti's *Actionable Agile Metrics for Predictability* establishes four flow metrics that, taken together, describe how work moves through a system. The metrics are simple to define; the discipline is in how they're used.

## Cycle time

**Definition**: the elapsed time, per work item, from "started" to "done."
- "Started" = when a human commits to actively working on it (not when the issue was opened).
- "Done" = when value reaches the user (PR merged, deployed, accepted — pick one and hold it).

**Reporting rule: report the 85th percentile (p85), not the mean.** The mean lies because cycle-time distributions are right-skewed — a handful of long-tail items inflate the mean, and the mean is sensitive to small numbers of outliers. The 85th percentile says "85% of items finish in this much time or less," which is what an SLO actually needs.

**Implementation note for Kno**: gh-velocity reports median + P90 + P95 (not P85). When you have raw cycle-time data, compute P85. When you only have aggregate output from gh-velocity, **lead with P90 and call it out**: "gh-velocity's P90 is 6.2 days — close to but not Vacanti's P85." Don't silently substitute mean for percentile.

When the user asks for "average cycle time," gently redirect: "Mean cycle time misleads because the distribution is skewed; here's the p85 instead." Never report the mean unless explicitly asked, and then accompany it with the p85.

## Throughput

**Definition**: count of items completed per unit time. Per ISO week is the typical period; per day is too noisy for most teams.

**Use for forecasting, not performance review.** Throughput multiplied through Monte Carlo gives you delivery forecasts. Throughput used as a *goal* is what Goodhart's law warns about — teams game it by splitting work into smaller items.

## Work In Progress (WIP)

**Definition**: count of items currently in the "started but not done" state right now.

**Little's Law**: avg cycle time = WIP / throughput.

This means: if you want faster average cycle time, you must reduce WIP or increase throughput. You cannot reduce average cycle time by working harder on each item. WIP is the lever the team controls most directly; pull-based systems use an explicit WIP limit as policy.

## WIP age (aging)

**Definition**: for each item *currently* in progress, the elapsed time since it started. (Distinct from cycle time, which is for completed items.)

**Operational signal**: items aged > 2× the median completed cycle time are flagged as at-risk. Aged items predict future cycle-time blowouts — they are the **leading** indicator. Cycle time itself is the **lagging** indicator.

A team with healthy flow has a thin tail of aging WIP. A team in trouble has items aged 3–5× the median sitting in "in progress" with no one looking at them.

## When asked "what's our velocity?"

The answer is **not one number**. The honest answer is four metrics together:

1. **Cycle time p85**: how predictable is delivery?
2. **Throughput per week**: how much do we ship?
3. **WIP right now**: how loaded is the system?
4. **Aged WIP**: are we ignoring anything?

Resist the temptation to compress this to a single number. **Story points are not on this list.** Story points are not a Vacanti metric. If the user asks about story points, redirect to throughput.

## Monte Carlo forecasting

For "when will we be done?" or "how many will we ship by X?" — use Monte Carlo over throughput, not story-point velocity. See [[monte-carlo-explainer]]. The `flowmetrics` MCP tool produces these forecasts.

## What Vacanti's framework rules out

- Reporting the mean cycle time without the percentile.
- "Velocity" as a single scalar.
- Story-point-based forecasting.
- Treating throughput as a performance metric.
- Ignoring aged WIP because "we'll get to it next week."

If you find yourself doing any of these in a response, course-correct.
