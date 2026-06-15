"""Network Reconnaissance Tools for Decepticon.

This module provides network reconnaissance capabilities including:
- Network scanning and service discovery
- Port scanning and vulnerability detection
- Network topology mapping
- Protocol-specific reconnaissance
- Network inventory and asset discovery

All network operations are designed to be:
- Non-intrusive (read-only by default)
- Rate-limited to avoid detection
- RoE (Rules of Engagement) compliant
- Scope-restricted to authorized targets only
"""

from decepticon.tools.network.protocols import (
    dns_recon,
    ftp_recon,
    http_recon,
    https_recon,
    rpc_recon,
    smb_recon,
    snmp_recon,
    ssh_recon,
)
from decepticon.tools.network.scanners import (
    network_inventory,
    nmap_scan,
    os_fingerprint_scan,
    port_scan,
    service_version_scan,
)
from decepticon.tools.network.vulnerability import (
    cve_scan,
    security_misconfiguration_scan,
    vulnerability_assessment,
)

__all__ = [
    # Scanners
    "nmap_scan",
    "port_scan",
    "service_version_scan",
    "os_fingerprint_scan",
    "network_inventory",
    # Protocols
    "http_recon",
    "https_recon",
    "dns_recon",
    "smb_recon",
    "rpc_recon",
    "snmp_recon",
    "ftp_recon",
    "ssh_recon",
    # Vulnerability
    "cve_scan",
    "vulnerability_assessment",
    "security_misconfiguration_scan",
]
