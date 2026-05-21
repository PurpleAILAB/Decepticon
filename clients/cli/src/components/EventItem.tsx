import React from "react";
import { Box } from "ink";
import type { AgentEvent } from "../types.js";
import { BashResult } from "./BashResult.js";
import { UserMessage } from "./messages/UserMessage.js";
import { AIMessage } from "./messages/AIMessage.js";
import { ToolCallMessage } from "./messages/ToolCallMessage.js";
import { DelegateMessage } from "./messages/DelegateMessage.js";
import { SystemMessage } from "./messages/SystemMessage.js";
import { BackgroundCompleteMessage } from "./messages/BackgroundCompleteMessage.js";

interface EventItemProps {
  event: AgentEvent;
}

/** Routes an AgentEvent to the appropriate visual renderer. */
export const EventItem = React.memo(function EventItem({
  event,
}: EventItemProps) {
  switch (event.type) {
    case "user":
      return <UserMessage content={event.content} />;

    case "bash_result":
      return (
        <Box marginTop={1}>
          <BashResult
            command={(event.toolArgs?.command as string) ?? ""}
            output={event.content}
            status={event.status}
          />
        </Box>
      );

    case "tool_result":
      return <ToolCallMessage event={event} />;

    case "delegate":
      return (
        <DelegateMessage
          agent={event.subagent ?? "unknown"}
          content={event.content}
        />
      );

    case "ai_message":
      return <AIMessage content={event.content} />;

    case "system":
      return <SystemMessage content={event.content} />;

    case "background_complete":
      return (
        <BackgroundCompleteMessage
          command={event.command}
          session={event.session}
          exitCode={event.exitCode}
          elapsed={event.elapsed}
          output={event.content}
        />
      );

    default:
      return null;
  }
});
