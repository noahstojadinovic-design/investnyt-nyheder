"""Henter nyheder til siden "Nyheder" i Makro Invest -> nyheder.json.

Kun overskrift, tidspunkt, kilde og link (plus en kort indledning fra de officielle kilder). Artiklernes tekst hentes
aldrig. Hver kilde er mærket `offentlig`:
  True   må vises i den offentlige udgave: officielle myndigheder og selskabsmeddelelser (lavet til at blive delt).
  False  kun til din egen, private udgave. Medierne tillader typisk kun deres RSS til privat brug
         (DR: "egne private sider"). byg.py fjerner dem fra den offentlige udgave.

Kør:  python nyheder_hent.py          (serve.py gør det hvert 5. minut)
Kilderne er testet 22. nov. 2026. Fejler en kilde, beholdes dens sidste nyheder.
"""
import email.utils, html, json, os, re, sys, time, datetime as dt
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo
import requests

HER = os.path.dirname(os.path.abspath(__file__))
UD = os.path.join(HER, "nyheder.json")
H = {"User-Agent": "Mozilla/5.0 (Makro Invest nyheder)"}
CPH = ZoneInfo("Europe/Copenhagen")
MAKS_DAGE = 30            # ældre nyheder smides ud
MAKS_PR_KILDE = 40

# kat: Danmark · Centralbanker · Nøgletal · Selskaber · Verden
KILDER = [
    # --- officielle kilder og selskabsmeddelelser (offentlige)
    dict(id="dst", navn="Danmarks Statistik", type="dst", url="https://www.dst.dk/da/Statistik/udgivelser?pub=nyt", kat="Nøgletal", sprog="da", offentlig=True),
    dict(id="nb", navn="Nationalbanken", type="nb", url="https://www.nationalbanken.dk/da/viden-og-nyheder", kat="Centralbanker", sprog="da", offentlig=True),
    dict(id="ecb", navn="ECB", type="rss", url="https://www.ecb.europa.eu/rss/press.html", kat="Centralbanker", sprog="en", offentlig=True),
    dict(id="ecbstat", navn="ECB statistik", type="rss", url="https://www.ecb.europa.eu/rss/statpress.html", kat="Nøgletal", sprog="en", offentlig=True),
    dict(id="fed", navn="Federal Reserve", type="rss", url="https://www.federalreserve.gov/feeds/press_all.xml", kat="Centralbanker", sprog="en", offentlig=True),
    dict(id="boe", navn="Bank of England", type="rss", url="https://www.bankofengland.co.uk/rss/news", kat="Centralbanker", sprog="en", offentlig=True),
    dict(id="bls", navn="BLS (USA)", type="rss", url="https://www.bls.gov/feed/bls_latest.rss", kat="Nøgletal", sprog="en", offentlig=True),
    dict(id="bea", navn="BEA (USA)", type="rss", url="https://apps.bea.gov/rss/rss.xml", kat="Nøgletal", sprog="en", offentlig=True),
    dict(id="gnw", navn="Selskabsmeddelelser (GlobeNewswire)", type="rss", url="https://www.globenewswire.com/RssFeed/country/Denmark/feedTitle/GlobeNewswire%20-%20News%20from%20Denmark", kat="Selskaber", sprog="da", offentlig=True),
    # --- medier (kun privat brug)
    dict(id="drpenge", navn="DR Penge", type="rss", url="https://www.dr.dk/nyheder/service/feeds/penge", kat="Danmark", sprog="da", offentlig=False),
    dict(id="borsen", navn="Børsen", type="rss", url="https://borsen.dk/rss", kat="Danmark", sprog="da", offentlig=False),
    dict(id="bbc", navn="BBC Business", type="rss", url="https://feeds.bbci.co.uk/news/business/rss.xml", kat="Verden", sprog="en", offentlig=False),
    dict(id="guardian", navn="The Guardian", type="rss", url="https://www.theguardian.com/uk/business/rss", kat="Verden", sprog="en", offentlig=False),
    dict(id="cnbc", navn="CNBC", type="rss", url="https://www.cnbc.com/id/100003114/device/rss/rss.html", kat="Verden", sprog="en", offentlig=False),
    dict(id="mw", navn="MarketWatch", type="rss", url="https://feeds.content.dowjones.io/public/rss/mw_topstories", kat="Verden", sprog="en", offentlig=False),
    dict(id="ft", navn="Financial Times", type="rss", url="https://www.ft.com/rss/home", kat="Verden", sprog="en", offentlig=False),
]


def ren(s, maks=None):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    s = re.sub(r"\s+", " ", s).strip()
    if maks and len(s) > maks:
        s = s[: maks - 1].rsplit(" ", 1)[0].rstrip(",.;:") + " …"
    return s


def tid(s):
    """RSS-/ISO-tid -> 'YYYY-MM-DDTHH:MM' i dansk tid."""
    s = (s or "").strip()
    if not s: return None
    try:
        d = email.utils.parsedate_to_datetime(s)
    except Exception:
        try:
            d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            m = re.match(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})", s)
            if not m: return None
            d = dt.datetime.fromisoformat(f"{m.group(1)}T{m.group(2)}")
    if d.tzinfo is None: d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(CPH).strftime("%Y-%m-%dT%H:%M")


DC = ("http://purl.org/dc/elements/1.1/", "http://dublincore.org/documents/dcmi-namespace/")


def rss(k):
    r = requests.get(k["url"], headers=H, timeout=20); r.raise_for_status()
    x = ET.fromstring(r.content)
    ud = []
    items = x.findall(".//item") or x.findall(".//{http://www.w3.org/2005/Atom}entry") or x.findall(".//{http://purl.org/rss/1.0/}item")
    for it in items:
        g = lambda *navne: next((it.findtext(n) for n in navne if it.findtext(n)), "")
        titel = ren(g("title", "{http://www.w3.org/2005/Atom}title", "{http://purl.org/rss/1.0/}title"), 220)
        url = g("link", "{http://purl.org/rss/1.0/}link") or ""
        if not url:
            l = it.find("{http://www.w3.org/2005/Atom}link")
            url = l.get("href") if l is not None else ""
        t = tid(g("pubDate", "{http://purl.org/dc/elements/1.1/}date", "{http://www.w3.org/2005/Atom}updated", "{http://www.w3.org/2005/Atom}published"))
        tekst = ren(g("description", "{http://purl.org/rss/1.0/}description"), 220) if k["offentlig"] else ""
        # selskabsmeddelelser (GlobeNewswire): selskabets navn og ticker, fx "Copenhagen:FLS"
        firma = ren(next((it.findtext(f"{{{ns}}}contributor") for ns in DC if it.findtext(f"{{{ns}}}contributor")), ""))
        ticker = next((c.text.split(":", 1)[1] for c in it.findall("category") if (c.get("domain") or "").endswith("/rss/stock") and c.text and ":" in c.text), "")
        if not re.fullmatch(r"[A-Z][A-Z0-9]{0,7}(?: [A-Z])?", ticker): ticker = ""      # fx "FLS", "NOVO B"; obligationer har ingen ticker
        if firma: tekst = firma
        if titel and url and t:
            i = dict(t=t, titel=titel, url=url.strip(), tekst=tekst)
            if ticker: i["ticker"] = ticker
            ud.append(i)
    return ud


def dst(k):
    r = requests.get(k["url"], headers=H, timeout=20); r.raise_for_status()
    t = r.content.decode("utf-8", errors="replace")
    ud = []
    for b in re.split(r'<div class="row release-row"', t)[1:]:
        m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", b)
        a = re.search(r'<a href="(/nyt/\d+)">(.*?)</a>', b, re.S)
        tx = re.search(r'<div class="flash-text">(.*?)</div>', b, re.S)
        if m and a:
            ud.append(dict(t=f"{m.group(3)}-{m.group(2)}-{m.group(1)}T08:00", titel=ren(a.group(2), 220),
                           url="https://www.dst.dk" + a.group(1), tekst=ren(tx.group(1) if tx else "", 220)))
    return ud


def nb(k):
    r = requests.get(k["url"], headers=H, timeout=20); r.raise_for_status()
    t = html.unescape(r.content.decode("utf-8", errors="replace"))
    ud, set_ = [], set()
    pat = (r'"metaData":\{"type":"(?P<type>(?:[^"\\]|\\.)*)","topic":(?:"(?P<topic>(?:[^"\\]|\\.)*)"|null),"publishTime":\{"dateTime":"(?P<t>[^"]+)"'
           r'.*?"link":\{.*?"text":"(?P<titel>(?:[^"\\]|\\.)*)".*?"url":"(?P<url>[^"]+)"')
    for m in re.finditer(pat, t):
        url = json.loads(f'"{m.group("url")}"')
        if url in set_: continue
        set_.add(url)
        typ, emne = json.loads(f'"{m.group("type")}"'), json.loads(f'"{m.group("topic")}"') if m.group("topic") else ""
        ud.append(dict(t=m.group("t")[:16], titel=ren(json.loads(f'"{m.group("titel")}"'), 220), url=url,
                       tekst=" · ".join(x for x in (typ, emne) if x)))
    return ud


def main():
    # --offentlig: kun kilder, der må vises offentligt (bruges af GitHub-automatikken til investnyt.com)
    # --kun-ved-nyt: skriv kun filen, når der er nye eller ændrede nyheder (så der ikke laves en ændring hvert kvarter)
    kilder = [k for k in KILDER if k["offentlig"]] if "--offentlig" in sys.argv else KILDER
    gl = {}
    if os.path.exists(UD):
        try: gl = json.load(open(UD, encoding="utf-8"))
        except Exception: gl = {}
    gamle = {}
    for n in gl.get("nyheder", []): gamle.setdefault(n["k"], []).append(n)
    nu = dt.datetime.now(CPH)
    graense = (nu - dt.timedelta(days=MAKS_DAGE)).strftime("%Y-%m-%dT%H:%M")
    fremtid = (nu + dt.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
    alle, status = [], {}
    for k in kilder:
        t0 = time.time()
        try:
            items = {"rss": rss, "dst": dst, "nb": nb}[k["type"]](k)
            ok = True
        except Exception as e:
            items, ok = [], False
            print(f"  FEJL {k['navn']}: {type(e).__name__}: {str(e)[:120]}")
        # flet med det, vi havde, så historikken bliver, selv om feedet kun viser de seneste
        set_ = {i["url"] for i in items}
        items += [{x: v for x, v in g.items() if x != "k"} for g in gamle.get(k["id"], []) if g["url"] not in set_]
        items = [i for i in items if graense <= i["t"] <= fremtid]
        items = sorted(items, key=lambda i: i["t"], reverse=True)[:MAKS_PR_KILDE]
        for i in items:
            alle.append(dict(k=k["id"], **i))
        status[k["id"]] = dict(navn=k["navn"], ok=ok, n=len(items), sek=round(time.time() - t0, 1),
                               sidste=items[0]["t"] if items else None, kat=k["kat"], sprog=k["sprog"], offentlig=k["offentlig"])
        print(f"  {'ok  ' if ok else 'FEJL'} {k['navn']:38s} {len(items):3d}  nyeste {items[0]['t'] if items else '-'}")
    alle.sort(key=lambda i: i["t"], reverse=True)
    ud = dict(hentet=nu.strftime("%Y-%m-%dT%H:%M"),
              kilder={k["id"]: dict(navn=k["navn"], kat=k["kat"], sprog=k["sprog"], offentlig=k["offentlig"], url=k["url"]) for k in kilder},
              status=status, nyheder=alle)
    noegle = lambda xs: [(n["k"], n["url"], n["titel"], n["t"]) for n in xs]
    if "--kun-ved-nyt" in sys.argv and noegle(alle) == noegle(gl.get("nyheder", [])):
        print(f"Intet nyt ({len(alle)} nyheder), nyheder.json er uændret"); return
    tmp = UD + ".tmp"
    json.dump(ud, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    for _ in range(10):
        try: os.replace(tmp, UD); break
        except PermissionError: time.sleep(0.3)
    print(f"Gemt {len(alle)} nyheder fra {sum(1 for s in status.values() if s['ok'])} af {len(kilder)} kilder i nyheder.json")


if __name__ == "__main__":
    main()
