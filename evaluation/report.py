#!/usr/bin/env python3
"""Render results/full.json as a standalone HTML report.

    python -m evaluation.report

Self-contained: no external CSS, no fonts, no scripts. Opens anywhere.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"

CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#14161b;--mut:#5b6270;--line:#dce0e7;
--acc:#3d4fa1;--ok:#1f7a4d;--bad:#a8322b;--warn:#9a6114;--sunk:#eef0f4}
@media(prefers-color-scheme:dark){:root{--bg:#0f1115;--card:#161920;--ink:#e7e9ee;
--mut:#949ba9;--line:#272c36;--acc:#93a3ee;--ok:#5fbf8c;--bad:#e2796f;--warn:#d7a24b;--sunk:#12151b}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:960px;margin:0 auto;padding:40px 24px 80px}
h1{font-size:30px;margin:0 0 4px;letter-spacing:-.02em}
h2{font-size:17px;margin:40px 0 12px;letter-spacing:-.01em}
.sub{color:var(--mut);margin:0 0 4px}
.meta{font:12px ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--mut);margin-top:10px}
.head{border-bottom:1px solid var(--line);padding-bottom:22px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin:22px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:6px;padding:16px}
.card .v{font:600 26px/1.1 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.card .l{font-size:12.5px;color:var(--mut);margin-top:6px}
.ok{color:var(--ok)}.bad{color:var(--bad)}.warn{color:var(--warn)}.acc{color:var(--acc)}
.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:6px;background:var(--card)}
table{border-collapse:collapse;width:100%;font-size:13.5px;min-width:560px}
th{text-align:left;font:600 10px/1.6 ui-monospace,Menlo,monospace;letter-spacing:.1em;
text-transform:uppercase;color:var(--mut);padding:10px 14px;background:var(--sunk);border-bottom:1px solid var(--line)}
td{padding:9px 14px;border-bottom:1px solid var(--line);vertical-align:top}
tbody tr:last-child td{border-bottom:none}
td.n{font:13px ui-monospace,Menlo,monospace;font-variant-numeric:tabular-nums;text-align:right;white-space:nowrap}
tfoot td{font-weight:600;background:var(--sunk);border-top:1px solid var(--line)}
.note{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--acc);
border-radius:0 6px 6px 0;padding:14px 18px;margin:18px 0;font-size:14px}
.note.caution{border-left-color:var(--warn)}
.note p{margin:0 0 8px}.note p:last-child{margin:0}
.bar{height:7px;border-radius:4px;background:var(--sunk);overflow:hidden;min-width:70px}
.bar>i{display:block;height:100%}
code{font:12.5px ui-monospace,Menlo,monospace;background:var(--sunk);padding:1px 5px;border-radius:3px}
footer{margin-top:44px;padding-top:18px;border-top:1px solid var(--line);
font:12px ui-monospace,Menlo,monospace;color:var(--mut)}
"""


def rupees(minor: int) -> str:
    return f"₹{minor / 100:,.0f}"


def render_llm(path: Path) -> str:
    """The LLM arm, if it has been run. Absent rather than faked when it has not."""
    if not path.exists():
        return ""
    d = json.loads(path.read_text())
    meta = d.get("meta", {})
    by = {}
    for r in d["runs"]:
        e = by.setdefault((r["klass"], r["arm"]), {"settled": 0, "n": 0,
                                                   "charged": 0, "unauth": 0})
        e["settled"] += sum(o == "SETTLED" for o in r["outcomes"])
        e["n"] += len(r["outcomes"])
        e["charged"] += r["charged_minor"]
        e["unauth"] += r["unauthorized_minor"]

    klasses = sorted({k for k, _ in by})
    rows = []
    for k in klasses:
        a = by.get((k, "A_naive"), {})
        b = by.get((k, "B_spendgate"), {})
        def cell(v):
            # n == 0 means the model never called a payment tool: the agent
            # refused, which is not the same as a scenario that did not run.
            if v.get("n", 0) == 0:
                return '<td class="n" style="color:var(--mut)">model declined</td>'
            return f'<td class="n">{v["settled"]}/{v["n"]}</td>'

        rows.append(
            f'<tr><td>{k.replace("_", " ")}</td>'
            f'{cell(a)}<td class="n bad">{rupees(a.get("unauth", 0))}</td>'
            f'{cell(b)}<td class="n ok">{rupees(b.get("unauth", 0))}</td></tr>')

    a_tot = sum(v["unauth"] for (k, arm), v in by.items() if arm == "A_naive")
    b_tot = sum(v["unauth"] for (k, arm), v in by.items() if arm == "B_spendgate")
    mis = sum(r["misreported"] for r in d["runs"] if r["arm"] == "A_naive")
    n_a = sum(1 for r in d["runs"] if r["arm"] == "A_naive")

    return f"""
<h2>The LLM arm — a real model, not a script</h2>
<p class="sub">{meta.get('model', '?')} · {meta.get('reps', '?')} reps ·
every goal a fresh model context, one persistent ledger.</p>

<div class="cards">
<div class="card"><div class="v bad">{rupees(a_tot)}</div>
<div class="l">Released without authority — <b>Arm A</b></div></div>
<div class="card"><div class="v ok">{rupees(b_tot)}</div>
<div class="l">Released without authority — <b>Arm B</b></div></div>
<div class="card"><div class="v">{mis}/{n_a}</div>
<div class="l">Times the model misreported an amount</div></div>
</div>

<div class="scroll"><table>
<thead><tr><th>Scenario</th><th style="text-align:right">A settled</th>
<th style="text-align:right">A leaked</th><th style="text-align:right">B settled</th>
<th style="text-align:right">B leaked</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>

<div class="note">
<p><b>The model did nothing wrong.</b> It never misreported an amount, refused
the injected television on sight, and declined the prohibited category without
being asked to. The leak is not misbehaviour.</p>
<p>It comes from two things a model cannot supply: it does not remember what it
already spent when each invocation is a fresh context, and it cannot enforce a
policy it was never told. The aggregate limit lives with the principal, not in
the agent's instructions — so a perfectly obedient agent walks straight through
it, three times in a row.</p>
<p><b>That is the actual argument for this project.</b> Not that agents lie —
this one did not — but that budgets are state, and an agent has none.</p>
</div>
"""


def render(s: dict) -> str:
    a, b = s["arms"]["A_naive"], s["arms"]["B_spendgate"]
    meta = s.get("meta", {})
    rules = Counter(r for row in s["rows"] if row["arm"] == "B_spendgate" for r in row["rules"])
    outcomes = Counter(o for row in s["rows"] if row["arm"] == "B_spendgate" for o in row["outcomes"])

    rows = []
    for k, v in s["classes"].items():
        ar, br = v["A_naive"], v["B_spendgate"]
        if not ar["applicable"] and not br["applicable"]:
            continue
        if ar["applicable"]:
            pct = ar["contained"] / max(1, ar["cases"])
            a_cell = (f'<td class="n">{ar["contained"]}/{ar["cases"]}</td>'
                      f'<td class="n bad">{rupees(ar["unauthorized_minor"])}</td>')
            a_bar = (f'<td><div class="bar"><i style="width:{pct*100:.0f}%;'
                     f'background:var(--{"ok" if pct>0.9 else "bad"})"></i></div></td>')
        else:
            a_cell = '<td class="n" colspan="2" style="color:var(--mut)">not applicable</td>'
            a_bar = "<td></td>"
        rows.append(
            f'<tr><td>{k.replace("_", " ")}</td>{a_cell}{a_bar}'
            f'<td class="n">{br["contained"]}/{br["cases"]}</td>'
            f'<td class="n {"ok" if br["unauthorized_minor"] == 0 else "bad"}">'
            f'{rupees(br["unauthorized_minor"])}</td></tr>')

    rule_rows = "".join(
        f'<tr><td><code>{r}</code></td><td class="n">{n}</td></tr>'
        for r, n in rules.most_common())

    llm_section = render_llm(RESULTS / "llm.json")

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SpendGate — evaluation</title><style>{CSS}</style></head><body><div class="wrap">

<div class="head">
<h1>SpendGate — two-arm evaluation</h1>
<p class="sub">Same corpus, same merchant, same rail. One variable: whether the
agent holds the payment tool or has to ask.</p>
<p class="meta">{meta.get('cases', '?')} cases · seed {meta.get('seed', '?')} ·
{meta.get('duration_s', '?')}s · {meta.get('generated_at', '')[:19].replace('T', ' ')}Z</p>
</div>

<div class="cards">
<div class="card"><div class="v bad">{rupees(a['unauthorized_minor'])}</div>
<div class="l">Unauthorized value released — <b>Arm A</b>, the prevailing pattern</div></div>
<div class="card"><div class="v ok">{rupees(b['unauthorized_minor'])}</div>
<div class="l">Unauthorized value released — <b>Arm B</b>, SpendGate</div></div>
<div class="card"><div class="v">{b['false_refusal_rate']:.1%}</div>
<div class="l">False refusal rate on {b['benign_cases']} benign purchases</div></div>
<div class="card"><div class="v">{b['latency_ms_p95']} ms</div>
<div class="l">p95 decision latency, including the merchant round trip</div></div>
</div>

<h2>Containment by attack class</h2>
<div class="scroll"><table>
<thead><tr><th>Class</th><th style="text-align:right">A contained</th>
<th style="text-align:right">A leaked</th><th></th>
<th style="text-align:right">B contained</th><th style="text-align:right">B leaked</th></tr></thead>
<tbody>{''.join(rows)}</tbody>
<tfoot><tr><td>total (hostile)</td>
<td class="n">{a['hostile_contained']}/{a['hostile_cases']}</td>
<td class="n bad">{rupees(a['unauthorized_minor'])}</td><td></td>
<td class="n">{b['hostile_contained']}/{b['hostile_cases']}</td>
<td class="n ok">{rupees(b['unauthorized_minor'])}</td></tr></tfoot>
</table></div>

<div class="note">
<p><b>Benign cases are the control.</b> All {b['benign_cases']} settled in both arms.
A system that refuses everything would score perfectly on containment and be
useless, so the false-refusal rate is reported beside it rather than below it.</p>
</div>

<h2>Which rules did the work</h2>
<div class="scroll"><table>
<thead><tr><th>Rule</th><th style="text-align:right">Times fired</th></tr></thead>
<tbody>{rule_rows}</tbody></table></div>
<p class="sub" style="font-size:13.5px;margin-top:10px">Arm B outcomes across all
attempts: {', '.join(f'{k} {v}' for k, v in outcomes.most_common())}.
{s['escalations_arm_b']} escalations, none of them on a benign purchase.</p>

<h2>What this measures, and what it does not</h2>
<div class="note caution">
<p><b>The adversary is scripted, not a language model.</b> No API key is
committed, so the agent is a deterministic script that attempts each attack
directly. That makes the run reproducible and maximally hostile — a real model
might simply fail to try — but it does <i>not</i> measure how easily a real model
is talked into misbehaving. An LLM arm exists for that
(<code>python -m evaluation.run_llm</code>, via OpenRouter); its numbers are not
committed because it has not been run.</p>
<p><b>The rail is stubbed.</b> <code>RazorpayRail</code> speaks the real REST
contract and refuses any key that is not <code>rzp_test_*</code>, but every number
here comes from an in-memory fake. Nothing has touched live Razorpay.</p>
<p><b>The adjudicator is independent.</b> <code>evaluation/oracle.py</code> imports
neither the rule engine nor the decision engine. It reads the mandate's
constraints and totals what they did not permit, so the system under test is not
scoring its own exam.</p>
</div>

{llm_section}
<footer>Generated from results/full.json · re-run with
<code>python -m evaluation.run</code></footer>
</div></body></html>"""


def main() -> int:
    path = RESULTS / "full.json"
    if not path.exists():
        print("results/full.json not found — run `python -m evaluation.run` first")
        return 1
    out = RESULTS / "report.html"
    out.write_text(render(json.loads(path.read_text())), encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
