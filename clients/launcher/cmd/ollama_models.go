package cmd

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"sync"
	"time"
)

// ollamaProbeClient is the HTTP client for onboard-time model
// discovery. Tests swap it via withOllamaProbeClient.
var ollamaProbeClient = &http.Client{Timeout: 1500 * time.Millisecond}

// ollamaProbeMaxBody caps response reads. /api/tags and /api/show
// payloads are tiny in practice; the cap is defense-in-depth against
// a misconfigured reverse proxy returning an unbounded HTML page.
const ollamaProbeMaxBody = 2 << 20 // 2 MiB

// ollamaProbeResult drives the wizard's UI branch. Reachable=true with
// empty ToolCapableModels means Ollama is up but has nothing usable
// pulled; Reachable=false means we couldn't reach it at all.
type ollamaProbeResult struct {
	Reachable         bool
	ToolCapableModels []string
}

// probeOllamaForOnboard returns models on the host that advertise
// ``tools``. Multi-candidate URL strategy mirrors the host-side
// reachability probe; the first candidate to answer /api/tags wins.
// Per-model /api/show calls run in parallel so a power user with many
// pulled models still finishes inside the wizard's overall budget.
func probeOllamaForOnboard(baseURL string) ollamaProbeResult {
	for _, candidate := range candidateProbeURLs(baseURL) {
		models, ok := fetchOllamaTags(candidate)
		if !ok {
			continue
		}
		return ollamaProbeResult{
			Reachable:         true,
			ToolCapableModels: filterToolCapable(candidate, models),
		}
	}
	return ollamaProbeResult{}
}

// filterToolCapable returns the subset of ``models`` whose /api/show
// response advertises the ``tools`` capability. Each call goes out
// concurrently — Ollama answers /api/show locally and the wizard's
// overall budget is small, so serializing the calls would only matter
// for users with many pulled models, but parallelizing costs nothing.
func filterToolCapable(baseURL string, models []string) []string {
	results := make([]bool, len(models))
	var wg sync.WaitGroup
	for i, m := range models {
		wg.Add(1)
		go func(i int, m string) {
			defer wg.Done()
			results[i] = hasOllamaToolsCapability(baseURL, m)
		}(i, m)
	}
	wg.Wait()
	capable := make([]string, 0, len(models))
	for i, ok := range results {
		if ok {
			capable = append(capable, models[i])
		}
	}
	return capable
}

type ollamaTag struct {
	Name string `json:"name"`
}

type ollamaTagsResponse struct {
	Models []ollamaTag `json:"models"`
}

type ollamaShowResponse struct {
	Capabilities []string `json:"capabilities"`
}

// fetchOllamaTags returns the /api/tags model names plus an ok flag —
// distinguishes "answered with zero models" from "no answer" since
// both produce empty slices but mean different things to the wizard.
func fetchOllamaTags(baseURL string) ([]string, bool) {
	resp, err := ollamaProbeClient.Get(strings.TrimRight(baseURL, "/") + "/api/tags")
	if err != nil {
		return nil, false
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		return nil, false
	}
	body, err := io.ReadAll(io.LimitReader(resp.Body, ollamaProbeMaxBody))
	if err != nil {
		return nil, false
	}
	var data ollamaTagsResponse
	if err := json.Unmarshal(body, &data); err != nil {
		return nil, false
	}
	out := make([]string, 0, len(data.Models))
	for _, m := range data.Models {
		if name := strings.TrimSpace(m.Name); name != "" {
			out = append(out, name)
		}
	}
	return out, true
}

// hasOllamaToolsCapability returns true only when /api/show lists
// ``tools`` in capabilities. Older Ollama (< 0.3) without the field
// reports false — the wizard's strict list stays trustworthy.
func hasOllamaToolsCapability(baseURL, model string) bool {
	payload, err := json.Marshal(map[string]string{"name": model})
	if err != nil {
		return false
	}
	resp, err := ollamaProbeClient.Post(
		strings.TrimRight(baseURL, "/")+"/api/show",
		"application/json",
		bytes.NewReader(payload),
	)
	if err != nil {
		return false
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		return false
	}
	body, err := io.ReadAll(io.LimitReader(resp.Body, ollamaProbeMaxBody))
	if err != nil {
		return false
	}
	var data ollamaShowResponse
	if err := json.Unmarshal(body, &data); err != nil {
		return false
	}
	for _, c := range data.Capabilities {
		if c == "tools" {
			return true
		}
	}
	return false
}
