import React from "react";
import { AppStateProvider } from "./state/AppState.js";
import { REPL } from "./screens/REPL.js";

interface AppProps {
  initialMessage?: string;
  resumeThread?: boolean;
}

export function App({ initialMessage, resumeThread }: AppProps) {
  return (
    <AppStateProvider>
      <REPL initialMessage={initialMessage} resumeThread={resumeThread} />
    </AppStateProvider>
  );
}
