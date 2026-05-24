"""Symbol triage — spot security-relevant imports at a glance.

We don't parse full ELF symbol tables here; instead we pattern-match
the extracted strings for known-dangerous API names. This is good
enough to prioritise binaries: if the blob imports both ``strcpy`` and
``system`` we know to spend more time on it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# API categories
_DANGEROUS_C = {
    "strcpy",
    "strcat",
    "sprintf",
    "vsprintf",
    "gets",
    "scanf",
    "memcpy",
    "alloca",
    "realpath",
    "tmpnam",
    "mktemp",
}
_COMMAND_EXEC = {
    "system",
    "popen",
    "execl",
    "execle",
    "execlp",
    "execv",
    "execve",
    "execvp",
    "posix_spawn",
    "fork",
    "vfork",
    "ShellExecuteA",
    "ShellExecuteW",
    "CreateProcessA",
    "CreateProcessW",
    "WinExec",
    "CreateProcess",
}
_NETWORK = {
    "socket",
    "connect",
    "bind",
    "listen",
    "accept",
    "recv",
    "send",
    "sendto",
    "recvfrom",
    "getaddrinfo",
    "gethostbyname",
    "inet_pton",
    "WSAStartup",
    "WSASocketA",
    "WSAConnect",
    "curl_easy_init",
    "curl_easy_perform",
}
_CRYPTO = {
    "EVP_EncryptInit",
    "EVP_DecryptInit",
    "AES_encrypt",
    "DES_encrypt",
    "RAND_bytes",
    "RAND_pseudo_bytes",
    "CryptAcquireContextA",
    "CryptEncrypt",
    "CryptDecrypt",
    "BCryptEncrypt",
    "BCryptDecrypt",
}
_DYNAMIC_CODE = {
    "dlopen",
    "dlsym",
    "LoadLibraryA",
    "LoadLibraryW",
    "GetProcAddress",
    "VirtualAlloc",
    "VirtualProtect",
    "mprotect",
    "mmap",
    "CreateRemoteThread",
    "NtMapViewOfSection",
    "NtCreateThreadEx",
}
_ANTI_DEBUG = {
    "IsDebuggerPresent",
    "CheckRemoteDebuggerPresent",
    "NtQueryInformationProcess",
    "NtSetInformationThread",
    "OutputDebugStringA",
    "ptrace",
}
_SANITIZER = {
    "__asan_report_load",
    "__asan_init",
    "__ubsan_handle",
    "__sanitizer_cov_trace",
    "__hwasan_init",
    "__msan_init",
    "__tsan_init",
}


@dataclass
class SymbolReport:
    dangerous_c: list[str] = field(default_factory=list)
    command_exec: list[str] = field(default_factory=list)
    network: list[str] = field(default_factory=list)
    crypto: list[str] = field(default_factory=list)
    dynamic_code: list[str] = field(default_factory=list)
    anti_debug: list[str] = field(default_factory=list)
    sanitizers: list[str] = field(default_factory=list)

    def risk_score(self) -> int:
        """Monotonic-ish risk heuristic used for binary triage."""
        score = 0
        score += len(self.command_exec) * 4
        score += len(self.dynamic_code) * 3
        score += len(self.dangerous_c) * 3
        score += len(self.network) * 2
        score += len(self.crypto) * 1
        score += len(self.anti_debug) * 2
        score -= len(self.sanitizers) * 2  # sanitized builds are safer
        return max(score, 0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dangerous_c": list(self.dangerous_c),
            "command_exec": list(self.command_exec),
            "network": list(self.network),
            "crypto": list(self.crypto),
            "dynamic_code": list(self.dynamic_code),
            "anti_debug": list(self.anti_debug),
            "sanitizers": list(self.sanitizers),
            "risk_score": self.risk_score(),
        }


def summarize_symbols(symbols: list[str]) -> SymbolReport:
    """Bucket a flat list of symbol names into security categories."""
    report = SymbolReport()
    sym_set = set(symbols)
    report.dangerous_c = sorted(sym_set & _DANGEROUS_C)
    report.command_exec = sorted(sym_set & _COMMAND_EXEC)
    report.network = sorted(sym_set & _NETWORK)
    report.crypto = sorted(sym_set & _CRYPTO)
    report.dynamic_code = sorted(sym_set & _DYNAMIC_CODE)
    report.anti_debug = sorted(sym_set & _ANTI_DEBUG)
    # Sanitizer names often have a common prefix — use startswith semantics
    report.sanitizers = sorted(s for s in symbols if any(s.startswith(p) for p in _SANITIZER))
    return report
