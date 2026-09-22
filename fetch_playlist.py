import json, os, re, urllib.request

PLID = "PLyzTA8cetPdHtlGw1X8Kt7Ea4bd27ApR7"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read().decode("utf-8", "replace")

def post(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
        headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9",
                 "Content-Type": "application/json",
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
        return x.get("simpleText", "")
    return str(x)

os.makedirs("out", exist_ok=True)

page = get("https://www.youtube.com/playlist?list=%s&hl=en&persist_hl=1" % PLID)
data = parse_json_after(page, "var ytInitialData = ")
if data is None:
    raise SystemExit("no ytInitialData (len=%d)" % len(page))

items = []
seen = set()

def collect(d):
    found = []
    walk(d, "playlistVideoRenderer", found)
    for p in found:
        vid = p.get("videoId")
        if not vid or vid in seen:
            continue
        seen.add(vid)
        items.append({
            "videoId": vid,
            "title": txt(p.get("title")),
            "byline": txt(p.get("shortBylineText")) or txt(p.get("longBylineText")) or txt(p.get("ownerText")),
            "lengthText": txt(p.get("lengthText")),
            "videoInfo": txt(p.get("videoInfo")),
        })

collect(data)
count_texts = re.findall(r"([\d,]+)\s*videos?", page)

conts = []
walk(data, "continuationItemRenderer", conts)
api = "https://www.youtube.com/youtubei/v1/browse?key=AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8&prettyPrint=false"
ctx = {"context": {"client": {"clientName": "WEB", "clientVersion": "2.20240920.01.00", "hl": "en", "gl": "US"}}}
guard = 0
while conts and guard < 40:
    guard += 1
    c = conts.pop(0)
    tok = ((c.get("continuationEndpoint") or {}).get("continuationCommand") or {}).get("token")
    if not tok:
        continue
    try:
        d2 = json.loads(post(api, dict(ctx, continuation=tok)))
    except Exception as e:
        print("CONTINUATION_ERROR", repr(e))
        break
    collect(d2)
    walk(d2, "continuationItemRenderer", conts)

with open("out/playlist.json", "w") as f:
    json.dump({"num": len(items), "count_texts": count_texts[:6], "items": items}, f, indent=1, ensure_ascii=False)

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
    block = "### %d | %s | %s | %s | %s | %s | %s\n%s" % (
        i + 1, it["videoId"], it["title"], it["byline"], it["lengthText"], it["videoInfo"], err, desc[:2000])
    buf.append(block)
    if len(buf) >= CHUNK:
        open("out/d_%02d.txt" % idx, "w").write("\n\n".join(buf))
        idx += 1
        buf = []
if buf:
    open("out/d_%02d.txt" % idx, "w").write("\n\n".join(buf))

print("DONE items=%d count_texts=%s" % (len(items), count_texts[:6]))
