# G19Display

**English summary:** A Windows helper that drives the Logitech G19 keyboard LCD when the official Logitech software is blocked by Windows Memory Integrity (Core Isolation). It talks to the LCD over WinUSB (installed with [Zadig](https://zadig.akeo.ie/)) and to the G-/M-keys over HID. Seven views (clock, media, network, system, weather, pictures, calendar), a settings app, G-key bindings, and an optional WhatsApp Web popup on new messages.

---

Ein kleiner Helfer für Windows, der das LCD der **Logitech G19** selbst ansteuert. Die offizielle Logitech-Software und ihr Treiber werden von der **Speicherintegrität** (Kernisolierung / Memory Integrity) in Windows oft blockiert oder ausgeschlossen. Dieses Programm nutzt deshalb **WinUSB** (über [Zadig](https://zadig.akeo.ie/)) für das Display und den normalen HID-Zugang für die G- und M-Tasten.

## Funktionen

- **Sieben Ansichten** auf dem 320×240-Display: Uhr, Musik (aktuell laufende Wiedergabe), Netzwerk, System (CPU, RAM, GPU), Wetter, Bilder-Diashow, Kalender
- Wechsel mit den Pfeiltasten am Display, Übersicht mit der Menütaste
- **Einstellungs-App** (`g19_einstellungen.pyw`): Ansichten ein- und ausschalten und sortieren, Bilderordner, Wetterort, Kalender-Adresse, Display-Helligkeit, Tastaturfarbe, G-Tasten, WhatsApp
- **G-Tasten** in den Modi M1–M3 belegen (zum Beispiel `CTRL+C` oder `F5`)
- **WhatsApp-Popup:** Nach der Anmeldung über WhatsApp Web erscheint bei einer neuen Nachricht kurz das WhatsApp-Symbol auf dem Display (Dauer einstellbar, Absender optional)

## Voraussetzungen

- Windows 10 oder 11
- Logitech G19
- [Python 3.12](https://www.python.org/downloads/) (auch neuere 3.x-Versionen sollten funktionieren)
- [Zadig](https://zadig.akeo.ie/), um WinUSB für das LCD zu installieren
- Für WhatsApp: Google Chrome (die Überwachung nutzt das installierte Chrome)

## Treiber mit Zadig

1. [Zadig](https://zadig.akeo.ie/) herunterladen und als Administrator starten.
2. Unter **Options** den Haken bei **List All Devices** setzen.
3. Das **LCD-Interface** der G19 auswählen (Vendor ID `046D`, Product ID `C229`, in der Regel Interface 0, oft als „Logitech G19 LCD“ oder ähnlich bezeichnet).
4. Als Treiber **WinUSB** wählen und installieren.
5. Die HID-Schnittstellen der Tastatur und der G-Tasten **nicht** ersetzen – sonst funktionieren Tasten oder Makros nicht mehr.

Wenn die Speicherintegrität den alten Logitech-LCD-Treiber blockiert, ist genau dieser Schritt der Ersatz dafür.

## Installation

1. Repository klonen oder als ZIP herunterladen:

   ```powershell
   git clone https://github.com/91dako/G19Display.git
   cd G19Display
   ```

2. Abhängigkeiten installieren (am besten in derselben Python-Version, die später `pythonw` nutzt):

   ```powershell
   py -3.12 -m pip install -r requirements.txt
   ```

3. Optional die Beispieldateien kopieren und anpassen (oder alles in der Einstellungs-App setzen):

   ```powershell
   copy einstellungen.example.json einstellungen.json
   copy kalender_url.example.txt kalender_url.txt
   copy tasten.example.json tasten.json
   ```

   `einstellungen.json`, `kalender_url.txt` und die WhatsApp-Sitzung gehören **nicht** ins Git-Repository – sie enthalten private Daten.

4. Einstellungs-App starten:

   ```powershell
   pyw -3.12 g19_einstellungen.pyw
   ```

5. In der App **Helfer neu starten**, oder den Helfer direkt starten:

   ```powershell
   pyw -3.12 g19_display.py
   ```

### Desktop-Verknüpfung

Eine Verknüpfung auf `pyw.exe` (oder `pythonw.exe`) mit dem Ziel `g19_einstellungen.pyw` anlegen, als Arbeitsverzeichnis den Projektordner wählen und als Symbol `g19_einstellungen.ico` verwenden.

### Autostart

Damit der Helfer nach der Anmeldung automatisch läuft, einen Eintrag in der Benutzer-Autostart-Registry anlegen, zum Beispiel:

```powershell
$pyw = (Get-Command pyw).Source
# oder der volle Pfad zu pythonw.exe, z. B. unter %LocalAppData%\Programs\Python\Python312\
$dir = "C:\Pfad\zu\G19Display"
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v G19Helfer /t REG_SZ /d "`"$pyw`" `"$dir\g19_display.py`"" /f
```

Der Helfer startet unsichtbar. Die Einstellungen öffnest du weiter über die Desktop-Verknüpfung oder `g19_einstellungen.pyw`.

## Nutzung

| Display-Taste | Funktion |
| ------------- | -------- |
| Links / Rechts (oder Hoch / Runter) | Vorherige / nächste Ansicht |
| Menü | Übersicht der Ansichten |
| OK | Nächstes Bild (in der Bildansicht); schließt ein WhatsApp-Popup |
| Zurück / Einstellungen | Zurück zur ersten Ansicht |

**Wetter:** In der Einstellungs-App einen Ort suchen. Die Vorhersage kommt von [Open-Meteo](https://open-meteo.com/).

**Kalender:** In Google Kalender unter *Einstellungen → Integration* die **Privatadresse im iCal-Format** kopieren und in der App eintragen. Diese URL ist ein Geheimnis – nicht veröffentlichen.

**WhatsApp:** Im Reiter *WhatsApp* die Funktion einschalten und auf **Mit WhatsApp verbinden** klicken. Am Handy unter *Verknüpfte Geräte* den QR-Code scannen. Das Anmeldefenster schließt sich danach von selbst; die Überwachung läuft unsichtbar weiter. Mit **Test-Popup** kannst du prüfen, ob das Symbol auf dem Display erscheint.

## Dateien

| Datei | Bedeutung |
| ----- | --------- |
| `g19_display.py` | Helfer (LCD, Tasten, Ansichten) |
| `g19_einstellungen.pyw` | Einstellungs-App |
| `whatsapp_waechter.py` | WhatsApp-Web-Überwachung |
| `tasten.json` | Belegung der G-Tasten (lokal; Vorlage: `tasten.example.json`) |
| `einstellungen.json` | Alle anderen Einstellungen (lokal; Vorlage: `einstellungen.example.json`) |
| `kalender_url.txt` | Fallback für die Kalender-Adresse (lokal) |

## Mitwirken

Fehler, Ideen und Verbesserungen sind willkommen: Issue oder Pull Request auf GitHub. Änderungen, die du weitergibst, müssen unter der GPL-3.0 offenbleiben (siehe Lizenz).

## Lizenz

Dieses Programm ist freie Software unter der **GNU General Public License, Version 3** (oder – nach deiner Wahl – jeder späteren Version). Den vollständigen Text findest du in der Datei [`LICENSE`](LICENSE).

Copyright (C) 2026 DaKo-Soft
