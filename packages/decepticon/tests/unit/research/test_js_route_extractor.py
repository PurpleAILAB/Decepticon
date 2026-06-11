"""Unit tests for the front-end JavaScript route extractor."""

from __future__ import annotations

import json

import pytest

from decepticon.tools.research.js_route_extractor import (
    classify_param,
    classify_route,
    extract_routes,
    js_route_extractor,
)


def _values(result: dict) -> set[str]:
    return {r["value"] for r in result["routes"]}


class TestExtractionPatterns:
    def test_fetch_call(self) -> None:
        result = extract_routes('fetch("/api/v1/users")')
        assert "/api/v1/users" in _values(result)
        route = next(r for r in result["routes"] if r["value"] == "/api/v1/users")
        assert "fetch" in route["sources"]

    def test_fetch_template_literal(self) -> None:
        result = extract_routes("fetch(`/users/${userId}/profile`)")
        assert "/users/${userId}/profile" in _values(result)

    def test_axios_verb_records_method(self) -> None:
        result = extract_routes('axios.get("/api/orders")')
        route = next(r for r in result["routes"] if r["value"] == "/api/orders")
        assert route["methods"] == ["GET"]
        assert "axios" in route["sources"]

    def test_axios_config_object_url(self) -> None:
        result = extract_routes('axios({ method: "post", url: "/api/login" })')
        assert "/api/login" in _values(result)

    def test_xhr_open_captures_method(self) -> None:
        result = extract_routes('xhr.open("DELETE", "/api/session")')
        route = next(r for r in result["routes"] if r["value"] == "/api/session")
        assert route["methods"] == ["DELETE"]

    def test_jquery_ajax_url(self) -> None:
        result = extract_routes('$.ajax({ url: "/admin/config", type: "GET" })')
        assert "/admin/config" in _values(result)

    def test_jquery_shorthand(self) -> None:
        result = extract_routes('$.post("/upload/avatar", data)')
        route = next(r for r in result["routes"] if r["value"] == "/upload/avatar")
        assert route["methods"] == ["POST"]

    def test_server_router_definition(self) -> None:
        result = extract_routes('router.get("/admin/users", handler)')
        route = next(r for r in result["routes"] if r["value"] == "/admin/users")
        assert route["methods"] == ["GET"]
        assert "router" in route["sources"]

    def test_spa_route_table(self) -> None:
        result = extract_routes('{ path: "/dashboard", component: Dashboard }')
        assert "/dashboard" in _values(result)

    def test_absolute_url(self) -> None:
        result = extract_routes('const base = "https://api.example.com/v2/search";')
        assert "https://api.example.com/v2/search" in _values(result)

    def test_bare_path_literal(self) -> None:
        result = extract_routes('const ENDPOINT = "/api/v1/products";')
        assert "/api/v1/products" in _values(result)

    def test_at_least_eight_distinct_patterns_fire(self) -> None:
        js = """
        fetch("/api/a");
        axios.get("/api/b");
        xhr.open("GET", "/api/c");
        $.ajax({ url: "/api/d" });
        router.post("/api/e", h);
        const r = { path: "/api/f" };
        const u = "https://h.example.com/api/g";
        const lit = "/api/h";
        const tpl = `/api/${id}/i`;
        """
        result = extract_routes(js)
        sources = {s for r in result["routes"] for s in r["sources"]}
        assert len(sources) >= 8


class TestDeduplication:
    def test_same_route_merges_methods_and_sources(self) -> None:
        js = 'axios.get("/api/x"); axios.post("/api/x");'
        result = extract_routes(js)
        route = next(r for r in result["routes"] if r["value"] == "/api/x")
        assert sorted(route["methods"]) == ["GET", "POST"]

    def test_total_routes_counts_unique_values(self) -> None:
        js = 'fetch("/api/y"); fetch("/api/y");'
        result = extract_routes(js)
        assert result["summary"]["total_routes"] == 1


class TestRouteClassification:
    @pytest.mark.parametrize(
        "route,category",
        [
            ("/api/login", "auth"),
            ("/oauth/token", "auth"),
            ("/admin/users", "admin"),
            ("/api/v1/users", "api"),
            ("/upload/file", "upload"),
            ("/search?q=x", "search"),
            ("/download?file=a", "file_access"),
        ],
    )
    def test_category_assignment(self, route: str, category: str) -> None:
        assert category in classify_route(route)

    def test_route_may_have_multiple_categories(self) -> None:
        cats = classify_route("/api/admin/login")
        assert {"api", "admin", "auth"} <= set(cats)

    def test_unclassified_route_has_no_categories(self) -> None:
        assert classify_route("/about") == []

    def test_categories_index_populated(self) -> None:
        result = extract_routes('fetch("/admin/settings")')
        assert "/admin/settings" in result["categories"]["admin"]


class TestParameterClassification:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("id", "id_params"),
            ("user_id", "id_params"),
            ("userId", "id_params"),
            ("account", "id_params"),
            ("file", "file_params"),
            ("filename", "file_params"),
            ("path", "file_params"),
            ("template", "file_params"),
            ("redirect", "redirect_params"),
            ("redirect_uri", "redirect_params"),
            ("returnUrl", "redirect_params"),
            ("next", "redirect_params"),
            ("cmd", "command_params"),
            ("command", "command_params"),
            ("exec", "command_params"),
        ],
    )
    def test_known_param_classes(self, name: str, expected: str) -> None:
        cls, hint = classify_param(name)
        assert cls == expected
        assert hint

    def test_unknown_param_is_unclassified(self) -> None:
        assert classify_param("locale") == (None, None)

    def test_short_keyword_does_not_match_substring(self) -> None:
        # "idea" must NOT be classified as id_params via a naive substring.
        assert classify_param("idea") == (None, None)

    def test_empty_name(self) -> None:
        assert classify_param("") == (None, None)

    def test_severity_priority_command_over_id(self) -> None:
        # A param whose tokens hit both command and id rules takes command.
        cls, _ = classify_param("exec_id")
        assert cls == "command_params"


class TestParameterExtraction:
    def test_query_params_from_path_literal(self) -> None:
        result = extract_routes('fetch("/profile?id=5&file=report.pdf")')
        params = {p["name"]: p["classification"] for p in result["parameters"]}
        assert params["id"] == "id_params"
        assert params["file"] == "file_params"

    def test_template_literal_params(self) -> None:
        result = extract_routes('fetch(`/redirect?url=${dest}&id=${u}`)')
        params = {p["name"]: p["classification"] for p in result["parameters"]}
        assert params["url"] == "redirect_params"
        assert params["id"] == "id_params"

    def test_absolute_url_query_params(self) -> None:
        result = extract_routes('const u = "https://x.example.com/run?cmd=ls";')
        params = {p["name"]: p["classification"] for p in result["parameters"]}
        assert params["cmd"] == "command_params"

    def test_sensitive_parameter_count(self) -> None:
        result = extract_routes('fetch("/x?id=1&cmd=2&locale=en")')
        assert result["summary"]["sensitive_parameters"] == 2
        assert result["summary"]["total_parameters"] == 3

    def test_route_without_query_has_no_params(self) -> None:
        result = extract_routes('fetch("/api/health")')
        route = next(r for r in result["routes"] if r["value"] == "/api/health")
        assert route["params"] == []


class TestNoiseRejection:
    def test_non_route_strings_ignored(self) -> None:
        js = 'const x = "hello world"; const y = "image/png"; const z = "1.2.3";'
        result = extract_routes(js)
        assert result["routes"] == []

    def test_bare_slash_rejected(self) -> None:
        result = extract_routes('const sep = "/"; const dbl = "//";')
        assert _values(result) == set()

    def test_empty_input(self) -> None:
        result = extract_routes("")
        assert result["summary"]["total_routes"] == 0
        assert result["routes"] == []

    def test_non_string_raises(self) -> None:
        with pytest.raises(TypeError):
            extract_routes(None)  # type: ignore[arg-type]


class TestToolInterface:
    async def test_tool_returns_valid_json(self) -> None:
        out = await js_route_extractor.ainvoke({"js_content": 'fetch("/api/users?id=1")'})
        payload = json.loads(out)
        assert payload["summary"]["total_routes"] == 1
        assert payload["parameters"][0]["classification"] == "id_params"

    async def test_tool_handles_empty_content(self) -> None:
        out = await js_route_extractor.ainvoke({"js_content": ""})
        payload = json.loads(out)
        assert payload["summary"]["total_routes"] == 0

    async def test_tool_realistic_bundle(self) -> None:
        js = """
        const api = {
          login: () => fetch("/api/auth/login", {method: "POST"}),
          getUser: (id) => axios.get(`/api/users/${id}?include=profile`),
          adminPanel: () => $.get("/admin/dashboard"),
          download: (f) => window.location = "/files/download?file=" + f,
          redirectTo: (u) => location.href = "/go?redirect_uri=" + u,
        };
        const routes = [{ path: "/search" }, { path: "/upload" }];
        """
        out = await js_route_extractor.ainvoke({"js_content": js})
        payload = json.loads(out)
        cats = payload["categories"]
        assert "auth" in cats
        assert "admin" in cats
        assert "api" in cats
        param_classes = {p["classification"] for p in payload["parameters"]}
        assert "redirect_params" in param_classes
        assert "file_params" in param_classes
