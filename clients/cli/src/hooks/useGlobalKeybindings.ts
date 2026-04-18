/**
 * Global keybinding handlers — Claude Code's GlobalKeybindingHandlers pattern.
 *
 * Registers all global keyboard shortcuts via Ink's useInput.
 * - ctrl+o: Toggle transcript (expand/collapse) — single expansion control
 * - ctrl+c: Interrupt (pause) / cancel / exit — context-dependent
 *   - Streaming: single = pause, double (within 500ms) = hard cancel
 *   - Paused: cancel the paused run
 *   - Idle with queue: clear the queue
 *   - Idle: exit app
 * - Escape: Exit transcript mode / clear queue
 */

import { useCallback, useRef } from "react";
import { useInput } from "ink";
import { useAppState, useSetAppState } from "../state/AppState.js";
import type { ScreenMode } from "../types.js";
import type { RunState } from "./useAgent.js";

interface Props {
  /** Called when ctrl+c should pause the current stream (single press). */
  onInterrupt: () => void;
  /** Called when ctrl+c should hard cancel (double press, or from paused). */
  onCancel: () => void;
  /** Called when ctrl+c should exit the app (idle, no queue). */
  onExit: () => void;
  /** Called to clear a queued message. */
  onClearQueue?: () => void;
  /** Current run lifecycle state. */
  runState: RunState;
  /** Whether a message is queued. */
  hasQueuedMessage?: boolean;
}

const DOUBLE_PRESS_MS = 500;

export function useGlobalKeybindings({
  onInterrupt,
  onCancel,
  onExit,
  onClearQueue,
  runState,
  hasQueuedMessage = false,
}: Props): void {
  const screen = useAppState((s) => s.screen);
  const setAppState = useSetAppState();
  const lastCtrlCRef = useRef(0);

  const toggleScreen = useCallback(() => {
    setAppState((prev) => ({
      ...prev,
      screen: (prev.screen === "transcript" ? "prompt" : "transcript") as ScreenMode,
    }));
  }, [setAppState]);

  const exitTranscript = useCallback(() => {
    setAppState((prev) => ({ ...prev, screen: "prompt" as ScreenMode }));
  }, [setAppState]);

  useInput((input, key) => {
    // ctrl+o: toggle transcript (expand/collapse all)
    if (key.ctrl && input === "o") {
      toggleScreen();
      return;
    }

    // Escape in transcript → return to prompt
    if (screen === "transcript" && key.escape) {
      exitTranscript();
      return;
    }

    // Escape: clear queued message (any screen mode)
    if (key.escape && hasQueuedMessage) {
      onClearQueue?.();
      return;
    }

    // ctrl+c: context-dependent behavior
    if (key.ctrl && input === "c") {
      const now = Date.now();
      const isDoubleTap = (now - lastCtrlCRef.current) < DOUBLE_PRESS_MS;
      lastCtrlCRef.current = now;

      if (runState === "streaming" || runState === "connecting") {
        if (isDoubleTap) {
          // Double Ctrl+C while streaming → hard cancel (state lost)
          onClearQueue?.();
          onCancel();
        } else {
          // Single Ctrl+C while streaming → pause (state preserved)
          onInterrupt();
        }
        // Also exit transcript if viewing it
        if (screen === "transcript") {
          exitTranscript();
        }
      } else if (runState === "paused") {
        // Ctrl+C while paused → hard cancel the paused run
        onClearQueue?.();
        onCancel();
        if (screen === "transcript") {
          exitTranscript();
        }
      } else {
        // Idle state
        if (hasQueuedMessage) {
          // Clear queued message first, don't exit
          onClearQueue?.();
        } else if (screen === "transcript") {
          exitTranscript();
        } else {
          // Truly idle, no queue → exit app
          onExit();
        }
      }
    }
  });
}
