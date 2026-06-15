#!/usr/bin/env python3
"""
Migrate a Miro board into an Excalidraw scene (.excalidraw JSON).

The Obsidian Excalidraw plugin imports .excalidraw files natively (drag into the
vault, or "Convert to Excalidraw drawing"). Miro shapes/sticky-notes/cards/text
become rectangles with bound text; connectors become arrows bound to those
rectangles so they stay attached when you move things around.

Usage:
    export MIRO_TOKEN="<your-access-token>"
    python3 miro_to_excalidraw.py <board_id> <output.excalidraw>

Board id is the part after /board/ in the Miro URL.
"""
import base64
import html
import json
import math
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request

API = "https://api.miro.com/v2"
NOW = int(time.time() * 1000)


def api_get(path, token):
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


def fetch_mindmap(board_id, token):
    """Map mindmap node id -> {text, fontSize, color} via the experimental API.

    The regular /items endpoint returns mindmap_node with empty data; the node's
    text only lives under the experimental mindmap_nodes endpoint.
    """
    out = {}
    cursor = None
    while True:
        url = (f"https://api.miro.com/v2-experimental/boards/{board_id}"
               f"/mindmap_nodes?limit=50" + (f"&cursor={cursor}" if cursor else ""))
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {token}", "Accept": "application/json"})
        try:
            page = json.loads(urllib.request.urlopen(req).read())
        except urllib.error.HTTPError:
            return out
        for n in page.get("data", []):
            nv = (n.get("data") or {}).get("nodeView") or {}
            nvs = nv.get("style") or {}
            ns = n.get("style") or {}
            out[n["id"]] = {
                "text": (nv.get("data") or {}).get("content") or "",
                "fontSize": nvs.get("fontSize") or ns.get("fontSize"),
                "color": ns.get("nodeColor"),
                "fillOpacity": nvs.get("fillOpacity"),
                "textColor": nvs.get("color"),
            }
        cursor = page.get("cursor")
        if not cursor:
            break
    return out


def fetch_image(url, token):
    """Download a Miro image, returning (bytes, mime_type)."""
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}", "Accept": "application/json"})
    with urllib.request.urlopen(req) as resp:
        ctype = resp.headers.get("Content-Type", "")
        body = resp.read()
    if "application/json" in ctype:  # redirect=false returns {"url": "..."}
        direct = json.loads(body).get("url")
        if not direct:
            raise ValueError("no image url in response")
        with urllib.request.urlopen(direct) as r2:
            return r2.read(), (r2.headers.get("Content-Type") or "image/png").split(";")[0]
    return body, (ctype or "image/png").split(";")[0]


def strip_html(s):
    if not s:
        return ""
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</p>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s).strip()


def rand():
    return random.randint(1, 2**31 - 1)


def base(eid, etype, x, y, w, h, **extra):
    """Common fields every Excalidraw element needs."""
    el = {
        "id": eid,
        "type": etype,
        "x": x, "y": y, "width": w, "height": h,
        "angle": 0,
        "strokeColor": "#1e1e1e",
        "backgroundColor": "transparent",
        "fillStyle": "solid",
        "strokeWidth": 2,
        "strokeStyle": "solid",
        "roughness": 0,
        "opacity": 100,
        "groupIds": [],
        "frameId": None,
        "roundness": None,
        "seed": rand(),
        "version": 1,
        "versionNonce": rand(),
        "isDeleted": False,
        "boundElements": [],
        "updated": NOW,
        "link": None,
        "locked": False,
    }
    el.update(extra)
    return el


def edge_point(rect, dx, dy):
    """Border point of a rect/ellipse from its center along direction (dx, dy)."""
    cx = rect["x"] + rect["width"] / 2
    cy = rect["y"] + rect["height"] / 2
    hw = rect["width"] / 2
    hh = rect["height"] / 2
    if rect.get("type") == "ellipse":
        denom = math.hypot(dx / hw, dy / hh) or 1.0
        t = 1.0 / denom
        return cx + dx * t, cy + dy * t
    sx = hw / abs(dx) if dx else float("inf")
    sy = hh / abs(dy) if dy else float("inf")
    s = min(sx, sy)
    return cx + dx * s, cy + dy * s


def wrap_lines(text, max_chars):
    """Greedy word-wrap; hard-splits words longer than max_chars."""
    out = []
    for para in text.split("\n"):
        line = ""
        for word in para.split(" "):
            while len(word) > max_chars:
                if line:
                    out.append(line)
                    line = ""
                out.append(word[:max_chars])
                word = word[max_chars:]
            cand = word if not line else line + " " + word
            if len(cand) <= max_chars:
                line = cand
            else:
                out.append(line)
                line = word
        out.append(line)
    return out or [""]


def fit_text(text, w, h, max_fs=20, pad=12):
    """Pick a font size + wrap text so it fits inside a w x h box."""
    avail_w = max(24, w - 2 * pad)
    avail_h = max(16, h - 2 * pad)
    for fs in range(int(max_fs), 7, -1):
        max_chars = max(1, int(avail_w / (fs * 0.55)))
        lines = wrap_lines(text, max_chars)
        if len(lines) * fs * 1.25 <= avail_h:
            return "\n".join(lines), fs, lines
    fs = 8
    max_chars = max(1, int(avail_w / (fs * 0.55)))
    lines = wrap_lines(text, max_chars)
    return "\n".join(lines), fs, lines


def hex8(color, opacity):
    """Bake a 0-1 fill opacity into an #rrggbb color as #rrggbbaa."""
    if not color or not color.startswith("#") or len(color) != 7:
        return color or "transparent"
    try:
        a = max(0, min(255, round(float(opacity) * 255)))
    except (TypeError, ValueError):
        return color
    return color + format(a, "02x")


def stroke_style(miro):
    return {"dashed": "dashed", "dotted": "dotted"}.get((miro or "").lower(), "solid")


def stroke_w(miro):
    try:
        w = float(miro)
    except (TypeError, ValueError):
        return 2
    return 1 if w < 2 else (2 if w < 5 else 4)


def font_family(miro):
    # current Excalidraw fonts: Comic Shanns (8) = code/mono, Nunito (6) = normal
    return 8 if "mono" in (miro or "").lower() else 6


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    board_id, out_path = sys.argv[1], sys.argv[2]
    token = os.environ.get("MIRO_TOKEN")
    if not token:
        sys.exit("Set MIRO_TOKEN env var with your Miro access token.")

    elements = []
    files = {}  # excalidraw file store for embedded images
    rects = {}  # miro id -> excalidraw element (for connector binding)
    mindmap = fetch_mindmap(board_id, token)

    def fnum(v, d):
        try:
            return float(v)
        except (TypeError, ValueError):
            return d

    def add_bound_text(container, text, fs0, color="#1e1e1e",
                       halign="center", valign="middle", ff=6):
        """Add a text element bound inside a container, honoring h/v alignment."""
        cid = container["id"]
        cw, ch = container["width"], container["height"]
        wrapped, fs, lines = fit_text(text, cw, ch, max_fs=fs0)
        th = len(lines) * fs * 1.25
        if valign == "top":
            ty = container["y"] + 12
        elif valign == "bottom":
            ty = container["y"] + ch - th - 12
        else:
            ty = container["y"] + (ch - th) / 2
        t = base(cid + "_t", "text",
                 container["x"] + 12, ty, cw - 24, th,
                 text=wrapped, originalText=wrapped,
                 fontSize=fs, fontFamily=ff,
                 textAlign=halign, verticalAlign=valign,
                 lineHeight=1.25, baseline=int(fs * 0.8),
                 containerId=cid, strokeColor=color)
        container["boundElements"].append({"type": "text", "id": cid + "_t"})
        elements.append(t)

    for it in paginate(f"/boards/{board_id}/items", token):
        itype = it["type"]
        pos = it.get("position") or {}
        geo = it.get("geometry") or {}
        data = it.get("data") or {}
        style = it.get("style") or {}
        w = float(geo.get("width") or 200)
        h = float(geo.get("height") or 100)
        x = float(pos.get("x") or 0) - w / 2
        y = float(pos.get("y") or 0) - h / 2

        # 1) plain text — standalone, no frame.
        # Miro shrinks text to fit the box width but never grows past fontSize,
        # so the rendered size is min(fontSize, width-fit). One line per paragraph.
        if itype == "text":
            text = strip_html(data.get("content") or "")
            if not text:
                continue
            miro_fs = fnum(style.get("fontSize"), 20)
            lines = text.split("\n")
            longest = max((len(l) for l in lines), default=1) or 1
            box_w = w or 400
            fit_fs = box_w / (longest * 0.5)
            fs = max(8.0, min(miro_fs, fit_fs))
            color = style.get("color")
            color = color if (color or "").startswith("#") else "#1e1e1e"
            natural_w = max(box_w, longest * fs * 0.6)
            t = base(it["id"], "text", x, y, natural_w, len(lines) * fs * 1.25,
                     text="\n".join(lines), originalText="\n".join(lines),
                     fontSize=fs, fontFamily=font_family(style.get("fontFamily")),
                     textAlign=(style.get("textAlign") or "left"), verticalAlign="top",
                     lineHeight=1.25, baseline=int(fs * 0.8),
                     autoResize=True, strokeColor=color)
            rects[it["id"]] = t
            elements.append(t)
            continue

        # 2) image — embed actual bytes from Miro as an Excalidraw image
        if itype == "image":
            try:
                raw, mime = fetch_image(data.get("imageUrl") or "", token)
                fid = "img_" + it["id"]
                files[fid] = {
                    "mimeType": mime,
                    "id": fid,
                    "dataURL": f"data:{mime};base64," + base64.b64encode(raw).decode(),
                    "created": NOW,
                }
                img = base(it["id"], "image", x, y, w, h,
                           fileId=fid, status="saved", scale=[1, 1],
                           strokeColor="transparent")
                rects[it["id"]] = img
                elements.append(img)
            except Exception:  # fall back to a labeled placeholder
                r = base(it["id"], "rectangle", x, y, w, h,
                         backgroundColor="#f1f3f5", fillStyle="solid",
                         strokeStyle="dashed", roundness={"type": 3})
                rects[it["id"]] = r
                elements.append(r)
                add_bound_text(r, "🖼 image", 16, "#868e96")
            continue

        # 3) mindmap node — filled (fillOpacity>0) -> box; else plain text, no frame
        if itype == "mindmap_node":
            mm = mindmap.get(it["id"], {})
            text = strip_html(mm.get("text") or "")
            if not text:
                continue
            fs0 = fnum(mm.get("fontSize") or style.get("fontSize"), 16)
            fop = fnum(mm.get("fillOpacity"), 0.0)
            tcolor = mm.get("textColor")
            tcolor = tcolor if (tcolor or "").startswith("#") else "#1e1e1e"
            if fop > 0:
                ncolor = mm.get("color")
                ncolor = ncolor if (ncolor or "").startswith("#") else "#1971c2"
                r = base(it["id"], "rectangle", x, y, w, h,
                         backgroundColor=hex8(ncolor, fop), fillStyle="solid",
                         strokeColor=ncolor, strokeWidth=2, roundness={"type": 3})
                rects[it["id"]] = r
                elements.append(r)
                add_bound_text(r, text, fs0, tcolor)
            else:
                wrapped, fs, lines = fit_text(text, w, h, max_fs=fs0)
                th = len(lines) * fs * 1.25
                t = base(it["id"], "text", x, y + (h - th) / 2, w, th,
                         text=wrapped, originalText=wrapped,
                         fontSize=fs, fontFamily=6,
                         textAlign="center", verticalAlign="middle",
                         lineHeight=1.25, baseline=int(fs * 0.8),
                         strokeColor=tcolor)
                rects[it["id"]] = t
                elements.append(t)
            continue

        # 4) shape — rect / ellipse / diamond + bound text
        text = strip_html(data.get("content") or data.get("title") or "")
        shp = (data.get("shape") or "").lower()
        if shp in ("circle", "oval", "ellipse"):
            etype, roundness = "ellipse", None
        elif shp in ("rhombus", "diamond"):
            etype, roundness = "diamond", None
        elif shp in ("round_rectangle", "rounded_rectangle"):
            etype, roundness = "rectangle", {"type": 3}
        else:  # plain rectangle and other shapes keep sharp corners
            etype, roundness = "rectangle", None
        fill = style.get("fillColor")
        bg = hex8(fill, style.get("fillOpacity")) if (fill and fill.startswith("#")) else "transparent"
        sc = style.get("borderColor")
        sc = sc if (sc or "").startswith("#") else "#1e1e1e"
        rect = base(it["id"], etype, x, y, w, h,
                    backgroundColor=bg, fillStyle="solid", roundness=roundness,
                    strokeColor=sc, strokeWidth=stroke_w(style.get("borderWidth")),
                    strokeStyle=stroke_style(style.get("borderStyle")))
        rects[it["id"]] = rect
        elements.append(rect)
        if text:
            tcolor = style.get("color")
            tcolor = tcolor if (tcolor or "").startswith("#") else "#1e1e1e"
            halign = style.get("textAlign") or "center"
            valign = style.get("textAlignVertical") or "middle"
            add_bound_text(rect, text, fnum(style.get("fontSize"), 16), tcolor,
                           halign, valign, font_family(style.get("fontFamily")))

    def attach(item, position):
        """Exact point on an item from a Miro percent position (else None)."""
        if not position:
            return None
        try:
            fx = float(str(position.get("x", "50%")).rstrip("%")) / 100.0
            fy = float(str(position.get("y", "50%")).rstrip("%")) / 100.0
        except (TypeError, ValueError):
            return None
        return item["x"] + fx * item["width"], item["y"] + fy * item["height"]

    for c in paginate(f"/boards/{board_id}/connectors", token):
        start = (c.get("startItem") or {}).get("id")
        end = (c.get("endItem") or {}).get("id")
        if start not in rects or end not in rects:
            continue
        a, b = rects[start], rects[end]
        acx, acy = a["x"] + a["width"] / 2, a["y"] + a["height"] / 2
        bcx, bcy = b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
        # exact Miro attach points if present, else clip to border toward other center
        sp = (attach(a, (c.get("startItem") or {}).get("position"))
              or edge_point(a, bcx - acx, bcy - acy))
        ep = (attach(b, (c.get("endItem") or {}).get("position"))
              or edge_point(b, acx - bcx, acy - bcy))
        sx, sy = sp
        ex, ey = ep
        if sx == ex and sy == ey:
            continue
        cstyle = c.get("style") or {}
        acolor = cstyle.get("strokeColor")
        acolor = acolor if (acolor or "").startswith("#") else "#1e1e1e"
        # Miro 'curved' connectors -> bowed 3-point arc; else straight
        dxl, dyl = ex - sx, ey - sy
        if c.get("shape") == "curved":
            mx = (sx + ex) / 2 - dyl * 0.15      # perpendicular bow ~15% of length
            my = (sy + ey) / 2 + dxl * 0.15
            pts = [[0.0, 0.0], [mx - sx, my - sy], [ex - sx, ey - sy]]
            rnd = {"type": 2}
        else:
            pts = [[0.0, 0.0], [dxl, dyl]]
            rnd = None
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        aid = f"arrow_{c['id']}"
        arrow = base(aid, "arrow", sx, sy, max(xs) - min(xs), max(ys) - min(ys),
                     points=pts, roundness=rnd,
                     strokeColor=acolor,
                     strokeWidth=stroke_w(cstyle.get("strokeWidth")),
                     strokeStyle=stroke_style(cstyle.get("strokeStyle")),
                     startBinding={"elementId": start, "focus": 0, "gap": 1},
                     endBinding={"elementId": end, "focus": 0, "gap": 1},
                     startArrowhead=None, endArrowhead="arrow")
        a["boundElements"].append({"type": "arrow", "id": aid})
        b["boundElements"].append({"type": "arrow", "id": aid})
        elements.append(arrow)

    # z-order: large shapes behind small; arrows above shapes; loose text on top
    containers = sorted(
        (e for e in elements if e["type"] in ("rectangle", "ellipse", "diamond", "image")),
        key=lambda e: e["width"] * e["height"], reverse=True)
    bound = {}
    for e in elements:
        if e["type"] == "text" and e.get("containerId"):
            bound.setdefault(e["containerId"], []).append(e)
    arrows = [e for e in elements if e["type"] == "arrow"]
    loose = [e for e in elements if e["type"] == "text" and not e.get("containerId")]
    ordered = []
    for c in containers:
        ordered.append(c)
        ordered.extend(bound.get(c["id"], []))
    ordered.extend(arrows)
    ordered.extend(loose)
    elements = ordered

    scene = {
        "type": "excalidraw",
        "version": 2,
        "source": "miro-to-excalidraw",
        "elements": elements,
        "appState": {"gridSize": None, "viewBackgroundColor": "#ffffff"},
        "files": files,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(scene, f, ensure_ascii=False, indent=2)
    rect_n = len(rects)
    arrow_n = sum(1 for e in elements if e["type"] == "arrow")
    print(f"Wrote {rect_n} shapes, {arrow_n} arrows -> {out_path}")


if __name__ == "__main__":
    main()
