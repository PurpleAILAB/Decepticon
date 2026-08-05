export function statusHtml(config, message = "checking dashboard…", detail = "") {
  const escapedMessage = escapeHtml(message);
  const escapedDetail = escapeHtml(detail);
  const escapedVersion = escapeHtml(config.installedVersion ? `v${config.installedVersion}` : "cloud");
  const setup = config.setup || {};
  const installCommand = escapeHtml(setup.installCommand || "curl -fsSL https://decepticon.red/install.sh | bash");
  const onboardCommand = escapeHtml(setup.onboardCommand || "decepticon onboard");
  const apiKeyCommand = escapeHtml(setup.apiKeyCommand || "decepticon onboard --reset");
  const cloudUrl = escapeHtml(config.cloudAppUrl || setup.cloudAppUrl || "https://app.decepticon.red");
  const dashboardUrl = escapeHtml(config.dashboardUrl || cloudUrl);
  const modeLabel = config.isCloud ? "cloud" : "local";
  const icon = config.iconDataUrl
    ? `<img class="mark" src="${escapeHtml(config.iconDataUrl)}" alt="Decepticon chameleon" />`
    : `<div class="mark mark-fallback" aria-hidden="true">D</div>`;

  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:;" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Decepticon</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #050609;
      --panel: #0a0c12;
      --line: rgb(255 255 255 / .08);
      --muted: #8b95a8;
      --text: #eef1f6;
      --red: #e11d2e;
      --purple: #7c3aed;
      --purple-soft: #a78bfa;
      --green: #22c55e;
      --font: "Geist", "Inter", ui-sans-serif, system-ui, -apple-system, sans-serif;
      --mono: "Geist Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: var(--font);
      background:
        radial-gradient(ellipse 80% 50% at 50% -20%, rgb(124 58 237 / .28), transparent 55%),
        radial-gradient(circle at 90% 80%, rgb(225 29 46 / .08), transparent 28rem),
        linear-gradient(180deg, #07080d 0%, var(--bg) 55%, #030407 100%);
      color: var(--text);
    }

    body::before {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      opacity: .35;
      background-image:
        linear-gradient(rgb(255 255 255 / .03) 1px, transparent 1px),
        linear-gradient(90deg, rgb(255 255 255 / .03) 1px, transparent 1px);
      background-size: 48px 48px;
      mask-image: radial-gradient(ellipse at center, black 20%, transparent 75%);
    }

    .screen {
      position: relative;
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: clamp(1.25rem, 4vw, 2.5rem);
    }

    .card {
      width: min(720px, 100%);
      border: 1px solid var(--line);
      border-radius: 1.15rem;
      background: rgb(10 12 18 / .88);
      box-shadow:
        0 0 0 1px rgb(124 58 237 / .08),
        0 2rem 5rem rgb(0 0 0 / .55);
      overflow: hidden;
      backdrop-filter: blur(12px);
    }

    .card-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
      padding: 1.25rem 1.4rem 1rem;
      border-bottom: 1px solid var(--line);
    }

    .brand { display: flex; align-items: center; gap: .9rem; min-width: 0; }
    .mark {
      width: 3.1rem;
      height: 3.1rem;
      object-fit: cover;
      border-radius: .8rem;
      background: #0d1018;
      box-shadow: 0 0 0 1px rgb(124 58 237 / .55), 0 0 28px rgb(124 58 237 / .35);
      flex: 0 0 auto;
    }
    .mark-fallback { display: grid; place-items: center; color: var(--purple-soft); font-weight: 900; }
    .kicker {
      color: #9aa3b5;
      font-size: .72rem;
      letter-spacing: .14em;
      text-transform: uppercase;
      font-weight: 600;
    }
    .title {
      margin: .15rem 0 0;
      font-size: clamp(1.55rem, 3vw, 2rem);
      line-height: 1;
      letter-spacing: -.05em;
      font-weight: 800;
    }
    .title .red { color: var(--red); }

    .badges { display: flex; flex-wrap: wrap; justify-content: end; gap: .4rem; }
    .badge {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: .35rem .65rem;
      background: rgb(255 255 255 / .04);
      color: #cbd5e1;
      font-size: .72rem;
      font-weight: 650;
    }
    .badge.live::before {
      content: "";
      display: inline-block;
      width: .45rem;
      height: .45rem;
      border-radius: 999px;
      margin-right: .35rem;
      background: var(--green);
      box-shadow: 0 0 10px var(--green);
      vertical-align: middle;
    }

    .card-body { padding: 1.35rem 1.4rem 1.2rem; }
    .headline {
      margin: 0 0 .55rem;
      font-size: 1.15rem;
      font-weight: 700;
      letter-spacing: -.02em;
    }
    .lede {
      margin: 0;
      color: var(--muted);
      font-size: .95rem;
      line-height: 1.55;
    }
    .status-line {
      margin-top: 1.1rem;
      padding: .85rem 1rem;
      border-radius: .75rem;
      border: 1px solid var(--line);
      background: rgb(0 0 0 / .28);
      font-family: var(--mono);
      font-size: .82rem;
      line-height: 1.55;
    }
    .status-line strong { color: #f8fafc; font-weight: 650; }
    .status-line .muted { color: var(--muted); }
    .status-line .target { color: #c4b5fd; word-break: break-all; }
    .detail {
      margin: .85rem 0 0;
      white-space: pre-wrap;
      word-break: break-word;
      color: #a8b3c7;
      font-family: var(--mono);
      font-size: .78rem;
      line-height: 1.55;
    }

    .steps {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: .7rem;
      margin-top: 1.15rem;
    }
    .step {
      border: 1px solid var(--line);
      border-radius: .8rem;
      padding: .85rem;
      background: rgb(255 255 255 / .03);
    }
    .step strong {
      display: block;
      font-size: .82rem;
      margin-bottom: .3rem;
      color: #f8fafc;
    }
    .step p {
      margin: 0;
      color: var(--muted);
      font-size: .78rem;
      line-height: 1.45;
    }
    .step code {
      display: block;
      margin-top: .55rem;
      color: var(--purple-soft);
      font-family: var(--mono);
      font-size: .7rem;
      white-space: pre-wrap;
      word-break: break-word;
    }

    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: .55rem;
      padding: 0 1.4rem 1.35rem;
    }
    button {
      border: 1px solid var(--line);
      border-radius: .65rem;
      background: rgb(255 255 255 / .04);
      color: #e8edf5;
      padding: .7rem .95rem;
      font: inherit;
      font-size: .86rem;
      font-weight: 650;
      cursor: pointer;
      transition: border-color .15s ease, background .15s ease, color .15s ease;
    }
    button.primary {
      background: linear-gradient(180deg, #8b5cf6 0%, #6d28d9 100%);
      border-color: rgb(167 139 250 / .45);
      color: white;
      box-shadow: 0 .4rem 1.4rem rgb(109 40 217 / .35);
    }
    button.primary:hover {
      background: linear-gradient(180deg, #9b6dff 0%, #7c3aed 100%);
    }
    button:hover {
      border-color: rgb(124 58 237 / .55);
      background: rgb(124 58 237 / .14);
      color: white;
    }
    button:focus-visible { outline: 2px solid var(--purple-soft); outline-offset: 2px; }

    @media (max-width: 760px) {
      .steps { grid-template-columns: 1fr; }
      .card-head { flex-direction: column; align-items: flex-start; }
      .badges { justify-content: start; }
    }
  </style>
</head>
<body>
  <main class="screen">
    <section class="card" aria-label="Decepticon desktop">
      <header class="card-head">
        <div class="brand">
          ${icon}
          <div>
            <div class="kicker">PurpleAILAB</div>
            <h1 class="title">Decepti<span class="red">con</span></h1>
          </div>
        </div>
        <div class="badges" aria-label="Runtime status">
          <span class="badge live">${escapeHtml(modeLabel)}</span>
          <span class="badge">${escapedVersion}</span>
          <span class="badge">session persisted</span>
        </div>
      </header>

      <div class="card-body">
        <h2 class="headline">An AI red team under your command.</h2>
        <p class="lede">
          Same control plane as the website — scope, RoE, and OPPLAN enforced at runtime.
          Sign in on the cloud app, or bootstrap the local dashboard when Docker is installed.
        </p>
        <div class="status-line">
          <div><strong>target</strong> <span class="target">${dashboardUrl}</span></div>
          <div><strong>status</strong> <span class="muted">${escapedMessage}</span></div>
        </div>
        <pre class="detail">${escapedDetail || "Tip: export cookies from app.decepticon.red into ~/.decepticon/desktop-cookies.txt (JSON or Netscape) to restore a browser session. Prefer signing in interactively — do not commit session tokens."}</pre>
        <div class="steps" aria-label="Setup paths">
          <div class="step">
            <strong>1. Cloud app</strong>
            <p>Open the hosted product UI (Google / GitHub / email login).</p>
            <code>${cloudUrl}</code>
          </div>
          <div class="step">
            <strong>2. Local install</strong>
            <p>Install CLI + Docker stack for offline / self-hosted use.</p>
            <code>${installCommand}</code>
          </div>
          <div class="step">
            <strong>3. Onboard</strong>
            <p>API keys, telemetry, updates, and model provider.</p>
            <code>${onboardCommand}</code>
            <code>${apiKeyCommand}</code>
          </div>
        </div>
      </div>

      <div class="actions">
        <button type="button" class="primary" data-desktop-action="retry">Continue</button>
        <button type="button" data-desktop-action="openCloud">Open cloud app</button>
        <button type="button" data-desktop-action="openInBrowser">Open in browser</button>
        <button type="button" data-desktop-action="copyInstall">Copy install</button>
        <button type="button" data-desktop-action="copyOnboard">Copy onboarding</button>
        <button type="button" data-desktop-action="copyApiKey">Copy API key setup</button>
        <button type="button" data-desktop-action="openDownload">Download</button>
        <button type="button" data-desktop-action="openDocs">Setup docs</button>
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
