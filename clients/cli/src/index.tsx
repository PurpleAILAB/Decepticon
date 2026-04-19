#!/usr/bin/env node
import React from "react";
import { render } from "ink";
import { App } from "./app.js";

const args = process.argv.slice(2);
const resumeThread = args.includes("--resume") || args.includes("-r");
const initialMessage = process.env.DECEPTICON_INITIAL_MESSAGE || undefined;

const instance = render(<App initialMessage={initialMessage} resumeThread={resumeThread} />, {
  patchConsole: true,
  exitOnCtrlC: false,
});

await instance.waitUntilExit();
