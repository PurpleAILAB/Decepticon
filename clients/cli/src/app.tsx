import React from "react";
import { AppStateProvider } from "./state/AppState.js";
import { REPL } from "./screens/REPL.js";

interface AppProps {
  initialMessage?: string;
  continueThread?: boolean;
}

export function App({ initialMessage, continueThread }: AppProps) {
  return (
    <AppStateProvider>
      <REPL initialMessage={initialMessage} continueThread={continueThread} />
    </AppStateProvider>
  );
}
