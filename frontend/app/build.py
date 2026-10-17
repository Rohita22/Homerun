#!/usr/bin/env python3
"""Build the served UI: dist/index.html = the design file + logic.js.

The design (../design/Homerun.html) is the source of truth for markup and styling and is never
edited. This script makes exactly two kinds of change to a copy of it:

1. the inline ``<script type="text/x-dc" data-dc-script>`` body is replaced by ``logic.js``
   (mock data -> backend calls), and
2. ten hard-coded prototype strings (plus the listing-photo layers) (demo-data badge, "sample trace" banner, p50/p95/errors
   tiles, model/deploy/source rows) become ``{{ bindings }}`` fed by real health/metrics/trace
   data. Styles and layout are untouched.

Each replacement must match exactly once, so a changed design file fails loudly instead of
silently shipping fake numbers.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DESIGN = HERE.parent / "design" / "Homerun.html"
LOGIC = HERE / "logic.js"
OUT = HERE / "dist" / "index.html"

TEXT_BINDINGS = [
    ('title="Demo inventory: synthetic fixture records, not live listings"', 'title="{{ srcTitle }}"'),
    (
        'background:var(--butter);box-shadow:0 0 10px var(--butter)"></span>demo data</span>',
        'background:{{ srcDot }};box-shadow:0 0 10px {{ srcDot }}"></span>{{ srcLabel }}</span>',
    ),
    (
        "sample trace</span>No live backend in this prototype. Wire /v1/trace and /metrics to fill this for real.",
        "{{ ev.bannerTitle }}</span>{{ ev.banner }}",
    ),
    (">412ms</div>", ">{{ ev.p50 }}</div>"),
    (">unavailable · n&lt;20</div>", ">{{ ev.p95 }}</div>"),
    (">0/14</div>", ">{{ ev.errors }}</div>"),
    ("<span>hdb-resale-gbm v0.4.2</span>", "<span>{{ ev.model }}</span>"),
    ("<span>IBM LinuxONE · s390x · FastAPI</span>", "<span>{{ ev.deploy }}</span>"),
    (">demo fixture · 7 records</span>", ">{{ ev.source }}</span>"),
    ("· demo source</div>", "· PropertyGuru</div>"),
    # --- listing photos: an image layer inside the existing placeholder boxes -------------------
    (
        """<span style="position:absolute;top:14px;left:14px;padding:7px 13px;border-radius:999px;background:var(--ink);color:var(--bg);font-weight:700;font-size:14px">#{{ c.rank }}</span>""",
        """<sc-if value="{{ c.hasPhoto }}"><img src="{{ c.photo }}" alt="" referrerpolicy="no-referrer" draggable="false" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;pointer-events:none"><div style="position:absolute;left:0;right:0;bottom:0;height:90px;background:linear-gradient(transparent,oklch(0.15 0.02 280 / .55));pointer-events:none"></div></sc-if><span style="position:absolute;top:14px;left:14px;padding:7px 13px;border-radius:999px;background:var(--ink);color:var(--bg);font-weight:700;font-size:14px">#{{ c.rank }}</span>""",
    ),
    (
        """<span style="position:absolute;bottom:14px;left:16px;font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--muted)">[ listing photo ]</span>""",
        """<span style="position:absolute;bottom:14px;left:16px;font-family:'JetBrains Mono',monospace;font-size:11px;color:{{ c.capColor }}">{{ c.photoCap }}</span>""",
    ),
    (
        """color:var(--muted);white-space:nowrap"><span style="width:7px;height:7px;border-radius:50%;background:var(--mint)"></span>active · {{ c.id }}</span>""",
        """color:{{ c.capColor }};white-space:nowrap"><span style="width:7px;height:7px;border-radius:50%;background:var(--mint)"></span>active · {{ c.id }}</span>""",
    ),
    (
        """<button onClick="{{ goResults }}" style="position:absolute;top:16px;left:16px;""",
        """<sc-if value="{{ d.hasPhoto }}"><img src="{{ d.photo }}" alt="" referrerpolicy="no-referrer" onClick="{{ d.nextPhoto }}" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;border-radius:32px;cursor:pointer"><div style="position:absolute;left:0;right:0;bottom:0;height:110px;border-radius:0 0 32px 32px;background:linear-gradient(transparent,oklch(0.15 0.02 280 / .55));pointer-events:none"></div></sc-if><button onClick="{{ goResults }}" style="position:absolute;top:16px;left:16px;""",
    ),
    (
        """<span style="position:absolute;bottom:18px;left:22px;font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--muted)">[ listing photos ]</span>""",
        """<span style="position:absolute;bottom:18px;left:22px;font-family:'JetBrains Mono',monospace;font-size:11px;color:{{ d.capColor }};pointer-events:none">{{ d.photoCap }}</span>""",
    ),
    ("""<span style="font-size:18px;font-weight:600">HDB, condo or both?</span>""", """<span style="font-size:18px;font-weight:600">{{ chat.askText }}</span>"""),
    (">voice preview · transcript only, audio isn’t stored</span>", ">{{ v.foot }}</span>"),
    # --- real map (Leaflet + OpenStreetMap, filled in by logic.js) instead of the schematic blob ---------
    (
        """<div style="position:absolute;left:8%;top:20%;width:84%;height:58%;border-radius:46% 54% 42% 58%/58% 42% 58% 42%;background:var(--soft)"></div>""",
        """<div id="hr-map" style="position:absolute;inset:0;z-index:0"></div>""",
    ),
    (
        """<span style="position:absolute;left:20px;bottom:16px;font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--muted)">schematic · from listing coordinates</span>""",
        "",
    ),
    ("flex:3 1 640px;position:relative;min-height:440px", "flex:3 1 640px;position:relative;min-height:600px;isolation:isolate"),
    (
        """<div style="display:flex;gap:6px"><sc-if value="{{ hub.filtered }}" """,
        """<div style="display:flex;gap:6px"><button onClick="{{ openCmpV }}" aria-label="Compare viewings and notes" style="border:0;background:var(--soft);border-radius:999px;padding:11px 16px;cursor:pointer;font-size:14px;font-weight:500;white-space:nowrap">⇆ Compare</button><sc-if value="{{ hub.filtered }}" """,
    ),
    # --- the remaining photo placeholders: compare, A/B refine, interest, my-move shortlist ----------
    (
        """padding:0"><span style="position:absolute;top:10px;left:10px;width:38px;height:38px;""",
        """padding:0"><sc-if value="{{ col.hasPhoto }}"><img src="{{ col.photo }}" alt="" referrerpolicy="no-referrer" draggable="false" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;border-radius:24px;pointer-events:none"></sc-if><span style="position:absolute;top:10px;left:10px;width:38px;height:38px;""",
    ),
    (
        """position:relative"><span style="position:absolute;top:12px;left:12px;width:48px;height:48px;""",
        """position:relative;overflow:hidden"><sc-if value="{{ p.hasPhoto }}"><img src="{{ p.photo }}" alt="" referrerpolicy="no-referrer" draggable="false" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;border-radius:24px;pointer-events:none"></sc-if><span style="position:absolute;top:12px;left:12px;width:48px;height:48px;""",
    ),
    (
        """<span style="position:absolute;top:16px;left:16px;padding:8px 14px;border-radius:999px;background:var(--tile);font-family:'JetBrains Mono',monospace;font-size:12px">{{ it.id }}</span>""",
        """<sc-if value="{{ it.hasPhoto }}"><img src="{{ it.photo }}" alt="" referrerpolicy="no-referrer" draggable="false" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;border-radius:32px;pointer-events:none"></sc-if><span style="position:absolute;top:16px;left:16px;padding:8px 14px;border-radius:999px;background:var(--tile);font-family:'JetBrains Mono',monospace;font-size:12px">{{ it.id }}</span>""",
    ),
    (
        """<span style="position:absolute;top:8px;left:8px;padding:4px 9px;border-radius:999px;background:var(--g-mint);color:var(--on);font-family:'JetBrains Mono',monospace;font-size:10px">{{ sh.score }}</span>""",
        """<sc-if value="{{ sh.hasPhoto }}"><img src="{{ sh.photo }}" alt="" referrerpolicy="no-referrer" draggable="false" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;border-radius:18px;pointer-events:none"></sc-if><span style="position:absolute;top:8px;left:8px;padding:4px 9px;border-radius:999px;background:var(--g-mint);color:var(--on);font-family:'JetBrains Mono',monospace;font-size:10px">{{ sh.score }}</span>""",
    ),
]
SCRIPT_RE = re.compile(r'(<script type="text/x-dc" data-dc-script[^>]*>)(.*?)(</script>)', re.DOTALL)


def main() -> int:
    html = DESIGN.read_text(encoding="utf-8")
    logic = LOGIC.read_text(encoding="utf-8")
    if "</script" in logic.lower():
        print("logic.js must not contain a closing script tag", file=sys.stderr)
        return 1

    matches = SCRIPT_RE.findall(html)
    if len(matches) != 1:
        print(f"expected exactly one x-dc logic script, found {len(matches)}", file=sys.stderr)
        return 1
    html = SCRIPT_RE.sub(lambda m: m.group(1) + "\n" + logic + m.group(3), html, count=1)

    for old, new in TEXT_BINDINGS:
        if html.count(old) != 1:
            print(f"design changed: {old[:60]!r} matched {html.count(old)}x (need 1)", file=sys.stderr)
            return 1
        html = html.replace(old, new)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT} ({len(html) // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
