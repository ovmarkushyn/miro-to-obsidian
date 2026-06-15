#!/usr/bin/env python3
"""
Migrate a Miro board into an Obsidian Canvas (.canvas) file.

Maps Miro items (shapes, sticky notes, text, cards, frames) to Canvas nodes,
and Miro connectors to Canvas edges. Coordinates, sizes and fill colors are
preserved. Miro positions are center-based; Canvas is top-left based, so we
convert.

Usage:
    export MIRO_TOKEN="<your-access-token>"
    python3 miro_to_canvas.py <board_id> <output.canvas>

Get a token: https://miro.com/app/settings/user-profile/  -> developer apps,
or any app with boards:read scope. Board id is the part after /board/ in the URL.
"""
import html
import json
import os
import re
import sys
import urllib.request
import urllib.error

API = "https://api.miro.com/v2"


def api_get(path, token):
    """GET a Miro API path, returning parsed JSON. Handles bearer auth."""
    req = urllib.request.Request(API + path, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        sys.exit(f"Miro API error {e.code} on {path}: {e.read().decode()[:300]}")


def paginate(path, token):
    """Yield every item across cursor-paginated Miro list endpoints."""
    cursor = None
    while True:
        sep = "&" if "?" in path else "?"
        url = f"{path}{sep}limit=50" + (f"&cursor={cursor}" if cursor else "")
        page = api_get(url, token)
        for item in page.get("data", []):
            yield item
        cursor = page.get("cursor")
        if not cursor:
            break


def strip_html(s):
    """Miro text/content arrives as HTML; flatten to plain text for Canvas."""
    if not s:
        return ""
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</p>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s).strip()


def norm_color(style):
    """Map a Miro fill color to a Canvas color (hex passthrough)."""
    if not style:
        return None
    c = style.get("fillColor") or style.get("color")
    if not c or c in ("transparent", "#ffffff", "none"):
        return None
    return c if c.startswith("#") else None  # named colors dropped; hex kept


def best_sides(a, b):
    """Pick edge attach sides from relative centers of two nodes."""
    ax, ay = a["_cx"], a["_cy"]
    bx, by = b["_cx"], b["_cy"]
    if abs(bx - ax) >= abs(by - ay):
        return ("right", "left") if bx >= ax else ("left", "right")
    return ("bottom", "top") if by >= ay else ("top", "bottom")


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    board_id, out_path = sys.argv[1], sys.argv[2]
    token = os.environ.get("MIRO_TOKEN")
    if not token:
        sys.exit("Set MIRO_TOKEN env var with your Miro access token.")

    nodes, by_id = [], {}
    for it in paginate(f"/boards/{board_id}/items", token):
        pos = it.get("position") or {}
        geo = it.get("geometry") or {}
        data = it.get("data") or {}
        w = int(geo.get("width") or 200)
        h = int(geo.get("height") or 100)
        cx = float(pos.get("x") or 0)
        cy = float(pos.get("y") or 0)
        text = strip_html(data.get("content") or data.get("title") or "")
        node = {
            "id": it["id"],
            "type": "text",
            "x": int(cx - w / 2),
            "y": int(cy - h / 2),
            "width": w,
            "height": h,
            "text": text or " ",
            "_cx": cx,
            "_cy": cy,
        }
        color = norm_color(it.get("style"))
        if color:
            node["color"] = color
        nodes.append(node)
        by_id[it["id"]] = node

    edges = []
    for c in paginate(f"/boards/{board_id}/connectors", token):
        start = (c.get("startItem") or {}).get("id")
        end = (c.get("endItem") or {}).get("id")
        if start not in by_id or end not in by_id:
            continue
        fs, ts = best_sides(by_id[start], by_id[end])
        edge = {
            "id": c["id"],
            "fromNode": start,
            "fromSide": fs,
            "toNode": end,
            "toSide": ts,
        }
        label = strip_html(((c.get("captions") or [{}])[0]).get("content"))
        if label:
            edge["label"] = label
        edges.append(edge)

    for n in nodes:
        n.pop("_cx", None)
        n.pop("_cy", None)

    canvas = {"nodes": nodes, "edges": edges}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(canvas, f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(nodes)} nodes, {len(edges)} edges -> {out_path}")


if __name__ == "__main__":
    main()
