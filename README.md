# Karumi Rollout QA Kit

A small, real, working tool for the problem a Forward Deployed Engineer actually has:
**"Does the agent's planned path through this specific customer's product still work?"**

Every SaaS product Karumi's agent gets pointed at is different — different auth, different
popups, different loading behavior, different multi-step flows. Before/after a rollout, someone
needs a fast way to walk the same path the agent will take, catch what broke, and hand back
something more useful than "it's broken" — timing, a screenshot, and a first guess at *why*.

This repo is that tool, plus a small fake product to run it against so the whole thing is
provable end-to-end without needing a real customer environment.

```
karumi-rollout-qa-kit/
├── qa_kit/            the QA runner itself (product-agnostic)
│   ├── runner.py       Playwright flow engine: navigate, click, fill, wait, assert, retry
│   ├── report.py       renders a single self-contained HTML report (screenshots inlined)
│   └── cli.py          colored terminal output + report generation
├── flows/              JSON flow configs — the "script" for a given product
│   ├── northwind_demo_flow.json      full happy-path rollout check (22 steps, all pass)
│   └── broken_selector_example.json  same idea, deliberately broken — shows failure output
├── mock_app/            "Northwind CRM" — a fake product to test against locally
└── reports/             example generated report + per-step screenshots (already run, included)
```

## Why a flow *engine* instead of a fixed script

A hardcoded Selenium script breaks the moment a customer's UI differs even slightly. This
kit separates the thing that changes (the JSON flow — selectors, steps, expected text) from
the thing that doesn't (the engine that drives the browser, times each step, retries flaky
ones, and reports what happened). Pointing this at a new customer means writing a new flow
file, not new code — which is the actual day-to-day shape of an FDE rollout.

## What it handles (the edge cases FDEs actually hit)

- **Popups that appear asynchronously**, after the page has already loaded (`dismiss_if_present`
  — waits briefly, dismisses if it shows up, doesn't fail the run if it doesn't)
- **Slow / async data loading** (`assert_text` polls until the expected text shows up or times
  out, rather than assuming data is there immediately)
- **Auth walls, multi-step wizards, and click targets blocked by overlays**
- **Flaky steps** — configurable per-step retries with backoff
- **Failure triage** — every failed step gets a screenshot at the moment of failure and a
  heuristic root-cause suggestion (e.g. "likely an overlay intercepting the click, add a
  dismiss step before this one") instead of a bare stack trace

## Quickstart

```bash
pip install -r requirements.txt
playwright install chromium

# terminal 1 — start the fake product to test against
python3 mock_app/app.py

# terminal 2 — run the QA kit against it
python3 -m qa_kit.cli run flows/northwind_demo_flow.json --open-report
```

You'll get colored pass/fail output per step in the terminal, and an HTML report at
`reports/report.html` (already generated and committed in this repo — open
`reports/northwind_demo_flow_report.html` directly to see it without running anything).

To see the failure-reporting side (screenshot + suggested fix) rather than a clean pass:

```bash
python3 -m qa_kit.cli run flows/broken_selector_example.json
```

## Writing a flow for a new product

```json
{ "action": "navigate", "path": "/login" }
{ "action": "dismiss_if_present", "selector": "#cookie-accept", "wait_ms": 1500 }
{ "action": "fill", "selector": "#username", "value": "demo" }
{ "action": "click", "selector": "#login-submit" }
{ "action": "wait_for", "selector": ".dashboard" }
{ "action": "assert_text", "selector": "#result-count", "contains": "3 results" }
```

Every step supports `description` (shown in the report), `timeout_ms`, `retries`, and
`retry_delay_ms`. That's the whole config surface — intentionally small enough to write by
hand while looking at a customer's product in a browser.

## How this maps to the FDE role

| JD responsibility | This project |
|---|---|
| Setup, configuration, validation of customer rollouts | The flow config format *is* a configuration — this is what validating a rollout looks like as a repeatable check |
| QA and troubleshooting for reliability | Retry logic, timing per step, screenshot-on-failure, root-cause suggestions |
| Adapt to different customer workflows, UIs, edge cases | Flow-per-product design; mock app deliberately includes async popups, slow loads, multi-step forms |
| Lightweight scripting/automation to reduce manual work | The whole tool — turns a manual click-through into a one-command check |
| Capture feedback, communicate to product/engineering | The HTML report is the artifact you'd actually attach to a ticket or Slack message |

## Honest scope notes

This is a weekend-scoped MVP, not a claim that it's what Karumi runs internally. Things I'd
build next if this were real: a real CRM/webhook integration for the logging step Karumi's
agent does, a multi-language test harness (switch locale, verify agent responses), and swapping
the JSON flow format for something an agent could generate from a recorded session rather than
hand-written. Scoped it tight on purpose to ship something that actually runs end-to-end rather
than something broader that's half-real.
