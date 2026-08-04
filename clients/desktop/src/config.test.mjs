import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";

import {
  canOpenExternal,
  canNavigateInApp,
  composeUpArgs,
  composeProcessEnv,
  DASHBOARD_READY_ATTEMPTS,
  DASHBOARD_READY_DELAY_MS,
  dashboardResponseReady,
  isTrustedIpcSender,
  missingConfigFiles,
  readInstalledVersion,
  resolveDesktopConfig,
  setupGuide,
} from "./config.mjs";
import { statusHtml } from "./ui.mjs";

test("resolveDesktopConfig defaults to the installed Decepticon home and WEB_PORT", () => {
  const cfg = resolveDesktopConfig(
    { WEB_PORT: "3999" },
    { homedir: () => "/home/alice", platform: "linux" },
  );

  assert.equal(cfg.dashboardUrl, "http://localhost:3999");
  assert.equal(cfg.decepticonHome, path.join("/home/alice", ".decepticon"));
  assert.equal(cfg.composeFile, path.join("/home/alice", ".decepticon", "docker-compose.yml"));
  assert.equal(cfg.envFile, path.join("/home/alice", ".decepticon", ".env"));
  assert.equal(cfg.webContainer, "decepticon-web");
  assert.equal(cfg.project, "decepticon");
});

test("resolveDesktopConfig reads WEB_PORT from the installed env file", () => {
  const cfg = resolveDesktopConfig(
    { DECEPTICON_HOME: "/opt/decepticon" },
    { homedir: () => "/unused", platform: "linux" },
    () => "POSTGRES_PASSWORD=secret\nWEB_PORT=4310\n",
  );

  assert.equal(cfg.dashboardUrl, "http://localhost:4310");
});

test("resolveDesktopConfig prefers explicit Compose project", () => {
  const cfg = resolveDesktopConfig({
    DECEPTICON_COMPOSE_PROJECT: "vendor-dev",
    DECEPTICON_STACK_NAME: "lab",
  });

  assert.equal(cfg.project, "vendor-dev");
});

test("readInstalledVersion pins Compose to the installed CLI version", () => {
  const cfg = resolveDesktopConfig(
    { DECEPTICON_HOME: "/opt/decepticon" },
    { homedir: () => "/unused", platform: "linux" },
  );

  assert.equal(cfg.versionFile, path.join("/opt/decepticon", ".version"));
  assert.equal(readInstalledVersion(cfg, () => "v1.1.23\n"), "1.1.23");
  assert.equal(readInstalledVersion(cfg, () => ""), "");
  assert.equal(resolveDesktopConfig({ DECEPTICON_STACK_NAME: "lab" }).webContainer, "decepticon-lab-web");
});

test("composeUpArgs starts only the dynamic web profile", () => {
  const cfg = resolveDesktopConfig(
    { DECEPTICON_HOME: "/opt/decepticon", DECEPTICON_STACK_NAME: "lab" },
    { homedir: () => "/unused", platform: "linux" },
  );

  assert.deepEqual(composeUpArgs(cfg), [
    "compose",
    "-p",
    "decepticon-lab",
    "-f",
    path.join("/opt/decepticon", "docker-compose.yml"),
    "--env-file",
    path.join("/opt/decepticon", ".env"),
    "--profile",
    "web",
    "up",
    "-d",
    "--no-build",
    "web",
  ]);
});

test("composeProcessEnv clears implicit profile activation", () => {
  assert.deepEqual(composeProcessEnv({ COMPOSE_PROFILES: "c2-sliver" }, "1.1.40"), {
    COMPOSE_PROFILES: "",
    DECEPTICON_COMPOSE_PROJECT: "",
    DECEPTICON_STACK_NAME: "",
    DECEPTICON_VERSION: "1.1.40",
  });
});

test("composeProcessEnv preserves explicit stack ownership", () => {
  assert.deepEqual(
    composeProcessEnv({ DECEPTICON_COMPOSE_PROJECT: "vendor-dev", DECEPTICON_STACK_NAME: "lab" }),
    {
      COMPOSE_PROFILES: "",
      DECEPTICON_COMPOSE_PROJECT: "vendor-dev",
      DECEPTICON_STACK_NAME: "lab",
    },
  );
});

test("missingConfigFiles catches incomplete desktop setup before Compose runs", () => {
  const cfg = resolveDesktopConfig(
    { DECEPTICON_HOME: "/tmp/decepticon-desktop-smoke" },
    { homedir: () => "/unused", platform: "linux" },
  );
  const existing = new Set([path.join("/tmp/decepticon-desktop-smoke", "docker-compose.yml")]);

  assert.deepEqual(missingConfigFiles(cfg, (file) => existing.has(file)), [
    ["environment file", path.join("/tmp/decepticon-desktop-smoke", ".env")],
  ]);
});

test("canNavigateInApp only allows same-origin dashboard navigation", () => {
  assert.equal(canNavigateInApp("http://localhost:3000/engagements", "http://localhost:3000"), true);
  assert.equal(canNavigateInApp("https://docs.decepticon.red", "http://localhost:3000"), false);
  assert.equal(canNavigateInApp("not a url", "http://localhost:3000"), false);
});

test("dashboardResponseReady rejects external redirects", () => {
  assert.equal(
    dashboardResponseReady(
      { status: 200, url: "https://example.com/login" },
      "http://localhost:3000",
    ),
    false,
  );
  assert.equal(
    dashboardResponseReady(
      { status: 200, url: "http://localhost:3000/engagements" },
      "http://localhost:3000",
    ),
    true,
  );
});

test("dashboard readiness wait covers the Compose health budget", () => {
  assert.ok(DASHBOARD_READY_ATTEMPTS * DASHBOARD_READY_DELAY_MS >= 150_000);
});

test("canOpenExternal allows web URLs", () => {
  assert.equal(canOpenExternal("https://docs.decepticon.red"), true);
  assert.equal(canOpenExternal("http://localhost:3000"), true);
});

test("canOpenExternal rejects non-web protocols", () => {
  assert.equal(canOpenExternal("file:///etc/passwd"), false);
  assert.equal(canOpenExternal("decepticon://run"), false);
  assert.equal(canOpenExternal("not a url"), false);
});

test("isTrustedIpcSender accepts only the generated status document main frame", () => {
  const mainFrame = { url: "data:text/html;charset=utf-8,%3Ch1%3Eoffline%3C%2Fh1%3E" };
  const webContents = { mainFrame };

  assert.equal(isTrustedIpcSender({ sender: webContents, senderFrame: mainFrame }, webContents), true);
  assert.equal(
    isTrustedIpcSender(
      { sender: webContents, senderFrame: { url: "http://localhost:3000" } },
      webContents,
    ),
    false,
  );
  assert.equal(
    isTrustedIpcSender(
      { sender: webContents, senderFrame: { url: mainFrame.url } },
      webContents,
    ),
    false,
  );
  assert.equal(isTrustedIpcSender({ sender: {}, senderFrame: mainFrame }, webContents), false);
});

test("setupGuide gives OS-specific install and onboarding commands", () => {
  assert.match(setupGuide("linux").installCommand, /curl/);
  assert.match(setupGuide("darwin").installCommand, /curl/);
  assert.match(setupGuide("win32").installCommand, /install\.ps1/);
  assert.equal(setupGuide("linux").onboardCommand, "decepticon onboard");
  assert.equal(setupGuide("linux").apiKeyCommand, "decepticon onboard --reset");
});

test("statusHtml renders CLI-style branding and no start button dependency", () => {
  const html = statusHtml(
    {
      dashboardUrl: "http://localhost:3000",
      decepticonHome: "/home/alice/.decepticon",
      iconDataUrl: "data:image/png;base64,chameleon",
      installedVersion: "1.1.23",
      setup: setupGuide("linux"),
    },
    "offline",
  );

  assert.match(html, /alt="Decepticon chameleon"/);
  assert.ok(html.includes("PurpleAILAB / Decepticon local runtime"));
  assert.ok(html.includes("root@decepticon:/workspace"));
  assert.ok(html.includes("docker compose --profile web up -d web"));
  assert.ok(html.includes("v1.1.23"));
  assert.ok(html.includes("auto-update via CLI"));
  assert.ok(html.includes("telemetry via .env"));
  assert.ok(html.includes("Copy install"));
  assert.ok(html.includes("Copy onboarding"));
  assert.ok(html.includes("Copy API key setup"));
  assert.ok(html.includes("Download"));
  assert.ok(html.includes("Setup docs"));
  assert.ok(html.includes("Set API keys"));
  assert.match(html, /data-desktop-action="retry"/);
  assert.match(html, /data-desktop-action="openInBrowser"/);
  assert.doesNotMatch(html, /data-desktop-action="startDashboard"/);
  assert.doesNotMatch(html, /onclick=/);
  assert.match(html, /Content-Security-Policy/);
});
