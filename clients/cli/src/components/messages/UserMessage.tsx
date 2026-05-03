import React from "react";
import { Box, Text } from "ink";
import { CtrlOToExpand } from "../shell/CtrlOToExpand.js";

const TRUNCATE_HEAD_CHARS = 8000;
const TRUNCATE_TAIL_CHARS = 2000;

interface Props {
  content: string;
}

export const UserMessage = React.memo(function UserMessage({ content }: Props) {
  const maxLen = TRUNCATE_HEAD_CHARS + TRUNCATE_TAIL_CHARS;
  const isTruncated = content.length > maxLen;

  const display = isTruncated
    ? content.slice(0, TRUNCATE_HEAD_CHARS) +
      "\n\u2026\n" +
      content.slice(-TRUNCATE_TAIL_CHARS)
    : content;

  return (
    <Box flexDirection="column" marginTop={1} marginBottom={1}>
      <Text backgroundColor="#333333" color="white" bold>
        {` \u276F ${display} `}
      </Text>
      {isTruncated && <CtrlOToExpand />}
    </Box>
  );
});
