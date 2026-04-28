package cmd

import (
	"fmt"
	"strings"

	"charm.land/huh/v2"
	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/config"
	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/ui"
	"github.com/spf13/cobra"
)

var resetFlag bool

var onboardCmd = &cobra.Command{
	Use:   "onboard",
	Short: "Configure Decepticon (auth methods, model profile, observability)",
	RunE:  runOnboard,
}

func init() {
	onboardCmd.Flags().BoolVar(&resetFlag, "reset", false, "Reconfigure even if .env already exists")
	rootCmd.AddCommand(onboardCmd)
}

// AuthMethod identifiers — must match decepticon/llm/models.py::AuthMethod.
const (
	methodAnthropicOAuth = "anthropic_oauth"
	methodAnthropicAPI   = "anthropic_api"
	methodOpenAIAPI      = "openai_api"
	methodGoogleAPI      = "google_api"
	methodMiniMaxAPI     = "minimax_api"
)

// methodOrder is the priority order surfaced in the wizard. The
// resulting DECEPTICON_AUTH_PRIORITY preserves this order, filtered
// to the methods the user actually selected. OAuth precedes the
// matching API on purpose: a subscription primary should fall back
// to the paid API only when the subscription quota is exhausted.
var methodOrder = []string{
	methodAnthropicOAuth,
	methodAnthropicAPI,
	methodOpenAIAPI,
	methodGoogleAPI,
	methodMiniMaxAPI,
}

func runOnboard(cmd *cobra.Command, args []string) error {
	if config.EnvExists() && !resetFlag {
		ui.Info(".env already configured at " + config.EnvPath())
		ui.DimText("Run 'decepticon onboard --reset' to reconfigure")
		return nil
	}

	var (
		methods       []string
		anthropicKey  string
		openaiKey     string
		geminiKey     string
		minimaxKey    string
		profile       string
		useLangSmith  bool
		langSmithKey  string
	)

	form := huh.NewForm(
		// Intro
		huh.NewGroup(
			huh.NewNote().
				Title("Decepticon Setup").
				Description("Configure auth methods, model profile, and\nobservability.\n\nUse ↑↓ to navigate, space to toggle, Enter to confirm."),
		),

		// Step 1: Auth methods (multi-select)
		huh.NewGroup(
			huh.NewMultiSelect[string]().
				Title("Auth Methods").
				Description("Pick every credential you have. Each method is an\nindependent fallback in priority order shown.").
				Options(
					huh.NewOption("Claude Code OAuth — Anthropic subscription (auth/*)", methodAnthropicOAuth),
					huh.NewOption("Anthropic API Key — sk-ant-...", methodAnthropicAPI),
					huh.NewOption("OpenAI API Key    — sk-...", methodOpenAIAPI),
					huh.NewOption("Google API Key    — AIza... (Gemini)", methodGoogleAPI),
					huh.NewOption("MiniMax API Key   — eyJ...", methodMiniMaxAPI),
				).
				Value(&methods).
				Validate(func(s []string) error {
					if len(s) == 0 {
						return fmt.Errorf("select at least one credential")
					}
					return nil
				}),
		).Title("1 / 4  ·  Credentials").
			Description("Select all that apply"),

		// Step 2a: Anthropic API key
		huh.NewGroup(
			huh.NewInput().
				Title("Anthropic API Key").
				Placeholder("sk-ant-...").
				EchoMode(huh.EchoModePassword).
				Value(&anthropicKey).
				Validate(nonEmpty),
		).Title("2 / 4  ·  Anthropic API").
			WithHideFunc(func() bool { return !contains(methods, methodAnthropicAPI) }),

		// Step 2b: OpenAI API key
		huh.NewGroup(
			huh.NewInput().
				Title("OpenAI API Key").
				Placeholder("sk-...").
				EchoMode(huh.EchoModePassword).
				Value(&openaiKey).
				Validate(nonEmpty),
		).Title("2 / 4  ·  OpenAI API").
			WithHideFunc(func() bool { return !contains(methods, methodOpenAIAPI) }),

		// Step 2c: Google API key
		huh.NewGroup(
			huh.NewInput().
				Title("Google (Gemini) API Key").
				Placeholder("AIza...").
				EchoMode(huh.EchoModePassword).
				Value(&geminiKey).
				Validate(nonEmpty),
		).Title("2 / 4  ·  Google API").
			WithHideFunc(func() bool { return !contains(methods, methodGoogleAPI) }),

		// Step 2d: MiniMax API key
		huh.NewGroup(
			huh.NewInput().
				Title("MiniMax API Key").
				Placeholder("eyJ...").
				EchoMode(huh.EchoModePassword).
				Value(&minimaxKey).
				Validate(nonEmpty),
		).Title("2 / 4  ·  MiniMax API").
			WithHideFunc(func() bool { return !contains(methods, methodMiniMaxAPI) }),

		// Step 3: Model profile
		huh.NewGroup(
			huh.NewSelect[string]().
				Title("Model Profile").
				Description("eco  per-agent tier (recommended)\nmax  every agent on HIGH (expensive)\ntest every agent on LOW (development)").
				Options(
					huh.NewOption("eco  — per-agent tier (recommended)", "eco"),
					huh.NewOption("max  — every agent on HIGH (expensive)", "max"),
					huh.NewOption("test — every agent on LOW (development)", "test"),
				).
				Value(&profile),
		).Title("3 / 4  ·  Profile"),

		// Step 4a: LangSmith toggle
		huh.NewGroup(
			huh.NewConfirm().
				Title("Enable LangSmith?").
				Description("LLM observability and trace collection").
				Affirmative("Yes").
				Negative("No").
				Value(&useLangSmith),
		).Title("4 / 4  ·  Observability"),

		// Step 4b: LangSmith key
		huh.NewGroup(
			huh.NewInput().
				Title("LangSmith API Key").
				Placeholder("lsv2_...").
				EchoMode(huh.EchoModePassword).
				Value(&langSmithKey).
				Validate(nonEmpty),
		).Title("4 / 4  ·  LangSmith").
			WithHideFunc(func() bool { return !useLangSmith }),
	).WithTheme(huh.ThemeFunc(ui.DecepticonTheme))

	if err := form.Run(); err != nil {
		return fmt.Errorf("setup cancelled: %w", err)
	}

	// huh.MultiSelect returns selected values in option order, not the
	// order the user toggled. Re-derive the priority by walking
	// methodOrder and keeping only what the user picked.
	priority := make([]string, 0, len(methods))
	for _, m := range methodOrder {
		if contains(methods, m) {
			priority = append(priority, m)
		}
	}

	values := map[string]string{
		"DECEPTICON_MODEL_PROFILE":    profile,
		"DECEPTICON_AUTH_PRIORITY":    strings.Join(priority, ","),
		"DECEPTICON_AUTH_CLAUDE_CODE": boolStr(contains(methods, methodAnthropicOAuth)),
	}

	if anthropicKey != "" {
		values["ANTHROPIC_API_KEY"] = anthropicKey
	}
	if openaiKey != "" {
		values["OPENAI_API_KEY"] = openaiKey
	}
	if geminiKey != "" {
		values["GEMINI_API_KEY"] = geminiKey
	}
	if minimaxKey != "" {
		values["MINIMAX_API_KEY"] = minimaxKey
	}

	if useLangSmith && langSmithKey != "" {
		values["LANGSMITH_TRACING"] = "true"
		values["LANGSMITH_API_KEY"] = langSmithKey
		values["LANGSMITH_PROJECT"] = "decepticon"
	}

	if err := config.WriteEnvFromEmbed(config.EnvPath(), values); err != nil {
		return fmt.Errorf("write .env: %w", err)
	}

	// Summary
	fmt.Println()
	fmt.Println(ui.Green.Render("  ✓ Configuration saved"))
	fmt.Println()
	fmt.Println(ui.Dim.Render("  ┌──────────────────────────────────┐"))
	fmt.Println(ui.Dim.Render("  │") + ui.Cyan.Render("  Methods   ") + ui.Dim.Render(strings.Join(priority, ", ")))
	fmt.Println(ui.Dim.Render("  │") + ui.Cyan.Render("  Profile   ") + ui.Dim.Render(profile))
	if useLangSmith {
		fmt.Println(ui.Dim.Render("  │") + ui.Cyan.Render("  LangSmith ") + ui.Green.Render("enabled"))
	}
	fmt.Println(ui.Dim.Render("  │"))
	fmt.Println(ui.Dim.Render("  │  ") + ui.Dim.Render(config.EnvPath()))
	fmt.Println(ui.Dim.Render("  └──────────────────────────────────┘"))
	fmt.Println()
	ui.DimText("  Run 'decepticon' to start the platform")
	return nil
}

func contains(haystack []string, needle string) bool {
	for _, s := range haystack {
		if s == needle {
			return true
		}
	}
	return false
}

func nonEmpty(s string) error {
	if strings.TrimSpace(s) == "" {
		return fmt.Errorf("value is required")
	}
	return nil
}

func boolStr(b bool) string {
	if b {
		return "true"
	}
	return "false"
}
