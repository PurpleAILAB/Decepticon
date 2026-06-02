import React from "react";
import { Box, Text } from "ink";

interface QuestionProps {
  header: string;
  question: string;
}

export const QAQuestionMessage = React.memo(function QAQuestionMessage({
  header,
  question,
}: QuestionProps) {
  return (
    <Box flexDirection="row" marginTop={1}>
      {header ? <Text color="cyan" bold>{`[${header}] `}</Text> : null}
      <Text wrap="wrap">{question}</Text>
    </Box>
  );
});

interface AnswerProps {
  answer: string;
}

export const QAAnswerMessage = React.memo(function QAAnswerMessage({
  answer,
}: AnswerProps) {
  return (
    <Box marginTop={1}>
      <Text color="green" wrap="wrap">{`› ${answer}`}</Text>
    </Box>
  );
});
