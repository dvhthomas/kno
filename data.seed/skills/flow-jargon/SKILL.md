---
name: flow-jargon
description: Common flow-management terms with crisp definitions so the agent uses them precisely, not interchangeably.
version: 1.0
author: dvhthomas@gmail.com
tags: [flow, glossary, flow-coach]
---

Use these terms with their canonical meanings. Avoid borrowing terms from adjacent vocabularies (Scrum, SAFe, "Agile coach" hype) that overlap but mean something subtly different.

## Cycle time
Started → done elapsed time, per item. See [[vacanti-metrics]] for reporting rules.

## Lead time
Created → done elapsed time, per item. Always ≥ cycle time. Useful for talking to stakeholders ("when can I expect this?") but less useful for team-internal flow analysis than cycle time.

## Throughput
Items completed per period. See [[vacanti-metrics]].

## WIP
Work In Progress. The current count, not cumulative. See [[vacanti-metrics]].

## WIP age
For items *currently* in progress, the elapsed time since start. See [[vacanti-metrics]].

## Little's Law
avg cycle time = WIP / throughput. Holds under steady state. Read it as a constraint: you cannot reduce average cycle time without reducing WIP or increasing throughput. Working harder on individual items doesn't help.

## Pull system
Work is pulled into the active state when capacity exists, rather than pushed in when "ready." The opposite is a push system. Pull systems naturally limit WIP.

## Monte Carlo (forecasting)
A sampling method that simulates "what would the next N items look like given this team's recent throughput?" Outputs a probability distribution: "85% chance of shipping ≥ 5 items in the next week." Use this instead of story-point velocity. See [[monte-carlo-explainer]].

## Variability
The spread in cycle time. High variability = unpredictable delivery. Reducing variability matters more than reducing average cycle time for stakeholder trust.

## Flow efficiency
(value-add time) / (total cycle time). Usually 5–15% in software teams — most of the calendar time is waiting, not working. Improving flow efficiency means removing queues, not working faster.

## CFD (Cumulative Flow Diagram)
Stacked area chart of work-state counts over time. Each band's width = items in that state. Useful for spotting bottlenecks (a band that grows = work piling up in that state).

## Aged WIP
Same as WIP age. The current age of in-progress items. Items aged > 2× median cycle time are at-risk.

## Reactive vs predictive metrics
- **Predictive** (leading): aged WIP, queue depths, blocked-status duration. These tell you about future cycle times.
- **Reactive** (lagging): cycle time of completed items. These tell you what already happened.

## What these terms do NOT mean (anti-vocabulary)

- **Velocity** as a single scalar = avoid. Use the four Vacanti metrics together.
- **Story points** = explicitly out of scope. If the user asks about points, redirect to throughput.
- **Sprint** = not a Vacanti term. Flow analysis is sprint-agnostic. Don't introduce sprint vocabulary unless the user does first.
- **Capacity** is ambiguous in industry usage. Prefer "WIP limit" if that's what's meant. Prefer "available throughput" if that's what's meant.
- **Burndown chart** = not a Vacanti tool. CFD is the equivalent that's actually useful.
- **Estimation accuracy** = not a Vacanti goal. Monte Carlo forecasting works on observed throughput, not on estimate quality.

If the user uses these anti-vocabulary terms casually, translate them. Don't lecture; just respond in the canonical vocabulary so the conversation drifts toward precision.
