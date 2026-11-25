# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 DaKo-Soft
# G19 Helfer v3: LCD-Ansichten (WinUSB, Interface 0) + G-/M-Tasten (HID, Interface 1)
# Display-Tasten: links/rechts = Ansicht wechseln, OK = naechstes Bild, Menue = Uebersicht
# Dateien im selben Ordner: tasten.json (G-Tasten), einstellungen.json (alle anderen Einstellungen, live neu geladen),
# kalender_url.txt (Fallback fuer Kalender-Adresse), whatsapp_waechter.py (WhatsApp-Web-Ueberwachung)
import os, sys, json, time, datetime, threading, ctypes, subprocess, asyncio, random, logging, logging.handlers
from ctypes import wintypes
import usb.core, usb.util, usb.backend.libusb1, libusb_package, psutil, hid, numpy as np, requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

VID, PID, W, H = 0x046D, 0xC229, 320, 240
BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
import g19_deck
HEADER = bytes([0x10,0x0F,0x00,0x58,0x02,0x00,0x00,0x00,0x00,0x00,0x00,0x3F,0x01,0xEF,0x00,0x0F] + [i & 0xFF for i in range(16, 512)])
TAGE = ["Montag","Dienstag","Mittwoch","Donnerstag","Freitag","Samstag","Sonntag"]
KURZ = ["Mo","Di","Mi","Do","Fr","Sa","So"]
M_LED = {"M1":0x80, "M2":0x40, "M3":0x20}
LAT, LON, ORT = 52.52, 13.405, "Berlin"
def _pics_default():
    home = os.path.expanduser("~")
    for p in (os.path.join(home, "Pictures"), os.path.join(home, "Bilder")):
        if os.path.isdir(p): return p
    return os.path.join(home, "Pictures")
PICS = _pics_default()
NVSMI = r"C:\Windows\System32\nvidia-smi.exe"
ALL_VIEWS = ["Uhr", "Musik", "Netzwerk", "System", "Wetter", "Bilder", "Kalender", "Stream Deck"]
VIEWS = list(ALL_VIEWS)          # aktive Ansichten in Reihenfolge (aus einstellungen.json)
st = {"mode":"M1", "last":"", "last_t":0, "view":0, "menu_t":0, "pic_next":True, "wa_t":0, "wa_name":"", "wa_text":"", "deck_hit":("", 0)}
NOWIN = 0x08000000

# ---------- Log ----------
log = logging.getLogger("g19")
try:
    _h = logging.handlers.RotatingFileHandler(os.path.join(BASE, "g19_helfer.log"), maxBytes=300_000, backupCount=1, encoding="utf-8")
    _h.setFormatter(logging.Formatter("%(asctime)s %(message)s")); log.addHandler(_h); log.setLevel(logging.INFO)
except Exception: pass

# ---------- Einstellungen (einstellungen.json, wird live neu geladen) ----------
CFG_PATH = os.path.join(BASE, "einstellungen.json")
DEFAULTS = {
    "ansichten": [{"name": v, "aktiv": True} for v in ALL_VIEWS],
    "bilder_ordner": PICS, "bilder_intervall": 10,
    "wetter": {"ort": ORT, "lat": LAT, "lon": LON},
    "kalender_url": "",
    "helligkeit_setzen": False, "helligkeit": 100,
    "tastatur_farbe_setzen": False, "tastatur_farbe": "#FFFFFF",
    "whatsapp": {"aktiv": False, "dauer": 3, "absender_anzeigen": True, "text_anzeigen": False, "fenster_sichtbar": False},
    "streamdeck": g19_deck.fresh_slots(),
}
CFG = json.loads(json.dumps(DEFAULTS)); cfg_state = {"mtime": None}
ev_wetter, ev_kal = threading.Event(), threading.Event()

def merge(d, u):
    for k, v in u.items():
        if isinstance(v, dict) and isinstance(d.get(k), dict): merge(d[k], v)
        else: d[k] = v
    return d

def apply_cfg(new):
    global LAT, LON, ORT, PICS
    old = json.dumps(CFG, sort_keys=True); CFG.clear(); CFG.update(new)
    w = CFG["wetter"]
    if (w.get("lat"), w.get("lon")) != (LAT, LON): ev_wetter.set(); data["wetter"] = None
    LAT, LON, ORT = float(w.get("lat", LAT)), float(w.get("lon", LON)), str(w.get("ort", ORT))
    if CFG.get("bilder_ordner") and CFG["bilder_ordner"] != PICS: PICS = CFG["bilder_ordner"]; pic["list"] = []; pic["list_t"] = 0
    known = [a.get("name") for a in CFG.get("ansichten", [])]
    order = [a["name"] for a in CFG.get("ansichten", []) if a.get("name") in ALL_VIEWS and a.get("aktiv", True)]
    order += [v for v in ALL_VIEWS if v not in known]
    cur = VIEWS[st["view"] % len(VIEWS)] if VIEWS else "Uhr"
    VIEWS[:] = order or ["Uhr"]
    st["view"] = VIEWS.index(cur) if cur in VIEWS else 0
    ev_kal.set()
    lcd["apply"] = True; st["kb_apply"] = True
    if old != json.dumps(CFG, sort_keys=True): log.info("Einstellungen geladen: Ansichten=%s, Ort=%s", VIEWS, ORT)

def cfg_thread():
    while True:
        try:
            m = os.path.getmtime(CFG_PATH) if os.path.exists(CFG_PATH) else 0
            if m != cfg_state["mtime"]:
                cfg_state["mtime"] = m
                new = json.loads(json.dumps(DEFAULTS))
                if m:
                    with open(CFG_PATH, encoding="utf-8-sig") as f: merge(new, json.load(f))
                apply_cfg(new)
        except Exception as e: log.info("Einstellungen fehlerhaft: %s", e)
        time.sleep(2)

def cur_view(): return VIEWS[st["view"] % len(VIEWS)]

# ---------- Schriften / Hilfen ----------
def font(size, bold=False):
    for f in (["segoeuib.ttf","arialbd.ttf"] if bold else ["segoeui.ttf","arial.ttf"]):
        try: return ImageFont.truetype(f, size)
        except OSError: pass
    return ImageFont.load_default()
F64, F40, F28, F22, F18, F15 = font(64,True), font(40,True), font(28,True), font(22), font(18), font(15)
GREY, WHITE, BLUE, YEL = (150,150,150), (255,255,255), (0,170,255), (255,200,0)

def fit(d, text, f, maxw):
    if d.textlength(text, font=f) <= maxw: return text
    while text and d.textlength(text + "…", font=f) > maxw: text = text[:-1]
    return text + "…"

banner = {"k": "", "t": 0}
def marquee(img, d, x, y, text, f, maxw, fill):
    """Laufbanner, wenn der Text nicht in die Breite passt. Kurzer Text bleibt stehen."""
    tw = d.textlength(text, font=f)
    if tw <= maxw:
        d.text((x, y), text, font=f, fill=fill); return
    gap, speed, hold = 40, 26, 1.6
    cycle = tw + gap
    now = time.time()
    if banner["k"] != text: banner["k"], banner["t"] = text, now
    gone = now - banner["t"]
    off = 0 if gone < hold else ((gone - hold) * speed) % cycle
    ascent, descent = f.getmetrics()
    strip = Image.new("RGB", (int(maxw), ascent + descent + 2))
    sd = ImageDraw.Draw(strip)
    sd.text((-off, 0), text, font=f, fill=fill)
    sd.text((-off + cycle, 0), text, font=f, fill=fill)
    img.paste(strip, (int(x), int(y)))

def title(d, t):
    d.text((12, 6), t, font=F18, fill=BLUE)
    d.text((W-12, 6), st["mode"], font=F18, fill=YEL, anchor="ra")
    d.line((12, 30, W-12, 30), fill=(50,50,50))

def bar(d, y, label, pct, color, x0=130):
    d.text((16, y), f"{label} {pct:3.0f} %", font=F18, fill=(220,220,220))
    d.rectangle((x0, y+4, 304, y+18), outline=(90,90,90))
    d.rectangle((x0+1, y+5, x0+1 + int((303-x0-1) * min(pct,100) / 100), y+17), fill=color)

# ---------- Datenquellen (Hintergrund) ----------
data = {"net": [], "net_now": (0,0), "gpu": None, "wetter": None, "musik": None, "kal": None, "kal_err": ""}

def net_thread():
    last = psutil.net_io_counters(); lt = time.time()
    while True:
        time.sleep(1)
        n = psutil.net_io_counters(); t = time.time()
        down = (n.bytes_recv - last.bytes_recv) / (t - lt); up = (n.bytes_sent - last.bytes_sent) / (t - lt)
        last, lt = n, t
        data["net_now"] = (down, up); data["net"] = (data["net"] + [(down, up)])[-120:]

def gpu_thread():
    while True:
        if cur_view() == "System" and os.path.exists(NVSMI):
            try:
                out = subprocess.run([NVSMI, "--query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.total",
                                      "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5, creationflags=NOWIN).stdout
                t, u, mu, mt = [float(x) for x in out.strip().split(",")[:4]]
                data["gpu"] = (t, u, mu, mt)
            except Exception: data["gpu"] = None
        time.sleep(3)

WCODE = {0:"Klar",1:"Überwiegend klar",2:"Teilweise bewölkt",3:"Bedeckt",45:"Nebel",48:"Reifnebel",51:"Leichter Niesel",53:"Niesel",
         55:"Starker Niesel",61:"Leichter Regen",63:"Regen",65:"Starker Regen",66:"Gefrierender Regen",67:"Gefrierender Regen",
         71:"Leichter Schnee",73:"Schnee",75:"Starker Schnee",77:"Schneegriesel",80:"Regenschauer",81:"Regenschauer",
         82:"Heftige Schauer",85:"Schneeschauer",86:"Schneeschauer",95:"Gewitter",96:"Gewitter mit Hagel",99:"Gewitter mit Hagel"}
def wetter_thread():
    while True:
        try:
            r = requests.get("https://api.open-meteo.com/v1/forecast", timeout=15, params={
                "latitude":LAT, "longitude":LON, "timezone":"Europe/Berlin", "forecast_days":4,
                "current":"temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code",
                "daily":"weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"}).json()
            data["wetter"] = r; ev_wetter.clear(); ev_wetter.wait(900)
        except Exception: ev_wetter.clear(); ev_wetter.wait(120)

def _timeline(tl):
    """Position und Ende relativ zum Start. last_updated ist der Zeitpunkt, zu dem pos galt."""
    if not tl: return 0.0, 0.0, None
    pos, end, start = tl.position.total_seconds(), tl.end_time.total_seconds(), tl.start_time.total_seconds()
    if pos >= start: pos -= start
    end = end - start if end >= start else 0.0
    lu = None
    try:
        dt = tl.last_updated_time
        if dt and dt.year >= 2000:
            if dt.tzinfo is None: dt = dt.replace(tzinfo=datetime.timezone.utc)
            lu = dt.timestamp()
    except Exception: lu = None
    return max(0.0, pos), max(0.0, end), lu

def musik_thread():
    try:
        from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as MGR
    except Exception: return
    async def poll():
        mgr = await MGR.request_async()
        while True:
            try:
                s = mgr.get_current_session()
                if s is None: data["musik"] = None
                else:
                    p = await s.try_get_media_properties_async()
                    pb = s.get_playback_info(); tl = s.get_timeline_properties()
                    app = (s.source_app_user_model_id or "").split("!")[0].split("\\")[-1].replace(".exe","")
                    pos, end, lu = _timeline(tl)
                    spielt = int(pb.playback_status) == 4
                    rate = 1.0
                    try:
                        pr = pb.playback_rate
                        if pr: rate = float(pr) or 1.0
                    except Exception: pass
                    if rate <= 0: rate = 1.0
                    now = time.time()
                    titel, kuenstler = p.title or "", p.artist or ""
                    prev = data["musik"]
                    same = bool(prev and prev.get("titel") == titel and prev.get("kuenstler") == kuenstler and titel)
                    base_pos, base_t = pos, (lu if lu else now)
                    # Chrome/YouTube meldet beim Abspielen oft Position 0 und frischt nur den
                    # Zeitstempel auf. Echte Sprünge (Pause, Vorspulen) bleiben gültig.
                    if same:
                        est = prev["pos"] + ((now - prev["t"]) * (prev.get("rate") or 1) if prev.get("spielt") else 0)
                        live = pos + ((now - lu) * rate if spielt and lu else 0)
                        if spielt and pos < 1.5 and est > live + 0.35:
                            base_pos, base_t = est, now
                        elif spielt and lu:
                            base_pos, base_t = pos, lu
                        else:
                            base_pos, base_t = pos, now
                    data["musik"] = {"titel": titel, "kuenstler": kuenstler, "album": p.album_title or "",
                                     "spielt": spielt, "app": app, "rate": rate,
                                     "pos": max(0.0, base_pos), "ende": end, "t": base_t}
            except Exception: data["musik"] = None
            await asyncio.sleep(1.0)
    asyncio.run(poll())

def kal_thread():
    import icalendar, recurring_ical_events
    while True:
        try:
            p = os.path.join(BASE, "kalender_url.txt"); url = (CFG.get("kalender_url") or "").strip()
            if not url and os.path.exists(p): url = open(p, encoding="utf-8-sig").read().strip()
            if not url: data["kal"] = None; data["kal_err"] = "nicht verbunden"; ev_kal.clear(); ev_kal.wait(30); continue
            cal = icalendar.Calendar.from_ical(requests.get(url, timeout=20).content)
            now = datetime.datetime.now().astimezone()
            evs = []
            for e in recurring_ical_events.of(cal).between(now - datetime.timedelta(hours=2), now + datetime.timedelta(days=21)):
                s = e.get("DTSTART").dt; en = e.get("DTEND").dt if e.get("DTEND") else s
                ganz = not isinstance(s, datetime.datetime)
                if ganz: s = datetime.datetime.combine(s, datetime.time()).astimezone(); en = datetime.datetime.combine(en, datetime.time()).astimezone()
                else: s = s.astimezone(); en = en.astimezone()
                if en < now: continue
                evs.append((s, ganz, str(e.get("SUMMARY", "(ohne Titel)"))))
            data["kal"] = sorted(evs)[:12]; data["kal_err"] = ""; ev_kal.clear(); ev_kal.wait(600)
        except Exception as ex: data["kal_err"] = "Fehler beim Laden"; ev_kal.clear(); ev_kal.wait(120)

# ---------- Bilder ----------
pic = {"list": [], "list_t": 0, "img": None, "t": 0, "name": ""}
def pics_local():
    out = []
    for root, _, files in os.walk(PICS):
        for f in files:
            if f.lower().endswith((".jpg",".jpeg",".png",".bmp",".webp",".gif")):
                fp = os.path.join(root, f)
                try:
                    a = os.stat(fp).st_file_attributes
                    if a & 0x400000 or a & 0x1000: continue      # nur in OneDrive-Cloud -> ueberspringen
                    out.append(fp)
                except Exception: pass
    random.shuffle(out); return out
def next_pic():
    if time.time() - pic["list_t"] > 600 or not pic["list"]:
        pic["list"], pic["list_t"] = pics_local(), time.time()
    for _ in range(5):
        if not pic["list"]: return
        fp = pic["list"].pop()
        try:
            im = ImageOps.exif_transpose(Image.open(fp)).convert("RGB")
            im = ImageOps.contain(im, (W, H))
            bg = Image.new("RGB", (W, H)); bg.paste(im, ((W - im.width)//2, (H - im.height)//2))
            pic["img"], pic["name"] = bg, os.path.basename(fp); return
        except Exception: continue

# ---------- Ansichten ----------
def v_uhr(d, img):
    now = datetime.datetime.now()
    d.text((W-12, 8), st["mode"], font=F18, fill=YEL, anchor="ra")
    d.text((W//2, 45), now.strftime("%H:%M:%S"), font=F64, fill=WHITE, anchor="mm")
    d.text((W//2, 95), f"{TAGE[now.weekday()]}, {now:%d.%m.%Y}", font=F22, fill=BLUE, anchor="mm")
    bar(d, 145, "CPU", psutil.cpu_percent(interval=None), (0,200,120))
    bar(d, 175, "RAM", psutil.virtual_memory().percent, (255,160,0))
    bar(d, 205, "C:  ", psutil.disk_usage("C:\\").percent, (200,80,255))

def v_musik(d, img):
    title(d, "Musik"); m = data["musik"]
    if not m or not m["titel"]:
        d.text((W//2, 125), "Gerade läuft nichts", font=F22, fill=GREY, anchor="mm"); return
    marquee(img, d, 16, 50, m["titel"], F28, 288, WHITE)
    d.text((16, 92), fit(d, m["kuenstler"], F22, 290), font=F22, fill=BLUE)
    d.text((16, 122), fit(d, m["album"], F18, 290), font=F18, fill=GREY)
    pos = m["pos"]
    if m["spielt"]:
        dt = time.time() - m["t"]
        if 0 <= dt <= 8 * 3600: pos += dt * (m.get("rate") or 1)
    if pos < 0: pos = 0
    if m["ende"] > 0:
        pos = min(pos, m["ende"])
        d.rectangle((16, 170, 304, 178), outline=(90,90,90))
        d.rectangle((17, 171, 17 + int(286 * pos / m["ende"]), 177), fill=(0,200,120))
        f = lambda s: f"{int(s)//60}:{int(s)%60:02d}"
        d.text((16, 184), f(pos), font=F15, fill=GREY); d.text((304, 184), f(m["ende"]), font=F15, fill=GREY, anchor="ra")
    d.text((16, 212), ("> läuft" if m["spielt"] else "|| Pause") + (f"  ·  {m['app']}" if m["app"] else ""), font=F15, fill=YEL)

_DECK_FONT, _DECK_IMG = {}, {}
def deck_font(kind, size):
    key = (kind, size)
    if key not in _DECK_FONT:
        try: _DECK_FONT[key] = ImageFont.truetype("segmdl2.ttf" if kind == "mdl2" else "segoeui.ttf", size)
        except OSError: _DECK_FONT[key] = F22
    return _DECK_FONT[key]
def deck_photo(path, size):
    if not path or not os.path.isfile(path): return None
    try: mt = os.path.getmtime(path)
    except OSError: return None
    key = (path, mt, size)
    if key in _DECK_IMG: return _DECK_IMG[key]
    try:
        im = ImageOps.fit(Image.open(path).convert("RGBA"), (size, size))
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
        im.putalpha(mask)
        if len(_DECK_IMG) > 16: _DECK_IMG.clear()
        _DECK_IMG[key] = im
        return im
    except Exception: return None

def v_stream(d, img):
    title(d, "Stream Deck")
    slots = g19_deck.normalize(CFG.get("streamdeck"))
    accents = ((0, 122, 204), (0, 164, 110), (230, 126, 34), (150, 80, 210))
    gap, x0, y0, cw, ch = 8, 10, 40, 146, 91
    hit_k, hit_t = st.get("deck_hit") or ("", 0)
    now = time.time()
    for i, s in enumerate(slots):
        x, y = x0 + (i % 2) * (cw + gap), y0 + (i // 2) * (ch + gap)
        hot = hit_k == s["taste"] and now - hit_t < 0.55
        d.rounded_rectangle((x, y, x + cw, y + ch), radius=10, fill=(48, 56, 72) if hot else (26, 30, 38),
                            outline=YEL if hot else accents[i], width=2)
        d.text((x + 8, y + 3), s["taste"], font=F15, fill=GREY)
        cx, cy = x + cw // 2, y + 42
        photo = deck_photo(s.get("bild") or "", 36)
        if photo is not None:
            img.paste(photo, (cx - 18, cy - 18), photo)
        else:
            d.ellipse((cx - 16, cy - 16, cx + 16, cy + 16), fill=accents[i])
            spec = g19_deck.ICON_BY_ID.get(s["icon"]) or g19_deck.ICON_BY_ID["leer"]
            if spec[2]:
                d.text((cx, cy), spec[2], font=deck_font(spec[3], 18), fill=WHITE, anchor="mm")
        d.text((x + cw // 2, y + ch - 14), fit(d, s["name"] or "Leer", F15, cw - 16), font=F15, fill=WHITE, anchor="mm")

def mbit(b): return b * 8 / 1_000_000
def v_netz(d, img):
    title(d, "Netzwerk"); dn, up = data["net_now"]
    d.text((16, 38), f"↓ {mbit(dn):6.1f} Mbit/s", font=F22, fill=(0,200,120))
    d.text((W-16, 38), f"↑ {mbit(up):5.1f} Mbit/s", font=F22, fill=(255,160,0), anchor="ra")
    hist = data["net"]; x0, y0, x1, y1 = 16, 75, 304, 225
    d.rectangle((x0, y0, x1, y1), outline=(60,60,60))
    if len(hist) > 1:
        mx = max(max(h[0] for h in hist), max(h[1] for h in hist), 125_000)
        for idx, col in ((0,(0,200,120)), (1,(255,160,0))):
            pts = [(x1 - (len(hist)-1-i) * (x1-x0) / 119, y1 - 2 - (h[idx] / mx) * (y1-y0-4)) for i, h in enumerate(hist)]
            d.line(pts, fill=col, width=2)
        d.text((x0+4, y0+2), f"max {mbit(mx):.1f} Mbit/s · 2 Min.", font=F15, fill=GREY)

def v_system(d, img):
    title(d, "System")
    cores = psutil.cpu_percent(percpu=True); n = len(cores)
    d.text((16, 36), f"CPU {sum(cores)/n:3.0f} %  ·  {n} Kerne", font=F18, fill=WHITE)
    bw = (288 - (n-1)*2) / n
    for i, c in enumerate(cores):
        x = 16 + i * (bw + 2); d.rectangle((x, 62, x + bw, 122), outline=(50,50,50))
        d.rectangle((x, 122 - 60 * c / 100, x + bw, 122), fill=(0,200,120))
    g = data["gpu"]
    if g:
        t, u, mu, mt = g
        d.text((16, 132), f"GPU {t:.0f} °C", font=F18, fill=(255,120,80) if t > 80 else WHITE)
        bar(d, 156, "GPU", u, (0,170,255)); bar(d, 182, "VRAM", 100 * mu / mt if mt else 0, (200,80,255))
    else:
        d.text((16, 140), "GPU: schläft oder keine Daten", font=F18, fill=GREY)
    bar(d, 208, "RAM", psutil.virtual_memory().percent, (255,160,0))

def v_wetter(d, img):
    title(d, f"Wetter {ORT}"); w = data["wetter"]
    if not w: d.text((W//2, 125), "Lade Wetter …", font=F22, fill=GREY, anchor="mm"); return
    c = w["current"]
    d.text((16, 38), f"{c['temperature_2m']:.0f}°", font=F64, fill=WHITE)
    d.text((140, 46), WCODE.get(c["weather_code"], ""), font=F22, fill=BLUE)
    d.text((140, 76), f"gefühlt {c['apparent_temperature']:.0f}°", font=F18, fill=GREY)
    d.text((140, 98), f"Wind {c['wind_speed_10m']:.0f} km/h · {c['relative_humidity_2m']:.0f} %", font=F15, fill=GREY)
    dy = w["daily"]
    for i in range(4):
        x = 16 + i * 74; dt = datetime.date.fromisoformat(dy["time"][i])
        d.rectangle((x, 132, x + 68, 228), outline=(50,50,50))
        d.text((x + 34, 142), "Heute" if i == 0 else KURZ[dt.weekday()], font=F15, fill=YEL, anchor="mm")
        d.text((x + 34, 166), f"{dy['temperature_2m_max'][i]:.0f}°", font=F22, fill=WHITE, anchor="mm")
        d.text((x + 34, 190), f"{dy['temperature_2m_min'][i]:.0f}°", font=F18, fill=GREY, anchor="mm")
        pp = dy["precipitation_probability_max"][i]
        d.text((x + 34, 214), f"{pp if pp is not None else '-'} % Regen", font=F15, fill=BLUE, anchor="mm")

def v_bilder(d, img):
    if st["pic_next"] or pic["img"] is None or time.time() - pic["t"] > max(2, float(CFG.get("bilder_intervall", 10))):
        st["pic_next"] = False; next_pic(); pic["t"] = time.time()
    if pic["img"] is None:
        title(d, "Bilder"); d.text((W//2, 125), "Keine lokalen Bilder gefunden", font=F18, fill=GREY, anchor="mm"); return
    img.paste(pic["img"])

def v_kal(d, img):
    title(d, "Kalender"); evs = data["kal"]
    if evs is None:
        d.text((W//2, 110), "Google Kalender", font=F22, fill=WHITE, anchor="mm")
        d.text((W//2, 140), data["kal_err"] or "Lade …", font=F18, fill=GREY, anchor="mm"); return
    if not evs: d.text((W//2, 125), "Keine Termine in 3 Wochen", font=F18, fill=GREY, anchor="mm"); return
    y = 38; today = datetime.date.today()
    for s, ganz, name in evs[:7]:
        dd = s.date()
        tag = "Heute" if dd == today else "Morgen" if dd == today + datetime.timedelta(days=1) else f"{KURZ[dd.weekday()]} {dd:%d.%m.}"
        zeit = "ganzt." if ganz else s.strftime("%H:%M")
        d.text((16, y), tag, font=F15, fill=YEL if dd == today else BLUE)
        d.text((92, y), zeit, font=F15, fill=GREY)
        d.text((146, y), fit(d, name, F15, 160), font=F15, fill=WHITE)
        y += 28

RENDER = {"Uhr": v_uhr, "Musik": v_musik, "Netzwerk": v_netz, "System": v_system, "Wetter": v_wetter, "Bilder": v_bilder, "Kalender": v_kal, "Stream Deck": v_stream}

# ---------- WhatsApp-Popup ----------
WA_GREEN = (37, 211, 102)
def make_wa_icon(size):
    S = size * 4; im = Image.new("RGBA", (S, S), (0,0,0,0)); d = ImageDraw.Draw(im)
    c, R = S / 2, S * 0.40
    d.ellipse((c-R, c-R, c+R, c+R), fill=WHITE)                                   # Sprechblase
    d.polygon([(c - R*0.80, c + R*0.45), (c - R*0.98, c + R*1.10), (c - R*0.30, c + R*0.88)], fill=WHITE)
    r2 = R * 0.84
    d.ellipse((c-r2, c-r2, c+r2, c+r2), fill=WA_GREEN)
    d.polygon([(c - R*0.72, c + R*0.52), (c - R*0.80, c + R*0.86), (c - R*0.42, c + R*0.74)], fill=WA_GREEN)
    rh, wdt = R * 0.40, R * 0.20                                                   # Telefonhoerer
    d.arc((c-rh, c-rh, c+rh, c+rh), 70, 200, fill=WHITE, width=int(wdt))
    for ang in (58, 212):
        a = np.radians(ang); x, y = c + rh*0.92*np.cos(a), c + rh*0.92*np.sin(a); b = wdt * 0.95
        d.ellipse((x-b, y-b, x+b, y+b), fill=WHITE)
    im = im.rotate(0).resize((size, size), Image.LANCZOS)
    return im
WA_ICON = make_wa_icon(120)

def draw_wa(img, d):
    wa = CFG.get("whatsapp", {})
    img.paste(Image.new("RGB", (W, H), (8, 20, 14)))
    d.rectangle((0, 0, W-1, H-1), outline=WA_GREEN, width=3)
    name = st["wa_name"] if wa.get("absender_anzeigen", True) else ""
    text = st["wa_text"] if wa.get("text_anzeigen", False) else ""
    y_icon = 14 if (name or text) else 40
    img.paste(WA_ICON, ((W - 120)//2, y_icon), WA_ICON)
    d.text((W//2, y_icon + 140), "WhatsApp", font=F28, fill=WHITE, anchor="mm")
    if name: d.text((W//2, y_icon + 175), fit(d, name, F22, 296), font=F22, fill=WA_GREEN, anchor="mm")
    if text: d.text((W//2, y_icon + 202), fit(d, text, F15, 296), font=F15, fill=GREY, anchor="mm")
    elif not name: d.text((W//2, y_icon + 172), "Neue Nachricht", font=F22, fill=WA_GREEN, anchor="mm")

WA_EVENT = os.path.join(BASE, "whatsapp_event.json")
WA_SCRIPT = os.path.join(BASE, "whatsapp_waechter.py")
WA_LOCK = os.path.join(BASE, "whatsapp_login.lock")
WA_PROFILE = os.path.join(BASE, "whatsapp_profil")
def wa_procs(login=None):
    out = []
    for p in psutil.process_iter(["cmdline"]):
        try:
            cl = " ".join(p.info["cmdline"] or [])
            if "whatsapp_waechter.py" in cl and (login is None or (("--login" in cl) == login)): out.append(p)
        except Exception: pass
    return out
def lock_active():
    try:
        pid = int(open(WA_LOCK).read().strip() or 0)
        return psutil.pid_exists(pid)
    except Exception: return False

def wa_thread():
    try: last = os.path.getmtime(WA_EVENT)
    except OSError: last = 0
    check_t = 0
    while True:
        time.sleep(0.3)
        try:
            m = os.path.getmtime(WA_EVENT) if os.path.exists(WA_EVENT) else 0
            if m and m != last:
                last = m
                with open(WA_EVENT, encoding="utf-8") as f: ev = json.load(f)
                if time.time() - float(ev.get("t", 0)) < 30:
                    st["wa_name"], st["wa_text"], st["wa_t"] = str(ev.get("name", "")), str(ev.get("text", "")), time.time()
                    log.info("WhatsApp-Popup: %s", st["wa_name"] or "(ohne Name)")
        except Exception: pass
        if time.time() - check_t > 10:                                  # Waechter-Prozess ueberwachen
            check_t = time.time()
            try:
                wa = CFG.get("whatsapp", {})
                if wa.get("aktiv") and os.path.exists(WA_SCRIPT) and os.path.isdir(WA_PROFILE) and not lock_active():
                    if not wa_procs(login=False):
                        exe = sys.executable.replace("python.exe", "pythonw.exe")
                        subprocess.Popen([exe, WA_SCRIPT], cwd=BASE, creationflags=NOWIN)
                        log.info("WhatsApp-Waechter gestartet")
                elif not wa.get("aktiv"):
                    for p in wa_procs(login=False): p.terminate(); log.info("WhatsApp-Waechter beendet (deaktiviert)")
            except Exception as e: log.info("WhatsApp-Waechter Fehler: %s", e)

def render():
    img = Image.new("RGB", (W, H)); d = ImageDraw.Draw(img)
    try: RENDER[cur_view()](d, img)
    except Exception as e: d.text((16, 110), f"Fehler: {e}"[:40], font=F15, fill=(255,80,80))
    try: wa_dauer = max(0.5, float(CFG.get("whatsapp", {}).get("dauer", 3)))
    except Exception: wa_dauer = 3
    if time.time() - st["wa_t"] < wa_dauer:
        draw_wa(img, d)
    elif time.time() - st["menu_t"] < 2.5:
        d.rectangle((60, 30, 260, 30 + 24 * len(VIEWS) + 12), fill=(20,20,30), outline=BLUE)
        for i, v in enumerate(VIEWS):
            d.text((80, 38 + 24 * i), ("> " if i == st["view"] else "   ") + v, font=F18, fill=YEL if i == st["view"] else WHITE)
    elif time.time() - st["last_t"] < 2:
        d.rectangle((40, 112, 280, 138), fill=(20,20,30), outline=YEL)
        d.text((W//2, 125), st["last"], font=F18, fill=YEL, anchor="mm")
    return img

def to_frame(img):
    a = np.asarray(img.convert("RGB"), dtype=np.uint16)
    v = ((a[:,:,0] & 0xF8) << 8) | ((a[:,:,1] & 0xFC) << 3) | (a[:,:,2] >> 3)
    return HEADER + v.T.astype("<u2").tobytes()

# ---------- Display-Tasten (Endpoint 0x81) ----------
L_UP, L_DOWN, L_LEFT, L_RIGHT, L_OK, L_MENU, L_BACK, L_SET = 128, 64, 32, 16, 8, 4, 2, 1
lcd = {"dev": None, "apply": True}
def apply_brightness(dev):
    if not CFG.get("helligkeit_setzen"): return
    v = max(0, min(100, int(CFG.get("helligkeit", 100))))
    try:
        dev.ctrl_transfer(0x41, 0x0A, 0, 0, [v, 0xE2, 0x12, 0x00, 0x8C, 0x11, 0x00, 0x10, 0x00], timeout=1000)
        log.info("Helligkeit gesetzt: %d %%", v)
    except Exception as e: log.info("Helligkeit nicht setzbar: %s", e)
def lkeys_thread():
    prev = 0
    while True:
        dev = lcd["dev"]
        if dev is None: time.sleep(0.5); continue
        try: r = list(dev.read(0x81, 64, timeout=200))
        except usb.core.USBTimeoutError: continue
        except Exception: time.sleep(0.5); continue
        for i in range(0, len(r), 2):
            b = r[i]; down = b & ~prev; prev = b
            n = len(VIEWS)
            if down & (L_RIGHT | L_DOWN): st["view"] = (st["view"] + 1) % n; st["pic_next"] = True
            if down & (L_LEFT | L_UP): st["view"] = (st["view"] - 1) % n; st["pic_next"] = True
            if down & L_MENU: st["menu_t"] = time.time()
            if down & (L_BACK | L_SET): st["view"] = 0
            if down & L_OK and cur_view() == "Bilder": st["pic_next"] = True
            if down & L_OK: st["wa_t"] = 0                      # OK schliesst WhatsApp-Popup
            if down & (L_RIGHT | L_LEFT | L_UP | L_DOWN): st["menu_t"] = time.time() - 1.3

def lcd_loop():
    psutil.cpu_percent(interval=None)
    while True:
        try:
            if lcd["dev"] is None:
                be = usb.backend.libusb1.get_backend(find_library=lambda x: libusb_package.get_library_path())
                dev = usb.core.find(idVendor=VID, idProduct=PID, backend=be)
                if dev is None: time.sleep(5); continue
                usb.util.claim_interface(dev, 0); lcd["dev"] = dev; lcd["apply"] = True; log.info("LCD verbunden")
            if lcd["apply"]: lcd["apply"] = False; apply_brightness(lcd["dev"])
            lcd["dev"].write(0x02, to_frame(render()), timeout=2000)
        except usb.core.USBError:
            try: usb.util.dispose_resources(lcd["dev"])
            except Exception: pass
            lcd["dev"] = None; time.sleep(3); continue
        step = 0.1 if cur_view() in ("Musik", "Stream Deck") else 0.25
        time.sleep(step - (time.time() % step))

# ---------- G-/M-Tasten (SendInput) ----------
VK = {"CTRL":0x11,"LCTRL":0xA2,"RCTRL":0xA3,"SHIFT":0x10,"LSHIFT":0xA0,"RSHIFT":0xA1,"ALT":0x12,"LALT":0xA4,"RALT":0xA5,
      "WIN":0x5B,"ENTER":0x0D,"SPACE":0x20,"SPACEBAR":0x20,"TAB":0x09,"ESC":0x1B,"BACKSPACE":0x08,"DEL":0x2E,"INS":0x2D,
      "HOME":0x24,"END":0x23,"PGUP":0x21,"PGDN":0x22,"LEFT":0x25,"UP":0x26,"RIGHT":0x27,"DOWN":0x28,
      "PLAYPAUSE":0xB3,"NEXT":0xB0,"PREV":0xB1,"MUTE":0xAD,"VOLUP":0xAF,"VOLDOWN":0xAE,"PRINT":0x2C}
for i in range(1,25): VK[f"F{i}"] = 0x6F + i
for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789": VK[c] = ord(c)
EXT = {0x25,0x26,0x27,0x28,0x2D,0x2E,0x24,0x23,0x21,0x22,0xA3,0xA5,0x5B}
ULONG_PTR = ctypes.c_size_t
class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk",wintypes.WORD),("wScan",wintypes.WORD),("dwFlags",wintypes.DWORD),("time",wintypes.DWORD),("dwExtraInfo",ULONG_PTR)]
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx",wintypes.LONG),("dy",wintypes.LONG),("mouseData",wintypes.DWORD),("dwFlags",wintypes.DWORD),("time",wintypes.DWORD),("dwExtraInfo",ULONG_PTR)]
class _U(ctypes.Union): _fields_ = [("ki",KEYBDINPUT),("mi",MOUSEINPUT)]
class INPUT(ctypes.Structure): _fields_ = [("type",wintypes.DWORD),("u",_U)]
user32 = ctypes.WinDLL("user32", use_last_error=True)
def key(vk, up):
    flags = (0x0002 if up else 0) | (0x0001 if vk in EXT else 0)
    inp = INPUT(type=1, u=_U(ki=KEYBDINPUT(vk, user32.MapVirtualKeyW(vk, 0), flags, 0, 0)))
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
def parse(spec):
    alias = {"STRG": "CTRL", "UMSCHALT": "SHIFT", "EINGABE": "ENTER", "ENTF": "DEL", "LOESCHEN": "DEL", "LÖSCHEN": "DEL", "LEERTASTE": "SPACE"}
    out = []
    for p in str(spec).split("+"):
        p = alias.get(p.strip().upper(), p.strip().upper())
        if p in VK: out.append(VK[p])
    return out
def tap(vks):
    for v in vks: key(v, False)
    time.sleep(0.04)
    for v in reversed(vks): key(v, True)
def type_text(text):
    for ch in str(text).replace("\\n", "\n").replace("\\t", "\t")[:400]:
        if ch in "\r\n": tap([VK["ENTER"]]); continue
        if ch == "\t": tap([VK["TAB"]]); continue
        code = ord(ch)
        if code > 0xFFFF: continue
        down = INPUT(type=1, u=_U(ki=KEYBDINPUT(0, code, 0x0004, 0, 0)))
        up = INPUT(type=1, u=_U(ki=KEYBDINPUT(0, code, 0x0004 | 0x0002, 0, 0)))
        user32.SendInput(1, ctypes.byref(down), ctypes.sizeof(INPUT))
        user32.SendInput(1, ctypes.byref(up), ctypes.sizeof(INPUT))
def open_target(wert, web=False):
    wert = os.path.expandvars(str(wert).strip().strip('"'))
    if not wert: return
    if web and "://" not in wert: wert = "https://" + wert
    try: os.startfile(wert)
    except OSError: subprocess.Popen([wert], creationflags=NOWIN)
def run_deck(name):
    slot = next((s for s in g19_deck.normalize(CFG.get("streamdeck")) if s["taste"] == name), None)
    if not slot: return
    akt, wert = slot["aktion"], slot["wert"]
    log.info("Stream Deck %s → %s", name, slot["name"] or akt)
    if akt == "taste": tap(parse(wert))
    elif akt in ("programm", "ordner"): open_target(wert)
    elif akt == "web": open_target(wert, web=True)
    elif akt == "text": type_text(wert)
def load_cfg():
    try:
        with open(os.path.join(BASE, "tasten.json"), encoding="utf-8-sig") as f: return json.load(f)
    except Exception: return {}

def keys_thread():
    cfg, cfg_t, held = load_cfg(), 0, {}
    while True:
        try:
            path = [d["path"] for d in hid.enumerate(VID, PID) if d["usage_page"] == 0xFF00][0]
            h = hid.device(); h.open_path(path); h.send_feature_report([0x05, M_LED[st["mode"]]]); prev = 0; st["kb_apply"] = True
            while True:
                r = h.read(64, 500)
                if time.time() - cfg_t > 3: cfg, cfg_t = load_cfg(), time.time()
                if st.get("kb_apply"):
                    st["kb_apply"] = False
                    if CFG.get("tastatur_farbe_setzen"):
                        try:
                            c = str(CFG.get("tastatur_farbe", "#FFFFFF")).lstrip("#")
                            h.send_feature_report([0x07, int(c[0:2],16), int(c[2:4],16), int(c[4:6],16)])
                        except Exception as e: log.info("Tastaturfarbe nicht setzbar: %s", e)
                if not r or r[0] != 2: continue
                bits = r[1] | (r[2] << 8); down, up = bits & ~prev, prev & ~bits; prev = bits
                for i, m in ((12,"M1"),(13,"M2"),(14,"M3")):
                    if down & (1 << i):
                        st["mode"] = m; h.send_feature_report([0x05, M_LED[m]]); st["last"], st["last_t"] = f"Modus {m}", time.time()
                for g in range(12):
                    b = 1 << g; name = f"G{g+1}"
                    if down & b:
                        if cur_view() == "Stream Deck" and name in g19_deck.DECK_KEYS:
                            st["deck_hit"] = (name, time.time())
                            try: run_deck(name)
                            except Exception as e: log.info("Stream Deck %s: %s", name, e)
                            held[name] = []
                        else:
                            spec = cfg.get(st["mode"], {}).get(name, ""); vks = parse(spec)
                            for v in vks: key(v, False)
                            held[name] = vks; st["last"], st["last_t"] = f"{name} → {spec or '-'}", time.time()
                    if up & b:
                        for v in reversed(held.pop(name, [])): key(v, True)
        except Exception:
            for vks in held.values():
                for v in reversed(vks): key(v, True)
            held.clear(); time.sleep(3)

if __name__ == "__main__":
    ctypes.windll.kernel32.CreateMutexW(None, False, "G19Helfer_einmalig")
    if ctypes.windll.kernel32.GetLastError() == 183: sys.exit(0)
    log.info("G19 Helfer v3 startet")
    try:
        cfg_state["mtime"] = os.path.getmtime(CFG_PATH) if os.path.exists(CFG_PATH) else 0
        new = json.loads(json.dumps(DEFAULTS))
        if cfg_state["mtime"]:
            with open(CFG_PATH, encoding="utf-8-sig") as f: merge(new, json.load(f))
        apply_cfg(new)
    except Exception as e: log.info("Einstellungen fehlerhaft: %s", e)
    for t in (cfg_thread, wa_thread, keys_thread, lkeys_thread, net_thread, gpu_thread, wetter_thread, musik_thread, kal_thread):
        threading.Thread(target=t, daemon=True).start()
    lcd_loop()

