package config

import (
	"bufio"
	_ "embed"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

//go:embed env.example
var EnvTemplate string

const (
	DefaultHome       = ".decepticon"
	EnvFileName       = ".env"
	EnvExampleName    = ".env.example"
	PlaceholderSuffix = "-key-here"
)

// Config holds the Decepticon launcher configuration.
type Config struct {
	Home string
	Env  map[string]string
}

// DecepticonHome returns the resolved DECEPTICON_HOME path.
func DecepticonHome() string {
	if h := os.Getenv("DECEPTICON_HOME"); h != "" {
		return h
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return filepath.Join("~", DefaultHome)
	}
	return filepath.Join(home, DefaultHome)
}

// EnvPath returns the full path to the .env file.
func EnvPath() string {
	return filepath.Join(DecepticonHome(), EnvFileName)
}

// EnvExists checks whether .env exists.
func EnvExists() bool {
	_, err := os.Stat(EnvPath())
	return err == nil
}

// LoadEnv reads a .env file and returns key-value pairs.
// It handles comments (#), empty lines, and optional quoting.
func LoadEnv(path string) (map[string]string, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("open env file: %w", err)
	}
	defer f.Close()

	env := make(map[string]string)
	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		key, val, ok := parseEnvLine(line)
		if !ok {
			continue
		}
		env[key] = val
	}
	if err := scanner.Err(); err != nil {
		return nil, fmt.Errorf("read env file: %w", err)
	}
	return env, nil
}

// parseEnvLine splits "KEY=VALUE" handling optional quotes.
func parseEnvLine(line string) (key, val string, ok bool) {
	idx := strings.IndexByte(line, '=')
	if idx < 1 {
		return "", "", false
	}
	key = strings.TrimSpace(line[:idx])
	val = strings.TrimSpace(line[idx+1:])
	// Strip surrounding quotes
	if len(val) >= 2 {
		if (val[0] == '"' && val[len(val)-1] == '"') ||
			(val[0] == '\'' && val[len(val)-1] == '\'') {
			val = val[1 : len(val)-1]
		}
	}
	return key, val, true
}

// WriteEnvFromEmbed writes key-value pairs into a .env file using the embedded template.
func WriteEnvFromEmbed(outputPath string, values map[string]string) error {
	return writeEnvFromString(EnvTemplate, outputPath, values)
}

// WriteEnv writes key-value pairs into a .env file using a template file.
func WriteEnv(templatePath, outputPath string, values map[string]string) error {
	tmpl, err := os.ReadFile(templatePath)
	if err != nil {
		return fmt.Errorf("read template: %w", err)
	}
	return writeEnvFromString(string(tmpl), outputPath, values)
}

func writeEnvFromString(tmpl string, outputPath string, values map[string]string) error {
	lines := strings.Split(tmpl, "\n")
	var out []string
	for _, line := range lines {
		trimmed := strings.TrimSpace(line)
		// Skip commented lines — keep as-is
		if trimmed == "" || strings.HasPrefix(trimmed, "#") {
			out = append(out, line)
			continue
		}
		key, _, ok := parseEnvLine(trimmed)
		if !ok {
			out = append(out, line)
			continue
		}
		if newVal, exists := values[key]; exists {
			out = append(out, key+"="+newVal)
		} else {
			out = append(out, line)
		}
	}

	if err := os.MkdirAll(filepath.Dir(outputPath), 0o755); err != nil {
		return fmt.Errorf("create directory: %w", err)
	}
	return os.WriteFile(outputPath, []byte(strings.Join(out, "\n")), 0o600)
}

// APIKeyNames lists the API key environment variable names to check.
// Order matters: a valid key in this list satisfies the "at least one
// credential" startup gate. Keep in sync with keyFormatRules below and
// with decepticon/llm/factory.py::_API_METHOD_ENV.
var APIKeyNames = []string{
	"ANTHROPIC_API_KEY",
	"OPENAI_API_KEY",
	"GEMINI_API_KEY",
	"MINIMAX_API_KEY",
	"OPENROUTER_API_KEY",
	"NVIDIA_API_KEY",
	"DEEPSEEK_API_KEY",
	"XAI_API_KEY",
	"MISTRAL_API_KEY",
}

// IsPlaceholder checks if a value looks like a placeholder.
func IsPlaceholder(val string) bool {
	return strings.HasSuffix(val, PlaceholderSuffix) || val == ""
}

// keyFormatRules maps an API key env var to its expected prefix and human-readable hint.
// Format checks are intentionally lenient — providers occasionally evolve key shapes
// (OpenAI shipped sk-proj-* in 2024, Anthropic sk-ant-api03-* etc.). The check only
// rejects values that are obviously malformed (typos, missing prefix).
//
// An empty Prefix means "no fixed shape, skip the prefix check" (only the
// length floor still applies). MiniMax/Mistral keys ship without a
// universal prefix and would otherwise be rejected when the user pastes
// the right key.
var keyFormatRules = map[string]struct {
	Prefix string
	Hint   string
}{
	"ANTHROPIC_API_KEY":  {Prefix: "sk-", Hint: "Anthropic keys start with 'sk-'"},
	"OPENAI_API_KEY":     {Prefix: "sk-", Hint: "OpenAI keys start with 'sk-'"},
	"GEMINI_API_KEY":     {Prefix: "AIza", Hint: "Gemini keys start with 'AIza'"},
	"OPENROUTER_API_KEY": {Prefix: "sk-or-", Hint: "OpenRouter keys start with 'sk-or-'"},
	"NVIDIA_API_KEY":     {Prefix: "nvapi-", Hint: "NVIDIA keys start with 'nvapi-'"},
	"DEEPSEEK_API_KEY":   {Prefix: "sk-", Hint: "DeepSeek keys start with 'sk-'"},
	"XAI_API_KEY":        {Prefix: "xai-", Hint: "xAI keys start with 'xai-'"},
	"MINIMAX_API_KEY":    {Prefix: "", Hint: ""},
	"MISTRAL_API_KEY":    {Prefix: "", Hint: ""},
}

// validateKeyFormat returns an empty string if the key looks valid, or a reason if not.
func validateKeyFormat(name, val string) string {
	if len(val) < 20 {
		return "value is too short to be a valid API key"
	}
	if rule, ok := keyFormatRules[name]; ok {
		// Empty Prefix → provider has no fixed prefix, length floor is the
		// only signal. Skip the prefix check rather than rejecting valid keys.
		if rule.Prefix != "" && !strings.HasPrefix(val, rule.Prefix) {
			return rule.Hint
		}
	}
	return ""
}

// ValidateAPIKeys checks that at least one API key is set with a valid format.
// Returns a fatal error listing both unset keys and any format problems found.
func ValidateAPIKeys(env map[string]string) error {
	var validNames []string
	invalidReasons := make(map[string]string)

	for _, name := range APIKeyNames {
		val := env[name]
		if val == "" || IsPlaceholder(val) {
			continue
		}
		if reason := validateKeyFormat(name, val); reason != "" {
			invalidReasons[name] = reason
			continue
		}
		validNames = append(validNames, name)
	}

	if len(validNames) > 0 {
		return nil
	}

	var msg strings.Builder
	msg.WriteString("no valid API key found.")
	if len(invalidReasons) > 0 {
		msg.WriteString(" Detected malformed key(s):")
		for name, reason := range invalidReasons {
			msg.WriteString(fmt.Sprintf("\n  %s: %s", name, reason))
		}
	}
	msg.WriteString("\nRun 'decepticon onboard --reset' to reconfigure credentials.")
	return fmt.Errorf("%s", msg.String())
}

// subscriptionMethod groups the env signal + credential layout for one
// OAuth subscription handler so we don't repeat the validation logic.
// Resolution order matches each handler in config/*_handler.py exactly:
//
//	1. <PROVIDER>_ACCESS_TOKEN   — pre-extracted Bearer
//	2. <PROVIDER>_SESSION_TOKEN  — browser session cookie value
//	3. ~/.config/<dir>/tokens.json on disk
//
// Two providers diverge slightly:
//   - Gemini Advanced ships a multi-cookie value (GEMINI_SESSION_COOKIES)
//     instead of a single session token. accept either env name.
//   - Copilot Pro uses a refresh-token rotation (COPILOT_REFRESH_TOKEN)
//     instead of a session cookie. Same fall-through, different env name.
type subscriptionMethod struct {
	Toggle    string   // DECEPTICON_AUTH_<X> boolean enabling this path
	TokenEnvs []string // env vars that satisfy the path on their own
	ConfigDir string   // ~/.config/<dir>/tokens.json fallback
	Label     string   // human name for error messages
}

var oauthSubscriptions = map[string]subscriptionMethod{
	"chatgpt": {
		Toggle:    "DECEPTICON_AUTH_CHATGPT",
		TokenEnvs: []string{"CHATGPT_ACCESS_TOKEN", "CHATGPT_SESSION_TOKEN"},
		ConfigDir: "chatgpt",
		Label:     "ChatGPT",
	},
	"gemini": {
		Toggle:    "DECEPTICON_AUTH_GEMINI",
		TokenEnvs: []string{"GEMINI_ACCESS_TOKEN", "GEMINI_SESSION_COOKIES"},
		ConfigDir: "gemini",
		Label:     "Gemini Advanced",
	},
	"copilot": {
		Toggle:    "DECEPTICON_AUTH_COPILOT",
		TokenEnvs: []string{"COPILOT_ACCESS_TOKEN", "COPILOT_REFRESH_TOKEN"},
		ConfigDir: "copilot",
		Label:     "Copilot Pro",
	},
	"grok": {
		Toggle:    "DECEPTICON_AUTH_GROK",
		TokenEnvs: []string{"GROK_ACCESS_TOKEN", "GROK_SESSION_TOKEN"},
		ConfigDir: "grok",
		Label:     "SuperGrok",
	},
	"perplexity": {
		Toggle:    "DECEPTICON_AUTH_PERPLEXITY",
		TokenEnvs: []string{"PERPLEXITY_ACCESS_TOKEN", "PERPLEXITY_SESSION_TOKEN"},
		ConfigDir: "perplexity",
		Label:     "Perplexity Pro",
	},
}

// ValidateAuth ensures at least one valid AuthMethod is configured.
//
// OAuth paths:
//   - DECEPTICON_AUTH_CLAUDE_CODE=true requires a parseable
//     ~/.claude/.credentials.json. LiteLLM mounts that file read-only.
//   - DECEPTICON_AUTH_<X>=true (CHATGPT, GEMINI, COPILOT, GROK,
//     PERPLEXITY) is satisfied by a token env var or a tokens.json
//     file under ~/.config/<x>/. See subscriptionMethod above.
//
// Local LLM path: ollama_local in DECEPTICON_AUTH_PRIORITY (or any
// OLLAMA_API_BASE configured) is treated as a valid credential. Ollama
// reachability is probed separately at startup (start.go).
//
// API path: at least one configured provider key (ANTHROPIC / OPENAI /
// GEMINI / MINIMAX / OPENROUTER / NVIDIA / DEEPSEEK / XAI / MISTRAL)
// must be non-placeholder and well-formed.
//
// At least one path must succeed. When OAuth is requested and its
// credentials are broken, the other paths are checked as fallbacks;
// if all fail, the OAuth error is surfaced first because that was the
// user's explicit choice.
func ValidateAuth(env map[string]string) error {
	claudeOAuth := isTruthy(Get(env, "DECEPTICON_AUTH_CLAUDE_CODE", ""))
	ollamaErr := validateOllamaCredentials(env)
	apiErr := ValidateAPIKeys(env)

	if claudeOAuth {
		if err := validateClaudeCredentials(); err == nil {
			return nil
		}
	}
	for _, sub := range oauthSubscriptions {
		if !isTruthy(Get(env, sub.Toggle, "")) {
			continue
		}
		if err := validateSubscriptionCredentials(env, sub); err == nil {
			return nil
		}
	}
	if ollamaErr == nil {
		return nil
	}
	if apiErr == nil {
		return nil
	}

	// All paths failed — surface the user's explicit choice first.
	if claudeOAuth {
		return validateClaudeCredentials()
	}
	for _, key := range []string{"chatgpt", "gemini", "copilot", "grok", "perplexity"} {
		sub := oauthSubscriptions[key]
		if isTruthy(Get(env, sub.Toggle, "")) {
			return validateSubscriptionCredentials(env, sub)
		}
	}
	if hasOllamaSelected(env) {
		return ollamaErr
	}
	return apiErr
}

// hasOllamaSelected returns true when the user has explicitly opted into
// the local-Ollama auth method (via the priority list or by setting
// OLLAMA_API_BASE without any other API key).
func hasOllamaSelected(env map[string]string) bool {
	priority := strings.ToLower(strings.TrimSpace(env["DECEPTICON_AUTH_PRIORITY"]))
	for _, m := range strings.Split(priority, ",") {
		if strings.TrimSpace(m) == "ollama_local" {
			return true
		}
	}
	return env["OLLAMA_API_BASE"] != ""
}

// validateOllamaCredentials accepts the Ollama path when the user has
// either listed ``ollama_local`` in DECEPTICON_AUTH_PRIORITY or set
// ``OLLAMA_API_BASE`` directly. Ollama itself has no API key — the
// only required signal is the base URL pointing at a running instance.
//
// We don't probe the URL here; the launcher runs on the host while the
// LiteLLM container talks to the URL from inside Docker, so a host-side
// reachability check would lie when the user (correctly) wired up
// host.docker.internal-style addressing.
func validateOllamaCredentials(env map[string]string) error {
	if !hasOllamaSelected(env) {
		return fmt.Errorf("ollama not configured")
	}
	base := strings.TrimSpace(env["OLLAMA_API_BASE"])
	if base == "" {
		return fmt.Errorf(
			"ollama_local selected but OLLAMA_API_BASE is empty.\n" +
				"Set OLLAMA_API_BASE=http://host.docker.internal:11434 (or your Ollama URL) " +
				"in ~/.decepticon/.env, or run 'decepticon onboard --reset' to reconfigure.",
		)
	}
	return nil
}

func isTruthy(s string) bool {
	switch strings.ToLower(strings.TrimSpace(s)) {
	case "true", "1", "yes", "on":
		return true
	}
	return false
}

// validateClaudeCredentials verifies ~/.claude/.credentials.json exists, is a regular
// file, parses as JSON, and carries an access token in one of the shapes the LiteLLM
// claude_code_handler accepts (claudeAiOauth.accessToken, top-level accessToken, or
// legacy oauthToken). Compose mounts this path into the LiteLLM container; if it's
// missing or empty, authentication fails opaquely on the first prompt instead of here.
func validateClaudeCredentials() error {
	home, err := os.UserHomeDir()
	if err != nil {
		return fmt.Errorf("locate home directory: %w", err)
	}
	path := filepath.Join(home, ".claude", ".credentials.json")
	info, err := os.Stat(path)
	if os.IsNotExist(err) {
		return fmt.Errorf("Claude Code credentials not found at %s\nRun 'claude /login' (Claude Code CLI) to authenticate, then retry.", path)
	}
	if err != nil {
		return fmt.Errorf("stat %s: %w", path, err)
	}
	if info.IsDir() {
		return fmt.Errorf("expected credentials file at %s but found a directory.\nRemove it and run 'claude /login' to re-authenticate.", path)
	}

	raw, err := os.ReadFile(path)
	if err != nil {
		return fmt.Errorf("read %s: %w\nCheck file permissions and re-run.", path, err)
	}
	var creds map[string]any
	if err := json.Unmarshal(raw, &creds); err != nil {
		return fmt.Errorf("credentials file at %s is not valid JSON: %w\nRun 'claude /login' to re-authenticate.", path, err)
	}
	if extractClaudeAccessToken(creds) == "" {
		return fmt.Errorf("no access token found in %s\nRun 'claude /login' to re-authenticate.", path)
	}
	return nil
}

// validateSubscriptionCredentials verifies the user has at least one credential
// path wired up for an OAuth subscription handler. The handlers themselves
// (config/<provider>_handler.py) walk the same resolution order at runtime:
//
//  1. <PROVIDER>_ACCESS_TOKEN env (pre-extracted Bearer)
//  2. <PROVIDER>_SESSION_TOKEN / _SESSION_COOKIES / _REFRESH_TOKEN env
//  3. ~/.config/<dir>/tokens.json on disk
//
// We don't validate token shape — providers ship them in many formats and shapes
// drift across versions. We only catch the "toggled on in onboard but never
// pasted a token" case before the first agent prompt fails opaquely.
func validateSubscriptionCredentials(env map[string]string, sub subscriptionMethod) error {
	for _, name := range sub.TokenEnvs {
		if strings.TrimSpace(env[name]) != "" {
			return nil
		}
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return fmt.Errorf("locate home directory: %w", err)
	}
	path := filepath.Join(home, ".config", sub.ConfigDir, "tokens.json")
	if _, err := os.Stat(path); err == nil {
		return nil
	}
	hints := strings.Join(sub.TokenEnvs, " or ")
	return fmt.Errorf(
		"%s subscription token not configured.\n"+
			"Provide one of:\n"+
			"  - %s env var\n"+
			"  - %s on disk\n"+
			"Run 'decepticon onboard --reset' to (re)configure interactively.",
		sub.Label, hints, path,
	)
}

// extractClaudeAccessToken walks the credentials JSON in the same resolution order as
// the LiteLLM handler (config/claude_code_handler.py): current nested format first,
// then legacy top-level keys. Returns "" if no usable token is present.
func extractClaudeAccessToken(creds map[string]any) string {
	if oauth, ok := creds["claudeAiOauth"].(map[string]any); ok {
		if tok, _ := oauth["accessToken"].(string); tok != "" {
			return tok
		}
	}
	if tok, _ := creds["accessToken"].(string); tok != "" {
		return tok
	}
	if tok, _ := creds["oauthToken"].(string); tok != "" {
		return tok
	}
	return ""
}

// AppendEnvLine appends a KEY=VALUE line to an existing .env file.
func AppendEnvLine(path, key, value string) error {
	f, err := os.OpenFile(path, os.O_APPEND|os.O_WRONLY, 0o600)
	if err != nil {
		return err
	}
	defer f.Close()
	_, err = fmt.Fprintf(f, "\n%s=%s\n", key, value)
	return err
}

// Get returns a config value with a fallback default.
func Get(env map[string]string, key, fallback string) string {
	if val, ok := env[key]; ok && val != "" {
		return val
	}
	return fallback
}
