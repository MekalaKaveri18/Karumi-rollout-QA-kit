"""Renders a RunResult into a single, self-contained HTML report.

Screenshots are embedded as base64 so the report is one portable file — you
can email it, drop it in Slack, or attach it to a ticket without anyone
needing access to a folder of loose PNGs.
"""
from __future__ import annotations

import html
from pathlib import Path

from .runner import RunResult

_CSS = """
:root {
  --bg:#0f1720; --panel:#16212c; --panel-2:#1c2b38; --border:#2a3b48;
  --text:#e6edf3; --muted:#8ba0b3; --accent:#ff9f43;
  --good:#4caf7d; --good-bg:#173325; --bad:#e2596b; --bad-bg:#341c22;
  --mono:"SFMono-Regular",Consolas,"Liberation Mono",Menlo,monospace;
}
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--text); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif; }
.wrap { max-width: 900px; margin: 0 auto; padding: 40px 24px 80px; }
header { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom: 28px; gap: 20px; }
h1 { font-size: 21px; margin: 0 0 6px; }
.meta { color: var(--muted); font-size: 13px; font-family: var(--mono); }
.summary-badge { text-align:right; }
.summary-badge .big { font-size: 30px; font-weight: 800; font-family: var(--mono); }
.summary-badge .big.ok { color: var(--good); }
.summary-badge .big.fail { color: var(--bad); }
.summary-badge .sub { color: var(--muted); font-size: 12px; margin-top: 2px; }
.stat-row { display:flex; gap: 12px; margin-bottom: 28px; }
.stat-pill { flex:1; background:var(--panel); border:1px solid var(--border); border-radius:10px; padding:14px 16px; }
.stat-pill .n { font-family: var(--mono); font-size: 20px; font-weight:700; }
.stat-pill .l { color:var(--muted); font-size:12px; margin-top:2px; }
.step { background:var(--panel); border:1px solid var(--border); border-radius:10px; margin-bottom:14px; overflow:hidden; }
.step-head { display:flex; align-items:center; gap:12px; padding:14px 18px; }
.idx { font-family: var(--mono); color: var(--muted); font-size:13px; width: 26px; }
.status-tag { font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.04em; padding:3px 9px; border-radius:100px; }
.status-tag.pass { background: var(--good-bg); color: var(--good); }
.status-tag.fail { background: var(--bad-bg); color: var(--bad); }
.status-tag.skipped { background: var(--panel-2); color: var(--muted); }
.step-desc { flex:1; font-size:14px; font-weight:500; }
.step-dur { font-family: var(--mono); font-size:12px; color: var(--muted); }
.step-body { padding: 0 18px 18px; }
.selector-line { font-family: var(--mono); font-size:12px; color: var(--muted); margin-bottom:10px; }
.error-box { background: var(--bad-bg); border:1px solid #5a2a33; border-radius:8px; padding:12px 14px; font-family: var(--mono); font-size:12.5px; color:#ffb3bc; margin-bottom:10px; white-space:pre-wrap; }
.suggestion-box { background: var(--panel-2); border-radius:8px; padding:12px 14px; font-size:13px; color: var(--text); margin-bottom:12px; border-left: 3px solid var(--accent); }
.suggestion-box .lbl { color: var(--accent); font-weight:700; font-size:11px; text-transform:uppercase; letter-spacing:.04em; display:block; margin-bottom:4px; }
.shot { max-width: 100%; border-radius: 8px; border:1px solid var(--border); display:block; }
details summary { cursor:pointer; color: var(--muted); font-size:12.5px; padding: 4px 0; }
footer { color: var(--muted); font-size:12px; text-align:center; margin-top: 40px; }
"""


def _step_html(step) -> str:
    status_cls = step.status
    desc = html.escape(step.description)
    selector = html.escape(step.selector or "")
    body = [f'<div class="selector-line">{step.action}' + (f"  &middot;  {selector}" if selector else "") + "</div>"]

    if step.error:
        body.append(f'<div class="error-box">{html.escape(step.error)}</div>')
    if step.suggestion:
        body.append(f'<div class="suggestion-box"><span class="lbl">Suggested next step</span>{html.escape(step.suggestion)}</div>')
    if step.attempts > 1:
        body.append(f'<div class="selector-line">Retried {step.attempts - 1}x before {"succeeding" if step.status == "pass" else "giving up"}</div>')
    if step.screenshot_b64:
        body.append(
            f'<details><summary>Screenshot at this step</summary>'
            f'<img class="shot" src="data:image/png;base64,{step.screenshot_b64}" loading="lazy"></details>'
        )

    return f"""
    <div class="step">
      <div class="step-head">
        <span class="idx">{step.index:02d}</span>
        <span class="status-tag {status_cls}">{step.status}</span>
        <span class="step-desc">{desc}</span>
        <span class="step-dur">{step.duration_ms} ms</span>
      </div>
      <div class="step-body">{''.join(body)}</div>
    </div>
    """


def render_report(result: RunResult) -> str:
    overall_cls = "ok" if result.ok else "fail"
    overall_text = "PASS" if result.ok else "FAIL"
    steps_html = "\n".join(_step_html(s) for s in result.steps)

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>QA Report — {html.escape(result.name)}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">
  <header>
    <div>
      <h1>{html.escape(result.name)}</h1>
      <div class="meta">{html.escape(result.base_url)} &middot; run at {result.started_at} &middot; {result.total_duration_ms} ms total</div>
    </div>
    <div class="summary-badge">
      <div class="big {overall_cls}">{overall_text}</div>
      <div class="sub">{result.passed}/{len(result.steps)} steps passed</div>
    </div>
  </header>

  <div class="stat-row">
    <div class="stat-pill"><div class="n">{result.passed}</div><div class="l">Passed</div></div>
    <div class="stat-pill"><div class="n">{result.failed}</div><div class="l">Failed</div></div>
    <div class="stat-pill"><div class="n">{result.skipped}</div><div class="l">Skipped</div></div>
    <div class="stat-pill"><div class="n">{result.total_duration_ms}</div><div class="l">Total ms</div></div>
  </div>

  {steps_html}

  <footer>Generated by karumi-rollout-qa-kit</footer>
</div>
</body>
</html>"""


def write_report(result: RunResult, out_path: str | Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_report(result))
    return out_path
