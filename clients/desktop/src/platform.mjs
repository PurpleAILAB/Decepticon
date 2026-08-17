/**
 * Pure platform helpers — no Electron import so unit tests run on every OS.
 */

/** Shell one-liner to set an env var for the current platform. */
export function envAssignHint(name, value, platform = process.platform) {
  if (platform === "win32") {
    return [
      `PowerShell:  $env:${name}="${value}"`,
      `cmd.exe:     set ${name}=${value}`,
    ].join("\n");
  }
  return `export ${name}=${value}`;
}

/** How to launch Docker Compose on this host (array form; no shell interpolation). */
export function dockerComposeSpawn(args, { platform = process.platform, env = process.env } = {}) {
  // Docker Desktop ships `docker.exe` / `docker` with the compose plugin on all
  // three platforms. Passing the argv array avoids Windows path-quoting bugs.
  return {
    command: "docker",
    args: [...args],
    options: {
      env,
      stdio: ["ignore", "pipe", "pipe"],
      // Hide the brief console flash when spawning from a GUI app on Windows.
      windowsHide: platform === "win32",
      // Never shell:true — args must not be re-parsed by cmd.exe / sh.
      shell: false,
    },
  };
}

export function dockerInspectSpawn(webContainer, { platform = process.platform, env = process.env } = {}) {
  return {
    command: "docker",
    args: ["inspect", "--format", "{{.Config.Image}}", webContainer],
    options: {
      env,
      timeout: 2000,
      windowsHide: platform === "win32",
      shell: false,
    },
  };
}

/**
 * Application menu template with platform roles.
 * macOS needs Edit roles or Cmd+C/V fail inside login forms.
 * Windows/Linux get the same Edit menu so Ctrl+C/V work consistently.
 */
export function applicationMenuTemplate(platform = process.platform, appName = "Decepticon") {
  /** @type {Array<Record<string, unknown>>} */
  const template = [];

  if (platform === "darwin") {
    template.push({
      label: appName,
      submenu: [
        { role: "about" },
        { type: "separator" },
        { role: "services" },
        { type: "separator" },
        { role: "hide" },
        { role: "hideOthers" },
        { role: "unhide" },
        { type: "separator" },
        { role: "quit" },
      ],
    });
  }

  template.push({
    label: "Edit",
    submenu: [
      { role: "undo" },
      { role: "redo" },
      { type: "separator" },
      { role: "cut" },
      { role: "copy" },
      { role: "paste" },
      { role: "selectAll" },
    ],
  });

  template.push({
    label: "View",
    submenu: [
      { role: "reload" },
      { role: "forceReload" },
      { role: "toggleDevTools" },
      { type: "separator" },
      { role: "resetZoom" },
      { role: "zoomIn" },
      { role: "zoomOut" },
      { type: "separator" },
      { role: "togglefullscreen" },
    ],
  });

  template.push({
    label: "Window",
    submenu: platform === "darwin"
      ? [
          { role: "minimize" },
          { role: "zoom" },
          { type: "separator" },
          { role: "front" },
          { type: "separator" },
          { role: "window" },
        ]
      : [
          { role: "minimize" },
          { role: "close" },
        ],
  });

  if (platform !== "darwin") {
    template.push({
      label: "Help",
      submenu: [
        {
          label: "Decepticon Docs",
          // main process wires click → shell.openExternal; role-less label only.
        },
      ],
    });
  }

  return template;
}

/** BrowserWindow construction options that differ by OS. */
export function browserWindowChrome(platform = process.platform) {
  const common = {
    width: 1440,
    height: 960,
    minWidth: 1000,
    minHeight: 700,
    show: false,
    title: "Decepticon",
    backgroundColor: "#050609",
    autoHideMenuBar: platform !== "darwin",
  };

  if (platform === "darwin") {
    return {
      ...common,
      // Traffic lights + title; keeps the product feel without a custom titlebar.
      titleBarStyle: "hiddenInset",
      trafficLightPosition: { x: 14, y: 14 },
    };
  }

  return common;
}
