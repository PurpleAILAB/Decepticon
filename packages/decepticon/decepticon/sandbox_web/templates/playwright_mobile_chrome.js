#!/usr/bin/env node
/**
 * Generic Playwright mobile fetcher — real Chrome + device emulation.
 *
 * Usage:
 *   echo '{"url":"...", "device":"iPhone 13 Pro"}' | node playwright_mobile_chrome.js
 *
 * Device name must match playwright `devices[...]` keys (Pixel 7, iPhone 13 Pro,
 * iPad Pro 11, etc.). When in doubt, omit `device` — default is iPhone 13 Pro.
 *
 * NO-SITE-NAME RULE: same as playwright_real_chrome.js — no hostname branches.
 */

function writeStdoutAsync(payload) {
  return new Promise((resolve, reject) => {
    process.stdout.write(payload, (err) => (err ? reject(err) : resolve()));
  });
}

async function buildEnvelope(ctx, page, html, resp, automation) {
  let cookies = [];
  try { cookies = (await ctx.cookies()).map((c) => ({ name: c.name, value: c.value, domain: c.domain })); } catch (_e) {}
  let userAgent = '';
  try { userAgent = await page.evaluate(() => navigator.userAgent); } catch (_e) {}
  let finalUrl = '';
  try { finalUrl = page.url(); } catch (_e) {}
  let status = 0;
  try { status = resp ? resp.status() : 0; } catch (_e) {}
  return JSON.stringify({ html, finalUrl, status, cookies, userAgent, automation });
}

async function readStdinJson() {
  return await new Promise((resolve, reject) => {
    let data = '';
    process.stdin.on('data', (c) => (data += c));
    process.stdin.on('end', () => {
      try { resolve(JSON.parse(data || '{}')); }
      catch (e) { reject(e); }
    });
    process.stdin.on('error', reject);
  });
}

async function main() {
  const args = await readStdinJson();
  const url = args.url;
  if (!url) { process.stderr.write('missing url\n'); process.exit(2); }

  const profileDir = args.profileDir || '/tmp/.insane_pw_mobile_profile';
  const deviceName = args.device || 'iPhone 13 Pro';
  const waitSelector = args.waitSelector || null;
  const timeoutMs = args.timeout || 60000;
  const headless = args.headless ?? false;

  let chromium, devices;
  let automation = 'playwright';
  try {
    // Patchright drop-in (additive; absent → previous behaviour unchanged).
    ({ chromium, devices } = require('patchright'));
    automation = 'patchright';
  } catch (_e0) {
    try {
      ({ chromium, devices } = require('playwright-extra'));
      const stealth = require('puppeteer-extra-plugin-stealth')();
      chromium.use(stealth);
      automation = 'playwright-extra+stealth';
    } catch (_e) {
      ({ chromium, devices } = require('playwright'));
      automation = 'playwright';
    }
  }

  const dev = devices[deviceName];
  if (!dev) {
    process.stderr.write(`unknown device: ${deviceName}\n`);
    process.exit(2);
  }

  let ctx;
  try {
    // Decepticon: prefer the sandbox's system Chromium (INSANE_CHROMIUM_PATH);
    // else the real Chrome channel.
    ctx = await chromium.launchPersistentContext(profileDir, {
      ...(process.env.INSANE_CHROMIUM_PATH
        ? { executablePath: process.env.INSANE_CHROMIUM_PATH }
        : { channel: 'chrome' }),
      headless,
      // Chromium won't launch as root without --no-sandbox in a container.
      args: ['--no-sandbox', '--disable-dev-shm-usage'],
      ...dev,
    });
    const page = await ctx.newPage();
    const deadline = Date.now() + timeoutMs;
    const rem = (cap) => Math.max(1000, Math.min(cap || timeoutMs, deadline - Date.now()));
    const mainResp = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: rem(90000) });

    if (waitSelector) {
      try {
        await page.waitForSelector(waitSelector, { timeout: rem(20000) });
      } catch (_e) {}
    }

    const html = await page.content();
    const payload = await buildEnvelope(ctx, page, html, mainResp, automation);
    await writeStdoutAsync(payload);  // flush fully before any exit
    process.exitCode = 0;
    return;                           // let finally close ctx, then exit naturally
  } catch (e) {
    process.stderr.write(`${e.name || 'Error'}: ${e.message || e}\n`);
    process.exitCode = 1;
    return;
  } finally {
    try { if (ctx) await ctx.close(); } catch (_e) {}
  }
}

main();
