package opscontrol

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"os"
	"strings"
	"time"
)

// Server is the HTTP API the agent calls. It binds to a Unix-domain
// socket — never to TCP — and a langgraph-only bind-mount is the
// capability grant. ADR-0006 §1' and §6 (Anthropic Claude Code
// sandboxing, Vercel Sandbox, Fly Machines) converge on this shape.
type Server struct {
	Backend   Backend
	Allowlist *Allowlist
	Registry  *registry
	Logger    *slog.Logger
}

// NewServer assembles a server with the standard registry + an
// internal lock map for per-workload serialization.
func NewServer(backend Backend, allow *Allowlist, logger *slog.Logger) *Server {
	if logger == nil {
		logger = slog.New(slog.NewTextHandler(os.Stderr, nil))
	}
	return &Server{
		Backend:   backend,
		Allowlist: allow,
		Registry:  newRegistry(),
		Logger:    logger,
	}
}

// Listen binds the UDS at socketPath and runs the HTTP server. The
// caller is responsible for cleaning up the socket file on shutdown
// (Serve does the unlink before binding to recover from a stale file
// left by a previous crash).
func (s *Server) Listen(ctx context.Context, socketPath string) error {
	// Stale socket file from a previous unclean shutdown would
	// otherwise fail the bind. Removing a non-socket inode would be
	// destructive, so guard with an os.Stat first.
	if info, err := os.Stat(socketPath); err == nil {
		if info.Mode()&os.ModeSocket == 0 {
			return fmt.Errorf("opscontrol: %s exists and is not a socket; refusing to overwrite", socketPath)
		}
		if err := os.Remove(socketPath); err != nil {
			return fmt.Errorf("opscontrol: remove stale socket: %w", err)
		}
	}

	lis, err := net.Listen("unix", socketPath)
	if err != nil {
		return fmt.Errorf("opscontrol: listen unix %s: %w", socketPath, err)
	}
	// Tighten permissions so only the user that owns $DECEPTICON_HOME
	// (and root, and processes that share the bind-mount) can connect.
	if err := os.Chmod(socketPath, 0o600); err != nil {
		_ = lis.Close()
		return fmt.Errorf("opscontrol: chmod socket: %w", err)
	}

	srv := &http.Server{
		Handler:           s.mux(),
		ReadHeaderTimeout: 5 * time.Second,
	}

	errc := make(chan error, 1)
	go func() {
		errc <- srv.Serve(lis)
	}()

	select {
	case <-ctx.Done():
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = srv.Shutdown(shutdownCtx)
		_ = os.Remove(socketPath)
		return ctx.Err()
	case err := <-errc:
		if errors.Is(err, http.ErrServerClosed) {
			return nil
		}
		return err
	}
}

func (s *Server) mux() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /v1/health", s.handleHealth)
	mux.HandleFunc("GET /v1/profiles", s.handleList)
	mux.HandleFunc("POST /v1/profiles/{workload}/start", s.handleStart)
	mux.HandleFunc("POST /v1/profiles/{workload}/stop", s.handleStop)
	return mux
}

// healthResponse is the envelope `/v1/health` returns. The allowlist
// is included so a misconfigured allowlist (e.g., bad
// DECEPTICON_OPS_ALLOWLIST_EXTRA) is caught by operators without
// reading daemon logs.
type healthResponse struct {
	OK        bool     `json:"ok"`
	Backend   string   `json:"backend"`
	Allowlist []string `json:"allowlist"`
}

func (s *Server) handleHealth(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, healthResponse{
		OK:        true,
		Backend:   s.Backend.Name(),
		Allowlist: s.Allowlist.Members(),
	})
}

func (s *Server) handleList(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, s.Registry.snapshot())
}

func (s *Server) handleStart(w http.ResponseWriter, r *http.Request) {
	workload := r.PathValue("workload")
	if !s.Allowlist.Permits(workload) {
		writeError(w, http.StatusBadRequest, "workload not in allowlist or contains illegal characters")
		return
	}
	engagementID := strings.TrimSpace(r.URL.Query().Get("engagement"))

	// Async control plane (ADR-0006 §1' converges with Fly Machines /
	// Modal Sandbox / Anthropic Bash run_in_background): the HTTP
	// handler returns IMMEDIATELY with the registry state. Long-running
	// compose calls (BHCE cold start measured 90-300s) run in a
	// goroutine bound to the daemon's own context, and the
	// OpsControlNotificationMiddleware delivers state transitions to
	// the agent through <system-reminder> blocks on its next turn.
	// Holding the HTTP request open for 5+ minutes invites
	// load-balancer timeouts, NAT eviction, and silent client
	// disconnects — none of which the agent loop can recover from.

	lock := s.Registry.lockFor(workload)
	lock.Lock()

	// State-aware fast paths run while holding the lock so a
	// race-in second request observes the in-flight Starting state
	// instead of duplicating the spawn.
	if existing, ok := s.Registry.get(workload); ok {
		switch existing.State {
		case StateRunning, StateStarting:
			lock.Unlock()
			writeJSON(w, http.StatusAccepted, Handle{
				Workload:     workload,
				State:        existing.State,
				EngagementID: existing.EngagementID,
			})
			return
		}
	}

	s.Registry.set(workload, StateStarting, engagementID)

	// The goroutine owns the lock for the full duration of the spawn.
	// We deliberately use a daemon-scoped context, not r.Context() —
	// the request returns in milliseconds, so a request-scoped
	// context would cancel compose mid-spawn the moment the client
	// disconnects.
	go func() {
		defer lock.Unlock()
		ctx := context.Background()
		handle, err := s.Backend.Start(ctx, workload, engagementID)
		if err != nil {
			s.Registry.set(workload, StateUnknown, engagementID)
			s.Logger.Error("opscontrol start failed",
				"workload", workload,
				"engagement", engagementID,
				"err", err,
			)
			return
		}
		s.Registry.set(workload, handle.State, engagementID)
		s.Logger.Info("opscontrol start ok",
			"workload", workload,
			"engagement", engagementID,
			"state", string(handle.State),
		)
	}()

	writeJSON(w, http.StatusAccepted, Handle{
		Workload:     workload,
		State:        StateStarting,
		EngagementID: engagementID,
	})
}

func (s *Server) handleStop(w http.ResponseWriter, r *http.Request) {
	workload := r.PathValue("workload")
	if !s.Allowlist.Permits(workload) {
		writeError(w, http.StatusBadRequest, "workload not in allowlist or contains illegal characters")
		return
	}

	lock := s.Registry.lockFor(workload)
	lock.Lock()
	defer lock.Unlock()

	if err := s.Backend.Stop(r.Context(), workload); err != nil {
		s.Logger.Error("opscontrol stop failed", "workload", workload, "err", err)
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	s.Registry.set(workload, StateStopped, "")
	writeJSON(w, http.StatusAccepted, Handle{Workload: workload, State: StateStopped})
}

func writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}

type errorEnvelope struct {
	Error string `json:"error"`
}

func writeError(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, errorEnvelope{Error: msg})
}
