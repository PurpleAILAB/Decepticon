from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from benchmark.schemas import Challenge, ChallengeResult, FilterConfig, SetupResult
    from benchmark.state import BenchmarkRunState


class BaseBenchmarkProvider(ABC):
    """Abstract base class for benchmark providers.

    A provider is responsible for loading challenges from a benchmark source,
    managing the lifecycle of challenge environments, and evaluating results.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """The provider's display name."""

    @abstractmethod
    def load_challenges(self, filters: FilterConfig) -> list[Challenge]:
        """Load and filter challenges from the benchmark source.

        Implementations should apply the given filters (levels, tags, range)
        and return only the matching challenges in a stable order.
        """

    @abstractmethod
    def setup(self, challenge: Challenge) -> SetupResult:
        """Set up the challenge environment (Docker build/run).

        Must return a SetupResult with success=True and a reachable target_url
        on success, or success=False with a non-None error message on failure.
        Callers rely on SetupResult.success to decide whether to proceed.
        """

    @abstractmethod
    def evaluate(
        self,
        challenge: Challenge,
        state: BenchmarkRunState,
        workspace: Path,
    ) -> ChallengeResult:
        """Evaluate whether the challenge was solved.

        Inspects the engagement state and any artefacts written under workspace
        to determine if the challenge win condition was met.  Must always return
        a ChallengeResult; exceptions should be caught and surfaced via
        ChallengeResult.error rather than propagated.
        """

    @abstractmethod
    def teardown(self, challenge: Challenge) -> None:
        """Clean up challenge environment.

        Stop and remove any containers or other resources created by setup().
        Should be idempotent: calling teardown on an already-torn-down
        challenge must not raise.
        """
