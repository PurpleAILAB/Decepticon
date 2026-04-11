"""Tests for GraphQL schema helpers."""

from __future__ import annotations

from decepticon.tools.web.graphql import GraphQLSchema, introspection_query


def _intr(types: list[dict]) -> dict:
    return {
        "data": {
            "__schema": {
                "queryType": {"name": "Query"},
                "mutationType": {"name": "Mutation"},
                "subscriptionType": None,
                "types": types,
            }
        }
    }


def test_introspection_query_is_valid_graphql_text() -> None:
    q = introspection_query()
    assert "IntrospectionQuery" in q
    assert "__schema" in q


def test_parses_schema_and_finds_idor_candidates() -> None:
    types = [
        {
            "kind": "OBJECT",
            "name": "Query",
            "fields": [
                {
                    "name": "user",
                    "args": [{"name": "id", "type": {"kind": "SCALAR", "name": "ID"}}],
                    "type": {"kind": "OBJECT", "name": "User"},
                    "isDeprecated": False,
                },
                {
                    "name": "me",
                    "args": [],
                    "type": {"kind": "OBJECT", "name": "User"},
                    "isDeprecated": False,
                },
            ],
        },
        {
            "kind": "OBJECT",
            "name": "Mutation",
            "fields": [
                {
                    "name": "updateUser",
                    "args": [{"name": "userId", "type": {"kind": "SCALAR", "name": "ID"}}],
                    "type": {"kind": "OBJECT", "name": "User"},
                    "isDeprecated": False,
                }
            ],
        },
        {
            "kind": "OBJECT",
            "name": "User",
            "fields": [
                {
                    "name": "email",
                    "args": [],
                    "type": {"kind": "SCALAR", "name": "String"},
                    "isDeprecated": False,
                },
                {
                    "name": "passwordHash",
                    "args": [],
                    "type": {"kind": "SCALAR", "name": "String"},
                    "isDeprecated": False,
                },
            ],
        },
    ]
    schema = GraphQLSchema.from_introspection(_intr(types))
    assert schema.query_type == "Query"
    idor = schema.idor_candidates()
    names = [f.name for _, f in idor]
    assert "user" in names
    assert "updateUser" in names
    assert "me" not in names  # no id-ish arg


def test_generate_query_produces_selection_set() -> None:
    types = [
        {
            "kind": "OBJECT",
            "name": "Query",
            "fields": [
                {
                    "name": "user",
                    "args": [{"name": "id", "type": {"kind": "SCALAR", "name": "ID"}}],
                    "type": {"kind": "OBJECT", "name": "User"},
                    "isDeprecated": False,
                }
            ],
        },
        {
            "kind": "OBJECT",
            "name": "User",
            "fields": [
                {
                    "name": "email",
                    "args": [],
                    "type": {"kind": "SCALAR", "name": "String"},
                    "isDeprecated": False,
                }
            ],
        },
    ]
    schema = GraphQLSchema.from_introspection(_intr(types))
    q = schema.generate_query("user")
    assert "query" in q
    assert 'id: "1"' in q
    assert "email" in q


def test_type_unwrapping_handles_non_null_lists() -> None:
    types = [
        {
            "kind": "OBJECT",
            "name": "Query",
            "fields": [
                {
                    "name": "items",
                    "args": [],
                    "type": {
                        "kind": "NON_NULL",
                        "ofType": {
                            "kind": "LIST",
                            "ofType": {"kind": "OBJECT", "name": "Item"},
                        },
                    },
                    "isDeprecated": False,
                }
            ],
        },
        {"kind": "OBJECT", "name": "Item", "fields": []},
    ]
    schema = GraphQLSchema.from_introspection(_intr(types))
    q = schema.generate_query("items")
    assert q.startswith("query {")


def test_generate_query_populates_required_input_objects_and_enums() -> None:
    types = [
        {
            "kind": "OBJECT",
            "name": "Mutation",
            "fields": [
                {
                    "name": "createUser",
                    "args": [
                        {
                            "name": "input",
                            "type": {
                                "kind": "NON_NULL",
                                "ofType": {"kind": "INPUT_OBJECT", "name": "CreateUserInput"},
                            },
                        }
                    ],
                    "type": {"kind": "OBJECT", "name": "User"},
                    "isDeprecated": False,
                }
            ],
        },
        {
            "kind": "INPUT_OBJECT",
            "name": "CreateUserInput",
            "inputFields": [
                {
                    "name": "email",
                    "type": {"kind": "NON_NULL", "ofType": {"kind": "SCALAR", "name": "String"}},
                },
                {
                    "name": "role",
                    "type": {"kind": "NON_NULL", "ofType": {"kind": "ENUM", "name": "Role"}},
                },
            ],
        },
        {
            "kind": "ENUM",
            "name": "Role",
            "enumValues": [{"name": "ADMIN"}],
        },
        {
            "kind": "OBJECT",
            "name": "User",
            "fields": [
                {
                    "name": "id",
                    "args": [],
                    "type": {"kind": "SCALAR", "name": "ID"},
                    "isDeprecated": False,
                }
            ],
        },
    ]
    schema = GraphQLSchema.from_introspection(_intr(types))
    q = schema.generate_query("createUser", kind="mutation")
    assert 'input: { email: "test", role: ADMIN }' in q
    assert "{ id }" in q
