import React from "react";
import { Text, Box, useStdout } from "ink";

// ── Full banner: braille logo + block-character text art (≥140 cols) ──
const BANNER_FULL = `
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢰⣶⣤⡀⠀⣤⣤⣾⣿⣦⣠⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣶⣶⣿⢿⣿⣿⣿⣿⣿⣻⣿⣟⣿⣿⣷⣾⣇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⢰⣿⣄⣼⣿⣆⠀⣀⣴⣾⣿⣻⣟⣷⣯⢿⡾⣯⣷⣿⣾⣯⣷⢿⡾⣿⣤⣀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⣀⣸⣿⣿⣽⣯⣿⣻⣿⣟⣿⢾⣽⣟⣿⣻⣟⣿⣻⣯⡿⣾⣽⣟⣿⣽⣟⡿⣿⢿⣦⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⢠⣾⣿⣷⣽⣷⢿⣷⢟⣮⣿⣻⡿⣿⣻⣿⣽⣻⢾⣯⣿⣻⣛⠿⣾⣽⢷⡿⣾⣻⣟⣯⣿⣇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠉⠙⢹⣷⢿⣯⡿⣿⢿⣟⣷⣿⣿⣿⣟⣯⣿⣻⢷⣿⡧⣿⢟⢮⣻⣟⣿⣽⣯⢿⣽⣿⠇⠀⠀⠀⠀⠀⠀⠀⠀⠀██████████                                         █████     ███⠀⠀
⠀⠀⠀⠀⣼⣿⣻⣿⣾⣿⣟⣿⡾⣿⢾⣽⣟⣿⣿⡾⣯⣿⣾⣷⣽⣳⣧⣿⢿⣷⢿⡾⣿⣞⡿⣿⡀⠀⠀⠀⠀⠀⠀⠀░░███░░░░███                                       ░░███     ░░░⠀⠀
⠀⠀⠀⠀⠻⣟⢽⣿⣾⢯⣿⣾⣟⡿⣯⣿⣿⣽⢿⣟⣿⣽⣟⣾⣿⣯⢿⡾⣿⣽⣻⣟⣷⡿⣽⣿⣯⠀⠀⠀⠀⠀⠀⠀⠀░███   ░░███  ██████   ██████   ██████  ████████  ███████   ████   ██████   ██████  ████████⠀⠀
⠀⠀⠀⠀⠀⠀⠸⣿⣟⣿⣻⣾⣽⣿⣿⣻⣯⣿⣿⡿⣿⣾⣿⣿⣾⣻⣟⣿⣷⢿⣷⣯⣿⣽⢿⣾⠗⠀⠀⠀⠀⠀⠀⠀⠀░███    ░███ ███░░███ ███░░███ ███░░███░░███░░███░░░███░   ░░███  ███░░███ ███░░███░░███░░███⠀
⠀⠀⠀⠀⠀⠀⢰⣿⣟⣿⢿⣿⡽⣷⣿⣿⡿⣿⡿⣿⣿⣿⣽⢷⣻⣽⣿⣿⣻⣿⣷⣿⣷⢿⠿⠉⠀⠀⠀⠀⠀⠀⠀⠀⠀░███    ░███░███████ ░███ ░░░ ░███████  ░███ ░███  ░███     ░███ ░███ ░░░ ░███ ░███ ░███ ░███
⠀⠀⠀⠀⠀⠀⢸⣿⣯⣟⣿⣯⣿⣟⣿⣾⣿⣿⢿⣿⡿⣺⣷⣿⢿⡫⠷⠝⠽⠝⣟⢷⣿⣷⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀░███    ███ ░███░░░  ░███  ███░███░░░   ░███ ░███  ░███ ███ ░███ ░███  ███░███ ░███ ░███ ░███
⠀⠀⠀⠀⠀⠀⢘⣿⣾⢯⣿⣷⢿⡿⣿⣟⣿⣽⣿⣿⣝⣿⢿⠕⠁⠀⠀⢀⠄⠀⠀⠉⢻⢿⣿⣆⠀⠀⠀⠀⠀⠀⠀⠀⠀ ██████████  ░░██████ ░░██████ ░░██████  ░███████   ░░█████  █████░░██████ ░░██████  ████ █████
⠀⠀⠀⠀⠀⠀⠀⣿⣿⢯⣿⣿⣻⣿⣿⣿⣻⣾⣿⣮⣿⡿⡇⠀⠀⠀⢃⣈⣤⠄⡨⠀⠈⢻⣿⡿⡄⠀⠀⠀⠀⠀⠀⠀⠀░░░░░░░░░░    ░░░░░░   ░░░░░░   ░░░░░░   ░███░░░     ░░░░░  ░░░░░  ░░░░░░   ░░░░░░  ░░░░ ░░░░░
⠀⠀⠀⠀⠀⠀⠀⠸⣿⣟⣷⢿⣿⣿⣯⣿⣽⣿⣿⢮⣿⣯⠇⠀⢀⡉⢴⡽⣙⠀⠄⠀⠀⣸⣿⣟⡇⠀⠀⠀⠀⠀⠀⠀⠀                                         ░███⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠹⣿⣯⡿⣿⣾⣿⡿⣾⣷⣿⣯⢿⣿⣣⠀⠀⠀⠯⠋⡁⠐⠀⠀⢠⣟⣿⢯⠂⠀⠀⠀⠀⠀⠀⠀⠀                                         █████⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠙⡿⣿⣳⣿⣻⣿⣷⡿⣿⣿⣝⣿⣿⣷⣄⡀⠀⠀⠀⠈⣀⣴⣿⣿⣻⠃⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀                                       ░░░░░
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠻⣻⣷⣿⣽⢿⣿⣿⣟⣿⣮⣟⣽⣿⣿⣷⣾⣾⣿⡿⣿⢯⣿⣾⣦⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠑⠿⡿⣿⣾⣽⣟⣿⢿⣿⣷⣷⣽⣽⣫⣟⣽⣽⡾⠓⠻⣿⣿⣿⣦⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠑⠋⠟⢟⢿⢿⡷⣿⢿⢿⡻⢟⠟⠋⠈⠀⠀⠀⠑⠿⣿⣿⣿⣶⡀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠙⢷⡿⡯⠃⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
`;

// ── Precomputed widths ───────────────────────────────────────────────
const BANNER_FULL_WIDTH = Math.max(
  ...BANNER_FULL.split("\n").map((l) => l.length),
);

/** Extract just the braille logo by stripping block-character text art. */
function extractLogo(banner: string): string {
  return banner
    .split("\n")
    .map((line) => {
      const idx = line.search(/[\u2588\u2591]/);
      return idx > 0 ? line.slice(0, idx).replace(/[\s\u2800]+$/, "") : line;
    })
    .join("\n");
}

const BANNER_LOGO = extractLogo(BANNER_FULL);
const BANNER_LOGO_WIDTH = Math.max(
  ...BANNER_LOGO.split("\n").map((l) => l.length),
);

// ── Responsive banner component ──────────────────────────────────────

export const Banner = React.memo(function Banner() {
  const { stdout } = useStdout();
  const cols = stdout?.columns ?? 80;

  // Wide terminal — full banner with logo + text art
  if (cols >= BANNER_FULL_WIDTH) {
    return <Text color="red">{BANNER_FULL}</Text>;
  }

  // Medium terminal — braille logo + text name below
  if (cols >= BANNER_LOGO_WIDTH) {
    return (
      <Box flexDirection="column">
        <Text color="red">{BANNER_LOGO}</Text>
        <Text color="red" bold>
          {"       D E C E P T I C O N"}
        </Text>
      </Box>
    );
  }

  // Narrow terminal — text only
  return (
    <Box marginTop={1} marginBottom={1}>
      <Text color="red" bold>
        {"D E C E P T I C O N"}
      </Text>
    </Box>
  );
});
