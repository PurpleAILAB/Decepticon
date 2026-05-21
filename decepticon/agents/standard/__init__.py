"""Standard bundle — OSS-shipped agents.

Contains the official ``decepticon`` main agent and its 8 subagents
(recon, exploit, postexploit, analyst, reverser, contract_auditor,
cloud_hunter, ad_operator), plus the ``soundwave`` standalone planning
agent. Each subagent module exposes a ``SUBAGENT_SPEC`` declaring
``bundle="standard"`` and ``parent_agents=("decepticon",)`` so the
plugin loader attaches them when the main agent is constructed.
"""
