import { app, BrowserWindow, Menu, clipboard, ipcMain, session, shell } from "electron";
import fs from "node:fs";
import { execFile, spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  canNavigateInShell,
  canOpenExternal,
  composeProcessEnv,
  composeUpArgs,
  DASHBOARD_READY_ATTEMPTS,
  DASHBOARD_READY_DELAY_MS,
  dashboardResponseReady,
  isTrustedIpcSender,
  missingConfigFiles,
  parseCookieImport,
  readCookieImportFile,
  readInstalledVersion,
  resolveDesktopConfig,
  setupGuide,
} from "./config.mjs";
import { statusHtml } from "./ui.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const iconPath = path.resolve(__dirname, "../assets/icon.png");
const iconDataUrl = `data:image/png;base64,${fs.readFileSync(iconPath).toString("base64")}`;
const config = resolveDesktopConfig();
const installedVersion = readInstalledVersion(config);
const setup = setupGuide();
const hasSingleInstanceLock = app.requestSingleInstanceLock();
const appSession = () => session.fromPartition(config.partition);
let mainWindow;
let starting = false;
let cookiesImported = false;

app.setName("Decepticon");
if (process.platform === "win32") app.setAppUserModelId("red.decepticon.desktop");

async function dashboardReady() {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 1500);
  try {
    const res = await fetch(config.dashboardUrl, {
      signal: controller.signal,
      redirect: "manual",
    });
    // Cloud login pages often 302 to /login — still "ready" for the shell.
    if (config.isCloud) {
      return res.status > 0 && res.status < 500;
    }
    return dashboardResponseReady(res, config.dashboardUrl);
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

async function runningWebImageCurrent() {
  if (!installedVersion) return true;
  return new Promise((resolve) => {
    execFile(
      "docker",
      ["inspect", "--format", "{{.Config.Image}}", config.webContainer],
      { env: composeEnv(), timeout: 2000 },
      (err, stdout) => {
        if (err) {
          resolve(true);
          return;
        }
        resolve(stdout.trim().endsWith(`:${installedVersion}`));
      },
    );
  });
}

async function waitForDashboardReady(
  attempts = DASHBOARD_READY_ATTEMPTS,
  delayMs = DASHBOARD_READY_DELAY_MS,
) {
  for (let i = 0; i < attempts; i += 1) {
    if (await dashboardReady()) return true;
    await new Promise((resolve) => setTimeout(resolve, delayMs));
  }
  return false;
}

async function loadStatus(message, detail) {
  if (!mainWindow) return;
  await mainWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(statusHtml({
    ...config,
    iconDataUrl,
    installedVersion,
    setup,
  }, message, detail))}`);
}

async function importSessionCookies() {
  if (cookiesImported) return { imported: 0, skipped: true };
  cookiesImported = true;
  const raw = readCookieImportFile(config.cookiesPath);
  if (!raw) return { imported: 0, skipped: true };

  let cookies;
  try {
    cookies = parseCookieImport(raw, config.dashboardUrl);
  } catch (err) {
    return { imported: 0, error: err instanceof Error ? err.message : String(err) };
  }
  if (cookies.length === 0) return { imported: 0, skipped: true };

  const ses = appSession();
  let imported = 0;
  for (const cookie of cookies) {
    try {
      await ses.cookies.set(cookie);
      imported += 1;
    } catch {
      // Skip malformed or rejected cookies; login can still proceed interactively.
    }
  }
  await ses.cookies.flushStore();
  return { imported };
}

async function loadDashboard() {
  if (!mainWindow) return;
  const result = await importSessionCookies();
  if (result.error) {
    await loadStatus("cookie import failed", result.error);
  }
  await mainWindow.loadURL(config.dashboardUrl);
}

async function bootstrapDashboard() {
  if (config.isCloud) {
    await loadStatus("connecting to Decepticon cloud…");
    if (await dashboardReady()) {
      await loadDashboard();
      return;
    }
    await loadStatus(
      "cloud app unreachable",
      [
        `Could not reach ${config.dashboardUrl}.`,
        "Check your network, then retry — or switch to a local dashboard:",
        "",
        "  set DECEPTICON_DESKTOP_MODE=local",
        "  npm run desktop",
      ].join("\n"),
    );
    return;
  }

  if (await dashboardReady()) {
    if (await runningWebImageCurrent()) {
      await loadDashboard();
      return;
    }
    await loadStatus(`dashboard is running on an older image; updating to v${installedVersion}…`);
    startWebProfile();
    return;
  }
  await loadStatus("dashboard offline; auto-starting web profile…");
  startWebProfile();
}

function composeEnv() {
  return composeProcessEnv(process.env, installedVersion);
}

function startWebProfile() {
  if (starting) return;
  const missing = missingConfigFiles(config);
  if (missing.length > 0) {
    const detail = [
      "Missing required Decepticon config file(s):",
      ...missing.map(([label, file]) => `- ${label}: ${file}`),
      "",
      "Use the buttons below to open the cloud app, copy the installer, or run onboarding.",
      "Onboarding handles API keys, telemetry consent, auto-update settings, Docker checks, and model/provider setup.",
    ].join("\n");
    loadStatus("desktop setup incomplete; bootstrap blocked", detail);
    return;
  }

  starting = true;
  const args = composeUpArgs(config);
  const child = spawn("docker", args, { env: composeEnv(), stdio: ["ignore", "pipe", "pipe"] });
  let output = `$ docker ${args.join(" ")}\n`;
  const append = (chunk) => {
    output = (output + chunk.toString()).slice(-8000);
  };
  child.stdout.on("data", append);
  child.stderr.on("data", append);
  child.on("error", async (err) => {
    starting = false;
    await loadStatus("docker compose launch failed", err.message);
  });
  child.on("close", async (code) => {
    starting = false;
    if (code === 0) {
      await loadStatus("web profile started; waiting for dashboard readiness…", output);
      if (await waitForDashboardReady()) {
        await loadDashboard();
        return;
      }
      await loadStatus("web profile started, but dashboard did not become ready", output);
      return;
    }
    await loadStatus(`docker compose exited ${code}`, output);
  });
}

function openWebUrl(url) {
  if (canOpenExternal(url)) shell.openExternal(url);
}

function registerIpcHandlers() {
  ipcMain.removeAllListeners("desktop:retry");
  ipcMain.removeAllListeners("desktop:open-in-browser");
  ipcMain.removeAllListeners("desktop:open-download");
  ipcMain.removeAllListeners("desktop:open-docs");
  ipcMain.removeAllListeners("desktop:open-cloud");
  ipcMain.removeAllListeners("desktop:copy-install");
  ipcMain.removeAllListeners("desktop:copy-onboard");
  ipcMain.removeAllListeners("desktop:copy-api-key");
  const onStatusAction = (channel, action) => {
    ipcMain.on(channel, (event) => {
      const webContents = mainWindow?.webContents;
      if (webContents && isTrustedIpcSender(event, webContents)) action();
    });
  };
  onStatusAction("desktop:retry", bootstrapDashboard);
  onStatusAction("desktop:open-in-browser", () => openWebUrl(config.dashboardUrl));
  onStatusAction("desktop:open-cloud", () => openWebUrl(config.cloudAppUrl || setup.cloudAppUrl));
  onStatusAction("desktop:open-download", () => openWebUrl(setup.downloadUrl));
  onStatusAction("desktop:open-docs", () => openWebUrl(setup.docsUrl));
  onStatusAction("desktop:copy-install", () => clipboard.writeText(setup.installCommand));
  onStatusAction("desktop:copy-onboard", () => clipboard.writeText(setup.onboardCommand));
  onStatusAction("desktop:copy-api-key", () => clipboard.writeText(setup.apiKeyCommand));
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 960,
    minWidth: 1000,
    minHeight: 700,
    show: false,
    title: "Decepticon",
    icon: iconPath,
    backgroundColor: "#050609",
    autoHideMenuBar: true,
    webPreferences: {
      partition: config.partition,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      preload: path.join(__dirname, "preload.cjs"),
    },
  });

  mainWindow.once("ready-to-show", () => {
    mainWindow?.show();
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    // Keep OAuth / product popups inside the shell when allowed; else system browser.
    if (canNavigateInShell(url, config.dashboardUrl, { cloud: config.isCloud })) {
      return {
        action: "allow",
        overrideBrowserWindowOptions: {
          width: 520,
          height: 720,
          autoHideMenuBar: true,
          backgroundColor: "#050609",
          webPreferences: {
            partition: config.partition,
            contextIsolation: true,
            nodeIntegration: false,
            sandbox: true,
          },
        },
      };
    }
    openWebUrl(url);
    return { action: "deny" };
  });

  mainWindow.webContents.on("will-navigate", (event, url) => {
    if (!canNavigateInShell(url, config.dashboardUrl, { cloud: config.isCloud })) {
      event.preventDefault();
      openWebUrl(url);
    }
  });

  mainWindow.webContents.on("will-redirect", (event, url) => {
    if (!canNavigateInShell(url, config.dashboardUrl, { cloud: config.isCloud })) {
      event.preventDefault();
    }
  });

  registerIpcHandlers();
  bootstrapDashboard();
}

if (!hasSingleInstanceLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (!mainWindow) return;
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  });

  app.whenReady().then(() => {
    Menu.setApplicationMenu(null);
    const ses = appSession();
    ses.setPermissionCheckHandler(() => false);
    ses.setPermissionRequestHandler((_webContents, _permission, callback) => {
      callback(false);
    });
    createWindow();
    app.on("activate", () => {
      if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
  });
}

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
