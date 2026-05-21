import { useState, useEffect, useRef } from "react";

const BRAILLE_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];
const INTERVAL_MS = 80;

export interface SpinnerState {
  frame: string;
  tick: number;
}

export function useSpinnerFrame(active: boolean): SpinnerState {
  const [tick, setTick] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!active) {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      setTick(0);
      return;
    }

    timerRef.current = setInterval(() => {
      setTick((prev) => prev + 1);
    }, INTERVAL_MS);

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [active]);

  return {
    frame: BRAILLE_FRAMES[tick % BRAILLE_FRAMES.length]!,
    tick,
  };
}
