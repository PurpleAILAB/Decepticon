"""Protocol-specific Reconnaissance Tools.

Provides specialized tools for various network protocols:
- HTTP/HTTPS
- DNS
- SMB
- RPC
- SNMP
- FTP
- SSH

All tools respect RoE and engagement scope.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import aiohttp

log = logging.getLogger(__name__)


@dataclass
class ProtocolResult:
    """Result of a protocol-specific reconnaissance operation."""

    target: str
    port: int
    protocol: str
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "port": self.port,
            "protocol": self.protocol,
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "timestamp": self.timestamp,
        }


async def http_recon(
    target: str,
    port: int = 80,
    use_https: bool = False,
    path: str = "/",
    timeout: float = 5.0,
    follow_redirects: bool = True,
    user_agent: str | None = None,
    verify_ssl: bool = True,
) -> ProtocolResult:
    """Perform HTTP reconnaissance on a target.

    Args:
        target: IP address or hostname
        port: HTTP port (default: 80)
        use_https: Use HTTPS instead of HTTP
        path: Path to request (default: "/")
        timeout: Request timeout in seconds
        follow_redirects: Follow HTTP redirects
        user_agent: Custom User-Agent string
        verify_ssl: Verify TLS certificate when use_https is set (default: True)

    Returns:
        ProtocolResult with HTTP reconnaissance data
    """
    url = f"http{'s' if use_https else ''}://{target}:{port}{path}"

    headers = {"Accept": "*/*"}
    if user_agent:
        headers["User-Agent"] = user_agent
    else:
        headers["User-Agent"] = "Mozilla/5.0 (compatible; Decepticon/1.0)"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
                allow_redirects=follow_redirects,
                ssl=None if (use_https and verify_ssl) else False,
            ) as response:
                # Read response body (limited)
                body = await response.read()
                body_text = body.decode("utf-8", errors="ignore")[:10000]

                # Extract headers
                response_headers = dict(response.headers)

                # Extract server information
                server_info = {
                    "status_code": response.status,
                    "headers": response_headers,
                    "content_type": response_headers.get("Content-Type", ""),
                    "content_length": response_headers.get("Content-Length", len(body)),
                    "server": response_headers.get("Server", "Unknown"),
                }

                # Extract title if HTML
                title = None
                if "text/html" in server_info["content_type"]:
                    title_match = re.search(
                        r"<title[^>]*>([^<]+)</title>", body_text, re.IGNORECASE
                    )
                    if title_match:
                        title = title_match.group(1).strip()

                # Extract forms if HTML
                forms = []
                if "text/html" in server_info["content_type"]:
                    form_matches = re.findall(
                        r'<form[^>]*action=["\']([^"\']*)["\'][^>]*>',
                        body_text,
                        re.IGNORECASE,
                    )
                    forms = list(set(form_matches))

                # Extract links
                links = []
                if "text/html" in server_info["content_type"]:
                    link_matches = re.findall(
                        r'href=["\']([^"\']*)["\']',
                        body_text,
                        re.IGNORECASE,
                    )
                    links = list(set(link_matches))[:50]

                # Check for common security headers
                security_headers = {
                    "X-Frame-Options": response_headers.get("X-Frame-Options"),
                    "X-XSS-Protection": response_headers.get("X-XSS-Protection"),
                    "X-Content-Type-Options": response_headers.get("X-Content-Type-Options"),
                    "Content-Security-Policy": response_headers.get("Content-Security-Policy"),
                    "Strict-Transport-Security": response_headers.get("Strict-Transport-Security"),
                    "Referrer-Policy": response_headers.get("Referrer-Policy"),
                    "Permissions-Policy": response_headers.get("Permissions-Policy"),
                }

                data = {
                    "url": url,
                    "server": server_info,
                    "title": title,
                    "forms": forms,
                    "links": links,
                    "security_headers": {k: v for k, v in security_headers.items() if v},
                    "body_preview": body_text[:500] if body_text else None,
                }

                return ProtocolResult(
                    target=target,
                    port=port,
                    protocol="https" if use_https else "http",
                    success=True,
                    data=data,
                )

    except asyncio.TimeoutError:
        return ProtocolResult(
            target=target,
            port=port,
            protocol="https" if use_https else "http",
            success=False,
            error="Request timed out",
        )
    except aiohttp.ClientError as e:
        return ProtocolResult(
            target=target,
            port=port,
            protocol="https" if use_https else "http",
            success=False,
            error=str(e),
        )
    except Exception as e:
        return ProtocolResult(
            target=target,
            port=port,
            protocol="https" if use_https else "http",
            success=False,
            error=str(e),
        )


async def https_recon(
    target: str,
    port: int = 443,
    path: str = "/",
    timeout: float = 5.0,
    verify_ssl: bool = False,
) -> ProtocolResult:
    """Perform HTTPS reconnaissance on a target.

    Args:
        target: IP address or hostname
        port: HTTPS port (default: 443)
        path: Path to request (default: "/")
        timeout: Request timeout in seconds
        verify_ssl: Verify SSL certificate (default: False for self-signed certs)

    Returns:
        ProtocolResult with HTTPS reconnaissance data
    """
    return await http_recon(
        target=target,
        port=port,
        use_https=True,
        path=path,
        timeout=timeout,
        verify_ssl=verify_ssl,
    )


async def dns_recon(
    target: str,
    dns_server: str | None = None,
    record_types: list[str] | None = None,
    timeout: float = 5.0,
) -> ProtocolResult:
    """Perform DNS reconnaissance on a target.

    Args:
        target: Domain name to query
        dns_server: DNS server to use (default: system resolver)
        record_types: DNS record types to query (A, AAAA, MX, TXT, etc.)
        timeout: Query timeout in seconds

    Returns:
        ProtocolResult with DNS reconnaissance data
    """

    if record_types is None:
        record_types = ["A", "AAAA", "MX", "TXT", "CNAME", "NS", "SOA", "PTR"]

    data: dict[str, Any] = {
        "target": target,
        "queries": {},
    }

    if dns_server:
        data["dns_server"] = dns_server

    try:
        for record_type in record_types:
            try:
                # Use dig command
                cmd = [
                    "dig",
                    f"@{dns_server}" if dns_server else "",
                    target,
                    record_type,
                    "+short",
                    "+time=1",
                    "+tries=1",
                ]
                cmd = [c for c in cmd if c]  # Remove empty strings

                result = await asyncio.create_subprocess_exec(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    timeout=timeout,
                )
                stdout, stderr = await result.communicate()

                if result.returncode == 0:
                    records = stdout.decode().strip().split("\n") if stdout else []
                    data["queries"][record_type] = [
                        r for r in records if r and not r.startswith(";")
                    ]
                else:
                    data["queries"][record_type] = {"error": stderr.decode().strip()}

            except Exception as e:
                data["queries"][record_type] = {"error": str(e)}

        return ProtocolResult(
            target=target,
            port=53,
            protocol="dns",
            success=True,
            data=data,
        )

    except Exception as e:
        return ProtocolResult(
            target=target,
            port=53,
            protocol="dns",
            success=False,
            error=str(e),
        )


async def smb_recon(
    target: str,
    port: int = 445,
    timeout: float = 5.0,
) -> ProtocolResult:
    """Perform SMB reconnaissance on a target.

    Args:
        target: IP address or hostname
        port: SMB port (default: 445)
        timeout: Connection timeout in seconds

    Returns:
        ProtocolResult with SMB reconnaissance data
    """

    data: dict[str, Any] = {
        "target": target,
        "port": port,
    }

    try:
        # Try smbclient to list shares (requires authentication for most operations)
        cmd = ["smbclient", "-L", f"//{target}", "-p", str(port), "-N", "-t", str(timeout)]

        try:
            result = await asyncio.create_subprocess_exec(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                timeout=timeout + 2,
            )
            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                output = stdout.decode()
                data["shares"] = _parse_smb_shares(output)
            else:
                data["error"] = stderr.decode().strip()

        except FileNotFoundError:
            data["error"] = "smbclient not found"
        except Exception as e:
            data["error"] = str(e)

        # Try to get SMB version using smbclient
        try:
            cmd = ["smbclient", "-V"]
            result = await asyncio.create_subprocess_exec(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                timeout=5,
            )
            stdout, _ = await result.communicate()
            if result.returncode == 0:
                version_output = stdout.decode().strip()
                version_match = re.search(r"Version\s+([0-9.]+)", version_output)
                if version_match:
                    data["smbclient_version"] = version_match.group(1)
        except Exception:
            # Best-effort enrichment; absence of version info is non-fatal.
            pass

        # Try nmblookup for NetBIOS information
        try:
            cmd = ["nmblookup", "-A", target]
            result = await asyncio.create_subprocess_exec(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                timeout=timeout,
            )
            stdout, _ = await result.communicate()
            if result.returncode == 0:
                data["netbios"] = stdout.decode().strip()
        except FileNotFoundError:
            # External tool not installed; skip this recon step silently.
            pass
        except Exception:
            # Parsing/lookup failed; leave netbios data unset.
            pass

        return ProtocolResult(
            target=target,
            port=port,
            protocol="smb",
            success=True,
            data=data,
        )

    except Exception as e:
        return ProtocolResult(
            target=target,
            port=port,
            protocol="smb",
            success=False,
            error=str(e),
        )


def _parse_smb_shares(output: str) -> list[dict[str, Any]]:
    """Parse smbclient output to extract share information."""
    shares = []
    lines = output.split("\n")

    for line in lines:
        line = line.strip()
        if (
            not line
            or line.startswith("-")
            or line.startswith("Domain")
            or line.startswith("Server")
        ):
            continue

        # Parse share line: Sharename       Type      Comment
        #                   ---------       ----      -------
        parts = line.split()
        if len(parts) >= 3:
            share_name = parts[0]
            share_type = parts[1]
            comment = " ".join(parts[2:])
            shares.append(
                {
                    "name": share_name,
                    "type": share_type,
                    "comment": comment,
                }
            )

    return shares


async def rpc_recon(
    target: str,
    port: int = 111,
    timeout: float = 5.0,
) -> ProtocolResult:
    """Perform RPC reconnaissance on a target.

    Args:
        target: IP address or hostname
        port: RPC port (default: 111)
        timeout: Connection timeout in seconds

    Returns:
        ProtocolResult with RPC reconnaissance data
    """

    data: dict[str, Any] = {
        "target": target,
        "port": port,
    }

    try:
        # Try rpcinfo to list RPC services
        cmd = ["rpcinfo", "-p", target]

        try:
            result = await asyncio.create_subprocess_exec(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                timeout=timeout,
            )
            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                data["services"] = _parse_rpcinfo_output(stdout.decode())
            else:
                data["error"] = stderr.decode().strip()

        except FileNotFoundError:
            data["error"] = "rpcinfo not found"
        except Exception as e:
            data["error"] = str(e)

        return ProtocolResult(
            target=target,
            port=port,
            protocol="rpc",
            success=True,
            data=data,
        )

    except Exception as e:
        return ProtocolResult(
            target=target,
            port=port,
            protocol="rpc",
            success=False,
            error=str(e),
        )


def _parse_rpcinfo_output(output: str) -> list[dict[str, Any]]:
    """Parse rpcinfo output to extract service information."""
    services = []
    lines = output.strip().split("\n")

    for line in lines[1:]:  # Skip header line
        parts = line.split()
        if len(parts) >= 4:
            services.append(
                {
                    "program": parts[0],
                    "version": parts[1],
                    "protocol": parts[2],
                    "port": parts[3],
                    "service": " ".join(parts[4:]) if len(parts) > 4 else None,
                }
            )

    return services


async def snmp_recon(
    target: str,
    port: int = 161,
    community: str = "public",
    timeout: float = 5.0,
    version: str = "2c",
) -> ProtocolResult:
    """Perform SNMP reconnaissance on a target.

    Args:
        target: IP address or hostname
        port: SNMP port (default: 161)
        community: SNMP community string (default: "public")
        timeout: Query timeout in seconds
        version: SNMP version ("1", "2c", "3")

    Returns:
        ProtocolResult with SNMP reconnaissance data
    """

    data: dict[str, Any] = {
        "target": target,
        "port": port,
        "community": community,
        "version": version,
    }

    try:
        # Try snmpwalk to get system information
        cmd = ["snmpwalk", "-v", version, "-c", community, target, "SYSTEM"]

        try:
            result = await asyncio.create_subprocess_exec(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                timeout=timeout,
            )
            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                data["system_info"] = _parse_snmp_output(stdout.decode())
            else:
                data["error"] = stderr.decode().strip()

        except FileNotFoundError:
            data["error"] = "snmpwalk not found"
        except Exception as e:
            data["error"] = str(e)

        # Try to get interface information
        try:
            cmd = ["snmpwalk", "-v", version, "-c", community, target, "IF-MIB::ifDescr"]
            result = await asyncio.create_subprocess_exec(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                timeout=timeout,
            )
            stdout, _ = await result.communicate()
            if result.returncode == 0:
                data["interfaces"] = _parse_snmp_output(stdout.decode())
        except Exception:
            # SNMP query/parse failed; leave interfaces data unset.
            pass

        return ProtocolResult(
            target=target,
            port=port,
            protocol="snmp",
            success=True,
            data=data,
        )

    except Exception as e:
        return ProtocolResult(
            target=target,
            port=port,
            protocol="snmp",
            success=False,
            error=str(e),
        )


def _parse_snmp_output(output: str) -> dict[str, str]:
    """Parse SNMP output to extract key-value pairs."""
    result = {}
    lines = output.strip().split("\n")

    for line in lines:
        if "=" in line:
            key, value = line.split("=", 1)
            key = key.strip().split()[-1]  # Get last part of key
            value = value.strip().strip('"')
            result[key] = value

    return result


async def ftp_recon(
    target: str,
    port: int = 21,
    timeout: float = 5.0,
    use_ftps: bool = False,
) -> ProtocolResult:
    """Perform FTP reconnaissance on a target.

    Args:
        target: IP address or hostname
        port: FTP port (default: 21)
        timeout: Connection timeout in seconds
        use_ftps: Use FTPS (FTP over SSL/TLS)

    Returns:
        ProtocolResult with FTP reconnaissance data
    """

    data: dict[str, Any] = {
        "target": target,
        "port": port,
        "ftps": use_ftps,
    }

    try:
        # Try to connect and get banner
        protocol = "ftps" if use_ftps else "ftp"

        try:
            # Use openssl for FTPS, netcat for FTP
            if use_ftps:
                cmd = [
                    "openssl",
                    "s_client",
                    "-connect",
                    f"{target}:{port}",
                    "-starttls",
                    "ftp",
                    "-quiet",
                ]
            else:
                cmd = ["nc", "-w", str(int(timeout)), target, str(port)]

            result = await asyncio.create_subprocess_exec(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                timeout=timeout + 2,
            )
            stdout, stderr = await result.communicate()

            if stdout:
                banner = stdout.decode().strip()
                data["banner"] = banner
                data["server"] = _parse_ftp_banner(banner)
            if stderr:
                data["error"] = stderr.decode().strip()

        except FileNotFoundError:
            data["error"] = "openssl or nc not found"
        except Exception as e:
            data["error"] = str(e)

        return ProtocolResult(
            target=target,
            port=port,
            protocol=protocol,
            success=True,
            data=data,
        )

    except Exception as e:
        return ProtocolResult(
            target=target,
            port=port,
            protocol="ftp",
            success=False,
            error=str(e),
        )


def _parse_ftp_banner(banner: str) -> dict[str, str]:
    """Parse FTP banner to extract server information."""
    result = {}

    # Common FTP server banners
    if "vsftpd" in banner.lower():
        result["server"] = "vsftpd"
        version_match = re.search(r"vsftpd\s+([0-9.]+)", banner)
        if version_match:
            result["version"] = version_match.group(1)

    elif "proftpd" in banner.lower():
        result["server"] = "ProFTPD"
        version_match = re.search(r"ProFTPD\s+([0-9.]+)", banner)
        if version_match:
            result["version"] = version_match.group(1)

    elif "pure-ftpd" in banner.lower():
        result["server"] = "Pure-FTPd"
        version_match = re.search(r"Pure-FTPd\s+([0-9.]+)", banner)
        if version_match:
            result["version"] = version_match.group(1)

    elif "microsoft" in banner.lower():
        result["server"] = "Microsoft FTP"

    elif "serv-u" in banner.lower():
        result["server"] = "Serv-U"

    return result


async def ssh_recon(
    target: str,
    port: int = 22,
    timeout: float = 5.0,
) -> ProtocolResult:
    """Perform SSH reconnaissance on a target.

    Args:
        target: IP address or hostname
        port: SSH port (default: 22)
        timeout: Connection timeout in seconds

    Returns:
        ProtocolResult with SSH reconnaissance data
    """

    data: dict[str, Any] = {
        "target": target,
        "port": port,
    }

    try:
        # Try to get SSH version and key information
        try:
            # Use ssh-keyscan to get host keys
            cmd = ["ssh-keyscan", "-p", str(port), "-t", "1", target]
            result = await asyncio.create_subprocess_exec(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                timeout=timeout,
            )
            stdout, stderr = await result.communicate()

            if result.returncode == 0:
                keys = stdout.decode().strip().split("\n")
                data["keys"] = []
                for key in keys:
                    if key.strip():
                        data["keys"].append(_parse_ssh_key(key))
            else:
                data["error"] = stderr.decode().strip()

        except FileNotFoundError:
            data["error"] = "ssh-keyscan not found"
        except Exception as e:
            data["error"] = str(e)

        # Try to connect and get SSH banner
        try:
            cmd = ["nc", "-w", str(int(timeout)), target, str(port)]
            result = await asyncio.create_subprocess_exec(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                timeout=timeout + 2,
            )
            stdout, _ = await result.communicate()
            if stdout:
                banner = stdout.decode().strip()
                data["banner"] = banner
                data["version"] = _parse_ssh_version(banner)
        except FileNotFoundError:
            # External tool not installed; skip SSH banner grab.
            pass
        except Exception:
            # Banner read/parse failed; leave SSH data unset.
            pass

        return ProtocolResult(
            target=target,
            port=port,
            protocol="ssh",
            success=True,
            data=data,
        )

    except Exception as e:
        return ProtocolResult(
            target=target,
            port=port,
            protocol="ssh",
            success=False,
            error=str(e),
        )


def _parse_ssh_key(key_line: str) -> dict[str, Any]:
    """Parse SSH key line to extract key information."""
    parts = key_line.split()
    result = {}

    if len(parts) >= 3:
        result["host"] = parts[0]
        result["port"] = parts[1] if len(parts) > 1 else "22"
        result["key_type"] = parts[2] if len(parts) > 2 else None
        result["key"] = " ".join(parts[3:]) if len(parts) > 3 else None

    return result


def _parse_ssh_version(banner: str) -> dict[str, str]:
    """Parse SSH banner to extract version information."""
    result = {}

    if "SSH" in banner:
        # Extract protocol version
        version_match = re.search(r"SSH-([0-9.]+)", banner)
        if version_match:
            result["protocol_version"] = version_match.group(1)

        # Extract server version
        server_match = re.search(r"OpenSSH_([0-9.]+)", banner)
        if server_match:
            result["server"] = "OpenSSH"
            result["version"] = server_match.group(1)
        else:
            server_match = re.search(r"([A-Za-z0-9._-]+)\s*SSH", banner)
            if server_match:
                result["server"] = server_match.group(1)

    return result
