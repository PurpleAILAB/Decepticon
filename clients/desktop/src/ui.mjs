export function statusHtml(config, message = "checking local dashboard…", detail = "") {
  const escapedMessage = escapeHtml(message);
  const escapedDetail = escapeHtml(detail);
  const escapedVersion = escapeHtml(config.installedVersion ? `v${config.installedVersion}` : "setup required");
  const setup = config.setup || {};
  const installCommand = escapeHtml(setup.installCommand || "curl -fsSL https://decepticon.red/install.sh | bash");
  const onboardCommand = escapeHtml(setup.onboardCommand || "decepticon onboard");
  const apiKeyCommand = escapeHtml(setup.apiKeyCommand || "decepticon onboard --reset");
  const icon = config.iconDataUrl
    ? `<img class="mark" src="${escapeHtml(config.iconDataUrl)}" alt="Decepticon chameleon" />`
    : `<div class="mark mark-fallback" aria-hidden="true">D</div>`;

  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:;" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Decepticon Desktop</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #050609;
      --panel: #090b10;
      --line: rgb(255 255 255 / .09);
      --muted: #7c8798;
      --text: #e7eaf0;
      --red: #d71925;
      --purple: #7c3aed;
      --green: #22c55e;
      --blue: #60a5fa;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background:
        radial-gradient(circle at 18% 8%, rgb(124 58 237 / .18), transparent 28rem),
        linear-gradient(180deg, #080a0f 0%, var(--bg) 100%);
      color: var(--text);
      overflow: hidden;
    }

    body::before {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      background: repeating-linear-gradient(0deg, rgb(255 255 255 / .035) 0 1px, transparent 1px 4px);
      opacity: .18;
      mix-blend-mode: screen;
    }

    .screen {
      position: relative;
      min-height: 100vh;
      padding: clamp(1rem, 2vw, 1.4rem);
      display: grid;
      grid-template-rows: auto 1fr;
      gap: 1rem;
    }

    .header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
      border: 1px solid var(--line);
      border-radius: .55rem;
      background: rgb(8 10 16 / .92);
      padding: .8rem 1rem;
      box-shadow: 0 1.5rem 4rem rgb(0 0 0 / .35);
    }

    .brand { display: flex; align-items: center; gap: .95rem; min-width: 0; }
    .mark {
      width: 4.35rem;
      height: 4.35rem;
      object-fit: cover;
      border-radius: .65rem;
      background: #0d1018;
      box-shadow: 0 0 0 1px rgb(124 58 237 / .65), 0 0 32px rgb(124 58 237 / .42);
      flex: 0 0 auto;
    }
    .mark-fallback { display: grid; place-items: center; color: #c4b5fd; font-weight: 900; }
    .brand-kicker { color: #9ca3af; font-size: .72rem; letter-spacing: .16em; text-transform: uppercase; }
    .brand-title { margin: .1rem 0 0; font-family: Inter, ui-sans-serif, system-ui, sans-serif; font-size: clamp(1.9rem, 3.4vw, 3.35rem); line-height: .9; letter-spacing: -.06em; font-weight: 900; }
    .brand-title .red { color: var(--red); text-shadow: 0 0 22px rgb(215 25 37 / .32); }

    .status { display: flex; flex-wrap: wrap; justify-content: end; gap: .45rem; color: #cbd5e1; }
    .status span { border: 1px solid var(--line); border-radius: 999px; padding: .42rem .62rem; background: rgb(255 255 255 / .045); font-size: .75rem; font-weight: 700; }
    .status .live::before { content: "● "; color: var(--green); text-shadow: 0 0 10px var(--green); }

    .terminal {
      min-height: 0;
      border: 1px solid var(--line);
      border-radius: .55rem;
      background: rgb(4 6 10 / .94);
      box-shadow: 0 2rem 6rem rgb(0 0 0 / .42);
      overflow: hidden;
      display: grid;
      grid-template-rows: auto 1fr auto;
    }

    .chrome { display: flex; align-items: center; gap: .55rem; padding: .72rem .9rem; border-bottom: 1px solid var(--line); background: rgb(255 255 255 / .035); color: #b7c0ce; font-size: .82rem; }
    .lights { display: flex; gap: .35rem; }
    .lights i { width: .68rem; height: .68rem; border-radius: 999px; display: block; }
    .lights i:nth-child(1) { background: #ef4444; }
    .lights i:nth-child(2) { background: #f59e0b; }
    .lights i:nth-child(3) { background: #22c55e; }

    .body { padding: clamp(1rem, 2vw, 1.55rem); font-size: clamp(.92rem, 1.25vw, 1.05rem); line-height: 1.72; overflow: auto; }
    .green { color: var(--green); }
    .blue { color: var(--blue); }
    .purple { color: #a78bfa; }
    .muted { color: var(--muted); }
    .red { color: #f87171; }
    .cmd { color: #f8fafc; }
    .target { color: #bae6fd; word-break: break-all; }
    .output { white-space: pre-wrap; word-break: break-word; margin-top: 1rem; color: #a8b3c7; }
    .setup-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: .75rem;
      margin-top: 1.1rem;
    }
    .setup-card {
      border: 1px solid var(--line);
      border-radius: .55rem;
      padding: .85rem;
      background: rgb(255 255 255 / .035);
    }
    .setup-card strong { display: block; color: #f8fafc; margin-bottom: .35rem; }
    .setup-card code { display: block; color: #c4b5fd; white-space: pre-wrap; word-break: break-word; margin-top: .45rem; }


    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: .65rem;
      border-top: 1px solid var(--line);
      padding: .85rem .9rem;
      background: rgb(255 255 255 / .025);
    }
    button {
      border: 1px solid var(--line);
      border-radius: .45rem;
      background: rgb(255 255 255 / .055);
      color: #e5e7eb;
      padding: .65rem .85rem;
      font: inherit;
      font-weight: 800;
      cursor: pointer;
    }
    button:hover { border-color: rgb(124 58 237 / .65); color: white; background: rgb(124 58 237 / .18); }
    button:focus-visible { outline: 2px solid #a78bfa; outline-offset: 2px; }

    @media (max-width: 760px) {
      body { overflow: auto; }
      .screen { min-height: auto; }
      .header { align-items: flex-start; flex-direction: column; }
      .status { justify-content: start; }
      .setup-grid { grid-template-columns: 1fr; }
      .mark { width: 3.5rem; height: 3.5rem; }
    }
  </style>
</head>
<body>
  <main class="screen">
    <header class="header">
      <div class="brand">
        ${icon}
        <div>
          <div class="brand-kicker">PurpleAILAB / Decepticon local runtime</div>
          <h1 class="brand-title">Decepti<span class="red">con</span></h1>
        </div>
      </div>
      <div class="status" aria-label="Runtime status">
        <span class="live">desktop online</span>
        <span>${escapedVersion}</span>
        <span>auto-update via CLI</span>
        <span>telemetry via .env</span>
      </div>
    </header>

    <section class="terminal" aria-label="Desktop bootstrap terminal">
      <div class="chrome"><span class="lights"><i></i><i></i><i></i></span> root@decepticon:/workspace — desktop bootstrap</div>
      <div class="body">
        <div><span class="green">●</span> Skill<span class="purple">(engagement-startup)</span></div>
        <div class="muted">└─ loaded desktop shell, chameleon icon, local web bridge</div>
        <br />
        <div><span class="green">┌─(desktop㉿host)-[</span><span class="blue">${escapeHtml(config.decepticonHome || "~/.decepticon")}</span><span class="green">]</span></div>
        <div><span class="green">└─#</span> <span class="cmd">docker compose --profile web up -d web</span></div>
        <br />
        <div><span class="green">●</span> dashboard target <span class="target">${escapeHtml(config.dashboardUrl)}</span></div>
        <div><span class="green">●</span> status <span class="cmd">${escapedMessage}</span></div>
        <div class="output ${escapedDetail ? "" : "muted"}">${escapedDetail || "# auto-starting dashboard when config is present\n# first run: install Decepticon, then run decepticon onboard"}</div>
        <div class="setup-grid" aria-label="Onboarding steps">
          <div class="setup-card"><strong>1. Download</strong><span class="muted">Install the CLI + config for this OS.</span><code>${installCommand}</code></div>
          <div class="setup-card"><strong>2. Onboard</strong><span class="muted">Set API keys, telemetry, updates, Docker, and model provider.</span><code>${onboardCommand}</code></div>
          <div class="setup-card"><strong>3. Change API key</strong><span class="muted">Re-run setup anytime without editing files by hand.</span><code>${apiKeyCommand}</code></div>
        </div>
      </div>
      <div class="actions">
        <button type="button" data-desktop-action="retry">Retry bootstrap</button>
        <button type="button" data-desktop-action="copyInstall">Copy install</button>
        <button type="button" data-desktop-action="copyOnboard">Copy onboarding</button>
        <button type="button" data-desktop-action="copyApiKey">Copy API key setup</button>
        <button type="button" data-desktop-action="openDownload">Download</button>
        <button type="button" data-desktop-action="openDocs">Setup docs</button>
        <button type="button" data-desktop-action="openInBrowser">Open dashboard in browser</button>
      </div>
    </section>
  </main>
</body>
</html>`;
}

export function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[ch]));
}
