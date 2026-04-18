/**
 * Thread persistence — save/load LangGraph thread IDs to disk.
 *
 * Stores a history of recent threads so the CLI can list and resume
 * previous sessions with `/resume`.
 *
 * Storage location: ~/.decepticon/threads.json
 */

import { existsSync, mkdirSync, readFileSync, writeFileSync } from "fs";
import { homedir } from "os";
import { join } from "path";

export interface ThreadEntry {
  /** LangGraph thread ID. */
  threadId: string;
  /** Assistant ID used with this thread. */
  assistantId: string;
  /** ISO timestamp when the thread was last used. */
  lastUsed: string;
  /** First user message — serves as session title. */
  title: string;
}

const MAX_ENTRIES = 20;
const STORE_DIR = join(homedir(), ".decepticon");
const STORE_PATH = join(STORE_DIR, "threads.json");

function readStore(): ThreadEntry[] {
  try {
    if (!existsSync(STORE_PATH)) return [];
    const raw = readFileSync(STORE_PATH, "utf-8");
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeStore(entries: ThreadEntry[]): void {
  try {
    if (!existsSync(STORE_DIR)) {
      mkdirSync(STORE_DIR, { recursive: true });
    }
    writeFileSync(STORE_PATH, JSON.stringify(entries, null, 2), "utf-8");
  } catch {
    // Non-critical — don't crash if storage fails
  }
}

/** Save or update a thread entry. Keeps the most recent MAX_ENTRIES. */
export function saveThread(threadId: string, assistantId: string, title: string): void {
  const entries = readStore().filter((e) => e.threadId !== threadId);
  entries.unshift({
    threadId,
    assistantId,
    lastUsed: new Date().toISOString(),
    title: title.slice(0, 100),
  });
  writeStore(entries.slice(0, MAX_ENTRIES));
}

/** Update the lastUsed timestamp for an existing thread. */
export function touchThread(threadId: string): void {
  const entries = readStore();
  const entry = entries.find((e) => e.threadId === threadId);
  if (entry) {
    entry.lastUsed = new Date().toISOString();
    writeStore(entries);
  }
}

/** Load all saved thread entries, most recent first. */
export function listThreads(): ThreadEntry[] {
  return readStore();
}

/** Load a single thread by index (0-based). */
export function loadThreadByIndex(index: number): ThreadEntry | null {
  const entries = readStore();
  return entries[index] ?? null;
}

/** Clear all saved threads (e.g., on /clear). */
export function clearThread(): void {
  writeStore([]);
}
