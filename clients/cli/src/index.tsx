#!/usr/bin/env node
import React from "react";
import { render } from "ink";
import { App } from "./app.js";

const args = process.argv.slice(2);
const continueThread = args.includes("--continue") || args.includes("-c");
const initialMessage = process.env.DECEPTICON_INITIAL_MESSAGE || undefined;

const instance = render(<App initialMessage={initialMessage} continueThread={continueThread} />, {
  patchConsole: true,
  exitOnCtrlC: false,
});

await instance.waitUntilExit();
