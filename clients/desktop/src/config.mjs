import fs from "node:fs";
import os from "node:os";
import path from "node:path";

export const DASHBOARD_READY_ATTEMPTS = 100;
export const DASHBOARD_READY_DELAY_MS = 1500;

/** Hosted product app (same UI as https://app.decepticon.red). */
export const CLOUD_APP_URL = "https://app.decepticon.red";
export const SESSION_PARTITION = "persist:decepticon-desktop";

/** OAuth / IdP hosts that must stay in-app so session cookies land in Electron. */
export const AUTH_HOST_SUFFIXES = [
  "accounts.google.com",
  "google.com",
  "gstatic.com",
  "googleapis.com",
  "github.com",
  "githubusercontent.com",
  "login.microsoftonline.com",
  "microsoftonline.com",
  "live.com",
  "appleid.apple.com",
];

function readInstalledWebPort(envFile, readFile) {
  try {
    for (const line of readFile(envFile, "utf8").split(/\r?\n/)) {
      const match = line.match(/^\s*WEB_PORT\s*=\s*(?:"([^"]+)"|'([^']+)'|([^#\s]+))\s*(?:#.*)?$/);
      if (match) return match[1] || match[2] || match[3];
    }
  } catch {
    // A missing or unreadable installer env file is reported by missingConfigFiles.
  }
  return "";
}

export function isLocalHost(hostname) {
  const host = String(hostname || "").toLowerCase();
  return host === "localhost"
    || host === "127.0.0.1"
    || host === "[::1]"
    || host === "::1"
    || host.endsWith(".localhost");
}

export function isLocalDashboardUrl(url) {
  try {
    return isLocalHost(new URL(url).hostname);
  } catch {
    return false;
  }
}

export function isDecepticonHost(hostname) {
  const host = String(hostname || "").toLowerCase();
  return host === "decepticon.red" || host.endsWith(".decepticon.red");
}

export function isAuthHost(hostname) {
  const host = String(hostname || "").toLowerCase();
  return AUTH_HOST_SUFFIXES.some((suffix) => host === suffix || host.endsWith(`.${suffix}`));
}

/**
 * Resolve desktop target.
 *
 * Modes (DECEPTICON_DESKTOP_MODE):
 * - cloud — always https://app.decepticon.red (or DECEPTICON_DESKTOP_URL)
 * - local — always the installed local dashboard
 * - auto  — local when install config exists, otherwise cloud (default)
 */
export function resolveDesktopConfig(env = process.env, host = os, readFile = fs.readFileSync, exists = fs.existsSync) {
  const decepticonHome = env.DECEPTICON_HOME || path.join(host.homedir(), ".decepticon");
  const envFile = env.DECEPTICON_COMPOSE_ENV_FILE || path.join(decepticonHome, ".env");
  const webPort = env.WEB_PORT?.trim() || readInstalledWebPort(envFile, readFile) || "3000";
  const stackName = env.DECEPTICON_STACK_NAME?.trim() || "";
  const project = env.DECEPTICON_COMPOSE_PROJECT?.trim()
    || (stackName ? `decepticon-${stackName}` : "decepticon");
  const versionFile = env.DECEPTICON_VERSION_FILE || path.join(decepticonHome, ".version");
  const localDashboardUrl = `http://localhost:${webPort}`;
  const explicitUrl = env.DECEPTICON_DESKTOP_URL?.trim() || "";
  const modeRaw = (env.DECEPTICON_DESKTOP_MODE || "auto").trim().toLowerCase();
  const mode = ["cloud", "local", "auto"].includes(modeRaw) ? modeRaw : "auto";

  const provisional = {
    decepticonHome,
    composeFile: env.DECEPTICON_COMPOSE_FILE || path.join(decepticonHome, "docker-compose.yml"),
    envFile,
    versionFile,
    project,
    webContainer: stackName ? `decepticon-${stackName}-web` : "decepticon-web",
  };

  let dashboardUrl = explicitUrl;
  let resolvedMode = mode;
  if (!dashboardUrl) {
    if (mode === "cloud") {
      dashboardUrl = CLOUD_APP_URL;
    } else if (mode === "local") {
      dashboardUrl = localDashboardUrl;
    } else {
      const hasLocalInstall = missingConfigFiles(provisional, exists).length === 0;
      resolvedMode = hasLocalInstall ? "local" : "cloud";
      dashboardUrl = hasLocalInstall ? localDashboardUrl : CLOUD_APP_URL;
    }
  } else {
    resolvedMode = isLocalDashboardUrl(dashboardUrl) ? "local" : "cloud";
  }

  const cookiesPath = env.DECEPTICON_DESKTOP_COOKIES?.trim()
    || path.join(decepticonHome, "desktop-cookies.txt");

  return {
    ...provisional,
    dashboardUrl,
    localDashboardUrl,
    cloudAppUrl: CLOUD_APP_URL,
    mode: resolvedMode,
    isCloud: !isLocalDashboardUrl(dashboardUrl),
    cookiesPath,
    partition: SESSION_PARTITION,
  };
}

export function composeProcessEnv(env = process.env, installedVersion = "") {
  const childEnv = { ...env, COMPOSE_PROFILES: "" };
  for (const key of ["DECEPTICON_STACK_NAME", "DECEPTICON_COMPOSE_PROJECT"]) {
    if (!(key in env)) childEnv[key] = "";
  }
  if (installedVersion) childEnv.DECEPTICON_VERSION = installedVersion;
  return childEnv;
}

export function missingConfigFiles(config, exists = fs.existsSync) {
  return [
    ["Docker Compose file", config.composeFile],
    ["environment file", config.envFile],
  ].filter(([, file]) => !exists(file));
}

export function readInstalledVersion(config, readFile = fs.readFileSync) {
  try {
    const version = readFile(config.versionFile, "utf8").trim().replace(/^v/, "");
    return version || "";
  } catch {
    return "";
  }
}

export function setupGuide(platform = os.platform()) {
  const installCommand = platform === "win32"
    ? "winget install Docker.DockerDesktop; iwr -useb https://decepticon.red/install.ps1 | iex"
    : "curl -fsSL https://decepticon.red/install.sh | bash";
  const onboardCommand = "decepticon onboard";
  return {
    platform,
    installCommand,
    onboardCommand,
    apiKeyCommand: "decepticon onboard --reset",
    downloadUrl: "https://github.com/PurpleAILAB/Decepticon/releases/latest",
    docsUrl: "https://docs.decepticon.red",
    cloudAppUrl: CLOUD_APP_URL,
    marketingUrl: "https://decepticon.red",
  };
}

export function composeUpArgs(config) {
  return [
    "compose",
    "-p",
    config.project,
    "-f",
    config.composeFile,
    "--env-file",
    config.envFile,
    "--profile",
    "web",
    "up",
    "-d",
    "--no-build",
    "web",
  ];
}

export function canNavigateInApp(targetUrl, dashboardUrl) {
  try {
    return new URL(targetUrl).origin === new URL(dashboardUrl).origin;
  } catch {
    return false;
  }
}

/**
 * Navigation allowed inside the shell window.
 * Local mode: same-origin only.
 * Cloud mode: app origin, other decepticon.red hosts, and known OAuth/IdP hosts
 * so Google/GitHub login cookies land in the persistent Electron session.
 */
export function canNavigateInShell(targetUrl, dashboardUrl, { cloud = false } = {}) {
  if (canNavigateInApp(targetUrl, dashboardUrl)) return true;
  const treatAsCloud = cloud || !isLocalDashboardUrl(dashboardUrl);
  if (!treatAsCloud) return false;
  try {
    const { protocol, hostname } = new URL(targetUrl);
    if (protocol !== "http:" && protocol !== "https:") return false;
    return isDecepticonHost(hostname) || isAuthHost(hostname);
  } catch {
    return false;
  }
}

export function dashboardResponseReady(response, dashboardUrl) {
  return response.status < 500 && canNavigateInApp(response.url, dashboardUrl);
}

export function canOpenExternal(targetUrl) {
  try {
    return ["http:", "https:"].includes(new URL(targetUrl).protocol);
  } catch {
    return false;
  }
}

export function isTrustedIpcSender(event, webContents) {
  return event.sender === webContents
    && event.senderFrame === webContents?.mainFrame
    && event.senderFrame.url?.startsWith("data:text/html;charset=utf-8,") === true;
}

/**
 * Parse Cookie-Editor JSON export or Netscape cookie file into Electron cookie set options.
 * Only cookies whose domain matches the dashboard host (or parent) are returned.
 */
export function parseCookieImport(raw, dashboardUrl) {
  const text = String(raw || "").trim();
  if (!text) return [];

  let dashboard;
  try {
    dashboard = new URL(dashboardUrl);
  } catch {
    return [];
  }

  const entries = text.startsWith("[") || text.startsWith("{")
    ? parseJsonCookies(text)
    : parseNetscapeCookies(text);

  return entries
    .map((entry) => normalizeCookieEntry(entry, dashboard))
    .filter(Boolean);
}

function parseJsonCookies(text) {
  const data = JSON.parse(text);
  const list = Array.isArray(data) ? data : [data];
  return list.map((item) => ({
    name: item.name,
    value: item.value,
    domain: item.domain,
    path: item.path || "/",
    secure: Boolean(item.secure),
    httpOnly: Boolean(item.httpOnly),
    hostOnly: Boolean(item.hostOnly),
    expirationDate: item.expirationDate,
    sameSite: item.sameSite,
  }));
}

function parseNetscapeCookies(text) {
  const out = [];
  for (const line of text.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) {
      // #HttpOnly_ prefix is Netscape extension for HttpOnly
      if (!trimmed.startsWith("#HttpOnly_")) continue;
    }
    let httpOnly = false;
    let row = trimmed;
    if (row.startsWith("#HttpOnly_")) {
      httpOnly = true;
      row = row.slice("#HttpOnly_".length);
    } else if (row.startsWith("#")) {
      continue;
    }
    const parts = row.split(/\t/);
    if (parts.length < 7) continue;
    const [domain, includeSubdomains, pathPart, secure, expires, name, value] = parts;
    const hostOnly = String(includeSubdomains).toUpperCase() === "FALSE" && !String(domain).startsWith(".");
    out.push({
      name,
      value,
      domain,
      path: pathPart || "/",
      secure: String(secure).toUpperCase() === "TRUE",
      httpOnly,
      hostOnly,
      expirationDate: Number(expires) > 0 ? Number(expires) : undefined,
      sameSite: "lax",
    });
  }
  return out;
}

function normalizeCookieEntry(entry, dashboard) {
  if (!entry?.name || entry.value == null) return null;
  const domain = String(entry.domain || dashboard.hostname).replace(/^\./, "");
  if (!cookieDomainMatches(domain, dashboard.hostname)) return null;

  const secure = Boolean(entry.secure) || dashboard.protocol === "https:";
  const cookiePath = entry.path || "/";
  const host = domain.replace(/^\./, "");
  const sameSite = normalizeSameSite(entry.sameSite);
  const url = `${secure ? "https" : "http"}://${host}${cookiePath}`;

  /** @type {{ url: string, name: string, value: string, path: string, secure: boolean, httpOnly: boolean, sameSite: string, domain?: string, expirationDate?: number }} */
  const details = {
    url,
    name: String(entry.name),
    value: String(entry.value),
    path: cookiePath,
    secure,
    httpOnly: Boolean(entry.httpOnly),
    sameSite,
  };

  // hostOnly / __Host- cookies must not set Domain
  const hostOnly = entry.hostOnly === true || details.name.startsWith("__Host-");
  if (!hostOnly) {
    details.domain = domain.startsWith(".") ? domain : `.${domain}`;
  }

  if (details.name.startsWith("__Secure-") || details.name.startsWith("__Host-")) {
    details.secure = true;
    details.url = `https://${host}${details.path}`;
  }
  if (details.name.startsWith("__Host-")) {
    details.path = "/";
    delete details.domain;
  }

  if (typeof entry.expirationDate === "number" && Number.isFinite(entry.expirationDate)) {
    details.expirationDate = entry.expirationDate;
  }

  return details;
}


function normalizeSameSite(value) {
  const v = String(value || "lax").toLowerCase();
  if (v === "no_restriction" || v === "none") return "no_restriction";
  if (v === "strict") return "strict";
  return "lax";
}

function cookieDomainMatches(cookieDomain, host) {
  const domain = cookieDomain.replace(/^\./, "").toLowerCase();
  const hostname = host.toLowerCase();
  return hostname === domain || hostname.endsWith(`.${domain}`);
}

export function readCookieImportFile(filePath, readFile = fs.readFileSync, exists = fs.existsSync) {
  if (!filePath || !exists(filePath)) return null;
  try {
    return readFile(filePath, "utf8");
  } catch {
    return null;
  }
}
