/**
 * AppState — global UI state for the Decepticon CLI.
 *
 * Uses a zero-dep external store with useSyncExternalStore,
 * following Claude Code's AppState pattern exactly.
 */

import React, { createContext, useContext, useSyncExternalStore, useState } from "react";
import { createStore, type Store } from "./store.js";
import type { ScreenMode } from "../types.js";

// ── State type ────────────────────────────────────────────────────

export type AppState = {
  /** Current screen mode: prompt (compact) or transcript (full). */
  screen: ScreenMode;
};

export type AppStateStore = Store<AppState>;

export function getDefaultAppState(): AppState {
  return {
    screen: "prompt",
  };
}

// ── Context + Provider ────────────────────────────────────────────

const AppStoreContext = createContext<AppStateStore | null>(null);

export function AppStateProvider({
  children,
  initialState,
}: {
  children: React.ReactNode;
  initialState?: AppState;
}) {
  const [store] = useState(() =>
    createStore(initialState ?? getDefaultAppState()),
  );

  return React.createElement(
    AppStoreContext.Provider,
    { value: store },
    children,
  );
}

// ── Hooks ─────────────────────────────────────────────────────────

function useStore(): AppStateStore {
  const store = useContext(AppStoreContext);
  if (!store) {
    throw new Error("useAppState must be used within an AppStateProvider");
  }
  return store;
}

/**
 * Read a slice of AppState with automatic re-render on change.
 *
 * Usage: const screen = useAppState(s => s.screen);
 */
export function useAppState<T>(selector: (s: AppState) => T): T {
  const store = useStore();
  return useSyncExternalStore(
    store.subscribe,
    () => selector(store.getState()),
  );
}

/**
 * Get the setState updater for AppState.
 *
 * Usage: const set = useSetAppState(); set(prev => ({ ...prev, screen: "transcript" }));
 */
export function useSetAppState(): AppStateStore["setState"] {
  return useStore().setState;
}
