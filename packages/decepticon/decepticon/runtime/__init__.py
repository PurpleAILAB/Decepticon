"""Runtime infrastructure for the Decepticon orchestrator process.

Each runtime module (event log, graceful shutdown, recording, CART, ...)
ships in its own PR. This package init imports every known module
best-effort so each PR can land in any order without colliding on
this file.
"""

_exports: list[str] = []

try:
    from decepticon.runtime.event_log import (  # noqa: F401  # re-exported via __all__
        EngagementEvent,
        EventLog,
        EventType,
        read_events,
    )

    _exports += ["EngagementEvent", "EventLog", "EventType", "read_events"]
except ImportError:
    pass

try:
    from decepticon.runtime.shutdown import (  # noqa: F401  # re-exported via __all__
        LangGraphState,
        install_shutdown_handlers,
    )

    _exports += ["LangGraphState", "install_shutdown_handlers"]
except ImportError:
    pass

try:
    from decepticon.runtime.programs import (  # noqa: F401  # re-exported via __all__
        GENERIC_PROGRAMS,
        KNOWN_PROGRAMS,
        SECURITY_PROGRAMS,
        WEB_SCANNER_PROGRAMS,
        extract_programs,
    )

    _exports += [
        "GENERIC_PROGRAMS",
        "KNOWN_PROGRAMS",
        "SECURITY_PROGRAMS",
        "WEB_SCANNER_PROGRAMS",
        "extract_programs",
    ]
except ImportError:
    pass

try:
    from decepticon.runtime.recording import (  # noqa: F401
        RecordingMiddleware,
        ReplayMiddleware,
        ReplayMismatchError,
        open_record,
        open_replay,
    )

    _exports += [
        "RecordingMiddleware",
        "ReplayMiddleware",
        "ReplayMismatchError",
        "open_record",
        "open_replay",
    ]
except ImportError:
    pass

try:
    from decepticon.runtime.task_spec import (  # noqa: F401
        Dispatcher,
        SubAgentTaskSpec,
    )

    _exports += ["Dispatcher", "SubAgentTaskSpec"]
except ImportError:
    pass

try:
    from decepticon.runtime.cart import (  # noqa: F401
        ChangeEvent,
        EngagementSnapshot,
        LinearOPPLANAdapter,
        OPPLANAdapter,
        ReplayPlan,
        ReplayRunner,
        SnapshotDelta,
        SnapshotNodeKey,
        Watcher,
        diff_snapshots,
    )

    _exports += [
        "ChangeEvent",
        "EngagementSnapshot",
        "LinearOPPLANAdapter",
        "OPPLANAdapter",
        "ReplayPlan",
        "ReplayRunner",
        "SnapshotDelta",
        "SnapshotNodeKey",
        "Watcher",
        "diff_snapshots",
    ]
except ImportError:
    pass

__all__ = _exports
