package health

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestCheckLangGraph_Success(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == "POST" && r.URL.Path == "/assistants/search" {
			w.WriteHeader(http.StatusOK)
			w.Write([]byte(`[{"assistant_id": "decepticon"}]`))
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	// Extract port from test server
	port := server.Listener.Addr().String()
	// Override by using the full URL check
	env := map[string]string{"LANGGRAPH_PORT": port[len("127.0.0.1:"):]}

	err := CheckLangGraph(env)
	if err != nil {
		t.Errorf("CheckLangGraph() unexpected error: %v", err)
	}
}

func TestCheckLiteLLM_Success(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/health/readiness" {
			w.WriteHeader(http.StatusOK)
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	port := server.Listener.Addr().String()
	env := map[string]string{"LITELLM_PORT": port[len("127.0.0.1:"):]}

	err := CheckLiteLLM(env)
	if err != nil {
		t.Errorf("CheckLiteLLM() unexpected error: %v", err)
	}
}

func TestCheckWeb_Success(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	port := server.Listener.Addr().String()
	env := map[string]string{"WEB_PORT": port[len("127.0.0.1:"):]}

	err := CheckWeb(env)
	if err != nil {
		t.Errorf("CheckWeb() unexpected error: %v", err)
	}
}
