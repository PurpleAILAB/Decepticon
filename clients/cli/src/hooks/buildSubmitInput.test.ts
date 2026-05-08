import { describe, expect, it } from "vitest";
import { buildSubmitInput } from "./buildSubmitInput.js";

describe("buildSubmitInput", () => {
  it("always includes the user message", () => {
    const { input } = buildSubmitInput({
      message: "hello",
      handoffSlug: null,
      envSlug: undefined,
      envWorkspacePath: undefined,
      modelOverride: null,
    });
    expect(input.messages).toEqual([{ role: "user", content: "hello" }]);
  });

  describe("slug precedence", () => {
    it("uses handoffSlug when present, ignoring envSlug — regression #159", () => {
      const { input } = buildSubmitInput({
        message: "go",
        handoffSlug: "soundwave-authored",
        envSlug: "launcher-set",
        envWorkspacePath: "/workspace",
        modelOverride: null,
      });
      expect(input.engagement_name).toBe("soundwave-authored");
    });

    it("falls back to envSlug when handoffSlug is null", () => {
      const { input } = buildSubmitInput({
        message: "go",
        handoffSlug: null,
        envSlug: "from-env",
        envWorkspacePath: undefined,
        modelOverride: null,
      });
      expect(input.engagement_name).toBe("from-env");
      expect(input.workspace_path).toBe("/workspace");
    });

    it("emits no engagement fields when both are null/undefined", () => {
      const { input } = buildSubmitInput({
        message: "go",
        handoffSlug: null,
        envSlug: undefined,
        envWorkspacePath: undefined,
        modelOverride: null,
      });
      expect(input.engagement_name).toBeUndefined();
      expect(input.workspace_path).toBeUndefined();
    });
  });

  describe("workspace_path", () => {
    it("uses envWorkspacePath when slug wins", () => {
      const { input } = buildSubmitInput({
        message: "go",
        handoffSlug: "eng",
        envSlug: undefined,
        envWorkspacePath: "/custom/path",
        modelOverride: null,
      });
      expect(input.workspace_path).toBe("/custom/path");
    });

    it("defaults workspace_path to /workspace when envWorkspacePath is undefined", () => {
      const { input } = buildSubmitInput({
        message: "go",
        handoffSlug: null,
        envSlug: "from-env",
        envWorkspacePath: undefined,
        modelOverride: null,
      });
      expect(input.workspace_path).toBe("/workspace");
    });
  });

  describe("modelOverride", () => {
    it("injects modelOverride into input and streamConfig.configurable", () => {
      const { input, streamConfig } = buildSubmitInput({
        message: "go",
        handoffSlug: null,
        envSlug: undefined,
        envWorkspacePath: undefined,
        modelOverride: "claude-opus-4",
      });
      expect(input.model_override).toBe("claude-opus-4");
      expect(streamConfig.configurable?.model_override).toBe("claude-opus-4");
    });

    it("emits no model_override fields when null", () => {
      const { input, streamConfig } = buildSubmitInput({
        message: "go",
        handoffSlug: null,
        envSlug: undefined,
        envWorkspacePath: undefined,
        modelOverride: null,
      });
      expect(input.model_override).toBeUndefined();
      expect(streamConfig.configurable).toBeUndefined();
    });
  });
});
