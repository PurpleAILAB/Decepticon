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
	}
	if be.startCount.Load() != 1 || be.stopCount.Load() != 1 {
		t.Errorf("calls: start=%d stop=%d; want 1/1", be.startCount.Load(), be.stopCount.Load())
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
