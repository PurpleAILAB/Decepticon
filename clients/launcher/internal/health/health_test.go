package health

import (
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestCheckLangGraph_Success(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == "POST" && r.URL.Path == "/assistants/search" {
			w.WriteHeader(http.StatusOK)
			w.Write([]byte(`[{"assistant_id": "abc", "graph_id": "decepticon"}]`))
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer server.Close()

	port := server.Listener.Addr().String()
	env := map[string]string{"LANGGRAPH_PORT": port[len("127.0.0.1:"):]}

	err := CheckLangGraph(env)
	if err != nil {
		t.Errorf("CheckLangGraph() unexpected error: %v", err)
	}
}

// 200 with an empty array means the API booted but the graph isn't compiled.
// CheckLangGraph must reject this and keep polling until timeout.
func TestCheckLangGraph_RejectsEmptyBody(t *testing.T) {
	prev := LangGraphTimeout
	LangGraphTimeout = 1 * time.Second
	defer func() { LangGraphTimeout = prev }()

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(`[]`))
	}))
	defer server.Close()

	port := server.Listener.Addr().String()
	env := map[string]string{"LANGGRAPH_PORT": port[len("127.0.0.1:"):]}

	if err := CheckLangGraph(env); err == nil {
		t.Error("CheckLangGraph() should fail when body lacks decepticon assistant")
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

func TestCheckNeo4j_Success(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer server.Close()

	port := server.Listener.Addr().String()
	env := map[string]string{"NEO4J_HTTP_PORT": port[len("127.0.0.1:"):]}

	if err := CheckNeo4j(env); err != nil {
		t.Errorf("CheckNeo4j() unexpected error: %v", err)
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
