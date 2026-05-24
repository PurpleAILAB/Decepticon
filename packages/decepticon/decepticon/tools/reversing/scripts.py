"""Ghidra headless and radare2 script generators.

The agent picks a recon template, drops it to disk inside the sandbox,
and executes it via bash. These templates are opinionated toward bug
hunting — they dump xrefs, strings with categories, symbol summaries,
and function boundaries rather than trying to be full-project analyses.
"""

from __future__ import annotations

_GHIDRA_RECON = """# Ghidra headless recon script — dumps symbols, xrefs, strings, calls
# Usage:
#   analyzeHeadless /tmp/ghidra_proj proj -import {binary} -postScript {script_name}
#   (requires Ghidra installed; the wrapper can `apt install ghidra` or download)
# @category Decepticon
# @keybinding
# @menupath
# @toolbar

from __future__ import print_function
from ghidra.program.model.symbol import SourceType
from ghidra.program.model.listing import Function

program = currentProgram
print("[+] Program: {{}}".format(program.getName()))
print("[+] Language: {{}}".format(program.getLanguageID()))
print("[+] Image base: 0x{{:x}}".format(program.getImageBase().getOffset()))

# Dump every exported function + call graph neighbors
fm = program.getFunctionManager()
print("[+] Functions: {{}}".format(fm.getFunctionCount()))
for f in fm.getFunctions(True):
    name = f.getName()
    if not f.isThunk() and f.isExternal() is False:
        addrs = [str(a) for a in f.getEntryPoint()]
        print("fn {{}} @ {{}}".format(name, f.getEntryPoint()))

# Dump external imports (likely interesting APIs)
st = program.getSymbolTable()
for sym in st.getExternalSymbols():
    print("extern {{}} <- {{}}".format(sym.getName(), sym.getAddress()))

print("[+] Done.")
"""


_R2_RECON = r"""# radare2 recon script — paste into `r2 -i`
# Usage: r2 -q -i r2_recon.r2 {binary}
aaa
?e === info
i
?e === sections
iS
?e === strings (filtered)
iz~http|sk_|AKIA|api_key|password|secret|BEGIN|eyJ|JWT
?e === imports
ii
?e === exports
iE
?e === symbols (top 50)
is~FUNC[:50]
?e === functions (head)
afl[:50]
?e === xrefs to system/execve
axt sym.imp.system
axt sym.imp.execve
axt sym.imp.popen
?e === hashed entry
pvj
"""


def ghidra_recon_script(binary: str, script_name: str = "decepticon_recon.py") -> str:
    """Return a Ghidra headless script body targeting ``binary``."""
    return _GHIDRA_RECON.format(binary=binary, script_name=script_name)


def r2_recon_script(binary: str) -> str:
    """Return a radare2 script body; feed via ``r2 -q -i <script> <binary>``."""
    return _R2_RECON.format(binary=binary)
