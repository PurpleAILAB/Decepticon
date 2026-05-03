package cmd

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"reflect"
	"sort"
	"strings"
	"testing"
	"time"
)

// withOllamaProbeClient swaps ollamaProbeClient for one test.
func withOllamaProbeClient(t *testing.T, c *http.Client) {
	t.Helper()
	prev := ollamaProbeClient
	ollamaProbeClient = c
	t.Cleanup(func() { ollamaProbeClient = prev })
}

// ollamaTestServer fakes /api/tags and /api/show. A nil capabilities
// entry simulates older Ollama (no capabilities field); a missing
// entry causes /api/show to 404.
func ollamaTestServer(t *testing.T, capabilities map[string][]string) *httptest.Server {
	t.Helper()
	mux := http.NewServeMux()
	mux.HandleFunc("/api/tags", func(w http.ResponseWriter, _ *http.Request) {
		models := make([]map[string]string, 0, len(capabilities))
		for name := range capabilities {
			models = append(models, map[string]string{"name": name})
		}
		_ = json.NewEncoder(w).Encode(map[string]any{"models": models})
	})
	mux.HandleFunc("/api/show", func(w http.ResponseWriter, r *http.Request) {
		body, err := io.ReadAll(r.Body)
		if err != nil {
			http.Error(w, "read body", http.StatusBadRequest)
			return
		}
		var req struct {
			Name string `json:"name"`
		}
		if err := json.Unmarshal(body, &req); err != nil {
			http.Error(w, "decode body", http.StatusBadRequest)
			return
		}
		caps, ok := capabilities[req.Name]
		if !ok {
			http.Error(w, "model not found", http.StatusNotFound)
			return
		}
		if caps == nil {
			// Older Ollama: omit capabilities field entirely.
			_ = json.NewEncoder(w).Encode(map[string]any{})
			return
		}
		_ = json.NewEncoder(w).Encode(map[string]any{"capabilities": caps})
	})
	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)
	return srv
}

func sortedCopy(s []string) []string {
	out := append([]string(nil), s...)
	sort.Strings(out)
	return out
}

func TestProbeOllamaForOnboard_FiltersToToolSupporters(t *testing.T) {
	withProbeStubs(t, false, "")
	srv := ollamaTestServer(t, map[string][]string{
		"qwen3-coder:30b": {"completion", "tools"},
		"llama3.2":        {"completion", "tools"},
		"gemma:2b":        {"completion"},
	})
	withOllamaProbeClient(t, &http.Client{Timeout: 2 * time.Second})

	got := probeOllamaForOnboard(srv.URL)
	if !got.Reachable {
		t.Fatalf("expected Reachable=true when /api/tags answers")
	}

	// Tags response order isn't guaranteed (map iteration), so compare
	// as a sorted slice rather than relying on order.
	if !reflect.DeepEqual(sortedCopy(got.ToolCapableModels), []string{"llama3.2", "qwen3-coder:30b"}) {
		t.Errorf("expected only tool-capable models, got %v", got.ToolCapableModels)
	}
	for _, m := range got.ToolCapableModels {
		if m == "gemma:2b" {
			t.Errorf("gemma:2b lacks tools capability and must not be returned")
		}
	}
}

func TestProbeOllamaForOnboard_EmptyTagsIsReachableButNoModels(t *testing.T) {
	// Ollama up but no models pulled: Reachable=true with empty
	// ToolCapableModels, distinct from the unreachable case.
	withProbeStubs(t, false, "")
	srv := ollamaTestServer(t, map[string][]string{})
	withOllamaProbeClient(t, &http.Client{Timeout: 2 * time.Second})

	got := probeOllamaForOnboard(srv.URL)
	if !got.Reachable {
		t.Errorf("empty tags response should still mark Ollama as reachable")
	}
	if len(got.ToolCapableModels) != 0 {
		t.Errorf("expected empty tool-capable list, got %v", got.ToolCapableModels)
	}
}

func TestProbeOllamaForOnboard_AllModelsLackToolsReturnsEmpty(t *testing.T) {
	withProbeStubs(t, false, "")
	srv := ollamaTestServer(t, map[string][]string{
		"gemma:2b":   {"completion"},
		"phi-3:mini": {"completion"},
	})
	withOllamaProbeClient(t, &http.Client{Timeout: 2 * time.Second})

	got := probeOllamaForOnboard(srv.URL)
	if !got.Reachable {
		t.Errorf("Ollama with non-empty tags must be reachable")
	}
	if len(got.ToolCapableModels) != 0 {
		t.Errorf("no models advertise tools — expected empty slice, got %v", got.ToolCapableModels)
	}
}

func TestProbeOllamaForOnboard_OllamaDownReturnsUnreachable(t *testing.T) {
	withProbeStubs(t, false, "")
	withOllamaProbeClient(t, &http.Client{Timeout: 250 * time.Millisecond})

	// Closed port — connection refused fires fast.
	got := probeOllamaForOnboard("http://127.0.0.1:1") // port 1: tcpmux, almost never bound
	if got.Reachable {
		t.Errorf("unreachable Ollama must mark Reachable=false")
	}
	if got.ToolCapableModels != nil {
		t.Errorf("unreachable Ollama must yield nil models, got %v", got.ToolCapableModels)
	}
}

func TestProbeOllamaForOnboard_MissingCapabilitiesIsTreatedAsIncompatible(t *testing.T) {
	// Older Ollama (< 0.3) lacks the capabilities field — wizard must
	// fail closed since tool support can't be confirmed.
	withProbeStubs(t, false, "")
	srv := ollamaTestServer(t, map[string][]string{
		"old-model": nil, // no capabilities key
	})
	withOllamaProbeClient(t, &http.Client{Timeout: 2 * time.Second})

	got := probeOllamaForOnboard(srv.URL)
	if !got.Reachable {
		t.Errorf("Ollama responded with /api/tags so it must be reachable")
	}
	if len(got.ToolCapableModels) != 0 {
		t.Errorf("model without capabilities field must not be marked tool-capable, got %v", got.ToolCapableModels)
	}
}

func TestProbeOllamaForOnboard_TrimsTrailingSlash(t *testing.T) {
	withProbeStubs(t, false, "")
	srv := ollamaTestServer(t, map[string][]string{
		"llama3.2": {"completion", "tools"},
	})
	withOllamaProbeClient(t, &http.Client{Timeout: 2 * time.Second})

	got := probeOllamaForOnboard(srv.URL + "/")
	if !got.Reachable {
		t.Errorf("trailing-slash URL should still reach the server")
	}
	if !reflect.DeepEqual(got.ToolCapableModels, []string{"llama3.2"}) {
		t.Errorf("trailing-slash URL should be normalized; got %v", got.ToolCapableModels)
	}
}

func TestProbeOllamaForOnboard_MalformedTagsBodyIsTolerated(t *testing.T) {
	// 200-OK with non-JSON body must yield Reachable=false, not panic.
	withProbeStubs(t, false, "")
	mux := http.NewServeMux()
	mux.HandleFunc("/api/tags", func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte("<html>oops</html>"))
	})
	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)
	withOllamaProbeClient(t, &http.Client{Timeout: 2 * time.Second})

	got := probeOllamaForOnboard(srv.URL)
	if got.Reachable {
		t.Errorf("malformed body must not count as reachable")
	}
	if got.ToolCapableModels != nil {
		t.Errorf("malformed body should yield nil models, got %v", got.ToolCapableModels)
	}
}

func TestHasOllamaToolsCapability_PostsExpectedBody(t *testing.T) {
	// /api/show is POST-only and reads the model name from the JSON body.
	withProbeStubs(t, false, "")
	var receivedBody string
	mux := http.NewServeMux()
	mux.HandleFunc("/api/show", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Errorf("expected POST, got %s", r.Method)
		}
		body, _ := io.ReadAll(r.Body)
		receivedBody = string(body)
		_ = json.NewEncoder(w).Encode(map[string]any{"capabilities": []string{"tools"}})
	})
	srv := httptest.NewServer(mux)
	t.Cleanup(srv.Close)
	withOllamaProbeClient(t, &http.Client{Timeout: 2 * time.Second})

	if !hasOllamaToolsCapability(srv.URL, "qwen3-coder:30b") {
		t.Errorf("expected tools capability for the served response")
	}
	if !strings.Contains(receivedBody, `"name":"qwen3-coder:30b"`) {
		t.Errorf("expected POST body to carry model name, got %q", receivedBody)
	}
}
