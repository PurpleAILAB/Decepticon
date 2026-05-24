"""Web exploitation tool suite.

A structured toolbelt for HTTP/S black-box work that goes beyond bash:

- ``jwt``      — JWT parse/forge/alg-confusion/secret-crack
- ``http``     — request/response history with replay + diff
- ``graphql``  — introspection + query auto-generation + field fuzzer
- ``oauth``    — OAuth 2.0 / OIDC state/nonce/PKCE flow analyser
- ``session``  — cookie entropy + framework fingerprint

Each module is pure-Python and dependency-free beyond the project's
existing stack (httpx, pydantic). Tools are exposed through
``decepticon.web.tools`` as LangChain ``@tool`` decorators.
"""

from __future__ import annotations

from decepticon.tools.web.graphql import GraphQLSchema, introspection_query
from decepticon.tools.web.http import HTTPHistory, HTTPRequest, HTTPResponse, HTTPSession
from decepticon.tools.web.jwt import JWTClaims, JWTHeader, JWTToken, forge_token, parse_token
from decepticon.tools.web.oauth import OAuthFinding, analyze_oauth_callback
from decepticon.tools.web.session import CookieAnalysis, analyze_cookie

__all__ = [
    "CookieAnalysis",
    "GraphQLSchema",
    "HTTPHistory",
    "HTTPRequest",
    "HTTPResponse",
    "HTTPSession",
    "JWTClaims",
    "JWTHeader",
    "JWTToken",
    "OAuthFinding",
    "analyze_cookie",
    "analyze_oauth_callback",
    "forge_token",
    "introspection_query",
    "parse_token",
]
