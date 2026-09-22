import json, os, re, urllib.request

PLID = "PLyzTA8cetPdHtlGw1X8Kt7Ea4bd27ApR7"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read().decode("utf-8", "replace")


def parse_json_after(s, marker):
    i = s.find(marker)
    if i < 0:
        return None
    start = s.index("{", i)
    return json.JSONDecoder().raw_decode(s[start:])[0]

os.makedirs("out", exist_ok=True)
page = get("https://www.youtube.com/playlist?list=%s&hl=en&persist_hl=1" % PLID)
data = parse_json_after(page, "var ytInitialData = ")
s = json.dumps(data, ensure_ascii=False)
idx = s.find("Show unavailable videos")
print("idx", idx)
if idx >= 0:
    open("out/unavail_ctx.txt", "w").write(s[max(0, idx - 3500):idx + 2500])
print("len", len(s))
