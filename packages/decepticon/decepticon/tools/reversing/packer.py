"""Packer / obfuscation detection via entropy + signature matching.

High entropy (>7.0 bits/byte) across the whole binary is a strong
signal of compression or encryption. Specific packer signatures
(UPX! header, ASPack, Themida stubs) pin the diagnosis.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PackerVerdict:
    likely_packed: bool
    entropy: float
    packer: str | None = None
    signatures: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "likely_packed": self.likely_packed,
            "entropy": round(self.entropy, 3),
            "packer": self.packer,
            "signatures": list(self.signatures),
            "notes": list(self.notes),
        }


def shannon_entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = Counter(data)
    length = len(data)
    entropy = 0.0
    for c in counts.values():
        p = c / length
        entropy -= p * math.log2(p)
    return entropy


# Packer signatures (magic bytes or section-name hints)
_SIGNATURES: list[tuple[bytes, str]] = [
    (b"UPX!", "UPX"),
    (b"UPX0", "UPX"),
    (b"UPX1", "UPX"),
    (b"UPX2", "UPX"),
    (b".aspack", "ASPack"),
    (b".adata", "ASPack"),
    (b"PEBundle", "PEBundle"),
    (b".petite", "Petite"),
    (b".Themida", "Themida"),
    (b".vmp0", "VMProtect"),
    (b".vmp1", "VMProtect"),
    (b".enigma1", "Enigma Protector"),
    (b".enigma2", "Enigma Protector"),
    (b".MPRESS1", "MPRESS"),
    (b".MPRESS2", "MPRESS"),
    (b"ByDwing", "ASPack"),
    (b".mew", "MEW"),
    (b"NSPack", "NsPack"),
    (b"PECompact2", "PECompact"),
    (b"Y0da", "Yoda's Protector"),
]


def detect_packer(data: bytes | str | Path) -> PackerVerdict:
    """Compute entropy + match packer signatures."""
    if isinstance(data, (str, Path)):
        blob = Path(data).read_bytes()
    else:
        blob = data

    if not blob:
        return PackerVerdict(likely_packed=False, entropy=0.0, notes=["empty file"])

    entropy = shannon_entropy(blob)

    hits: list[str] = []
    packer: str | None = None
    for sig, name in _SIGNATURES:
        if sig in blob:
            hits.append(name)
            packer = packer or name

    likely = entropy > 7.0 or packer is not None
    verdict = PackerVerdict(likely_packed=likely, entropy=entropy, packer=packer, signatures=hits)
    if entropy > 7.5 and not packer:
        verdict.notes.append(
            f"entropy {entropy:.2f} is very high — compressed or encrypted, but no signature. "
            "Consider custom packer."
        )
    elif entropy < 4.0:
        verdict.notes.append(f"entropy {entropy:.2f} is low — likely unpacked or text-heavy.")
    return verdict
