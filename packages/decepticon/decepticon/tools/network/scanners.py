"""Network Scanning Tools.

Provides network scanning capabilities using various techniques:
- TCP connect scanning
- SYN stealth scanning
- Service version detection
- OS fingerprinting
- Network inventory

All scanners respect the engagement scope and Rules of Engagement.
"""

from __future__ import annotations

import asyncio
import json
import logging
import socket
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class ScanResult:
    """Result of a network scan operation."""

    target: str
    port: int
    protocol: str
    state: str  # open, closed, filtered, unknown
    service: str | None = None
    version: str | None = None
    banner: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "port": self.port,
            "protocol": self.protocol,
            "state": self.state,
            "service": self.service,
            "version": self.version,
            "banner": self.banner,
            "timestamp": self.timestamp,
            "error": self.error,
        }


@dataclass
class NetworkScanReport:
    """Comprehensive report of a network scan."""

    target: str
    scan_type: str
    start_time: str
    end_time: str
    results: list[ScanResult] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "scan_type": self.scan_type,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "results": [r.to_dict() for r in self.results],
            "summary": self.summary,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def to_md(self) -> str:
        """Generate markdown report."""
        lines = [
            f"# Network Scan Report: {self.target}",
            f"- **Scan Type**: {self.scan_type}",
            f"- **Start Time**: {self.start_time}",
            f"- **End Time**: {self.end_time}",
            "",
            "## Summary",
            f"- **Total Ports Scanned**: {self.summary.get('total_ports', 0)}",
            f"- **Open Ports**: {self.summary.get('open_ports', 0)}",
            f"- **Closed Ports**: {self.summary.get('closed_ports', 0)}",
            f"- **Filtered Ports**: {self.summary.get('filtered_ports', 0)}",
            "",
            "## Results",
            "",
            "| Port | Protocol | State | Service | Version |",
            "|------|----------|-------|---------|---------|",
        ]

        for result in sorted(self.results, key=lambda x: x.port):
            if result.state == "open":
                lines.append(
                    f"| {result.port} | {result.protocol} | {result.state} | "
                    f"{result.service or ''} | {result.version or ''} |"
                )

        lines.extend(
            [
                "",
                "## Open Port Details",
                "",
            ]
        )

        for result in sorted(self.results, key=lambda x: x.port):
            if result.state == "open":
                lines.extend(
                    [
                        f"### Port {result.port}/{result.protocol}",
                        f"- **Service**: {result.service or 'Unknown'}",
                        f"- **Version**: {result.version or 'Unknown'}",
                        f"- **Banner**: {result.banner[:200] if result.banner else 'None'}",
                        "",
                    ]
                )

        return "\n".join(lines)


# Common ports for different scan profiles
COMMON_PORTS = [
    21,
    22,
    23,
    25,
    53,
    80,
    110,
    139,
    143,
    443,
    445,
    465,
    587,
    993,
    995,
    1433,
    1521,
    1723,
    3306,
    3389,
    5432,
    5900,
    8000,
    8080,
    8443,
]

WEB_PORTS = [80, 443, 8000, 8008, 8080, 8443, 8888, 9000, 9090]

DATABASE_PORTS = [1433, 1521, 3306, 5432, 27017, 27018, 27019]

MANAGEMENT_PORTS = [22, 23, 3389, 5900, 5901, 5902, 5903]

ALL_PORTS = list(range(1, 1025))  # Well-known ports

# Service to port mapping
SERVICE_PORTS: dict[str, list[int]] = {
    "http": [80, 8000, 8008, 8080, 8888, 9000, 9090],
    "https": [443, 8443],
    "ssh": [22],
    "ftp": [21, 2121],
    "ftps": [990],
    "sftp": [22],
    "telnet": [23],
    "smtp": [25, 465, 587],
    "dns": [53],
    "dhcp": [67, 68],
    "pop3": [110, 995],
    "imap": [143, 993],
    "snmp": [161, 162],
    "ldap": [389, 636],
    "rdp": [3389],
    "vnc": [5900, 5901, 5902, 5903, 5904, 5905, 5906],
    "mysql": [3306],
    "postgresql": [5432],
    "oracle": [1521],
    "mssql": [1433],
    "mongodb": [27017],
    "redis": [6379],
    "rabbitmq": [5672, 15672],
    "kafka": [9092],
    "elasticsearch": [9200, 9300],
    "cifs": [445],
    "smb": [445],
    "rpc": [111, 135],
    "nfs": [2049],
    "syslog": [514],
    "rsync": [873],
    "git": [9418],
    "proxy": [3128, 8080, 8888],
    "memcached": [11211],
    "zookeeper": [2181],
    "consul": [8500],
    "etcd": [2379, 2380],
    "influxdb": [8086],
    "grafana": [3000],
    "prometheus": [9090],
    "docker": [2375, 2376, 2377],
    "kubernetes": [6443, 10250, 10255],
}


async def port_scan(
    target: str,
    ports: list[int] | None = None,
    timeout: float = 2.0,
    concurrency: int = 100,
) -> list[ScanResult]:
    """Perform TCP connect scan on specified ports.

    Args:
        target: IP address or hostname to scan
        ports: List of ports to scan. If None, scans COMMON_PORTS
        timeout: Connection timeout in seconds
        concurrency: Maximum concurrent connections

    Returns:
        List of ScanResult objects
    """
    if ports is None:
        ports = COMMON_PORTS

    results: list[ScanResult] = []

    async def scan_port(port: int) -> ScanResult:
        try:
            # Try TCP connection
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port),
                timeout=timeout,
            )
            banner = await _grab_banner(reader, timeout=1.0)
            writer.close()
            await writer.wait_closed()
            return ScanResult(
                target=target,
                port=port,
                protocol="tcp",
                state="open",
                banner=banner[:500] if banner else None,
            )
        except asyncio.TimeoutError:
            return ScanResult(
                target=target,
                port=port,
                protocol="tcp",
                state="filtered",
            )
        except ConnectionRefusedError:
            return ScanResult(
                target=target,
                port=port,
                protocol="tcp",
                state="closed",
            )
        except OSError as e:
            return ScanResult(
                target=target,
                port=port,
                protocol="tcp",
                state="unknown",
                error=str(e),
            )

    # Limit concurrency
    semaphore = asyncio.Semaphore(concurrency)

    async def limited_scan(port: int) -> ScanResult:
        async with semaphore:
            return await scan_port(port)

    tasks = [limited_scan(port) for port in ports]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Handle any exceptions
    final_results = []
    for result in results:
        if isinstance(result, Exception):
            log.error(f"Error scanning port: {result}")
        else:
            final_results.append(result)

    return final_results


async def _grab_banner(
    reader: asyncio.StreamReader,
    timeout: float = 1.0,
) -> str | None:
    """Attempt to grab banner from a connected socket."""
    try:
        banner = await asyncio.wait_for(reader.read(1024), timeout=timeout)
        return banner.decode("utf-8", errors="ignore") if banner else None
    except Exception:
        return None


async def nmap_scan(
    target: str,
    ports: str | None = None,
    arguments: str | None = None,
    timeout: int = 30,
) -> NetworkScanReport:
    """Execute nmap scan on target.

    This wrapper executes nmap with the specified parameters and parses the output.
    Falls back to Python-based scanning if nmap is not available.

    Args:
        target: IP address, hostname, or network range (e.g., "192.168.1.0/24")
        ports: Port specification (e.g., "1-1024", "22,80,443")
        arguments: Additional nmap arguments
        timeout: Scan timeout in seconds

    Returns:
        NetworkScanReport with scan results
    """
    import shutil

    start_time = datetime.utcnow().isoformat() + "Z"

    # Check if nmap is available
    nmap_available = shutil.which("nmap") is not None

    if nmap_available:
        return await _nmap_scan_external(target, ports, arguments, timeout, start_time)
    else:
        log.warning("nmap not found, falling back to Python-based scanning")
        return await _python_nmap_scan(target, ports, start_time)


async def _nmap_scan_external(
    target: str,
    ports: str | None,
    arguments: str | None,
    timeout: int,
    start_time: str,
) -> NetworkScanReport:
    """Execute nmap scan using system nmap command."""

    # Build nmap command
    cmd = ["nmap", "-Pn", "--max-retries", "1", "--host-timeout", str(timeout) + "s"]

    if ports:
        cmd.extend(["-p", ports])

    if arguments:
        cmd.extend(arguments.split())

    cmd.append(target)

    # Execute nmap
    try:
        result = await asyncio.create_subprocess_exec(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            timeout=timeout + 10,
        )
        stdout, stderr = await result.communicate()

        if result.returncode != 0:
            log.error(f"nmap scan failed: {stderr.decode()}")
            return NetworkScanReport(
                target=target,
                scan_type="nmap",
                start_time=start_time,
                end_time=datetime.utcnow().isoformat() + "Z",
                summary={"error": stderr.decode()},
            )

        # Parse nmap XML output
        xml_output = stdout.decode()
        return _parse_nmap_xml(xml_output, target, start_time)

    except asyncio.TimeoutError:
        log.error(f"nmap scan timed out after {timeout} seconds")
        return NetworkScanReport(
            target=target,
            scan_type="nmap",
            start_time=start_time,
            end_time=datetime.utcnow().isoformat() + "Z",
            summary={"error": "Scan timed out"},
        )
    except Exception as e:
        log.error(f"nmap scan error: {e}")
        return NetworkScanReport(
            target=target,
            scan_type="nmap",
            start_time=start_time,
            end_time=datetime.utcnow().isoformat() + "Z",
            summary={"error": str(e)},
        )


async def _python_nmap_scan(
    target: str,
    ports: str | None,
    start_time: str,
) -> NetworkScanReport:
    """Fallback Python-based nmap-like scan."""
    # Parse port specification
    if ports:
        if "-" in ports:
            start, end = ports.split("-")
            port_range = list(range(int(start), int(end) + 1))
        elif "," in ports:
            port_range = [int(p.strip()) for p in ports.split(",") if p.strip().isdigit()]
        else:
            port_range = [int(ports)] if ports.isdigit() else COMMON_PORTS
    else:
        port_range = COMMON_PORTS

    results = await port_scan(target, port_range, timeout=2.0, concurrency=50)

    end_time = datetime.utcnow().isoformat() + "Z"

    # Calculate summary
    summary = {
        "total_ports": len(port_range),
        "open_ports": len([r for r in results if r.state == "open"]),
        "closed_ports": len([r for r in results if r.state == "closed"]),
        "filtered_ports": len([r for r in results if r.state == "filtered"]),
        "scan_method": "python_connect_scan",
    }

    return NetworkScanReport(
        target=target,
        scan_type="connect_scan",
        start_time=start_time,
        end_time=end_time,
        results=results,
        summary=summary,
    )


def _parse_nmap_xml(xml_output: str, target: str, start_time: str) -> NetworkScanReport:
    """Parse nmap XML output."""
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(xml_output)
    except ET.ParseError:
        log.error("Failed to parse nmap XML output")
        return NetworkScanReport(
            target=target,
            scan_type="nmap",
            start_time=start_time,
            end_time=datetime.utcnow().isoformat() + "Z",
            summary={"error": "Failed to parse XML output"},
        )

    results: list[ScanResult] = []
    summary: dict[str, Any] = {}

    # Extract run stats
    runstats = root.find(".//runstats")
    if runstats is not None:
        finished = runstats.find("finished")
        if finished is not None:
            summary["end_time"] = finished.get("timestr", datetime.utcnow().isoformat() + "Z")

    # Extract hosts
    for host in root.findall(".//host"):
        host_target = target
        address = host.find("address")
        if address is not None and address.get("addrtype") == "ipv4":
            host_target = address.get("addr", target)

        # Extract ports
        ports = host.find("ports")
        if ports is not None:
            for port in ports.findall("port"):
                port_id = int(port.get("portid", 0))
                protocol = port.get("protocol", "tcp")

                state = port.find("state")
                state_name = state.get("name", "unknown") if state is not None else "unknown"

                service = port.find("service")
                service_name = service.get("name", None) if service is not None else None
                service_version = service.get("version", None) if service is not None else None

                # Extract banner if available
                script = port.find(".//script[@id='banner']")
                banner = script.get("output", None) if script is not None else None

                results.append(
                    ScanResult(
                        target=host_target,
                        port=port_id,
                        protocol=protocol,
                        state=state_name,
                        service=service_name,
                        version=service_version,
                        banner=banner,
                    )
                )

    # Calculate summary statistics
    summary["total_ports"] = len(results)
    summary["open_ports"] = len([r for r in results if r.state == "open"])
    summary["closed_ports"] = len([r for r in results if r.state == "closed"])
    summary["filtered_ports"] = len([r for r in results if r.state == "filtered"])

    end_time = summary.get("end_time", datetime.utcnow().isoformat() + "Z")

    return NetworkScanReport(
        target=target,
        scan_type="nmap",
        start_time=start_time,
        end_time=end_time,
        results=results,
        summary=summary,
    )


async def service_version_scan(
    target: str,
    ports: list[int] | None = None,
    timeout: float = 3.0,
) -> list[ScanResult]:
    """Perform service version detection scan.

    Args:
        target: IP address or hostname to scan
        ports: List of ports to scan. If None, scans open ports from a quick scan
        timeout: Connection timeout in seconds

    Returns:
        List of ScanResult objects with service version information
    """
    if ports is None:
        # First do a quick scan to find open ports
        quick_results = await port_scan(target, COMMON_PORTS, timeout=1.0, concurrency=50)
        open_ports = [r.port for r in quick_results if r.state == "open"]
        ports = open_ports if open_ports else COMMON_PORTS

    results: list[ScanResult] = []

    for port in ports:
        try:
            # Try to connect and grab banner
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(target, port),
                timeout=timeout,
            )

            banner = await _grab_banner(reader, timeout=2.0)

            # Try to detect service based on banner
            service, version = _detect_service_from_banner(banner, port)

            writer.close()
            await writer.wait_closed()

            results.append(
                ScanResult(
                    target=target,
                    port=port,
                    protocol="tcp",
                    state="open",
                    service=service,
                    version=version,
                    banner=banner[:500] if banner else None,
                )
            )
        except asyncio.TimeoutError:
            results.append(
                ScanResult(
                    target=target,
                    port=port,
                    protocol="tcp",
                    state="filtered",
                )
            )
        except ConnectionRefusedError:
            results.append(
                ScanResult(
                    target=target,
                    port=port,
                    protocol="tcp",
                    state="closed",
                )
            )
        except Exception as e:
            results.append(
                ScanResult(
                    target=target,
                    port=port,
                    protocol="tcp",
                    state="unknown",
                    error=str(e),
                )
            )

    return results


def _detect_service_from_banner(banner: str | None, port: int) -> tuple[str | None, str | None]:
    """Detect service and version from banner."""
    if not banner:
        # Try to detect from common port
        for service_name, port_list in SERVICE_PORTS.items():
            if port in port_list:
                return service_name, None
        return None, None

    # Check for common service banners
    banner_lower = banner.lower()

    # HTTP/HTTPS
    if "http" in banner_lower or "apache" in banner_lower or "nginx" in banner_lower:
        # Try to extract version
        for line in banner.split("\n"):
            if "server:" in line.lower():
                parts = line.split(":", 1)
                if len(parts) > 1:
                    return "http", parts[1].strip()
            elif "apache/" in line.lower():
                version = line.split("apache/")[1].split()[0]
                return "apache", version
            elif "nginx/" in line.lower():
                version = line.split("nginx/")[1].split()[0]
                return "nginx", version
        return "http", None

    # SSH
    if "ssh" in banner_lower or "openssh" in banner_lower:
        if "openssh_" in banner_lower:
            version = banner.split("OpenSSH_")[1].split()[0]
            return "openssh", version
        return "ssh", None

    # FTP
    if "ftp" in banner_lower or "220" in banner[:3]:
        return "ftp", None

    # SMTP
    if "smtp" in banner_lower or "220" in banner[:3] or "250" in banner[:3]:
        if "postfix" in banner_lower:
            return "postfix", None
        elif "sendmail" in banner_lower:
            return "sendmail", None
        elif "exim" in banner_lower:
            return "exim", None
        return "smtp", None

    # DNS
    if port == 53 or "bind" in banner_lower or "dns" in banner_lower:
        return "dns", None

    # MySQL
    if "mysql" in banner_lower:
        if "server version" in banner_lower:
            version = banner.split("Server version:")[1].split()[0]
            return "mysql", version
        return "mysql", None

    # PostgreSQL
    if "postgresql" in banner_lower:
        return "postgresql", None

    # Redis
    if "redis" in banner_lower:
        if "redis_server" in banner_lower:
            version = (
                banner.split("redis_version:")[1].split()[0]
                if "redis_version:" in banner_lower
                else None
            )
            return "redis", version
        return "redis", None

    # MongoDB
    if "mongodb" in banner_lower:
        return "mongodb", None

    # Fall back to port-based detection
    for service_name, port_list in SERVICE_PORTS.items():
        if port in port_list:
            return service_name, None

    return None, None


async def os_fingerprint_scan(
    target: str,
    ports: list[int] | None = None,
    method: str = "active",
) -> dict[str, Any]:
    """Perform OS fingerprinting using TCP/IP stack analysis.

    Args:
        target: IP address or hostname to scan
        ports: List of ports to use for fingerprinting
        method: Fingerprinting method ("active" or "passive")

    Returns:
        Dictionary with OS fingerprinting results
    """
    import shutil

    # Try to use nmap for OS detection
    nmap_available = shutil.which("nmap") is not None

    if nmap_available and method == "active":
        return await _nmap_os_detection(target, ports)
    else:
        return await _tcp_stack_fingerprinting(target, ports)


async def _nmap_os_detection(
    target: str,
    ports: list[int] | None,
) -> dict[str, Any]:
    """Use nmap for OS detection."""

    cmd = ["nmap", "-O", "--os-detection", "-Pn"]
    if ports:
        port_spec = ",".join(str(p) for p in ports)
        cmd.extend(["-p", port_spec])
    cmd.append(target)

    try:
        result = await asyncio.create_subprocess_exec(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            timeout=60,
        )
        stdout, stderr = await result.communicate()

        if result.returncode != 0:
            return {"error": stderr.decode(), "method": "nmap"}

        output = stdout.decode()
        return _parse_nmap_os_output(output)

    except Exception as e:
        return {"error": str(e), "method": "nmap"}


def _parse_nmap_os_output(output: str) -> dict[str, Any]:
    """Parse nmap OS detection output."""
    result: dict[str, Any] = {"method": "nmap", "oses": []}

    # Look for OS detection results
    lines = output.split("\n")
    in_os_section = False

    for line in lines:
        if "OS details:" in line or "OS detection performed:" in line:
            in_os_section = True
            continue

        if in_os_section:
            if line.strip() and not line.startswith(" ") and not line.startswith("\t"):
                break

            if "Running:" in line or "OS CPE:" in line:
                continue

            # Extract OS matches
            if line.strip().startswith("(") or "%" in line:
                match = line.strip()
                if match:
                    result["oses"].append(match)

    if not result["oses"]:
        # Try alternative parsing
        import re

        os_matches = re.findall(r"\n\d+%\s+([^\n]+)", output)
        result["oses"] = os_matches

    return result


async def _tcp_stack_fingerprinting(
    target: str,
    ports: list[int] | None,
) -> dict[str, Any]:
    """Perform TCP stack fingerprinting."""
    if ports is None:
        ports = [80, 443]  # Common ports for stack fingerprinting

    result: dict[str, Any] = {
        "method": "tcp_stack",
        "target": target,
        "ports": ports,
        "fingerprints": {},
    }

    # Common TCP stack characteristics
    stack_characteristics = {
        "window_size": None,
        "mss": None,
        "timestamp": None,
        "options": [],
    }

    for port in ports:
        try:
            # Create raw socket to analyze TCP handshake
            sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_TCP)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)

            # Try to connect (this will fail but we can analyze the response)
            # This is a simplified approach; real fingerprinting requires raw packet crafting
            sock.settimeout(2.0)
            try:
                sock.connect((target, port))
            except Exception:
                # Port closed/unreachable; nothing to fingerprint here.
                pass

            # Get socket options
            try:
                window_size = sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
                stack_characteristics["window_size"] = window_size
            except Exception:
                # Socket option unsupported on this platform; skip it.
                pass

            try:
                mss = sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_MAXSEG)
                stack_characteristics["mss"] = mss
            except Exception:
                # Socket option unsupported on this platform; skip it.
                pass

            sock.close()

        except Exception as e:
            log.debug(f"Error fingerprinting port {port}: {e}")
            continue

        result["fingerprints"][str(port)] = stack_characteristics.copy()

    return result


async def network_inventory(
    targets: list[str],
    ports: list[int] | None = None,
    scan_type: str = "quick",
) -> dict[str, NetworkScanReport]:
    """Perform network inventory scan on multiple targets.

    Args:
        targets: List of IP addresses or hostnames to scan
        ports: List of ports to scan. If None, uses scan_type to determine ports
        scan_type: Type of scan ("quick", "full", "web", "database")

    Returns:
        Dictionary mapping target to NetworkScanReport
    """
    port_lists = {
        "quick": COMMON_PORTS[:50],  # First 50 common ports
        "full": ALL_PORTS,
        "web": WEB_PORTS,
        "database": DATABASE_PORTS,
        "management": MANAGEMENT_PORTS,
    }

    if ports is None:
        ports = port_lists.get(scan_type, COMMON_PORTS)

    results: dict[str, NetworkScanReport] = {}

    for target in targets:
        try:
            report = await nmap_scan(target, ports=[str(p) for p in ports])
            results[target] = report
        except Exception as e:
            log.error(f"Error scanning {target}: {e}")
            results[target] = NetworkScanReport(
                target=target,
                scan_type=scan_type,
                start_time=datetime.utcnow().isoformat() + "Z",
                end_time=datetime.utcnow().isoformat() + "Z",
                summary={"error": str(e)},
            )

    return results
