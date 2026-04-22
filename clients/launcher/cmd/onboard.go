package cmd

import (
	"fmt"

	"charm.land/huh/v2"
	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/config"
	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/ui"
	"github.com/spf13/cobra"
)

var resetFlag bool

var onboardCmd = &cobra.Command{
	Use:   "onboard",
	Short: "Configure Decepticon (authentication, provider, model profile)",
	RunE:  runOnboard,
}

func init() {
	onboardCmd.Flags().BoolVar(&resetFlag, "reset", false, "Reconfigure even if .env already exists")
	rootCmd.AddCommand(onboardCmd)
}

func runOnboard(cmd *cobra.Command, args []string) error {
	if config.EnvExists() && !resetFlag {
		ui.Info(".env already configured at " + config.EnvPath())
		ui.DimText("Run 'decepticon onboard --reset' to reconfigure")
		return nil
	}

	var (
		authMethod   string
		llmProvider  string
		apiKey       string
		profile      string
		useLangSmith bool
		langSmithKey string
	)

	form := huh.NewForm(
		// Intro
		huh.NewGroup(
			huh.NewNote().
				Title("Decepticon Setup").
				Description("Configure authentication, LLM provider,\nmodel profile, and observability.\n\nUse ↑↓ to navigate, Enter to confirm."),
		),

		// Step 1: Authentication method
		huh.NewGroup(
			huh.NewSelect[string]().
				Title("Authentication Method").
				Description("How should Decepticon authenticate with LLM providers?").
				Options(
					huh.NewOption("API Key — Direct API access via x-api-key header", "api"),
					huh.NewOption("OAuth  — Subscription-based (Claude Code, Codex)", "auth"),
				).
				Value(&authMethod),
		).Title("1 / 5  ·  Authentication").
			Description("Choose how to connect to LLM services"),

		// Step 2: Provider selection
		huh.NewGroup(
			huh.NewSelect[string]().
				Title("LLM Provider").
				Description("Which provider will power the agents?").
				OptionsFunc(func() []huh.Option[string] {
					if authMethod == "auth" {
						return []huh.Option[string]{
							huh.NewOption("Claude Code  — Anthropic OAuth", "claude-code"),
							huh.NewOption("Codex        — coming soon", "codex"),
						}
					}
					return []huh.Option[string]{
						huh.NewOption("Anthropic  — Claude Opus / Sonnet / Haiku", "anthropic"),
						huh.NewOption("OpenAI     — GPT-5.4 / GPT-4.1", "openai"),
						huh.NewOption("Google     — Gemini 2.5 Flash", "google"),
						huh.NewOption("MiniMax    — M2.7", "minimax"),
					}
				}, &authMethod).
				Value(&llmProvider),
		).Title("2 / 5  ·  Provider").
			Description("Select your primary LLM provider"),

		// Step 3: API key input (only for api mode)
		huh.NewGroup(
			huh.NewInput().
				TitleFunc(func() string {
					switch llmProvider {
					case "anthropic":
						return "Anthropic API Key"
					case "openai":
						return "OpenAI API Key"
					case "google":
						return "Google API Key"
					case "minimax":
						return "MiniMax API Key"
					}
					return "API Key"
				}, &llmProvider).
				PlaceholderFunc(func() string {
					switch llmProvider {
					case "anthropic":
						return "sk-ant-..."
					case "openai":
						return "sk-..."
					case "google":
						return "AIza..."
					case "minimax":
						return "eyJ..."
					}
					return ""
				}, &llmProvider).
				EchoMode(huh.EchoModePassword).
				Value(&apiKey).
				Validate(func(s string) error {
					if s == "" {
						return fmt.Errorf("API key is required")
					}
					return nil
				}),
		).Title("3 / 5  ·  Credentials").
			Description("Enter your provider API key").
			WithHideFunc(func() bool {
				return authMethod == "auth"
			}),

		// Step 4: Model profile
		huh.NewGroup(
			huh.NewSelect[string]().
				Title("Model Profile").
				Description("Controls which models each agent tier uses").
				Options(
					huh.NewOption("eco  — Opus + Sonnet + Haiku mix (recommended)", "eco"),
					huh.NewOption("max  — Opus everywhere (expensive)", "max"),
					huh.NewOption("test — Haiku only (for development)", "test"),
				).
				Value(&profile),
		).Title("4 / 5  ·  Performance").
			Description("Balance between cost and capability"),

		// Step 5: LangSmith tracing
		huh.NewGroup(
			huh.NewConfirm().
				Title("Enable LangSmith?").
				Description("LLM observability and trace collection").
				Affirmative("Yes").
				Negative("No").
				Value(&useLangSmith),
		).Title("5 / 5  ·  Observability").
			Description("Optional tracing integration"),

		// LangSmith API key (only when enabled)
		huh.NewGroup(
			huh.NewInput().
				Title("LangSmith API Key").
				Placeholder("lsv2_...").
				EchoMode(huh.EchoModePassword).
				Value(&langSmithKey).
				Validate(func(s string) error {
					if s == "" {
						return fmt.Errorf("LangSmith API key is required")
					}
					return nil
				}),
		).Title("5 / 5  ·  Observability").
			Description("Enter your LangSmith credentials").
			WithHideFunc(func() bool {
				return !useLangSmith
			}),
	).WithTheme(huh.ThemeFunc(ui.DecepticonTheme))

	if err := form.Run(); err != nil {
		return fmt.Errorf("setup cancelled: %w", err)
	}

	// Build values map
	values := map[string]string{
		"DECEPTICON_MODEL_PROFILE":  profile,
		"DECEPTICON_MODEL_PROVIDER": authMethod,
	}

	if authMethod == "api" && apiKey != "" {
		switch llmProvider {
		case "anthropic":
			values["ANTHROPIC_API_KEY"] = apiKey
		case "openai":
			values["OPENAI_API_KEY"] = apiKey
		case "google":
			values["GOOGLE_API_KEY"] = apiKey
		case "minimax":
			values["MINIMAX_API_KEY"] = apiKey
		}
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
	fmt.Println(ui.Dim.Render("  │") + ui.Cyan.Render("  Auth      ") + ui.Dim.Render(authMethod))
	fmt.Println(ui.Dim.Render("  │") + ui.Cyan.Render("  Provider  ") + ui.Dim.Render(llmProvider))
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
