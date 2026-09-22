import json, os, re, urllib.request

PLID = "PLyzTA8cetPdHtlGw1X8Kt7Ea4bd27ApR7"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
API = "https://www.youtube.com/youtubei/v1/browse?key=AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8&prettyPrint=false"

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
    diag.append("has_ytid=%s" % ("var ytInitialData" in page))
    diag.append("has_pvr_str=%s" % ("playlistVideoRenderer" in page))
    diag.append("has_lockup_str=%s" % ("lockupViewModel" in page))
    mt = re.search(r"<title>(.*?)</title>", page, re.S)
    diag.append("title=%s" % (mt.group(1) if mt else "?"))
    count_texts = re.findall(r"([\d,]+)\s*videos?", page)
    diag.append("count_texts=" + ",".join(count_texts[:8]))
    data = parse_json_after(page, "var ytInitialData = ")
    if data is None:
        diag.append("parse_ytid=fail")
    else:
        keys = set()
        def ck(o):
            if isinstance(o, dict):
                for k in o:
                    if (k.endswith("Renderer") or k.endswith("ViewModel")) and k not in keys:
                        keys.add(k)
                for v in o.values():
                    ck(v)
            elif isinstance(o, list):
                for v in o:
                    ck(v)
        ck(data)
        diag.append("keys=" + ",".join(sorted(keys)))
        diag.append("extracted_page=%d" % extract(data))
        conts = []
        walk(data, "continuationItemRenderer", conts)
        ctx = {"context": {"client": {"clientName": "WEB", "clientVersion": "2.20240920.01.00", "hl": "en", "gl": "US"}}}
        guard = 0
        while conts and guard < 40:
            guard += 1
            c = conts.pop(0)
            tok = ((c.get("continuationEndpoint") or {}).get("continuationCommand") or {}).get("token")
            if not tok:
                continue
            try:
                d2 = json.loads(post(API, dict(ctx, continuation=tok)))
                extract(d2)
                walk(d2, "continuationItemRenderer", conts)
            except Exception as e:
                diag.append("cont_err=%r" % (e,))
                break
        diag.append("after_cont=%d" % len(items))
except Exception as e:
    diag.append("page_err=%r" % (e,))

if len(items) == 0:
    for cli in [
        {"clientName": "WEB", "clientVersion": "2.20240920.01.00", "hl": "en", "gl": "US"},
        {"clientName": "ANDROID", "clientVersion": "19.09.37", "androidSdkVersion": 30, "hl": "en", "gl": "US"},
        {"clientName": "MWEB", "clientVersion": "2.20240920.01.00", "hl": "en", "gl": "US"},
    ]:
        try:
            resp = post(API, {"context": {"client": cli}, "browseId": "VL" + PLID})
            d = json.loads(resp)
            diag.append("browse_%s_extracted=%d" % (cli["clientName"], extract(d)))
            conts = []
            walk(d, "continuationItemRenderer", conts)
            guard = 0
            while conts and guard < 40:
                guard += 1
                c = conts.pop(0)
                tok = ((c.get("continuationEndpoint") or {}).get("continuationCommand") or {}).get("token")
                if not tok:
                    continue
                d2 = json.loads(post(API, {"context": {"client": cli}, "continuation": tok}))
                extract(d2)
                walk(d2, "continuationItemRenderer", conts)
            diag.append("browse_%s_total=%d" % (cli["clientName"], len(items)))
            if len(items):
                break
        except Exception as e:
            diag.append("browse_%s_err=%r" % (cli["clientName"], e))

os.makedirs("out", exist_ok=True)
open("out/diag.txt", "w").write("\n".join(diag))
json.dump({"num": len(items), "items": items}, open("out/playlist.json", "w"), indent=1, ensure_ascii=False)

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
