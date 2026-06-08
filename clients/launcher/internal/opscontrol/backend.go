package opscontrol

import "context"

// WorkloadState is the narrow vocabulary the API uses to describe a
// workload's lifecycle. The DockerComposeBackend maps `compose ps`
// container states onto these four values; KubernetesBackend (future)
// will map pod Phase. The agent never sees container-runtime-specific
// states.
type WorkloadState string

const (
	StateRunning  WorkloadState = "running"
	StateStarting WorkloadState = "starting"
	StateStopped  WorkloadState = "stopped"
	StateUnknown  WorkloadState = "unknown"
)

// Handle is what Backend.Start returns. ADR-0006 §5' also lists
// EndpointURL and BootstrapTokenRef on this struct; those fields are
// intentionally deferred to Sprint 3 (BHCE token bootstrap migration)
// because Sprint 1 has nothing to put in them. Adding a field to a
// Go struct is non-breaking, so future sprints can land them without
// touching agent code.
type Handle struct {
	Workload     string        `json:"workload"`
	State        WorkloadState `json:"state"`
	EngagementID string        `json:"engagement_id,omitempty"`
}

// WorkloadStatus is one row of the Backend.List response.
type WorkloadStatus struct {
	Workload     string        `json:"workload"`
	State        WorkloadState `json:"state"`
	EngagementID string        `json:"engagement_id,omitempty"`
	Since        string        `json:"since,omitempty"`
}

// Backend abstracts the substrate that actually starts and stops
// workloads. ADR-0006 §5' lists DockerComposeBackend, KubernetesBackend,
// CloudRunBackend, FargateBackend, NomadBackend. Sprint 1 ships
// DockerComposeBackend only; the interface exists so the daemon HTTP
// surface and the `(workload, lifecycle_op)` tuple stay
// backend-independent.
type Backend interface {
	// Start brings up the workload. Idempotent: calling it on an
	// already-running workload returns the existing handle without
	// re-running compose up.
	Start(ctx context.Context, workload string, engagementID string) (Handle, error)

	// Stop tears down the workload. Idempotent: stopping a stopped
	// workload returns nil.
	Stop(ctx context.Context, workload string) error

	// List returns the current state of every known workload — both
	// running ones and ones the daemon has previously started in this
	// session.
	List(ctx context.Context) ([]WorkloadStatus, error)

	// Name identifies the backend in `/v1/health`. Useful for
	// operators diagnosing "why didn't K8s spawn?" issues across
	// runtimes.
	Name() string
}
