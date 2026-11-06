# Changelog

## 1.4.0

- The web control panel is now a separate **on-demand editor**
  (`turmo_display.webapp`). The display service runs continuously without an
  HTTP server.
- The editor starts from the desktop shortcut and stops when the browser tab is
  closed (detected in about 3 seconds), with the **Stop control panel** button,
  or after 20 seconds without requests.
- The display service reloads `config.json` automatically when the editor saves;
  no restart is needed.
- Removed `web_enabled` and `web_host`; the editor always binds to `127.0.0.1`.
- Added a live preview rendered with real system data in the editor.
- Added Stop action to the desktop shortcut and a Stop button in the header and
  footer; both terminate the editor process and free the port immediately.
- Added regression tests for the preview provider and shutdown endpoint.

## 1.3.0

- English is now the primary project language (UI, CLI, logs, API errors, docs).
- Added UI translations for English, German, Simplified Chinese and Serbian.
- Added a first-launch language chooser; the choice is stored per browser and
  can be changed from the header at any time.
- Added a desktop shortcut (`tools/install-desktop-shortcut.sh`) with actions
  to open the control panel, edit `config.json` and restart the service.
- Added a portable per-user service installer
  (`tools/install-user-service.sh`).
- Added project icon and favicon.
- Added English README, kept Serbian documentation in `README.sr.md`.
- Added locale completeness tests (17 tests total).
- Dashboard date abbreviations are now English.

## 1.2.0

- Dodata web kontrolna tabla (`http://IP:8777`) sa uživo pregledom displeja.
- Izbor tema, panela, detalja, naslova, orijentacije, osvetljenja i brzine
  osvežavanja iz browsera; promene se primenjuju bez restarta.
- Color picker za svaku boju izabrane teme, sa vraćanjem na podrazumevanu paletu.
- Konfiguracija se automatski upisuje u `config.json` (atomski).
- Web GUI radi u pozadini servisa, bez dodatnih zavisnosti (stdlib HTTP server).
- Dodati `runtime.py`, `webui/` i testovi za web API.

## 1.1.0

- Dodato 8 ugrađenih tema: Blackbox, Nord, Dracula, Gruvbox, Solarized, Light,
  Mono Green i Amber CRT.
- Dodat izbor teme kroz `theme` u konfiguraciji i `--theme` u CLI-ju.
- Dodate proizvoljne izmjene boja kroz `theme_colors`.
- Dodati detaljni prekidači za CPU temperaturu, frekvenciju, load, istoriju,
  swap, mrežne totalе, GPU memoriju i GPU ventilator.
- Dodati `--list-themes`, `tools/preview_themes.py` i render testovi.
- Dodata galerija tema i dokumentacija za sve opcije prikaza.

## 1.0.0

- Početna verzija: Turing Smart Screen rev. A protokol, BLACKBOX dashboard,
  systemd servis, udev pravilo i preview režim.
