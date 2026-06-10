package opscontrol

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

// fakeBackend is an in-memory Backend used by the server tests. It
// records every Start/Stop call so tests can verify idempotency and
// per-workload serialization without a real docker daemon.
type fakeBackend struct {
	startCount atomic.Int32
	stopCount  atomic.Int32
	startDelay time.Duration
	mu         sync.Mutex
	running    map[string]bool
}

func newFakeBackend() *fakeBackend {
	return &fakeBackend{running: map[string]bool{}}
}

func (b *fakeBackend) Name() string { return "fake" }

func (b *fakeBackend) Start(_ context.Context, workload string, _ string) (Handle, error) {
	b.startCount.Add(1)
	if b.startDelay > 0 {
		time.Sleep(b.startDelay)
	}
	b.mu.Lock()
	b.running[workload] = true
	b.mu.Unlock()
	return Handle{Workload: workload, State: StateRunning}, nil
}

func (b *fakeBackend) Stop(_ context.Context, workload string) error {
	b.stopCount.Add(1)
	b.mu.Lock()
	delete(b.running, workload)
	b.mu.Unlock()
	return nil
}

func (b *fakeBackend) List(_ context.Context) ([]WorkloadStatus, error) { return nil, nil }

func newTestServer(t *testing.T) (*Server, *fakeBackend) {
	t.Helper()
	t.Setenv(AllowlistExtraEnv, "")
	al, err := LoadAllowlist()
	if err != nil {
		t.Fatalf("LoadAllowlist: %v", err)
	}
	be := newFakeBackend()
	return NewServer(be, al, nil), be
}

func TestServer_HealthEnvelope(t *testing.T) {
	s, _ := newTestServer(t)
	w := httptest.NewRecorder()
	r := httptest.NewRequest(http.MethodGet, "/v1/health", nil)
	s.mux().ServeHTTP(w, r)

	if w.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200", w.Code)
	}
	var got healthResponse
	if err := json.NewDecoder(w.Body).Decode(&got); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if !got.OK || got.Backend != "fake" || len(got.Allowlist) == 0 {
		t.Errorf("envelope = %+v; want ok=true, backend=fake, non-empty allowlist", got)
	}
}

func TestServer_StartRejectsUnknownWorkload(t *testing.T) {
	s, be := newTestServer(t)
	w := httptest.NewRecorder()
	r := httptest.NewRequest(http.MethodPost, "/v1/profiles/fake-but-valid-name/start", nil)
	s.mux().ServeHTTP(w, r)

	if w.Code != http.StatusBadRequest {
		t.Errorf("status = %d, want 400", w.Code)
	}
	if be.startCount.Load() != 0 {
		t.Errorf("backend.Start called %d times; want 0 (allowlist must reject before backend)", be.startCount.Load())
	}
	if !strings.Contains(w.Body.String(), "allowlist") {
		t.Errorf("body = %q; expected mention of allowlist", w.Body.String())
	}
}

func TestServer_StartRejectsTraversal(t *testing.T) {
	s, _ := newTestServer(t)
	w := httptest.NewRecorder()
	r := httptest.NewRequest(http.MethodPost, "/v1/profiles/..%2Fbad/start", nil)
	s.mux().ServeHTTP(w, r)
	if w.Code == http.StatusOK || w.Code == http.StatusAccepted {
		t.Errorf("path traversal accepted with status %d; want 4xx", w.Code)
	}
}

func TestServer_StartIdempotentForSameWorkload(t *testing.T) {
	s, be := newTestServer(t)
	for i := 0; i < 3; i++ {
		w := httptest.NewRecorder()
		r := httptest.NewRequest(http.MethodPost, "/v1/profiles/ad/start?engagement=eng-1", nil)
		s.mux().ServeHTTP(w, r)
		if w.Code != http.StatusAccepted {
			t.Fatalf("attempt %d: status = %d, want 202; body=%s", i, w.Code, w.Body.String())
		}
	}
	if got := be.startCount.Load(); got != 1 {
		t.Errorf("backend.Start called %d times; want 1 (second/third call should hit registry idempotency)", got)
	}
}

func TestServer_StartConcurrentSerializes(t *testing.T) {
	s, be := newTestServer(t)
	be.startDelay = 30 * time.Millisecond

	const N = 5
	var wg sync.WaitGroup
	wg.Add(N)
	for i := 0; i < N; i++ {
		go func() {
			defer wg.Done()
			w := httptest.NewRecorder()
			r := httptest.NewRequest(http.MethodPost, "/v1/profiles/c2-sliver/start", nil)
			s.mux().ServeHTTP(w, r)
		}()
	}
	wg.Wait()

	if got := be.startCount.Load(); got != 1 {
		t.Errorf("backend.Start called %d times under concurrent load; want 1 (mutex must serialize)", got)
	}
}

func TestServer_StopAfterStart(t *testing.T) {
	s, be := newTestServer(t)

	{
		w := httptest.NewRecorder()
		r := httptest.NewRequest(http.MethodPost, "/v1/profiles/ad/start", nil)
		s.mux().ServeHTTP(w, r)
		if w.Code != http.StatusAccepted {
			t.Fatalf("start status = %d", w.Code)
		}
	}
	{
		w := httptest.NewRecorder()
		r := httptest.NewRequest(http.MethodPost, "/v1/profiles/ad/stop", nil)
		s.mux().ServeHTTP(w, r)
		if w.Code != http.StatusAccepted {
			t.Fatalf("stop status = %d", w.Code)
		}
		// handleStop now returns immediately with state=stopping;
		// the compose call runs in a goroutine.
		var got Handle
		if err := json.NewDecoder(w.Body).Decode(&got); err != nil {
			t.Fatalf("decode stop body: %v", err)
		}
		if got.State != StateStopping {
			t.Errorf("stop response state = %q, want %q", got.State, StateStopping)
		}
	}

	// Poll until the goroutine has invoked backend.Stop. The
	// fakeBackend's stop is a no-op so this resolves in one tick
	// in the happy path; the deadline guards against goroutine
	// scheduling jitter under -race.
	deadline := time.Now().Add(1 * time.Second)
	for time.Now().Before(deadline) {
		if be.stopCount.Load() == 1 {
			break
		}
		time.Sleep(10 * time.Millisecond)
	}
	if be.startCount.Load() != 1 || be.stopCount.Load() != 1 {
		t.Errorf("calls: start=%d stop=%d; want 1/1", be.startCount.Load(), be.stopCount.Load())
	}
}

func TestServer_CleanupEngagementStopsTaggedWorkloads(t *testing.T) {
	s, be := newTestServer(t)

	// Tag two workloads with eng-1, one with eng-2.
	for _, payload := range []struct{ workload, engagement string }{
		{"ad", "eng-1"},
		{"c2-sliver", "eng-1"},
		{"reversing", "eng-2"},
	} {
		w := httptest.NewRecorder()
		r := httptest.NewRequest(http.MethodPost,
			"/v1/profiles/"+payload.workload+"/start?engagement="+payload.engagement, nil)
		s.mux().ServeHTTP(w, r)
		if w.Code != http.StatusAccepted {
			t.Fatalf("seed start %s: %d", payload.workload, w.Code)
		}
	}

	// Cleanup eng-1.
	w := httptest.NewRecorder()
	r := httptest.NewRequest(http.MethodPost, "/v1/engagements/eng-1/cleanup", nil)
	s.mux().ServeHTTP(w, r)
	if w.Code != http.StatusAccepted {
		t.Fatalf("cleanup status = %d", w.Code)
	}
	var resp cleanupResponse
	if err := json.NewDecoder(w.Body).Decode(&resp); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if len(resp.Stopped) != 2 {
		t.Errorf("stopped = %v; want 2 entries", resp.Stopped)
	}
	if be.stopCount.Load() != 2 {
		t.Errorf("backend.Stop called %d times; want 2", be.stopCount.Load())
	}
	// reversing (eng-2) must still be running.
	be.mu.Lock()
	stillUp := be.running["reversing"]
	be.mu.Unlock()
	if !stillUp {
		t.Error("reversing (eng-2) was stopped; cleanup must only touch its own engagement")
	}
}

func TestServer_CleanupEngagementRejectsBadID(t *testing.T) {
	s, _ := newTestServer(t)
	for _, bad := range []string{
		"../etc",
		"with space",
		"$(rm -rf)",
		"",
	} {
		w := httptest.NewRecorder()
		// Replace whitespace so http.NewRequest accepts the URL; the
		// handler validation must still reject it.
		urlPath := "/v1/engagements/" + strings.ReplaceAll(bad, " ", "%20") + "/cleanup"
		r := httptest.NewRequest(http.MethodPost, urlPath, nil)
		s.mux().ServeHTTP(w, r)
		// ServeMux returns 301 (path normalization) for `../etc` and
		// empty-segment paths before our handler runs; that is still
		// "rejected before the backend was called", which is the
		// security property we care about. The handler-level 400 covers
		// names that survive mux normalization.
		if w.Code < 300 || w.Code >= 500 {
			t.Errorf("engagement=%q got status %d; want a 3xx/4xx rejection", bad, w.Code)
		}
	}
}

func TestServer_ListReflectsRegistry(t *testing.T) {
	s, _ := newTestServer(t)
	// Empty before any start.
	{
		w := httptest.NewRecorder()
		r := httptest.NewRequest(http.MethodGet, "/v1/profiles", nil)
		s.mux().ServeHTTP(w, r)
		if w.Code != http.StatusOK || strings.TrimSpace(w.Body.String()) != "[]" {
			t.Errorf("initial list = %q; want []", w.Body.String())
		}
	}
	// After a start, registry should report the workload + engagement.
	{
		w := httptest.NewRecorder()
		r := httptest.NewRequest(http.MethodPost, "/v1/profiles/ad/start?engagement=eng-xyz", nil)
		s.mux().ServeHTTP(w, r)
		if w.Code != http.StatusAccepted {
			t.Fatalf("start: %d", w.Code)
		}
	}
	// Start is async — poll the list endpoint until the registry
	// transitions out of "starting" or a generous deadline expires.
	// The fakeBackend's zero start delay makes this resolve in a
	// single iteration in the happy path.
	var got []WorkloadStatus
	deadline := time.Now().Add(1 * time.Second)
	for time.Now().Before(deadline) {
		w := httptest.NewRecorder()
		r := httptest.NewRequest(http.MethodGet, "/v1/profiles", nil)
		s.mux().ServeHTTP(w, r)
		if err := json.NewDecoder(w.Body).Decode(&got); err != nil {
			t.Fatalf("decode: %v", err)
		}
		if len(got) == 1 && got[0].State == StateRunning {
			break
		}
		time.Sleep(20 * time.Millisecond)
	}
	if len(got) != 1 || got[0].Workload != "ad" || got[0].EngagementID != "eng-xyz" || got[0].State != StateRunning {
		t.Errorf("list = %+v; want [{ad, eng-xyz, running}] after async start completes", got)
	}
}
