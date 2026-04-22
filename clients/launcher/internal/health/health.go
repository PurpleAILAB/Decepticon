package health

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"time"

	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/config"
	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/ui"
)

const (
	DefaultLangGraphPort = "2024"
	DefaultLiteLLMPort   = "4000"
	DefaultWebPort       = "3000"

	LangGraphTimeout = 90 * time.Second
	LiteLLMTimeout   = 60 * time.Second
	WebTimeout       = 60 * time.Second
	PollInterval     = 2 * time.Second
)

// CheckLangGraph polls the LangGraph API until the decepticon assistant is loaded.
func CheckLangGraph(env map[string]string) error {
	port := config.Get(env, "LANGGRAPH_PORT", DefaultLangGraphPort)
	url := fmt.Sprintf("http://localhost:%s/assistants/search", port)

	body, _ := json.Marshal(map[string]any{
		"graph_id": "decepticon",
		"limit":    1,
	})

	deadline := time.Now().Add(LangGraphTimeout)
	client := &http.Client{Timeout: 5 * time.Second}

	for time.Now().Before(deadline) {
		resp, err := client.Post(url, "application/json", bytes.NewReader(body))
		if err == nil {
			resp.Body.Close()
			if resp.StatusCode == http.StatusOK {
				return nil
			}
		}
		time.Sleep(PollInterval)
	}

	return fmt.Errorf("LangGraph server not ready after %s (port %s)", LangGraphTimeout, port)
}

// CheckLiteLLM polls the LiteLLM health endpoint.
func CheckLiteLLM(env map[string]string) error {
	port := config.Get(env, "LITELLM_PORT", DefaultLiteLLMPort)
	url := fmt.Sprintf("http://localhost:%s/health/readiness", port)

	deadline := time.Now().Add(LiteLLMTimeout)
	client := &http.Client{Timeout: 5 * time.Second}

	for time.Now().Before(deadline) {
		resp, err := client.Get(url)
		if err == nil {
			resp.Body.Close()
			if resp.StatusCode == http.StatusOK {
				return nil
			}
		}
		time.Sleep(PollInterval)
	}

	return fmt.Errorf("LiteLLM proxy not ready after %s (port %s)", LiteLLMTimeout, port)
}

// CheckWeb polls the web dashboard.
func CheckWeb(env map[string]string) error {
	port := config.Get(env, "WEB_PORT", DefaultWebPort)
	url := fmt.Sprintf("http://localhost:%s", port)

	deadline := time.Now().Add(WebTimeout)
	client := &http.Client{Timeout: 5 * time.Second}

	for time.Now().Before(deadline) {
		resp, err := client.Get(url)
		if err == nil {
			resp.Body.Close()
			if resp.StatusCode == http.StatusOK {
				return nil
			}
		}
		time.Sleep(PollInterval)
	}

	return fmt.Errorf("web dashboard not ready after %s (port %s)", WebTimeout, port)
}

// WaitForServices runs all health checks with status output.
func WaitForServices(env map[string]string) error {
	ui.Info("Waiting for LangGraph server...")
	if err := CheckLangGraph(env); err != nil {
		ui.Error(err.Error())
		return err
	}
	ui.Success("LangGraph server ready")

	ui.Info("Waiting for LiteLLM proxy...")
	if err := CheckLiteLLM(env); err != nil {
		ui.Warning(err.Error() + " (first LLM call may fail)")
		// Non-fatal: continue
	} else {
		ui.Success("LiteLLM proxy ready")
	}

	ui.Info("Waiting for web dashboard...")
	if err := CheckWeb(env); err != nil {
		ui.Warning(err.Error())
		// Non-fatal
	} else {
		port := config.Get(env, "WEB_PORT", DefaultWebPort)
		ui.Success(fmt.Sprintf("Web dashboard ready at http://localhost:%s", port))
	}

	return nil
}
