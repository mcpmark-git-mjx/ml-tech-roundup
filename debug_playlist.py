import json, os, re, urllib.request

PLID = "PLyzTA8cetPdHtlGw1X8Kt7Ea4bd27ApR7"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
API = "https://www.youtube.com/youtubei/v1/browse?key=AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8&prettyPrint=false"
WEB = {"clientName": "WEB", "clientVersion": "2.20240920.01.00", "hl": "en", "gl": "US"}
MWEB = {"clientName": "MWEB", "clientVersion": "2.20240920.01.00", "hl": "en", "gl": "US"}

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

def raw_items(d):
    out = []
    pvrs = []
    walk(d, "playlistVideoRenderer", pvrs)
    for p in pvrs:
        out.append({"videoId": p.get("videoId"), "title": txt(p.get("title"))})
    lus = []
    walk(d, "lockupViewModel", lus)
    for l in lus:
        t = ""
        try:
            t = txt(l.get("metadata", {}).get("lockupMetadataViewModel", {}).get("title"))
        except Exception:
            pass
        out.append({"videoId": l.get("contentId"), "title": t})
    return out

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

def get_tokens2(d):
    toks = []
    found = []
    walk(d, "continuationItemViewModel", found)
    for f in found:
        s = json.dumps(f)
        for m in re.finditer(r'"token":\s*"([^"]+)"', s):
            if m.group(1) not in toks:
                toks.append(m.group(1))
    for key in ("continuationCommand", "getContinuationCommand", "nextContinuationData"):
        found = []
        walk(d, key, found)
        for f in found:
            t = f.get("token") if isinstance(f, dict) else None
            if t and t not in toks:
                toks.append(t)
    return toks

D = []
os.makedirs("out", exist_ok=True)

page = get("https://www.youtube.com/playlist?list=%s&hl=en&persist_hl=1" % PLID)
data = parse_json_after(page, "var ytInitialData = ")

# count contexts with big numbers
big = []
for m in re.finditer(r"(\d[\d,]{0,6})\s*videos?", page):
    n = m.group(1)
    try:
        if int(n.replace(",", "")) > 5:
            s = max(0, m.start() - 200)
            big.append("NUM=%s CTX=%s" % (n, re.sub(r"\s+", " ", page[s:m.end() + 80])))
    except Exception:
        pass
D.append("big_count_matches=%d" % len(big))
open("out/bigcount.txt", "w").write("\n===\n".join(big[:30]))

# page header metadata
phs = []
walk(data, "pageHeaderViewModel", phs)
D.append("pageHeaderViewModel=%d" % len(phs))
if phs:
    open("out/page_header.json", "w").write(json.dumps(phs[0], indent=1)[:20000])
    texts = []
    def collect_text(o):
        if isinstance(o, dict):
            if isinstance(o.get("content"), str) and o.get("content"):
                texts.append(o["content"])
            if isinstance(o.get("text"), str) and o.get("text"):
                texts.append(o["text"])
            for v in o.values():
                collect_text(v)
        elif isinstance(o, list):
            for v in o:
                collect_text(v)
    collect_text(phs[0])
    D.append("header_texts=%s" % json.dumps(texts[:40]))

# playlist metadata renderer
pmr = []
walk(data, "playlistMetadataRenderer", pmr)
if pmr:
    D.append("playlistMetadata=%s" % json.dumps(pmr[0])[:800])

# MWEB full pagination with token2
try:
    d = json.loads(post(API, {"context": {"client": MWEB}, "browseId": "VL" + PLID}))
    allitems = raw_items(d)
    pending = get_tokens2(d)
    used = set()
    guard = 0
    D.append("mweb_first=%d toks2=%d" % (len(allitems), len(pending)))
    while pending and guard < 20:
        guard += 1
        tok = pending.pop(0)
        if tok in used:
            continue
        used.add(tok)
        d2 = json.loads(post(API, {"context": {"client": MWEB}, "continuation": tok}))
        got = raw_items(d2)
        D.append("mweb_c+%d" % len(got))
        allitems.extend(got)
        for t in get_tokens2(d2):
            if t not in used and t not in pending:
                pending.append(t)
    from collections import Counter
    cc = Counter([x["videoId"] for x in allitems])
    D.append("mweb_total=%d distinct=%d" % (len(allitems), len(cc)))
    open("out/mweb_ids.txt", "w").write("\n".join("%s\t%s" % (x["videoId"], x["title"]) for x in allitems))
except Exception as e:
    D.append("mweb_err=%r" % (e,))

open("out/debug.txt", "w").write("\n".join(D))
print("\n".join(D))
