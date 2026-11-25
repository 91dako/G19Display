# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 DaKo-Soft
# G19 WhatsApp-Waechter: haelt WhatsApp Web (eigenes Chrome-Profil) im Hintergrund offen
# und schreibt bei neuen Nachrichten whatsapp_event.json -> der G19-Helfer zeigt dann das Popup.
#   pythonw whatsapp_waechter.py          -> unsichtbar im Hintergrund (startet der G19-Helfer automatisch)
#   pythonw whatsapp_waechter.py --login  -> sichtbares Fenster mit QR-Code zum Anmelden
import os, sys, json, time, re, ctypes, logging, logging.handlers, winreg
import psutil

BASE = os.path.dirname(os.path.abspath(__file__))
PROFILE = os.path.join(BASE, "whatsapp_profil")
EVENT = os.path.join(BASE, "whatsapp_event.json")
STATUS = os.path.join(BASE, "whatsapp_status.json")
LOCK = os.path.join(BASE, "whatsapp_login.lock")
CFG_PATH = os.path.join(BASE, "einstellungen.json")
URL = "https://web.whatsapp.com/"
LOGIN = "--login" in sys.argv

log = logging.getLogger("wa")
_h = logging.handlers.RotatingFileHandler(os.path.join(BASE, "whatsapp_waechter.log"), maxBytes=300_000, backupCount=1, encoding="utf-8")
_h.setFormatter(logging.Formatter("%(asctime)s %(message)s")); log.addHandler(_h); log.setLevel(logging.INFO)

def write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)

def status(s, **kw):
    try: write_json(STATUS, dict({"status": s, "t": time.time(), "pid": os.getpid()}, **kw))
    except Exception: pass

def cfg():
    try:
        with open(CFG_PATH, encoding="utf-8-sig") as f: return json.load(f).get("whatsapp", {})
    except Exception: return {}

def chrome_version():
    for root, key in ((winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon"),
                      (winreg.HKEY_LOCAL_MACHINE, r"Software\Google\Chrome\BLBeacon")):
        try:
            with winreg.OpenKey(root, key) as k: return winreg.QueryValueEx(k, "version")[0]
        except OSError: pass
    return "131.0.0.0"

UA = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_version().split('.')[0]}.0.0.0 Safari/537.36"

# Abfrage im Browser: angemeldet? QR sichtbar? ungelesene Chats mit Namen
JS_STATE = r"""() => {
  const pane = document.querySelector('#pane-side');
  const qr = !!document.querySelector('canvas[aria-label], div[data-ref]');
  const chats = {}; let rowsN = 0;
  if (pane) {
    const rows = pane.querySelectorAll('[role="listitem"], [role="row"]'); rowsN = rows.length;
    rows.forEach(row => {
      let n = 0;
      row.querySelectorAll('span[aria-label]').forEach(sp => {
        const al = sp.getAttribute('aria-label') || '';
        if (/ungelesen|unread/i.test(al)) {
          const m = al.match(/\d+/) || (sp.textContent || '').match(/\d+/);
          n = Math.max(n, m ? parseInt(m[0]) : 1);
        }
      });
      if (n > 0) {
        const t = row.querySelector('span[title][dir="auto"], span[dir="auto"][title], span[title]');
        const name = t ? (t.getAttribute('title') || t.textContent) : '';
        chats[name || ('chat' + Object.keys(chats).length)] = n;
      }
    });
  }
  const m = document.title.match(/^\((\d+)\)/);
  return {logged: !!pane, qr: qr && !pane, title: m ? parseInt(m[1]) : 0, chats: chats, rows: rowsN};
}"""

# Benachrichtigungen von WhatsApp Web abfangen (liefert Absender + Text, falls WhatsApp welche sendet)
JS_NOTIFY = r"""(() => {
  const N = function(title, opts) { try { window.g19Notify(String(title || ''), String((opts && opts.body) || '')); } catch (e) {}
    this.close = () => {}; this.addEventListener = () => {}; this.onclick = null; };
  N.permission = 'granted'; N.requestPermission = (cb) => { cb && cb('granted'); return Promise.resolve('granted'); };
  try { Object.defineProperty(window, 'Notification', {value: N, configurable: true, writable: true}); } catch (e) { window.Notification = N; }
})();"""

state = {"last_ev": 0}
def fire(name, text, quelle):
    if time.time() - state["last_ev"] < 4: return
    state["last_ev"] = time.time()
    write_json(EVENT, {"t": time.time(), "name": name, "text": text, "quelle": quelle})
    log.info("Neue Nachricht (%s): %s", quelle, name or "?")

def other_watchers():
    out = []
    for p in psutil.process_iter(["cmdline"]):
        try:
            if p.pid == os.getpid(): continue
            cl = " ".join(p.info["cmdline"] or [])
            if "whatsapp_waechter.py" in cl: out.append(p)
        except Exception: pass
    return out

def main():
    from playwright.sync_api import sync_playwright
    if LOGIN:
        with open(LOCK, "w") as f: f.write(str(os.getpid()))
        for p in other_watchers():                         # Hintergrund-Waechter beenden (Profil wird gebraucht)
            try: p.terminate(); p.wait(8)
            except Exception: pass
        time.sleep(1)
    else:
        ctypes.windll.kernel32.CreateMutexW(None, False, "G19WhatsApp_einmalig")
        if ctypes.windll.kernel32.GetLastError() == 183: return
    sichtbar = LOGIN or bool(cfg().get("fenster_sichtbar"))
    os.makedirs(PROFILE, exist_ok=True)
    log.info("Start (%s)", "Anmeldung" if LOGIN else ("sichtbar" if sichtbar else "unsichtbar"))
    with sync_playwright() as pw:
        args = ["--disable-features=Translate", "--no-first-run", "--no-default-browser-check"]
        ctx = pw.chromium.launch_persistent_context(
            PROFILE, channel="chrome", headless=not sichtbar, user_agent=UA, locale="de-DE",
            viewport=None if sichtbar else {"width": 1280, "height": 900}, args=args)
        try:
            ctx.grant_permissions(["notifications"], origin=URL.rstrip("/"))
        except Exception: pass
        ctx.expose_binding("g19Notify", lambda src, title, body: fire(title, body, "benachrichtigung"))
        ctx.add_init_script(JS_NOTIFY)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(URL, wait_until="domcontentloaded", timeout=90000)
        if LOGIN: run_login(ctx, page)
        else: run_watch(ctx, page)
        try: ctx.close()
        except Exception: pass

def run_login(ctx, page):
    status("warte_auf_qr")
    logged_t = None
    while True:
        if page.is_closed() or not ctx.pages:
            status("angemeldet" if logged_t else "abgebrochen"); log.info("Anmeldefenster geschlossen"); return
        try: s = page.evaluate(JS_STATE)
        except Exception: s = {"logged": False, "qr": False}
        if s.get("logged"):
            if not logged_t: logged_t = time.time(); status("angemeldet_sync"); log.info("Angemeldet, synchronisiere ...")
            if time.time() - logged_t > 20:                # Zeit zum Speichern der Sitzung lassen
                status("angemeldet"); log.info("Anmeldung fertig"); return
        elif s.get("qr"): status("warte_auf_qr")
        try: page.wait_for_timeout(1000)
        except Exception: pass

def run_watch(ctx, page):
    prev, baseline, start, not_logged_t = {}, None, time.time(), None
    reload_t = time.time()
    while True:
        if os.path.exists(LOCK):
            try:
                if psutil.pid_exists(int(open(LOCK).read().strip() or 0)): log.info("Anmeldung laeuft -> beende"); return
            except Exception: pass
        c = cfg()
        if not c.get("aktiv", False): log.info("Deaktiviert -> beende"); status("aus"); return
        if time.time() - reload_t > 6 * 3600:              # alle 6 h frisch laden
            reload_t = time.time(); baseline = None; page.reload(wait_until="domcontentloaded", timeout=90000)
        try: s = page.evaluate(JS_STATE)
        except Exception as e:
            log.info("Seite nicht lesbar: %s", e); page.wait_for_timeout(3000)
            if page.is_closed(): return
            continue
        if not s["logged"]:
            not_logged_t = not_logged_t or time.time()
            if s["qr"] and time.time() - not_logged_t > 60:
                status("nicht_angemeldet")
                page.wait_for_timeout(30000); continue
            page.wait_for_timeout(2000); continue
        not_logged_t = None
        chats, total = s["chats"], max(sum(s["chats"].values()), s["title"])
        if baseline is None:
            if time.time() - start > 5 or chats or s["title"]:
                baseline = total; prev = chats; prev_title = s["title"]; status("verbunden", ungelesen=total)
                log.info("Verbunden, ungelesen: %d, Chats in Liste: %s, ungelesene Chats: %s", total, s.get("rows"), list(chats))
            page.wait_for_timeout(2000); continue
        new = [n for n, k in chats.items() if k > prev.get(n, 0)]
        if new:
            fire(new[0] if not new[0].startswith("chat") else "", "", "liste")
        elif not chats and s["title"] > prev_title:
            fire("", "", "titel")
        if total != baseline: status("verbunden", ungelesen=total)
        prev, baseline, prev_title = chats, total, s["title"]
        page.wait_for_timeout(2000)

if __name__ == "__main__":
    try: main()
    except Exception as e:
        log.exception("Fehler: %s", e); status("fehler", fehler=str(e)[:200])
    finally:
        if LOGIN:
            try: os.remove(LOCK)
            except Exception: pass
