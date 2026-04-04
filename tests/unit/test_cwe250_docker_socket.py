"""Test that docker-compose.yml does NOT expose the raw Docker socket to the langgraph container.

CWE-250: Execution with Unnecessary Privileges
Finding: /var/run/docker.sock mounted into langgraph container enables container escape.

The raw Docker socket gives full Docker API access regardless of :ro flag.
The fix replaces the direct socket mount with a Docker socket proxy that restricts
API access to only the endpoints needed (exec, inspect, cp).
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

# Resolve docker-compose.yml from project root (two levels up from tests/unit/)
COMPOSE_PATH = pathlib.Path(__file__).resolve().parents[2] / "docker-compose.yml"


@pytest.fixture
def compose() -> dict:
    with open(COMPOSE_PATH) as f:
        return yaml.safe_load(f)


class TestDockerSocketNotExposed:
    """Verify the langgraph container does not have direct Docker socket access."""

    def test_langgraph_no_raw_docker_socket(self, compose: dict):
        """The langgraph service must NOT mount /var/run/docker.sock directly.

        Mounting the raw socket (even :ro) gives full Docker API access,
        enabling container escape to the host.
        """
        langgraph = compose["services"]["langgraph"]
        volumes = langgraph.get("volumes", [])

        for vol in volumes:
            vol_str = str(vol)
            assert "/var/run/docker.sock" not in vol_str, (
                f"Raw Docker socket mounted into langgraph container: {vol_str}. "
                f"Use docker-socket-proxy instead."
            )

    def test_docker_socket_proxy_exists(self, compose: dict):
        """A docker-socket-proxy service must be defined to mediate Docker API access."""
        services = compose.get("services", {})
        proxy_service = services.get("docker-socket-proxy")
        assert proxy_service is not None, (
            "Missing 'docker-socket-proxy' service. "
            "A restricted proxy is needed to mediate Docker API access."
        )

    def test_docker_socket_proxy_restricts_operations(self, compose: dict):
        """The docker-socket-proxy must deny container creation and other dangerous ops."""
        proxy = compose["services"]["docker-socket-proxy"]
        env = proxy.get("environment", [])

        # Normalize environment to dict
        if isinstance(env, list):
            env_dict = {}
            for item in env:
                if "=" in str(item):
                    k, v = str(item).split("=", 1)
                    env_dict[k.strip()] = v.strip()
            env = env_dict

        # These dangerous operations should be explicitly denied (0)
        dangerous_ops = [
            "CONTAINERS_CREATE",
            "CONTAINERS_DELETE",
            "IMAGES",
            "VOLUMES",
            "NETWORKS",
            "SWARM",
            "BUILD",
        ]
        for op in dangerous_ops:
            val = env.get(op, None)
            if val is not None:
                assert str(val) == "0", (
                    f"docker-socket-proxy has {op}={val}, expected 0 (deny)"
                )

    def test_docker_socket_proxy_has_socket(self, compose: dict):
        """The proxy service must have the actual Docker socket mounted."""
        proxy = compose["services"]["docker-socket-proxy"]
        volumes = proxy.get("volumes", [])
        has_socket = any("/var/run/docker.sock" in str(v) for v in volumes)
        assert has_socket, "docker-socket-proxy must mount /var/run/docker.sock"

    def test_langgraph_uses_docker_host_env(self, compose: dict):
        """The langgraph service must set DOCKER_HOST to point to the proxy."""
        langgraph = compose["services"]["langgraph"]
        env = langgraph.get("environment", [])

        # Normalize to dict
        if isinstance(env, list):
            env_dict = {}
            for item in env:
                if "=" in str(item):
                    k, v = str(item).split("=", 1)
                    env_dict[k.strip()] = v.strip()
            env = env_dict

        docker_host = env.get("DOCKER_HOST")
        assert docker_host is not None, (
            "langgraph must set DOCKER_HOST to point to docker-socket-proxy"
        )
        assert "docker-socket-proxy" in docker_host or "socket-proxy" in docker_host, (
            f"DOCKER_HOST should point to docker-socket-proxy, got: {docker_host}"
        )

    def test_no_service_mounts_raw_socket_except_proxy(self, compose: dict):
        """Only the docker-socket-proxy service should mount the Docker socket."""
        for name, svc in compose.get("services", {}).items():
            if name == "docker-socket-proxy":
                continue
            volumes = svc.get("volumes", [])
            for vol in volumes:
                assert "/var/run/docker.sock" not in str(vol), (
                    f"Service '{name}' mounts raw Docker socket: {vol}. "
                    f"Only docker-socket-proxy should have socket access."
                )
