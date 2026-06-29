"""Offensive Vaccine tool package.

Exposes the four LangChain tools that power the vaccine agent's
attack→defend→verify loop:

- ``generate_remediation_brief`` — structured mitigation plan for a Finding.
- ``apply_defense`` — deploy a compensating control and record it in the KG.
- ``verify_defense`` — re-execute the attack vector to prove the fix holds.
- ``record_vaccine_result`` — persist the overall vaccine outcome for a Finding.
"""

from decepticon.tools.vaccine.tools import (
    VACCINE_TOOLS,
    apply_defense,
    generate_remediation_brief,
    record_vaccine_result,
    verify_defense,
)

__all__ = [
    "generate_remediation_brief",
    "apply_defense",
    "verify_defense",
    "record_vaccine_result",
    "VACCINE_TOOLS",
]
