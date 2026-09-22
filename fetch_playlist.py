import json, os, re, urllib.request

PLID = "PLyzTA8cetPdHtlGw1X8Kt7Ea4bd27ApR7"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
API = "https://www.youtube.com/youtubei/v1/browse?key=AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8&prettyPrint=false"
WEB = {"clientName": "WEB", "clientVersion": "2.20240920.01.00", "hl": "en", "gl": "US"}

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

def extract_items(d):
    out = []
    seen = set()

    def add(vid, title, byline="", length="", info=""):
        if not vid or vid in seen:
            return
        seen.add(vid)
        out.append({"videoId": vid, "title": title or "", "byline": byline or "",
                    "lengthText": length or "", "videoInfo": info or ""})

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
    return out

def dedupe(lists):
    seen = set()
    out = []
    for l in lists:
        for it in l:
            if it["videoId"] in seen:
                continue
            seen.add(it["videoId"])
            out.append(it)
    return out

def run_source(ctx, extra):
    try:
        resp = post(API, dict({"context": {"client": ctx}}, **extra))
        d = json.loads(resp)
    except Exception as e:
        return [], "err=%r" % (e,)
    chunks = [extract_items(d)]
    pending = get_tokens(d)
    used = set()
    guard = 0
    log = ["first=%d" % len(chunks[0])]
    while pending and guard < 30:
        guard += 1
        tok = pending.pop(0)
        if tok in used:
            continue
        used.add(tok)
        try:
            d2 = json.loads(post(API, {"context": {"client": ctx}, "continuation": tok}))
        except Exception as e:
            log.append("cerr=%r" % (e,))
            continue
        got = extract_items(d2)
        log.append("c+%d" % len(got))
        chunks.append(got)
        for t in get_tokens(d2):
            if t not in used and t not in pending:
                pending.append(t)
    return dedupe(chunks), ",".join(log)

diag = []

# --- A) browseId VL<playlist>
browse_items = []
for cli in [WEB,
            {"clientName": "ANDROID", "clientVersion": "19.09.37", "androidSdkVersion": 30, "hl": "en", "gl": "US"},
            {"clientName": "MWEB", "clientVersion": "2.20240920.01.00", "hl": "en", "gl": "US"}]:
    got, log = run_source(cli, {"browseId": "VL" + PLID})
    diag.append("browse[%s] %s -> %d" % (cli["clientName"], log, len(got)))
    if got:
        browse_items = got
        break

# --- B) web page
page_items = []
try:
    page = get("https://www.youtube.com/playlist?list=%s&hl=en&persist_hl=1" % PLID)
    data = parse_json_after(page, "var ytInitialData = ")
    chunks = [extract_items(data)]
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
            d2 = json.loads(post(API, {"context": {"client": WEB}, "continuation": tok}))
        except Exception:
            continue
        chunks.append(extract_items(d2))
        for t in get_tokens(d2):
            if t not in used and t not in pending:
                pending.append(t)
    page_items = dedupe(chunks)
    diag.append("page_items=%d" % len(page_items))
    diag.append("page_len=%d" % len(page))
    count_texts = re.findall(r"([\d,]+)\s*videos?", page)
    diag.append("count_texts=" + ",".join(count_texts[:8]))
    diag.append("private_str=%d deleted_str=%d" % (page.count("Private video"), page.count("Deleted video")))
except Exception as e:
    diag.append("page_err=%r" % (e,))

final = dedupe([page_items, browse_items])
diag.append("final=%d" % len(final))

os.makedirs("out", exist_ok=True)
open("out/diag.txt", "w").write("\n".join(diag))
json.dump({"num": len(final), "items": final}, open("out/playlist.json", "w"), indent=1, ensure_ascii=False)
lines = []
for i, it in enumerate(final):
    lines.append("%d | %s | %s | %s | %s" % (i + 1, it["videoId"], it["title"], it["byline"], it["lengthText"]))
open("out/titles.txt", "w").write("\n".join(lines))

if final:
    CHUNK = 6
    buf = []
    idx = 0
    for i, it in enumerate(final):
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

print("DONE items=%d" % len(final))
print("\n".join(diag))
