import json, os, re, urllib.request

PLID = "PLyzTA8cetPdHtlGw1X8Kt7Ea4bd27ApR7"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
API = "https://www.youtube.com/youtubei/v1/browse?key=AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8&prettyPrint=false"
WEBCTX = {"context": {"client": {"clientName": "WEB", "clientVersion": "2.20240920.01.00", "hl": "en", "gl": "US"}}}

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
    for key in ("continuationCommand", "getContinuationCommand", "nextContinuationData"):
        found = []
        walk(d, key, found)
        for f in found:
            t = f.get("token") if isinstance(f, dict) else None
            if t and t not in toks:
                toks.append(t)
    return toks

items = []
seen = set()
diag = []

def add(vid, title, byline="", length="", info=""):
    if not vid or vid in seen:
        return
    seen.add(vid)
    items.append({"videoId": vid, "title": title or "", "byline": byline or "",
                  "lengthText": length or "", "videoInfo": info or ""})

def extract(d):
    n0 = len(items)
    pvrs = []
    walk(d, "playlistVideoRenderer", pvrs)
    for p in pvrs:
        add(p.get("videoId"), txt(p.get("title")),
            txt(p.get("shortBylineText")) or txt(p.get("longBylineText")) or txt(p.get("ownerText")),
            txt(p.get("lengthText")), txt(p.get("videoInfo")))
    lus = []
    walk(d, "lockupViewModel", lus)
    for l in lus:
        vid = l.get("contentId")
        if not vid:
            continue
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
        add(vid, t, by, "", "")
    vrs = []
    walk(d, "videoRenderer", vrs)
    for p in vrs:
        add(p.get("videoId"), txt(p.get("title")),
            txt(p.get("ownerText")) or txt(p.get("longBylineText")),
            txt(p.get("lengthText")), txt(p.get("publishedTimeText")))
    return len(items) - n0

page = ""
try:
    page = get("https://www.youtube.com/playlist?list=%s&hl=en&persist_hl=1" % PLID)
    diag.append("page_len=%d" % len(page))
    count_texts = re.findall(r"([\d,]+)\s*videos?", page)
    diag.append("count_texts=" + ",".join(count_texts[:8]))
    data = parse_json_after(page, "var ytInitialData = ")
    diag.append("extracted_page=%d" % extract(data))
    pending = get_tokens(data)
    used = set()
    guard = 0
    while pending and guard < 30:
        guard += 1
        tok = pending.pop(0)
        if tok in used:
            continue
        used.add(tok)
        try:
            d2 = json.loads(post(API, dict(WEBCTX, continuation=tok)))
        except Exception as e:
            diag.append("cont_err=%r" % (e,))
            continue
        before = len(items)
        extract(d2)
        diag.append("cont_new=%d total=%d" % (len(items) - before, len(items)))
        for t in get_tokens(d2):
            if t not in used and t not in pending:
                pending.append(t)
    diag.append("final=%d" % len(items))
except Exception as e:
    diag.append("page_err=%r" % (e,))

os.makedirs("out", exist_ok=True)
open("out/diag.txt", "w").write("\n".join(diag))
json.dump({"num": len(items), "items": items}, open("out/playlist.json", "w"), indent=1, ensure_ascii=False)
lines = []
for i, it in enumerate(items):
    lines.append("%d | %s | %s | %s | %s" % (i + 1, it["videoId"], it["title"], it["byline"], it["lengthText"]))
open("out/titles.txt", "w").write("\n".join(lines))

if items:
    CHUNK = 6
    buf = []
    idx = 0
    for i, it in enumerate(items):
        desc = ""
        err = ""
        try:
            w = get("https://www.youtube.com/watch?v=%s&hl=en" % it["videoId"])
            pr = parse_json_after(w, "ytInitialPlayerResponse = ")
            if pr:
                desc = ((pr.get("videoDetails") or {}).get("shortDescription")) or ""
            if not desc:
                m = re.search(r'"shortDescription"\s*:\s*"((?:[^"\\]|\\.)*)"', w)
                if m:
                    desc = m.group(1)
        except Exception as e:
            err = "ERROR %r" % (e,)
        buf.append("### %d | %s | %s | %s | %s | %s | %s\n%s" % (
            i + 1, it["videoId"], it["title"], it["byline"], it["lengthText"], it["videoInfo"], err, desc[:2200]))
        if len(buf) >= CHUNK:
            open("out/d_%02d.txt" % idx, "w").write("\n\n".join(buf))
            idx += 1
            buf = []
    if buf:
        open("out/d_%02d.txt" % idx, "w").write("\n\n".join(buf))

print("DONE items=%d" % len(items))
print("\n".join(diag))
