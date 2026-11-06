"use strict";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

const LANGUAGES = ["en", "de", "zh", "sr"];
const STORAGE_KEY = "turmo.lang";

const PANEL_KEYS = [
  "show_clock",
  "show_cpu",
  "show_gpu",
  "show_system",
  "show_memory",
  "show_network",
  "show_tiles",
  "show_footer",
];

const DETAIL_KEYS = [
  "show_cpu_temp",
  "show_cpu_freq",
  "show_cpu_load",
  "show_cpu_history",
  "show_swap",
  "show_net_totals",
  "show_net_history",
  "show_gpu_mem",
  "show_gpu_fan",
];

const TILE_KEYS = ["show_disk", "show_fan", "show_free", "show_procs"];

const COLOR_KEYS = [
  "accent",
  "bg_top",
  "bg_bottom",
  "grid",
  "card",
  "card_shadow",
  "border",
  "highlight",
  "track",
  "text",
  "muted",
  "dim",
  "amber",
  "blue",
  "green",
  "red",
  "plot_bg",
  "plot_grid",
];

const app = {
  config: {},
  themes: [],
  status: {},
  revision: -1,
  configPath: "",
  themesBuilt: false,
  colorsBuilt: false,
  locale: "en",
  strings: {},
  fallbackStrings: {},
  localeCache: {},
  pendingLanguage: null,
  toastTimer: null,
  stateTimer: null,
  brightnessTimer: null,
  refreshTimer: null,
  colorTimer: null,
  previewTimer: null,
  events: null,
  stopped: false,
};

/* --------------------------------------------------------------- i18n */

async function loadLocale(code) {
  if (app.localeCache[code]) {
    return app.localeCache[code];
  }
  const response = await fetch(`/locales/${code}.json`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  const data = await response.json();
  app.localeCache[code] = data;
  return data;
}

function t(key, vars = {}, fallback = null) {
  const template =
    app.strings[key] !== undefined
      ? app.strings[key]
      : app.fallbackStrings[key] !== undefined
        ? app.fallbackStrings[key]
        : fallback !== null
          ? fallback
          : key;
  return String(template).replace(/\{(\w+)\}/g, (match, name) =>
    vars[name] !== undefined ? String(vars[name]) : match
  );
}

function applyTranslations(root = document) {
  for (const element of root.querySelectorAll("[data-i18n]")) {
    element.textContent = t(element.dataset.i18n);
  }
  for (const element of root.querySelectorAll("[data-i18n-placeholder]")) {
    element.placeholder = t(element.dataset.i18nPlaceholder);
  }
  for (const element of root.querySelectorAll("[data-i18n-aria]")) {
    element.setAttribute("aria-label", t(element.dataset.i18nAria));
  }
  document.title = `TURMO · ${t("preview.control")}`;
}

async function loadStrings() {
  if (!app.fallbackStrings || !Object.keys(app.fallbackStrings).length) {
    try {
      app.fallbackStrings = await loadLocale("en");
    } catch (error) {
      app.fallbackStrings = {};
    }
  }
  try {
    app.strings = app.locale === "en" ? app.fallbackStrings : await loadLocale(app.locale);
  } catch (error) {
    app.strings = app.fallbackStrings;
  }
}

function setLanguageSelect(code) {
  const select = $("#language-select");
  if (select) {
    select.value = code;
  }
}

async function changeLanguage(code, persist) {
  if (!LANGUAGES.includes(code)) {
    return;
  }
  app.locale = code;
  await loadStrings();
  document.documentElement.lang = code;
  applyTranslations();
  rebuildDynamic();
  setLanguageSelect(code);
  if (persist) {
    try {
      localStorage.setItem(STORAGE_KEY, code);
    } catch (error) {
      /* ignore private mode */
    }
  }
}

function updateGateSelection(code) {
  for (const option of $$(".language-option")) {
    const selected = option.dataset.lang === code;
    option.classList.toggle("selected", selected);
    option.setAttribute("aria-pressed", selected ? "true" : "false");
  }
  $("#gate-continue").disabled = !code;
}

/* ---------------------------------------------------------- dynamic UI */

function buildToggles(container, keys) {
  container.innerHTML = "";
  const fragment = document.createDocumentFragment();
  for (const key of keys) {
    const row = document.createElement("label");
    row.className = "toggle-row";
    row.innerHTML = `
      <span class="toggle-text"><strong></strong><small></small></span>
      <input type="checkbox" data-bool="${key}">
      <span class="switch" aria-hidden="true"></span>`;
    row.querySelector("strong").textContent = t(`panels.${key}.label`, {}, key);
    row.querySelector("small").textContent = t(`panels.${key}.desc`, {}, "");
    const input = row.querySelector("input");
    input.addEventListener("change", () => save({ [key]: input.checked }));
    fragment.append(row);
  }
  container.append(fragment);
}

function buildThemes() {
  const grid = $("#themes");
  grid.innerHTML = "";
  for (const theme of app.themes) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "theme-card";
    card.dataset.theme = theme.id;
    card.innerHTML = `
      <span class="theme-thumb"><img loading="lazy" alt=""></span>
      <span class="theme-name"></span>
      <span class="theme-desc"></span>`;
    const name = t(`theme.${theme.id}.name`, {}, theme.label || theme.id);
    const description = t(`theme.${theme.id}.desc`, {}, theme.description || "");
    const image = card.querySelector("img");
    image.src = `/api/theme-preview/${encodeURIComponent(theme.id)}.png`;
    image.alt = name;
    card.querySelector(".theme-name").textContent = name;
    card.querySelector(".theme-desc").textContent = description;
    card.addEventListener("click", () => {
      save({ theme: theme.id }, { message: t("toast.theme", { name }) });
    });
    grid.append(card);
  }
  app.themesBuilt = true;
}

function buildColors() {
  const grid = $("#colors");
  grid.innerHTML = "";
  for (const key of COLOR_KEYS) {
    const field = document.createElement("div");
    field.className = "color-field";
    field.dataset.color = key;
    field.innerHTML = `
      <input type="color" aria-label="">
      <label><b></b><code></code></label>
      <span class="dot" aria-hidden="true"></span>`;
    const label = t(`colors.${key}`, {}, key);
    field.querySelector("b").textContent = label;
    const input = field.querySelector("input");
    input.setAttribute("aria-label", label);
    input.addEventListener("input", () => {
      field.querySelector("code").textContent = input.value;
      clearTimeout(app.colorTimer);
      const colors = { ...(app.config.theme_colors || {}), [key]: input.value };
      app.config.theme_colors = colors;
      app.colorTimer = setTimeout(
        () => save({ theme_colors: colors }, { silent: true }),
        250
      );
    });
    grid.append(field);
  }
  app.colorsBuilt = true;
}

function rebuildDynamic() {
  app.themesBuilt = false;
  app.colorsBuilt = false;
  buildToggles($("#panel-toggles"), PANEL_KEYS);
  buildToggles($("#detail-toggles"), DETAIL_KEYS);
  buildToggles($("#tile-toggles"), TILE_KEYS);
  buildColors();
  if (app.themes.length) {
    buildThemes();
  }
  syncForm();
  updateStatus();
}

/* -------------------------------------------------------------- state */

function effectiveColors() {
  const theme = app.themes.find((item) => item.id === app.config.theme);
  return { ...(theme ? theme.colors : {}), ...(app.config.theme_colors || {}) };
}

function syncThemes() {
  for (const card of $$(".theme-card")) {
    const selected = card.dataset.theme === app.config.theme;
    card.classList.toggle("selected", selected);
    card.setAttribute("aria-pressed", selected ? "true" : "false");
  }
}

function setText(selector, value) {
  const element = $(selector);
  if (document.activeElement !== element) {
    element.value = value ?? "";
  }
}

function syncForm() {
  const config = app.config;
  for (const input of $$("input[data-bool]")) {
    if (document.activeElement !== input) {
      input.checked = Boolean(config[input.dataset.bool]);
    }
  }

  setText("#title", config.title ?? "");
  setText("#subtitle", config.subtitle ?? "");
  setText("#footer-text", config.footer_text ?? "");
  setText("#hostname", config.hostname ?? "");

  const orientation = $("#orientation");
  if (document.activeElement !== orientation) {
    orientation.value = String(config.orientation ?? 0);
  }

  const brightness = Number(config.brightness ?? 85);
  const brightnessInput = $("#brightness");
  if (document.activeElement !== brightnessInput) {
    brightnessInput.value = String(brightness);
  }
  $("#brightness-value").textContent = `${brightness}%`;

  const refresh = Number(config.refresh_seconds ?? 1);
  const refreshInput = $("#refresh");
  if (document.activeElement !== refreshInput) {
    refreshInput.value = String(refresh);
  }
  $("#refresh-value").textContent = `${refresh.toFixed(1)} s`;

  syncThemes();
  syncColors();
}

function syncColors() {
  if (!app.colorsBuilt) {
    return;
  }
  const colors = effectiveColors();
  const overrides = app.config.theme_colors || {};
  for (const field of $$(".color-field")) {
    const key = field.dataset.color;
    const input = field.querySelector("input");
    const value = colors[key] || "#000000";
    if (document.activeElement !== input) {
      input.value = value;
    }
    field.querySelector("code").textContent =
      document.activeElement === input ? input.value : value;
    field.classList.toggle("custom", Object.prototype.hasOwnProperty.call(overrides, key));
  }
  const note = $("#colors-note");
  const count = Object.keys(overrides).length;
  note.textContent =
    count === 0 ? t("colors.hint") : t("colors.hintCustom", { count });
}

function formatAge(seconds) {
  if (seconds == null) {
    return "—";
  }
  if (seconds < 3) {
    return t("age.now");
  }
  if (seconds < 60) {
    return t("age.seconds", { n: Math.round(seconds) });
  }
  return t("age.minutes", { n: Math.round(seconds / 60) });
}

function updateStatus() {
  const status = app.status || {};
  const connected = Boolean(status.connected);
  const dot = $("#status-dot");
  dot.className = `status-dot${connected ? " ok" : status.last_error ? " err" : ""}`;

  $("#status-text").textContent = connected
    ? t("status.connected", { model: status.model || "TURMO" })
    : status.last_error
      ? t("status.notConnected")
      : t("status.searching");

  const meta = $("#device-meta");
  if (connected) {
    meta.textContent = t("preview.meta", {
      model: status.model || "TURMO",
      width: status.width,
      height: status.height,
      refresh: Number(app.config.refresh_seconds ?? 1).toFixed(1),
    });
  } else if (status.last_error) {
    meta.textContent = t("preview.error", { error: status.last_error });
  } else {
    meta.textContent = t("preview.waiting");
  }

  const tag = $("#preview-tag");
  const live = connected && Number(status.frame_id || 0) > 0;
  tag.textContent = live ? t("preview.live") : t("preview.demo");
  tag.className = `pill ${live ? "live" : "demo"}`;

  $("#config-path").textContent = app.configPath || "—";
  $("#web-url").textContent = window.location.origin;
  $("#footer-status").textContent = connected
    ? t("footer.refreshed", { age: formatAge(status.frame_age) })
    : t("footer.demo");
}

function applyState(data) {
  app.config = data.config || {};
  app.themes = data.themes || [];
  app.status = data.status || {};
  app.revision = data.revision ?? app.revision;
  app.configPath = data.config_path || "";

  if (!app.themesBuilt && app.themes.length) {
    buildThemes();
  }
  if (!app.colorsBuilt) {
    buildColors();
  }
  syncForm();
  updateStatus();
}

/* --------------------------------------------------------------- API */

async function api(path, options = {}) {
  const response = await fetch(path, { cache: "no-store", ...options });
  let data = null;
  try {
    data = await response.json();
  } catch (error) {
    throw new Error(`HTTP ${response.status}`);
  }
  if (!response.ok || data.ok === false) {
    const message =
      data.error ||
      (Array.isArray(data.errors) ? data.errors.join(" ") : "") ||
      `HTTP ${response.status}`;
    throw new Error(message);
  }
  return data;
}

function setSaveState(text, kind = "") {
  for (const element of $$("#save-state, #colors-state")) {
    element.textContent = text;
    element.className = `save-state${kind ? ` ${kind}` : ""}`;
  }
  clearTimeout(app.stateTimer);
  if (text) {
    app.stateTimer = setTimeout(() => setSaveState(""), 2200);
  }
}

function toast(message, isError = false) {
  const element = $("#toast");
  element.textContent = message;
  element.className = `toast show${isError ? " error" : ""}`;
  clearTimeout(app.toastTimer);
  app.toastTimer = setTimeout(() => element.classList.remove("show"), 2800);
}

async function save(patch, options = {}) {
  setSaveState(t("save.saving"));
  try {
    const data = await api("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    });
    applyState(data);
    setSaveState(t("save.saved"), "ok");
    if (!options.silent) {
      toast(options.message || t("toast.applied"));
    }
    refreshPreview();
  } catch (error) {
    setSaveState(t("save.error"), "err");
    toast(error.message, true);
    try {
      const data = await api("/api/state");
      applyState(data);
    } catch (ignored) {
      /* server unavailable; keep the current view */
    }
  }
}

async function pollState() {
  if (app.stopped) {
    return;
  }
  try {
    const data = await api("/api/state");
    applyState(data);
  } catch (error) {
    $("#status-dot").className = "status-dot err";
    $("#status-text").textContent = t("status.guiOffline");
  }
}

async function stopPanel() {
  if (!window.confirm(t("app.confirmStop"))) {
    return;
  }
  app.stopped = true;
  clearInterval(app.pollTimer);
  clearInterval(app.previewTimer);
  if (app.events) {
    app.events.close();
  }
  try {
    await api("/api/shutdown?force=1", { method: "POST" });
  } catch (error) {
    /* the server may close the connection before the response is read */
  }
  $("#stopped-overlay").classList.add("show");
}

function refreshPreview() {
  if (app.stopped) {
    return;
  }
  const image = $("#preview");
  image.classList.add("loading");
  image.onload = () => image.classList.remove("loading");
  image.onerror = () => image.classList.remove("loading");
  image.src = `/api/preview.png?t=${Date.now()}`;
}

/* ------------------------------------------------------------ events */

function bindEvents() {
  for (const tab of $$(".tab")) {
    tab.addEventListener("click", () => {
      for (const item of $$(".tab")) {
        item.classList.toggle("active", item === tab);
        item.setAttribute("aria-selected", item === tab ? "true" : "false");
      }
      for (const panel of $$(".tab-panel")) {
        panel.classList.toggle("active", panel.dataset.panel === tab.dataset.tab);
      }
    });
  }

  $("#orientation").addEventListener("change", (event) => {
    save(
      { orientation: Number(event.target.value) },
      { message: t("toast.orientation") }
    );
  });

  $("#brightness").addEventListener("input", (event) => {
    const value = Number(event.target.value);
    $("#brightness-value").textContent = `${value}%`;
    clearTimeout(app.brightnessTimer);
    app.brightnessTimer = setTimeout(
      () => save({ brightness: value }, { silent: true }),
      250
    );
  });

  $("#refresh").addEventListener("input", (event) => {
    const value = Number(event.target.value);
    $("#refresh-value").textContent = `${value.toFixed(1)} s`;
    clearTimeout(app.refreshTimer);
    app.refreshTimer = setTimeout(
      () => save({ refresh_seconds: value }, { silent: true }),
      300
    );
  });

  const textFields = [
    ["#title", "title"],
    ["#subtitle", "subtitle"],
    ["#footer-text", "footer_text"],
    ["#hostname", "hostname"],
  ];
  for (const [selector, key] of textFields) {
    const element = $(selector);
    element.addEventListener("change", () => save({ [key]: element.value }));
  }

  const resetColors = () =>
    save({ theme_colors: {} }, { message: t("toast.colorsReset") });
  $("#reset-colors").addEventListener("click", resetColors);
  $("#reset-colors-2").addEventListener("click", resetColors);

  $("#language-select").addEventListener("change", (event) => {
    changeLanguage(event.target.value, true);
  });

  for (const option of $$(".language-option")) {
    option.addEventListener("click", async () => {
      const code = option.dataset.lang;
      app.pendingLanguage = code;
      app.locale = code;
      document.documentElement.lang = code;
      updateGateSelection(code);
      setLanguageSelect(code);
      await loadStrings();
      applyTranslations();
      rebuildDynamic();
    });
  }

  $("#stop-panel").addEventListener("click", stopPanel);
  $("#stop-panel-bottom").addEventListener("click", stopPanel);

  $("#close-tab").addEventListener("click", () => {
    window.close();
  });

  window.addEventListener("pagehide", () => {
    if (app.stopped) {
      return;
    }
    const body = new Blob([JSON.stringify({})], { type: "application/json" });
    if (navigator.sendBeacon) {
      navigator.sendBeacon("/api/shutdown", body);
    } else {
      fetch("/api/shutdown", {
        method: "POST",
        keepalive: true,
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
    }
  });

  $("#gate-continue").addEventListener("click", () => {
    const code = app.pendingLanguage || app.locale;
    try {
      localStorage.setItem(STORAGE_KEY, code);
    } catch (error) {
      /* ignore private mode */
    }
    document.documentElement.classList.add("has-lang");
    setLanguageSelect(code);
  });
}

/* --------------------------------------------------------------- init */

async function init() {
  bindEvents();

  let saved = null;
  try {
    saved = localStorage.getItem(STORAGE_KEY);
  } catch (error) {
    saved = null;
  }
  if (!LANGUAGES.includes(saved)) {
    saved = null;
  }

  app.locale = saved || "en";
  await loadStrings();
  applyTranslations();
  setLanguageSelect(app.locale);

  buildToggles($("#panel-toggles"), PANEL_KEYS);
  buildToggles($("#detail-toggles"), DETAIL_KEYS);
  buildToggles($("#tile-toggles"), TILE_KEYS);
  buildColors();

  if (!saved) {
    updateGateSelection(null);
  }

  try {
    const data = await api("/api/state");
    applyState(data);
  } catch (error) {
    toast(error.message, true);
    $("#status-text").textContent = t("status.guiOffline");
  }

  refreshPreview();
  if ("EventSource" in window) {
    app.events = new EventSource("/api/events");
  }
  app.pollTimer = setInterval(pollState, 5000);
  app.previewTimer = setInterval(refreshPreview, 2000);
}

document.addEventListener("DOMContentLoaded", init);
