"""JS endpoint + parameter classification taxonomy (proposal item 9).

Ported from RedAmon's resource_enum/classification.py.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from langchain_core.tools import tool

from decepticon.tools.research._state import _json

PARAM_PATTERNS = {
    "id_params": [
        r"^id$",
        r"_id$",
        r"Id$",
        r"^uid$",
        r"^pid$",
        r"^aid$",
        r"^cid$",
        r"^user_?id$",
        r"^product_?id$",
        r"^item_?id$",
        r"^post_?id$",
        r"^article_?id$",
        r"^page_?id$",
        r"^cat_?id$",
        r"^category_?id$",
        r"^artist$",
        r"^cat$",
        r"^pic$",
        r"^num$",
        r"^no$",
        r"^index$",
    ],
    "file_params": [
        r"^file$",
        r"^filename$",
        r"^path$",
        r"^filepath$",
        r"^download$",
        r"^include$",
        r"^require$",
        r"^read$",
        r"^load$",
        r"^src$",
        r"^template$",
        r"^page$",
        r"^doc$",
        r"^document$",
        r"^img$",
        r"^image$",
        r"^attachment$",
    ],
    "search_params": [
        r"^q$",
        r"^query$",
        r"^search$",
        r"^s$",
        r"^keyword$",
        r"^term$",
        r"^find$",
        r"^filter$",
        r"^text$",
        r"^input$",
    ],
    "auth_params": [
        r"^user$",
        r"^username$",
        r"^login$",
        r"^email$",
        r"^mail$",
        r"^password$",
        r"^passwd$",
        r"^pass$",
        r"^pwd$",
        r"^token$",
        r"^auth$",
        r"^key$",
        r"^apikey$",
        r"^api_key$",
        r"^secret$",
        r"^session$",
        r"^cookie$",
    ],
    "redirect_params": [
        r"^url$",
        r"^redirect$",
        r"^return$",
        r"^next$",
        r"^goto$",
        r"^target$",
        r"^dest$",
        r"^destination$",
        r"^continue$",
        r"^ref$",
        r"^callback$",
        r"^returnurl$",
        r"^return_url$",
    ],
    "command_params": [
        r"^cmd$",
        r"^command$",
        r"^exec$",
        r"^execute$",
        r"^run$",
        r"^shell$",
        r"^system$",
        r"^ping$",
        r"^host$",
        r"^ip$",
    ],
}


def classify_parameter(param_name: str) -> str:
    """Classify a parameter name into a category.

    Categories: id_params, file_params, search_params, auth_params,
                redirect_params, command_params, other
    """
    param_lower = param_name.lower()
    for category, patterns in PARAM_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, param_lower, re.IGNORECASE):
                return category
    return "other"


def infer_parameter_type(param_name: str, sample_values: list[str]) -> str:
    """Infer the data type of a parameter from its name and sample values."""
    param_lower = param_name.lower()

    if sample_values:
        all_numeric = all(
            v.isdigit() or (v.startswith("-") and v[1:].isdigit()) for v in sample_values if v
        )
        if all_numeric:
            return "integer"

        if any("/" in v or "\\" in v or "." in v for v in sample_values if v):
            if any(
                v.endswith((".jpg", ".png", ".gif", ".pdf", ".txt", ".html", ".php", ".js"))
                for v in sample_values
                if v
            ):
                return "path"

        if any("@" in v and "." in v for v in sample_values if v):
            return "email"

        if any(v.startswith(("http://", "https://")) for v in sample_values if v):
            return "url"

    if any(p in param_lower for p in ["id", "num", "count", "page", "limit", "offset", "size"]):
        return "integer"
    if any(p in param_lower for p in ["file", "path", "dir", "template", "include"]):
        return "path"
    if any(p in param_lower for p in ["email", "mail"]):
        return "email"
    if any(p in param_lower for p in ["url", "link", "redirect", "callback"]):
        return "url"
    if any(p in param_lower for p in ["date", "time", "timestamp"]):
        return "datetime"
    if any(p in param_lower for p in ["bool", "flag", "enabled", "active", "is_"]):
        return "boolean"

    return "string"


def classify_endpoint(path: str, methods: list[str], params: dict[str, Any]) -> str:
    """Classify an endpoint into a category based on path, methods, and parameters."""
    path_lower = path.lower()

    auth_patterns = [
        "/login",
        "/signin",
        "/signup",
        "/register",
        "/logout",
        "/signout",
        "/auth",
        "/oauth",
        "/password",
        "/reset",
        "/forgot",
        "/session",
        "/token",
        "/jwt",
        "/sso",
    ]
    if any(p in path_lower for p in auth_patterns):
        return "authentication"

    admin_patterns = [
        "/admin",
        "/dashboard",
        "/panel",
        "/manage",
        "/control",
        "/backend",
        "/cms",
        "/wp-admin",
        "/administrator",
    ]
    if any(p in path_lower for p in admin_patterns):
        return "admin"

    api_patterns = ["/api/", "/v1/", "/v2/", "/v3/", "/rest/", "/graphql", "/json", "/xml", "/rpc"]
    if any(p in path_lower for p in api_patterns):
        return "api"

    file_patterns = [
        "/download",
        "/file",
        "/image",
        "/img",
        "/media",
        "/upload",
        "/attachment",
        "/document",
        "/doc",
        "/pdf",
        "/export",
    ]
    if any(p in path_lower for p in file_patterns):
        if any(p in path_lower for p in ["/upload", "/import"]):
            return "upload"
        return "file_access"

    search_patterns = ["/search", "/find", "/query", "/filter", "/browse"]
    if any(p in path_lower for p in search_patterns):
        return "search"

    body_params = params.get("body", [])
    if isinstance(body_params, list):
        body_param_names = []
        for p in body_params:
            if isinstance(p, dict) and "name" in p:
                body_param_names.append(str(p["name"]).lower())
            elif isinstance(p, str):
                body_param_names.append(p.lower())
        if any(p in body_param_names for p in ["username", "password", "email", "login"]):
            return "authentication"

    static_extensions = [
        ".html",
        ".htm",
        ".css",
        ".js",
        ".txt",
        ".xml",
        ".json",
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".svg",
        ".ico",
        ".webp",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".pdf",
        ".zip",
    ]
    if any(path_lower.endswith(ext) for ext in static_extensions):
        return "static"

    dynamic_extensions = [".php", ".asp", ".aspx", ".jsp", ".cgi", ".pl"]
    if any(path_lower.endswith(ext) for ext in dynamic_extensions):
        return "dynamic"

    if params.get("query"):
        return "dynamic"

    return "other"


@tool
def classify_endpoints(urls: list[str]) -> str:
    """Classify a list of URLs and their parameters into vulnerability-relevant categories.

    Returns a JSON object mapping each URL to its category, parsed parameters,
    and inferred parameter types/categories.

    Args:
        urls: List of URL strings to analyze.
    """
    results = {}
    for url in urls:
        try:
            parsed = urlparse(url)
            path = parsed.path or "/"
            query_params = []
            if parsed.query:
                for part in parsed.query.split("&"):
                    if "=" in part:
                        k, v = part.split("=", 1)
                    else:
                        k, v = part, ""
                    if k:
                        query_params.append({"name": k, "value": v})

            params = {"query": query_params, "body": []}
            category = classify_endpoint(path, ["GET"], params)

            pclasses = []
            ptypes = []
            for p in query_params:
                name = p["name"]
                val = p["value"]
                pclasses.append(classify_parameter(name))
                ptypes.append(infer_parameter_type(name, [val] if val else []))

            results[url] = {
                "category": category,
                "parameters": [p["name"] for p in query_params],
                "parameter_categories": pclasses,
                "parameter_types": ptypes,
            }
        except Exception as e:
            results[url] = {"error": str(e)}

    return _json(results)
