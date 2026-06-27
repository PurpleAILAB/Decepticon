import fs from "node:fs";
import os from "node:os";
import path from "node:path";

export function resolveDesktopConfig(env = process.env, host = os) {
  const decepticonHome = env.DECEPTICON_HOME || path.join(host.homedir(), ".decepticon");
  const webPort = env.WEB_PORT || "3000";
  const stackName = env.DECEPTICON_STACK_NAME || "";
  const versionFile = env.DECEPTICON_VERSION_FILE || path.join(decepticonHome, ".version");
  return {
    dashboardUrl: env.DECEPTICON_DESKTOP_URL || `http://localhost:${webPort}`,
    decepticonHome,
    composeFile: env.DECEPTICON_COMPOSE_FILE || path.join(decepticonHome, "docker-compose.yml"),
    envFile: env.DECEPTICON_COMPOSE_ENV_FILE || path.join(decepticonHome, ".env"),
    versionFile,
    project: stackName ? `decepticon-${stackName}` : "decepticon",
    webContainer: stackName ? `decepticon-${stackName}-web` : "decepticon-web",
  };
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
