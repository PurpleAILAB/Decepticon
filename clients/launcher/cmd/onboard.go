package cmd

import (
	"fmt"
	"slices"
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
	methodAnthropicOAuth   = "anthropic_oauth"
	methodAnthropicAPI     = "anthropic_api"
	methodOpenAIOAuth      = "openai_oauth"
	methodOpenAIAPI        = "openai_api"
	methodGoogleOAuth      = "google_oauth"
	methodGoogleAPI        = "google_api"
	methodMiniMaxAPI       = "minimax_api"
	methodDeepSeekAPI      = "deepseek_api"
	methodXAIAPI           = "xai_api"
	methodGrokOAuth        = "grok_oauth"
	methodMistralAPI       = "mistral_api"
	methodOpenRouterAPI    = "openrouter_api"
	methodNvidiaAPI        = "nvidia_api"
	methodCopilotOAuth     = "copilot_oauth"
	methodPerplexityOAuth  = "perplexity_oauth"
	methodOllamaLocal      = "ollama_local"
)

// Default Ollama wiring shown to OSS users. host.docker.internal works
// out of the box on macOS, Docker Desktop on Windows/WSL2, and on
// Linux thanks to the ``extra_hosts: [host.docker.internal:host-gateway]``
// entry on the litellm service in docker-compose.yml. WSL2 users who
// installed Ollama *inside* the WSL distro itself (rather than on the
// Windows host) need to override this with http://localhost:11434.
// The default model is the smallest/fastest one most laptops can
// actually run; users with a GPU will pick something like qwen3-coder:30b.
const (
	defaultOllamaAPIBase = "http://host.docker.internal:11434"
	defaultOllamaModel   = "llama3.2"
)

// methodOrder is the priority order surfaced in the wizard. The
// resulting DECEPTICON_AUTH_PRIORITY preserves this order, filtered
// to the methods the user actually selected. OAuth precedes the
// matching API on purpose: a subscription primary should fall back
// to the paid API only when the subscription quota is exhausted.
// Ollama sits last: cloud providers are usually preferred when both
// are configured, but a user wanting to lead with local-only inference
// can reorder the priority manually in .env.
var methodOrder = []string{
	methodAnthropicOAuth,
	methodAnthropicAPI,
	methodOpenAIOAuth,
	methodOpenAIAPI,
	methodGoogleOAuth,
	methodGoogleAPI,
	methodMiniMaxAPI,
	methodDeepSeekAPI,
	methodXAIAPI,
	methodGrokOAuth,
	methodMistralAPI,
	methodOpenRouterAPI,
	methodNvidiaAPI,
	methodCopilotOAuth,
	methodPerplexityOAuth,
	methodOllamaLocal,
}

func runOnboard(cmd *cobra.Command, args []string) error {
	if config.EnvExists() && !resetFlag {
		ui.Info(".env already configured at " + config.EnvPath())
		ui.DimText("Run 'decepticon onboard --reset' to reconfigure")
		return nil
	}

	var (
		methods                []string
		anthropicKey           string
		openaiKey              string
		geminiKey              string
		minimaxKey             string
		deepseekKey            string
		xaiKey                 string
		mistralKey             string
		openrouterKey          string
		nvidiaKey              string
		chatgptSessionToken    string
		geminiSessionCookies   string
		copilotRefreshToken    string
		grokSessionToken       string
		perplexitySessionToken string
		ollamaAPIBase          = defaultOllamaAPIBase
		ollamaModel            = defaultOllamaModel
		profile                string
		useLangSmith           bool
		langSmithKey           string
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
					huh.NewOption("ChatGPT OAuth     — ChatGPT Pro/Plus/Team subscription (auth/gpt-*)", methodOpenAIOAuth),
					huh.NewOption("OpenAI API Key    — sk-...", methodOpenAIAPI),
					huh.NewOption("Google API Key    — AIza... (Gemini)", methodGoogleAPI),
					huh.NewOption("MiniMax API Key   — eyJ...", methodMiniMaxAPI),
					huh.NewOption("DeepSeek API Key  — sk-...", methodDeepSeekAPI),
					huh.NewOption("xAI API Key       — xai-... (Grok)", methodXAIAPI),
					huh.NewOption("Mistral API Key   — (no fixed prefix)", methodMistralAPI),
					huh.NewOption("OpenRouter API Key — sk-or-...", methodOpenRouterAPI),
					huh.NewOption("Nvidia NIM API Key — nvapi-...", methodNvidiaAPI),
					huh.NewOption("Gemini Advanced     — Google One AI Premium subscription (gemini-sub/*)", methodGoogleOAuth),
					huh.NewOption("SuperGrok           — X Premium+ Grok subscription (grok-sub/*)", methodGrokOAuth),
					huh.NewOption("GitHub Copilot Pro  — Copilot subscription (copilot/*)", methodCopilotOAuth),
					huh.NewOption("Perplexity Pro      — Perplexity subscription (pplx-sub/*)", methodPerplexityOAuth),
					huh.NewOption("Local LLM (Ollama)  — any pulled model, no API key", methodOllamaLocal),
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

		// Step 2b: ChatGPT subscription session token
		// ChatGPT OAuth has no equivalent of `claude /login` to provision
		// tokens automatically, so we ask the user to paste the
		// `__Secure-next-auth.session-token` cookie from a signed-in
		// chatgpt.com browser session. Optional — users who set
		// CHATGPT_ACCESS_TOKEN externally or place ~/.config/chatgpt/tokens.json
		// can leave this blank and skip with Enter.
		huh.NewGroup(
			huh.NewNote().
				Title("ChatGPT Session Token").
				Description("Open chatgpt.com → DevTools → Application →\nCookies → chatgpt.com → copy the value of\n`__Secure-next-auth.session-token`. Or leave\nblank to use CHATGPT_ACCESS_TOKEN / tokens.json."),
			huh.NewInput().
				Title("CHATGPT_SESSION_TOKEN").
				Placeholder("eyJhbGciOiJ...   (leave blank to skip)").
				EchoMode(huh.EchoModePassword).
				Value(&chatgptSessionToken),
		).Title("2 / 4  ·  ChatGPT OAuth").
			WithHideFunc(func() bool { return !contains(methods, methodOpenAIOAuth) }),

		// Step 2c: OpenAI API key
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

		// Step 2d-i: DeepSeek API key
		huh.NewGroup(
			huh.NewInput().
				Title("DeepSeek API Key").
				Placeholder("sk-...").
				EchoMode(huh.EchoModePassword).
				Value(&deepseekKey).
				Validate(nonEmpty),
		).Title("2 / 4  ·  DeepSeek API").
			WithHideFunc(func() bool { return !contains(methods, methodDeepSeekAPI) }),

		// Step 2d-ii: xAI API key
		huh.NewGroup(
			huh.NewInput().
				Title("xAI API Key").
				Placeholder("xai-...").
				EchoMode(huh.EchoModePassword).
				Value(&xaiKey).
				Validate(nonEmpty),
		).Title("2 / 4  ·  xAI API (Grok)").
			WithHideFunc(func() bool { return !contains(methods, methodXAIAPI) }),

		// Step 2d-iii: Mistral API key
		huh.NewGroup(
			huh.NewInput().
				Title("Mistral API Key").
				Placeholder("paste your Mistral API key").
				EchoMode(huh.EchoModePassword).
				Value(&mistralKey).
				Validate(nonEmpty),
		).Title("2 / 4  ·  Mistral API").
			WithHideFunc(func() bool { return !contains(methods, methodMistralAPI) }),

		// Step 2e: OpenRouter API key
		huh.NewGroup(
			huh.NewInput().
				Title("OpenRouter API Key").
				Placeholder("sk-or-...").
				EchoMode(huh.EchoModePassword).
				Value(&openrouterKey).
				Validate(nonEmpty),
		).Title("2 / 4  ·  OpenRouter API").
			WithHideFunc(func() bool { return !contains(methods, methodOpenRouterAPI) }),

		// Step 2f: Nvidia NIM API key
		huh.NewGroup(
			huh.NewInput().
				Title("Nvidia NIM API Key").
				Placeholder("nvapi-...").
				EchoMode(huh.EchoModePassword).
				Value(&nvidiaKey).
				Validate(nonEmpty),
		).Title("2 / 4  ·  Nvidia NIM API").
			WithHideFunc(func() bool { return !contains(methods, methodNvidiaAPI) }),

		// Step 2-oauth-i: Gemini Advanced subscription
		// Multi-cookie value (NID + Secure-1PSID + Secure-1PSIDTS, etc.)
		// joined with semicolons. Optional — power users can drop a
		// tokens.json under ~/.config/gemini/ instead and skip with Enter.
		huh.NewGroup(
			huh.NewNote().
				Title("Gemini Advanced Subscription").
				Description("Open gemini.google.com → DevTools → Application →\nCookies → gemini.google.com. Copy the values of\nNID, __Secure-1PSID, __Secure-1PSIDTS as a single\nsemicolon-joined string. Or leave blank to use\nGEMINI_ACCESS_TOKEN / ~/.config/gemini/tokens.json."),
			huh.NewInput().
				Title("GEMINI_SESSION_COOKIES").
				Placeholder("NID=...; __Secure-1PSID=...   (leave blank to skip)").
				EchoMode(huh.EchoModePassword).
				Value(&geminiSessionCookies),
		).Title("2 / 4  ·  Gemini Advanced").
			WithHideFunc(func() bool { return !contains(methods, methodGoogleOAuth) }),

		// Step 2-oauth-ii: SuperGrok subscription
		huh.NewGroup(
			huh.NewNote().
				Title("SuperGrok Subscription").
				Description("Open grok.com → DevTools → Application →\nCookies → grok.com → copy the value of\n`auth_token`. Or leave blank to use\nGROK_ACCESS_TOKEN / ~/.config/grok/tokens.json."),
			huh.NewInput().
				Title("GROK_SESSION_TOKEN").
				Placeholder("paste auth_token cookie value (leave blank to skip)").
				EchoMode(huh.EchoModePassword).
				Value(&grokSessionToken),
		).Title("2 / 4  ·  SuperGrok").
			WithHideFunc(func() bool { return !contains(methods, methodGrokOAuth) }),

		// Step 2-oauth-iii: GitHub Copilot Pro subscription
		// Refresh token rotation, not a single session cookie. Devs can
		// extract one from VSCode's Copilot extension config or follow
		// gh-copilot-cli onboarding. Optional via tokens.json fallback.
		huh.NewGroup(
			huh.NewNote().
				Title("GitHub Copilot Pro Subscription").
				Description("Provide a Copilot refresh token (long-lived, used\nto rotate access tokens). Or leave blank to use\nCOPILOT_ACCESS_TOKEN / ~/.config/copilot/tokens.json."),
			huh.NewInput().
				Title("COPILOT_REFRESH_TOKEN").
				Placeholder("ghu_... or ghr_... (leave blank to skip)").
				EchoMode(huh.EchoModePassword).
				Value(&copilotRefreshToken),
		).Title("2 / 4  ·  Copilot Pro").
			WithHideFunc(func() bool { return !contains(methods, methodCopilotOAuth) }),

		// Step 2-oauth-iv: Perplexity Pro subscription
		huh.NewGroup(
			huh.NewNote().
				Title("Perplexity Pro Subscription").
				Description("Open perplexity.ai → DevTools → Application →\nCookies → perplexity.ai → copy the value of\n`next-auth.session-token`. Or leave blank to use\nPERPLEXITY_ACCESS_TOKEN / ~/.config/perplexity/tokens.json."),
			huh.NewInput().
				Title("PERPLEXITY_SESSION_TOKEN").
				Placeholder("paste next-auth.session-token (leave blank to skip)").
				EchoMode(huh.EchoModePassword).
				Value(&perplexitySessionToken),
		).Title("2 / 4  ·  Perplexity Pro").
			WithHideFunc(func() bool { return !contains(methods, methodPerplexityOAuth) }),

		// Step 2g: Local Ollama
		// No API key — the user provides only the endpoint and the model
		// tag they pulled (``ollama pull qwen3-coder:30b``). The proxy
		// dynamically registers ``ollama_chat/<model>`` at startup via
		// litellm_dynamic_config.py — no yaml editing needed. The
		// ``ollama_chat/`` provider routes to /api/chat which is the
		// only Ollama endpoint that supports tool/function calling, and
		// every Decepticon agent uses tools.
		huh.NewGroup(
			huh.NewNote().
				Title("Local Ollama").
				Description("Ollama must already be running on your host\n(`ollama serve`) with the model pulled\n(`ollama pull <name>`).\n\nLeave the URL as-is on macOS / Linux Docker /\nDocker Desktop on Windows or WSL2 with Ollama\nrunning on the Windows host.\n\nIf Ollama runs INSIDE your WSL distro instead,\nchange it to http://localhost:11434.\n\nFor remote / custom setups use the full URL."),
			huh.NewInput().
				Title("OLLAMA_API_BASE").
				Placeholder(defaultOllamaAPIBase).
				Value(&ollamaAPIBase).
				Validate(nonEmpty),
			huh.NewInput().
				Title("OLLAMA_MODEL").
				Description("Any tag you pulled. Examples: qwen3-coder:30b,\nllama3.2, deepseek-r1:14b, mistral-small3.").
				Placeholder(defaultOllamaModel).
				Value(&ollamaModel).
				Validate(nonEmpty),
		).Title("2 / 4  ·  Local LLM (Ollama)").
			WithHideFunc(func() bool { return !contains(methods, methodOllamaLocal) }),

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
		"DECEPTICON_AUTH_CHATGPT":     boolStr(contains(methods, methodOpenAIOAuth)),
		"DECEPTICON_AUTH_GEMINI":      boolStr(contains(methods, methodGoogleOAuth)),
		"DECEPTICON_AUTH_GROK":        boolStr(contains(methods, methodGrokOAuth)),
		"DECEPTICON_AUTH_COPILOT":     boolStr(contains(methods, methodCopilotOAuth)),
		"DECEPTICON_AUTH_PERPLEXITY":  boolStr(contains(methods, methodPerplexityOAuth)),
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
	if deepseekKey != "" {
		values["DEEPSEEK_API_KEY"] = deepseekKey
	}
	if xaiKey != "" {
		values["XAI_API_KEY"] = xaiKey
	}
	if mistralKey != "" {
		values["MISTRAL_API_KEY"] = mistralKey
	}
	if openrouterKey != "" {
		values["OPENROUTER_API_KEY"] = openrouterKey
	}
	if nvidiaKey != "" {
		values["NVIDIA_API_KEY"] = nvidiaKey
	}
	if chatgptSessionToken != "" {
		values["CHATGPT_SESSION_TOKEN"] = chatgptSessionToken
	}
	if geminiSessionCookies != "" {
		values["GEMINI_SESSION_COOKIES"] = geminiSessionCookies
	}
	if grokSessionToken != "" {
		values["GROK_SESSION_TOKEN"] = grokSessionToken
	}
	if copilotRefreshToken != "" {
		values["COPILOT_REFRESH_TOKEN"] = copilotRefreshToken
	}
	if perplexitySessionToken != "" {
		values["PERPLEXITY_SESSION_TOKEN"] = perplexitySessionToken
	}
	if contains(methods, methodOllamaLocal) {
		values["OLLAMA_API_BASE"] = strings.TrimSpace(ollamaAPIBase)
		values["OLLAMA_MODEL"] = strings.TrimSpace(ollamaModel)
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
	return slices.Contains(haystack, needle)
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
