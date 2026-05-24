"""Decepticon server-side custom HTTP surface mounted on LangGraph platform.

LangGraph Platform's ``langgraph.json`` allows mounting a user-defined
ASGI app via the ``http.app`` field. We use that hook to add endpoints
that aren't part of the standard /threads | /assistants | /runs surface
but still need to live inside the same process — currently:

  - ``/_decepticon/bundles`` — runtime plugin bundle enable/disable, see
    :mod:`decepticon.server.plugins_api`.

Anything mounted here runs inside the same Python process as the agent
graphs, so it can mutate ``langgraph_api.graph.GRAPHS`` and call
``register_graph()`` directly — that's what makes runtime plugin
activation possible without a container restart.
"""
