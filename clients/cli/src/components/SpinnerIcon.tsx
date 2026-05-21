import React from "react";
import { Text } from "ink";
import { useSpinnerFrame } from "../hooks/useSpinnerFrame.js";

interface SpinnerIconProps {
  active: boolean;
}

export const SpinnerIcon = React.memo(function SpinnerIcon({
  active,
}: SpinnerIconProps) {
  const { frame } = useSpinnerFrame(active);
  if (!active) return null;
  return <Text color="blue">{` ${frame}`}</Text>;
});
