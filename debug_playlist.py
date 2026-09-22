import json, os, re, urllib.request

PLID = "PLyzTA8cetPdHtlGw1X8Kt7Ea4bd27ApR7"
CTRL = "PLZHQObOWTQDPD3MizzM2xVFitgF8hE_ab"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
API = "https://www.youtube.com/youtubei/v1/browse?key=AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8&prettyPrint=false"
NEXT = "https://www.youtube.com/youtubei/v1/next?key=AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8&prettyPrint=false"
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

def header_texts(data):
    phs = []
    walk(data, "pageHeaderViewModel", phs)
    if not phs:
        return []
    texts = []
    def ct(o):
        if isinstance(o, dict):
            if isinstance(o.get("content"), str) and o.get("content"):
                texts.append(o["content"])
            for v in o.values():
                ct(v)
        elif isinstance(o, list):
            for v in o:
                ct(v)
    ct(phs[0])
    return texts

D = []
os.makedirs("out", exist_ok=True)

for tag, plid in [("TARGET", PLID), ("CTRL", CTRL)]:
    try:
        page = get("https://www.youtube.com/playlist?list=%s&hl=en&persist_hl=1" % plid)
        data = parse_json_after(page, "var ytInitialData = ")
        D.append("%s header=%s" % (tag, json.dumps(header_texts(data))))
        D.append("%s has_show_unavailable=%s" % (tag, "Show unavailable videos" in page))
    except Exception as e:
        D.append("%s err=%r" % (tag, e))

# playlist panel via watch page
try:
    w = get("https://www.youtube.com/watch?v=SSKVgrwhzus&list=%s&hl=en" % PLID)
    pr = parse_json_after(w, "ytInitialPlayerResponse = ")
    wd = parse_json_after(w, "var ytInitialData = ")
    D.append("watch_len=%d" % len(w))
    if wd:
        panes = []
        walk(wd, "playlistPanelVideoRenderer", panes)
        D.append("panel_items=%d" % len(panes))
        rows = []
        for p in panes:
            rows.append("%s\t%s\t%s" % (p.get("videoId"), txt(p.get("title")), txt(p.get("unplayableText"))))
        open("out/panel_ids.txt", "w").write("\n".join(rows))
        lu = []
        walk(wd, "lockupViewModel", lu)
        D.append("watch_lockups=%d" % len(lu))
        # also check for any "Private video" strings
        D.append("watch_private=%d deleted=%d" % (w.count("Private video"), w.count("Deleted video")))
except Exception as e:
    D.append("watch_err=%r" % (e,))

# next endpoint with playlistId
try:
    r = post(NEXT, {"context": {"client": WEB}, "playlistId": PLID, "videoId": "SSKVgrwhzus"})
    d = json.loads(r)
    panes = []
    walk(d, "playlistPanelVideoRenderer", panes)
    D.append("next_panel=%d" % len(panes))
    rows = []
    for p in panes:
        rows.append("%s\t%s\t%s" % (p.get("videoId"), txt(p.get("title")), txt(p.get("unplayableText"))))
    open("out/next_panel_ids.txt", "w").write("\n".join(rows))
except Exception as e:
    D.append("next_err=%r" % (e,))

open("out/debug.txt", "w").write("\n".join(D))
print("\n".join(D))
