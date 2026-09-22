import json, os, re, urllib.request
from collections import Counter

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

def raw_items(d):
    """Return list of dicts in document order, no dedupe."""
    out = []
    pvrs = []
    walk(d, "playlistVideoRenderer", pvrs)
    for p in pvrs:
        out.append({"kind": "pvr", "videoId": p.get("videoId"), "title": txt(p.get("title")),
                    "byline": txt(p.get("shortBylineText")) or txt(p.get("ownerText"))})
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
        out.append({"kind": "lockup", "videoId": vid, "title": t, "byline": by})
    return out

diag = []
os.makedirs("out", exist_ok=True)

# --- page
page = get("https://www.youtube.com/playlist?list=%s&hl=en&persist_hl=1" % PLID)
data = parse_json_after(page, "var ytInitialData = ")
page_raw = raw_items(data)
diag.append("page_raw=%d" % len(page_raw))
c = Counter([x["videoId"] for x in page_raw])
diag.append("page_distinct=%d dups=%s" % (len(c), json.dumps({k: v for k, v in c.items() if v > 1})))
mt = re.search(r"([\d,]+) videos", page)
diag.append("page_count_text=%s" % (mt.group(1) if mt else "?"))
open("out/raw_page_ids.txt", "w").write("\n".join("%s\t%s\t%s" % (x["videoId"], x["title"], x["byline"]) for x in page_raw))

# --- browse for each client
for cli in [WEB,
            {"clientName": "ANDROID", "clientVersion": "19.09.37", "androidSdkVersion": 30, "hl": "en", "gl": "US"},
            {"clientName": "MWEB", "clientVersion": "2.20240920.01.00", "hl": "en", "gl": "US"},
            {"clientName": "TVHTML5", "clientVersion": "7.20240920.00.00", "hl": "en", "gl": "US"}]:
    try:
        resp = post(API, {"context": {"client": cli}, "browseId": "VL" + PLID})
        d = json.loads(resp)
    except Exception as e:
        diag.append("browse[%s] err=%r" % (cli["clientName"], e))
        continue
    raw = raw_items(d)
    toks = get_tokens(d)
    diag.append("browse[%s] raw=%d tokens=%d kinds=%s" % (
        cli["clientName"], len(raw), len(toks), ",".join(sorted(set(x["kind"] for x in raw)))))
    cc = Counter([x["videoId"] for x in raw])
    diag.append("browse[%s] distinct=%d dups=%s" % (cli["clientName"], len(cc), json.dumps({k: v for k, v in cc.items() if v > 1})))
    if cli["clientName"] == "WEB":
        open("out/raw_browse_ids.txt", "w").write("\n".join("%s\t%s\t%s" % (x["videoId"], x["title"], x["byline"]) for x in raw))
        # try each token, dump result keys
        for i, tok in enumerate(toks[:5]):
            try:
                d2 = json.loads(post(API, {"context": {"client": cli}, "continuation": tok}))
                r2 = raw_items(d2)
                keys = set()
                def ck(o):
                    if isinstance(o, dict):
                        for k in o:
                            if k.endswith("Renderer") or k.endswith("ViewModel"):
                                keys.add(k)
                        for v in o.values():
                            ck(v)
                    elif isinstance(o, list):
                        for v in o:
                            ck(v)
                ck(d2)
                diag.append("tok%d items=%d keys=%s" % (i, len(r2), ",".join(sorted(keys)[:25])))
            except Exception as e:
                diag.append("tok%d err=%r" % (i, e))

open("out/diag.txt", "w").write("\n".join(diag))
print("\n".join(diag))
