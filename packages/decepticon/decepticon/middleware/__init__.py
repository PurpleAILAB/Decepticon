"""Decepticon middleware - custom AgentMiddleware implementations."""

from decepticon.middleware.budget import BudgetEnforcementMiddleware
from decepticon.middleware.detection_feedback import DetectionFeedbackMiddleware
from decepticon.middleware.engagement import EngagementContextMiddleware
from decepticon.middleware.event_logging import EventLogMiddleware
from decepticon.middleware.filesystem import FilesystemMiddleware
from decepticon.middleware.hitl import (
    DEFAULT_HIGH_IMPACT_POLICY,
    ApprovalDecision,
    ApprovalPolicyRule,
    ApprovalRequest,
    ApprovalTransport,
    FileBackedApprovalTransport,
    HITLApprovalMiddleware,
    InProcessApprovalTransport,
)
from decepticon.middleware.kg import KGMiddleware
from decepticon.middleware.notifications import (
    SandboxNotificationMiddleware,
)
from decepticon.middleware.opplan import OPPLANMiddleware
from decepticon.middleware.prompt_injection_shield import (
    PromptInjectionShieldMiddleware,
)
from decepticon.middleware.roe import RoEEnforcementMiddleware
from decepticon.middleware.skillogy import SkillogyMiddleware, maybe_install_skillogy
from decepticon.middleware.skills import SkillsMiddleware
from decepticon.middleware.untrusted_output import UntrustedOutputMiddleware

__all__ = [
    "ApprovalDecision",
    "ApprovalPolicyRule",
    "ApprovalRequest",
    "ApprovalTransport",
    "BudgetEnforcementMiddleware",
    "DEFAULT_HIGH_IMPACT_POLICY",
    "DetectionFeedbackMiddleware",
    "EngagementContextMiddleware",
    "EventLogMiddleware",
    "FileBackedApprovalTransport",
    "FilesystemMiddleware",
    "HITLApprovalMiddleware",
    "InProcessApprovalTransport",
    "KGMiddleware",
    "OPPLANMiddleware",
    "PromptInjectionShieldMiddleware",
    "RoEEnforcementMiddleware",
    "SandboxNotificationMiddleware",
    "SkillogyMiddleware",
    "SkillsMiddleware",
    "UntrustedOutputMiddleware",
    "maybe_install_skillogy",
]
