import fs from "node:fs";
import os from "node:os";
import path from "node:path";

export const DASHBOARD_READY_ATTEMPTS = 100;
export const DASHBOARD_READY_DELAY_MS = 1500;

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

export function resolveDesktopConfig(env = process.env, host = os, readFile = fs.readFileSync) {
  const decepticonHome = env.DECEPTICON_HOME || path.join(host.homedir(), ".decepticon");
  const envFile = env.DECEPTICON_COMPOSE_ENV_FILE || path.join(decepticonHome, ".env");
  const webPort = env.WEB_PORT?.trim() || readInstalledWebPort(envFile, readFile) || "3000";
  const stackName = env.DECEPTICON_STACK_NAME?.trim() || "";
  const project = env.DECEPTICON_COMPOSE_PROJECT?.trim()
    || (stackName ? `decepticon-${stackName}` : "decepticon");
  const versionFile = env.DECEPTICON_VERSION_FILE || path.join(decepticonHome, ".version");
  return {
    dashboardUrl: env.DECEPTICON_DESKTOP_URL || `http://localhost:${webPort}`,
    decepticonHome,
    composeFile: env.DECEPTICON_COMPOSE_FILE || path.join(decepticonHome, "docker-compose.yml"),
    envFile,
    versionFile,
    project,
    webContainer: stackName ? `decepticon-${stackName}-web` : "decepticon-web",
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
