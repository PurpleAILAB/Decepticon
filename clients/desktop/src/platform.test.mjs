import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";

import {
  applicationMenuTemplate,
  browserWindowChrome,
  dockerComposeSpawn,
  dockerInspectSpawn,
  envAssignHint,
} from "./platform.mjs";
import { resolveDesktopConfig, setupGuide } from "./config.mjs";

test("envAssignHint is shell-correct on Windows, macOS, and Linux", () => {
  const win = envAssignHint("DECEPTICON_DESKTOP_MODE", "local", "win32");
  assert.match(win, /\$env:DECEPTICON_DESKTOP_MODE="local"/);
  assert.match(win, /set DECEPTICON_DESKTOP_MODE=local/);

  const unix = envAssignHint("DECEPTICON_DESKTOP_MODE", "local", "linux");
  assert.equal(unix, "export DECEPTICON_DESKTOP_MODE=local");

  const mac = envAssignHint("DECEPTICON_DESKTOP_MODE", "cloud", "darwin");
  assert.equal(mac, "export DECEPTICON_DESKTOP_MODE=cloud");
});

test("dockerComposeSpawn never enables shell and hides the console on Windows", () => {
  const win = dockerComposeSpawn(["compose", "ps"], {
    platform: "win32",
    env: { PATH: "C:\\Program Files\\Docker\\Docker\\resources\\bin" },
  });
  assert.equal(win.command, "docker");
  assert.deepEqual(win.args, ["compose", "ps"]);
  assert.equal(win.options.shell, false);
  assert.equal(win.options.windowsHide, true);
  assert.equal(win.options.env.PATH.includes("Docker"), true);

  const linux = dockerComposeSpawn(["compose", "ps"], { platform: "linux", env: {} });
  assert.equal(linux.options.windowsHide, false);
  assert.equal(linux.options.shell, false);
});

test("dockerInspectSpawn uses the Go template format string on every OS", () => {
  for (const platform of ["win32", "darwin", "linux"]) {
    const spawn = dockerInspectSpawn("decepticon-web", { platform, env: {} });
    assert.equal(spawn.command, "docker");
    assert.deepEqual(spawn.args, ["inspect", "--format", "{{.Config.Image}}", "decepticon-web"]);
    assert.equal(spawn.options.shell, false);
    assert.equal(spawn.options.windowsHide, platform === "win32");
  }
});

test("applicationMenuTemplate includes Edit roles required for login forms", () => {
  for (const platform of ["win32", "darwin", "linux"]) {
    const template = applicationMenuTemplate(platform, "Decepticon");
    const labels = template.map((item) => item.label);
    assert.ok(labels.includes("Edit"), `Edit menu missing on ${platform}`);
    assert.ok(labels.includes("View"), `View menu missing on ${platform}`);
    assert.ok(labels.includes("Window"), `Window menu missing on ${platform}`);

    const edit = template.find((item) => item.label === "Edit");
    const roles = edit.submenu.map((item) => item.role).filter(Boolean);
    assert.ok(roles.includes("copy"), `copy role missing on ${platform}`);
    assert.ok(roles.includes("paste"), `paste role missing on ${platform}`);
    assert.ok(roles.includes("selectAll"), `selectAll role missing on ${platform}`);
  }

  const mac = applicationMenuTemplate("darwin", "Decepticon");
  assert.equal(mac[0].label, "Decepticon");
  assert.ok(mac[0].submenu.some((item) => item.role === "quit"));

  const win = applicationMenuTemplate("win32", "Decepticon");
  assert.ok(win.some((item) => item.label === "Help"));
  assert.equal(win[0].label, "Edit");
});

test("browserWindowChrome uses hiddenInset title bar only on macOS", () => {
  const mac = browserWindowChrome("darwin");
  assert.equal(mac.titleBarStyle, "hiddenInset");
  assert.deepEqual(mac.trafficLightPosition, { x: 14, y: 14 });
  assert.equal(mac.autoHideMenuBar, false);

  const win = browserWindowChrome("win32");
  assert.equal(win.titleBarStyle, undefined);
  assert.equal(win.autoHideMenuBar, true);

  const linux = browserWindowChrome("linux");
  assert.equal(linux.titleBarStyle, undefined);
  assert.equal(linux.autoHideMenuBar, true);
});

test("setupGuide install commands match each OS family", () => {
  assert.match(setupGuide("win32").installCommand, /install\.ps1/);
  assert.match(setupGuide("win32").installCommand, /winget|Docker\.DockerDesktop/);
  assert.match(setupGuide("darwin").installCommand, /install\.sh/);
  assert.match(setupGuide("linux").installCommand, /install\.sh/);
  assert.doesNotMatch(setupGuide("darwin").installCommand, /install\.ps1/);
  assert.doesNotMatch(setupGuide("linux").installCommand, /install\.ps1/);
});

test("resolveDesktopConfig joins cookie and home paths with the host path module", () => {
  const host = {
    homedir: () => "/home/alice",
  };
  const cfg = resolveDesktopConfig(
    { DECEPTICON_DESKTOP_MODE: "cloud" },
    host,
    () => {
      throw new Error("no env");
    },
    () => false,
  );
  // path.join is the Node path for the runner OS (correct for desktop runtime).
  assert.equal(cfg.decepticonHome, path.join("/home/alice", ".decepticon"));
  assert.equal(cfg.cookiesPath, path.join("/home/alice", ".decepticon", "desktop-cookies.txt"));
  assert.equal(cfg.dashboardUrl, "https://app.decepticon.red");
});

test("resolveDesktopConfig uses path.join so Windows home paths stay native", () => {
  const home = process.platform === "win32"
    ? "C:\\Users\\Alice"
    : "/home/alice";
  const cfg = resolveDesktopConfig(
    { DECEPTICON_HOME: home, DECEPTICON_DESKTOP_MODE: "cloud" },
    { homedir: () => home, platform: process.platform },
    () => {
      throw new Error("no env");
    },
    () => false,
  );
  assert.equal(cfg.decepticonHome, home);
  assert.equal(cfg.cookiesPath, path.join(home, "desktop-cookies.txt"));
  // Path separators must match the host OS.
  if (process.platform === "win32") {
    assert.match(cfg.cookiesPath, /\\/);
  } else {
    assert.doesNotMatch(cfg.cookiesPath, /\\/);
  }
});
