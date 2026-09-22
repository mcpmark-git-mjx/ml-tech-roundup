import json, os, re, urllib.request
from collections import Counter

PLID = "PLyzTA8cetPdHtlGw1X8Kt7Ea4bd27ApR7"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
API = "https://www.youtube.com/youtubei/v1/browse?key=AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8&prettyPrint=false"
PLAYER = "https://www.youtube.com/youtubei/v1/player?key=AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8&prettyPrint=false"
WEB = {"clientName": "WEB", "clientVersion": "2.20240920.01.00", "hl": "en", "gl": "US"}
ANDROID = {"clientName": "ANDROID", "clientVersion": "19.09.37", "androidSdkVersion": 30, "hl": "en", "gl": "US"}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read().decode("utf-8", "replace")


def post(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
        headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9", "Content-Type": "application/json",
                 "Origin": "https://www.youtube.com", "Referer": "https://www.youtube.com/"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read().decode("utf-8", "replace")


def walk(o, key, out):
    if isinstance(o, dict):
        if key in o:
            out.append(o[key])
        for v in o.values():
            walk(v, key, out)
    elif isinstance(o, list):
        for v in o:
            walk(v, key, out)


def parse_json_after(s, marker):
    i = s.find(marker)
    if i < 0:
        return None
    start = s.index("{", i)
    return json.JSONDecoder().raw_decode(s[start:])[0]


def txt(x):
    if not x:
        return ""
    if isinstance(x, dict):
        if "runs" in x:
            return "".join(r.get("text", "") for r in x["runs"])
        if isinstance(x.get("content"), str):
            return x["content"]
        return x.get("simpleText", "")
    return str(x)


def get_tokens(d):
    toks = []
    s = json.dumps(d)
    for m in re.finditer(r'"token":\s*"([^"]+)"', s):
        if m.group(1) not in toks:
            toks.append(m.group(1))
    return toks


def raw_items(d):
    out = []
    pvrs = []
    walk(d, "playlistVideoRenderer", pvrs)
    for p in pvrs:
        out.append({"kind": "pvr", "videoId": p.get("videoId"), "title": txt(p.get("title")),
                    "byline": txt(p.get("shortBylineText")) or txt(p.get("ownerText")),
                    "unplayable": txt(p.get("unplayableText"))})
    lus = []
    walk(d, "lockupViewModel", lus)
    for l in lus:
        vid = l.get("contentId")
        t = ""
        by = ""
        try:
            md = l.get("metadata", {}).get("lockupMetadataViewModel", {})
            t = txt(md.get("title"))
            rows = md.get("metadata", {}).get("contentMetadataViewModel", {}).get("metadataRows", [])
            parts = []
            for row in rows:
                for ppart in row.get("metadataParts", []):
                    parts.append(txt(ppart.get("text")))
            by = " | ".join([x for x in parts if x])
        except Exception:
            pass
        out.append({"kind": "lockup", "videoId": vid, "title": t, "byline": by, "unplayable": ""})
    return out


D = []
os.makedirs("out", exist_ok=True)

best = []
for params in ["wgYCCAA=", "wgYCCAA%3D"]:
    try:
        resp = post(API, {"context": {"client": WEB}, "browseId": "VL" + PLID, "params": params})
        d = json.loads(resp)
        raw = raw_items(d)
        toks = get_tokens(d)
        D.append("params=%s raw=%d toks=%d" % (params, len(raw), len(toks)))
        chunks = [raw]
        pending = list(toks)
        used = set()
        guard = 0
        while pending and guard < 20:
            guard += 1
            tok = pending.pop(0)
            if tok in used:
                continue
            used.add(tok)
            try:
                d2 = json.loads(post(API, {"context": {"client": WEB}, "browseId": "VL" + PLID,
                                          "params": params, "continuation": tok}))
            except Exception as e:
                D.append("cerr=%r" % (e,))
                continue
            got = raw_items(d2)
            D.append("c+%d" % len(got))
            chunks.append(got)
            for t in get_tokens(d2):
                if t not in used and t not in pending:
                    pending.append(t)
        merged = []
        seen = set()
        for ch in chunks:
            for it in ch:
                if it["videoId"] in seen:
                    continue
                seen.add(it["videoId"])
                merged.append(it)
        D.append("params=%s merged=%d" % (params, len(merged)))
        if len(merged) > len(best):
            best = merged
    except Exception as e:
        D.append("params=%s err=%r" % (params, e))

lines = []
for i, it in enumerate(best):
    lines.append("%d | %s | %s | %s | %s | %s" % (
        i + 1, it["videoId"], it["kind"], it["title"], it["byline"], it["unplayable"]))
open("out/full_list.txt", "w").write("\n".join(lines))
json.dump({"num": len(best), "items": best}, open("out/full_list.json", "w"), indent=1, ensure_ascii=False)

# descriptions via player API
CHUNK = 5
buf = []
idx = 0
for i, it in enumerate(best):
    desc = ""
    note = ""
    for cli in [ANDROID, WEB]:
        try:
            r = post(PLAYER, {"context": {"client": cli}, "videoId": it["videoId"]})
            pr = json.loads(r)
            vd = pr.get("videoDetails") or {}
            if vd.get("shortDescription"):
                desc = vd["shortDescription"]
                note = "via=%s title=%s author=%s" % (cli["clientName"], vd.get("title"), vd.get("author"))
                break
            if pr.get("playabilityStatus", {}).get("reason"):
                note = "reason=%s" % pr["playabilityStatus"].get("reason")
        except Exception as e:
            note = "err=%r" % (e,)
    buf.append("### %d | %s | %s | %s\nNOTE %s\n%s" % (
        i + 1, it["videoId"], it["title"], it["byline"], note, desc[:2500]))
    if len(buf) >= CHUNK:
        open("out/desc_%02d.txt" % idx, "w").write("\n\n".join(buf))
        idx += 1
        buf = []
if buf:
    open("out/desc_%02d.txt" % idx, "w").write("\n\n".join(buf))

open("out/debug.txt", "w").write("\n".join(D))
print("\n".join(D))
