package health

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strconv"
	"time"

	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/config"
	"github.com/PurpleAILAB/Decepticon/clients/launcher/internal/ui"
)

const (
	DefaultLangGraphPort = "2024"
	DefaultLiteLLMPort   = "4000"
	DefaultNeo4jHTTPPort = "7474"
	DefaultWebPort       = "3000"
)

// Timeouts are var (not const) so tests can shrink them.
var (
	// LangGraph healthcheck (compose) only verifies /ok responds. The graph may
	// still be compiling — this functional probe waits for the decepticon
	// assistant to appear in /assistants/search.
	LangGraphTimeout = 60 * time.Second

	// Reserved for ad-hoc diagnostics commands.
	LiteLLMTimeout = 90 * time.Second
	Neo4jTimeout   = 90 * time.Second
	WebTimeout     = 60 * time.Second

	PollInterval = 2 * time.Second
)

// CheckLangGraph polls /assistants/search until the response references the
// decepticon assistant. Compose's healthcheck only verifies that /ok serves;
// graph compilation can still be in progress, so this functional probe is the
// only signal that the agent is actually callable.
//
// DECEPTICON_STARTUP_TIMEOUT_SECONDS overrides LangGraphTimeout for slow
// environments where graph compile is the long pole.
func CheckLangGraph(env map[string]string) error {
	port := config.Get(env, "LANGGRAPH_PORT", DefaultLangGraphPort)
	url := fmt.Sprintf("http://localhost:%s/assistants/search", port)

	body, _ := json.Marshal(map[string]any{
		"graph_id": "decepticon",
		"limit":    1,
	})

	timeout := LangGraphTimeout
	if v := os.Getenv("DECEPTICON_STARTUP_TIMEOUT_SECONDS"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			timeout = time.Duration(n) * time.Second
		}
	}
	deadline := time.Now().Add(timeout)
	client := &http.Client{Timeout: 5 * time.Second}

	for time.Now().Before(deadline) {
		resp, err := client.Post(url, "application/json", bytes.NewReader(body))
		if err == nil {
			if resp.StatusCode == http.StatusOK {
				respBody, _ := io.ReadAll(resp.Body)
				resp.Body.Close()
				if bytes.Contains(respBody, []byte(`"decepticon"`)) {
					return nil
				}
			} else {
				resp.Body.Close()
			}
		}
		time.Sleep(PollInterval)
	}

	return fmt.Errorf("LangGraph assistant not loaded after %s (port %s)", timeout, port)
}

// CheckLiteLLM polls the LiteLLM health endpoint. Kept for diagnostics.
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

// CheckNeo4j polls the Neo4j HTTP endpoint. Kept for diagnostics.
func CheckNeo4j(env map[string]string) error {
	port := config.Get(env, "NEO4J_HTTP_PORT", DefaultNeo4jHTTPPort)
	url := fmt.Sprintf("http://localhost:%s", port)

	deadline := time.Now().Add(Neo4jTimeout)
	client := &http.Client{Timeout: 5 * time.Second}

	for time.Now().Before(deadline) {
		resp, err := client.Get(url)
		if err == nil {
			resp.Body.Close()
			if resp.StatusCode >= 200 && resp.StatusCode < 500 {
				return nil
			}
		}
		time.Sleep(PollInterval)
	}

	return fmt.Errorf("Neo4j not ready after %s (port %s)", Neo4jTimeout, port)
}

// CheckWeb polls the web dashboard. Kept for diagnostics.
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

// WaitForServices verifies the agent stack is functionally ready.
//
// Infrastructure readiness (postgres, neo4j, litellm, langgraph http server,
// web) is delegated to Docker Compose healthchecks via `compose up --wait`,
// so by the time this runs every container is already healthy. The remaining
// gap is graph-compile readiness inside LangGraph: /ok answers before the
// decepticon graph finishes compiling, so we probe /assistants/search until
// the assistant is registered.
func WaitForServices(env map[string]string) error {
	ui.Info("Verifying agent stack...")
	if err := CheckLangGraph(env); err != nil {
		ui.Error(err.Error())
		return err
	}
	ui.Success("Agent stack ready")
	return nil
}
