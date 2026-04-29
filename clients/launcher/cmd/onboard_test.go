package cmd

import "testing"

func TestNormalizeModelID(t *testing.T) {
	tests := []struct {
		provider string
		model    string
		want     string
	}{
		{"openai", "gpt-4.1", "openai/gpt-4.1"},
		{"google", "gemini-2.5-flash", "gemini/gemini-2.5-flash"},
		{"custom-openai", "qwen3-coder", "custom/qwen3-coder"},
		{"groq", "groq/llama-3.3-70b-versatile", "groq/llama-3.3-70b-versatile"},
		{"together", "meta-llama/Llama-3.3-70B-Instruct-Turbo", "together/meta-llama/Llama-3.3-70B-Instruct-Turbo"},
		{"fireworks", "accounts/fireworks/models/llama-v3p1-405b-instruct", "fireworks_ai/accounts/fireworks/models/llama-v3p1-405b-instruct"},
		{"openrouter", "anthropic/claude-3.7-sonnet", "openrouter/anthropic/claude-3.7-sonnet"},
		{"ollama", "", ""},
	}

	for _, tt := range tests {
		t.Run(tt.provider+"/"+tt.model, func(t *testing.T) {
			if got := normalizeModelID(tt.provider, tt.model); got != tt.want {
				t.Fatalf("normalizeModelID(%q, %q) = %q, want %q", tt.provider, tt.model, got, tt.want)
			}
		})
	}
}

func TestProviderCredentialEnv(t *testing.T) {
	tests := map[string]string{
		"anthropic":     "ANTHROPIC_API_KEY",
		"openrouter":    "OPENROUTER_API_KEY",
		"custom-openai": "CUSTOM_OPENAI_API_KEY",
		"ollama":        "",
	}

	for provider, want := range tests {
		if got := providerCredentialEnv(provider); got != want {
			t.Fatalf("providerCredentialEnv(%q) = %q, want %q", provider, got, want)
		}
	}
}
