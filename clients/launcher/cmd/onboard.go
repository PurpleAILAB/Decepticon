package cmd

import (
	"errors"
	"fmt"

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

	requiredKey := func(s string) error {
		if s == "" {
			return fmt.Errorf("required")
		}
		return nil
	}

	// Step 0 — welcome note.
	if err := ui.Continue(
		"Decepticon Setup",
		"Configure authentication, LLM provider, model profile, and observability.",
	); err != nil {
		return cancelled(err)
	}

	// Step 1 — authentication method.
	authMethod, err := ui.Select(
		"1 / 5 · Authentication",
		"Choose how to connect to LLM services",
		[]ui.SelectOption{
			{Label: "API Key", Description: "Direct API access via x-api-key header", Value: "api"},
			{Label: "OAuth", Description: "Subscription-based (Claude Code, Codex)", Value: "auth"},
		},
	)
	if err != nil {
		return cancelled(err)
	}

	// Step 2 — provider selection (options depend on auth method).
	var providerOpts []ui.SelectOption
	if authMethod == "auth" {
		providerOpts = []ui.SelectOption{
			{Label: "Claude Code", Description: "Anthropic OAuth", Value: "claude-code"},
			{Label: "Codex", Description: "coming soon", Value: "codex"},
		}
	} else {
		providerOpts = []ui.SelectOption{
			{Label: "Anthropic", Description: "Claude Opus / Sonnet / Haiku", Value: "anthropic"},
			{Label: "OpenAI", Description: "GPT-5.4 / GPT-4.1", Value: "openai"},
			{Label: "Google", Description: "Gemini 2.5 Flash", Value: "google"},
			{Label: "MiniMax", Description: "M2.7", Value: "minimax"},
		}
	}
	llmProvider, err := ui.Select(
		"2 / 5 · Provider",
		"Select your primary LLM provider",
		providerOpts,
	)
	if err != nil {
		return cancelled(err)
	}

	// Step 3 — API key (only when auth method is "api").
	var apiKey string
	if authMethod == "api" {
		title, placeholder := apiKeyLabels(llmProvider)
		apiKey, err = ui.Input(ui.InputOptions{
			Title:       "3 / 5 · " + title,
			Description: "Enter your provider API key",
			Placeholder: placeholder,
			Password:    true,
			Validate:    requiredKey,
		})
		if err != nil {
			return cancelled(err)
		}
	}

	// Step 4 — model profile.
	profile, err := ui.Select(
		"4 / 5 · Performance",
		"Balance between cost and capability",
		[]ui.SelectOption{
			{Label: "eco", Description: "Opus + Sonnet + Haiku mix (recommended)", Value: "eco"},
			{Label: "max", Description: "Opus everywhere (expensive)", Value: "max"},
			{Label: "test", Description: "Haiku only (for development)", Value: "test"},
		},
	)
	if err != nil {
		return cancelled(err)
	}

	// Step 5 — LangSmith tracing toggle.
	useLangSmith, err := ui.Confirm(
		"5 / 5 · Observability",
		"Enable LangSmith for LLM observability and trace collection?",
		"Yes", "No",
	)
	if err != nil {
		return cancelled(err)
	}

	var langSmithKey string
	if useLangSmith {
		langSmithKey, err = ui.Input(ui.InputOptions{
			Title:       "5 / 5 · LangSmith API Key",
			Description: "Enter your LangSmith credentials",
			Placeholder: "lsv2_...",
			Password:    true,
			Validate:    requiredKey,
		})
		if err != nil {
			return cancelled(err)
		}
	}

	// Build values map and write .env.
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

	// Summary card.
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

// apiKeyLabels returns the input title and placeholder for the given provider.
func apiKeyLabels(provider string) (title, placeholder string) {
	switch provider {
	case "anthropic":
		return "Anthropic API Key", "sk-ant-..."
	case "openai":
		return "OpenAI API Key", "sk-..."
	case "google":
		return "Google API Key", "AIza..."
	case "minimax":
		return "MiniMax API Key", "eyJ..."
	}
	return "API Key", ""
}

// cancelled converts a prompt cancellation into a setup-cancelled error,
// passing other errors through unchanged.
func cancelled(err error) error {
	if errors.Is(err, ui.ErrPromptCancelled) {
		return fmt.Errorf("setup cancelled")
	}
	return err
}
