import subprocess
import sys


def test_research_tools_do_not_import_neo4j_at_module_load():
    # Base `pip install decepticon` (no neo4j extra) must still import the
    # research tools. The neo4j driver is loaded lazily only when a
    # Neo4jStore is constructed (decepticon/tools/research/neo4j_store.py).
    # A subprocess gives a clean module table independent of import order.
    code = (
        "import sys; "
        "import decepticon.tools.research.tools; "
        "assert 'neo4j' not in sys.modules, sorted(m for m in sys.modules if 'neo4j' in m)"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
