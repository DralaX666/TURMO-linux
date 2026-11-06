# Contributing

Thanks for your interest in TURMO Linux.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
```

Quick visual check without a display:

```bash
python3 tools/preview_themes.py docs/themes
python3 -m turmo_display --preview /tmp/turmo.png --fake --theme nord
python3 -m turmo_display.webapp --demo   # editor with demo statistics
```

## Themes

New themes are added in `turmo_display/themes.py`:

1. Add a `Theme` or `_theme(...)` entry to `THEMES`.
2. Use the semantic color names (`accent`, `text`, `muted`, `plot_bg`, ...).
3. Add a preview to `docs/themes/`.
4. Run the tests and check both portrait and landscape layouts.

If you change the renderer, verify that it still works with disabled panels
(`show_*: false`) and with `theme_colors` overrides.

## Web GUI

The editor is a **separate on-demand process** (`turmo_display/webapp.py`) so
the display service can keep running without an HTTP server. It writes
`config.json`; the display loop notices the mtime change and reloads it within
about a second.

The web part lives in `turmo_display/webui/` (`server.py`, `index.html`,
`app.js`, `style.css`, `locales/`) and uses only the Python standard library.
The API is intentionally small:

- `GET /api/state` — configuration, themes and display status
- `POST /api/config` — partial configuration update (validated)
- `POST /api/shutdown` — stop the editor (display keeps running)
- `GET /api/preview.png` — preview rendered with live system data
- `GET /api/theme-preview/<theme>.png` — preview of a single theme
- `GET /locales/<code>.json` — UI translations

When adding a setting, update `DEFAULT_CONFIG`, `sanitize_changes()` (if it may
be changed from the GUI) and the form in `app.js`.

## Translations

Locale files are plain JSON in `turmo_display/webui/locales/`:

- `en.json` is the source of truth.
- Every locale must have exactly the same keys as `en.json`; a test enforces it.
- Use the `{name}` placeholders exactly as they appear in English.
- Keep technical terms (CPU, GPU, RAM, config.json) unchanged.

To add a language, create `<code>.json`, add the option to the language selector
and the first-launch gate in `index.html`, and add the code to `LANGUAGES` in
`app.js` and `LOCALES` in `server.py`.

## Pull requests

- One logical change per PR.
- No `config.json`, local paths or generated files.
- Add a test or preview for new functionality.
- Describe what changed and how it was tested.

## License

Contributions are released under the project's GPL-3.0 license.
