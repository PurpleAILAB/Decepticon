import { app, BrowserWindow, Menu, clipboard, ipcMain, shell } from "electron";
import fs from "node:fs";
import { execFile, spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { canNavigateInApp, canOpenExternal, composeUpArgs, missingConfigFiles, readInstalledVersion, resolveDesktopConfig, setupGuide } from "./config.mjs";
import { statusHtml } from "./ui.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const iconPath = path.resolve(__dirname, "../assets/icon.png");
const iconDataUrl = `data:image/png;base64,${fs.readFileSync(iconPath).toString("base64")}`;
const config = resolveDesktopConfig();
const installedVersion = readInstalledVersion(config);
const setup = setupGuide();
const hasSingleInstanceLock = app.requestSingleInstanceLock();
let mainWindow;
let starting = false;

app.setName("Decepticon Desktop");
if (process.platform === "win32") app.setAppUserModelId("red.decepticon.desktop");

async function dashboardReady() {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 1500);
  try {
    const res = await fetch(config.dashboardUrl, { signal: controller.signal });
    return res.status < 500;
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

async function waitForDashboardReady(attempts = 40, delayMs = 1500) {
  for (let i = 0; i < attempts; i += 1) {
    if (await dashboardReady()) return true;
    await new Promise((resolve) => setTimeout(resolve, delayMs));
  }
  return false;
}

async function loadStatus(message, detail) {
  if (!mainWindow) return;
  await mainWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(statusHtml({ ...config, iconDataUrl, installedVersion, setup }, message, detail))}`);
}

async function bootstrapDashboard() {
  if (await dashboardReady()) {
    if (await runningWebImageCurrent()) {
      await mainWindow?.loadURL(config.dashboardUrl);
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
  const env = { ...process.env };
  if (installedVersion) env.DECEPTICON_VERSION = installedVersion;
  return env;
}

function startWebProfile() {
  if (starting) return;
  const missing = missingConfigFiles(config);
  if (missing.length > 0) {
    const detail = [
      "Missing required Decepticon config file(s):",
      ...missing.map(([label, file]) => `- ${label}: ${file}`),
      "",
      "Use the buttons below to copy the installer, run onboarding, or open docs.",
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
        await mainWindow?.loadURL(config.dashboardUrl);
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
  ipcMain.removeAllListeners("desktop:copy-install");
  ipcMain.removeAllListeners("desktop:copy-onboard");
  ipcMain.removeAllListeners("desktop:copy-api-key");
  ipcMain.on("desktop:retry", bootstrapDashboard);
  ipcMain.on("desktop:open-in-browser", () => openWebUrl(config.dashboardUrl));
  ipcMain.on("desktop:open-download", () => openWebUrl(setup.downloadUrl));
  ipcMain.on("desktop:open-docs", () => openWebUrl(setup.docsUrl));
  ipcMain.on("desktop:copy-install", () => clipboard.writeText(setup.installCommand));
  ipcMain.on("desktop:copy-onboard", () => clipboard.writeText(setup.onboardCommand));
  ipcMain.on("desktop:copy-api-key", () => clipboard.writeText(setup.apiKeyCommand));
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 960,
    minWidth: 1000,
    minHeight: 700,
    show: false,
    title: "Decepticon Desktop",
    icon: iconPath,
    backgroundColor: "#050609",
    webPreferences: {
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
    openWebUrl(url);
    return { action: "deny" };
  });

  mainWindow.webContents.on("will-navigate", (event, url) => {
    if (!canNavigateInApp(url, config.dashboardUrl)) {
      event.preventDefault();
      openWebUrl(url);
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
    createWindow();
    app.on("activate", () => {
      if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
  });
}

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
