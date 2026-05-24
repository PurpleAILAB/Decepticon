"""GraphQL introspection + query auto-generation.

Pure-Python — no ``graphql-core`` dependency. We hand-parse the
introspection JSON that every server emits so agents can:

1. Fetch the full schema.
2. Enumerate every Query / Mutation / Subscription field.
3. Auto-generate a valid default query for any field (args + selection
   set), used as a baseline for IDOR / auth-bypass / injection fuzzing.
4. Walk argument types to find ID-shaped inputs that are classic IDOR
   candidates.

This keeps the module entirely offline-testable: pass any SDL-less
introspection blob and we handle it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# The canonical introspection query GraphQL servers respond to.
INTROSPECTION_QUERY = """
query IntrospectionQuery {
  __schema {
    queryType { name }
    mutationType { name }
    subscriptionType { name }
    types {
      kind
      name
      description
      fields(includeDeprecated: true) {
        name
        description
        args {
          name
          description
          type { ...TypeRef }
          defaultValue
        }
        type { ...TypeRef }
        isDeprecated
      }
      inputFields {
        name
        type { ...TypeRef }
      }
      enumValues(includeDeprecated: true) { name }
    }
  }
}

fragment TypeRef on __Type {
  kind
  name
  ofType {
    kind
    name
    ofType {
      kind
      name
      ofType {
        kind
        name
      }
    }
  }
}
"""


def introspection_query() -> str:
    """Return the canonical GraphQL introspection query (single-line)."""
    return INTROSPECTION_QUERY.strip()


# ── Type unwrapping ─────────────────────────────────────────────────────


def _unwrap_type(type_ref: dict[str, Any] | None) -> tuple[str, bool, bool]:
    """Unwrap NON_NULL / LIST wrappers.

    Returns ``(base_type_name, is_list, is_non_null)``.
    """
    if type_ref is None:
        return ("Unknown", False, False)
    is_non_null = False
    is_list = False
    node = type_ref
    # Outer NON_NULL wraps the rest
    if node.get("kind") == "NON_NULL":
        is_non_null = True
        node = node.get("ofType") or {}
    if node.get("kind") == "LIST":
        is_list = True
        node = node.get("ofType") or {}
        if node.get("kind") == "NON_NULL":
            node = node.get("ofType") or {}
    name = node.get("name") or "Unknown"
    return name, is_list, is_non_null


# ── Schema wrapper ──────────────────────────────────────────────────────


@dataclass
class GraphQLField:
    name: str
    args: dict[str, dict[str, Any]]
    return_type: str
    is_list: bool
    deprecated: bool = False


@dataclass
class GraphQLSchema:
    query_type: str | None
    mutation_type: str | None
    subscription_type: str | None
    types: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_introspection(cls, data: dict[str, Any]) -> GraphQLSchema:
        """Parse a raw introspection response into a queryable schema."""
        root = data
        if "data" in data:
            root = data["data"]
        schema = root.get("__schema") or root.get("schema") or {}
        q = (schema.get("queryType") or {}).get("name")
        m = (schema.get("mutationType") or {}).get("name")
        s = (schema.get("subscriptionType") or {}).get("name")
        types: dict[str, dict[str, Any]] = {}
        for t in schema.get("types") or []:
            name = t.get("name")
            if name:
                types[name] = t
        return cls(query_type=q, mutation_type=m, subscription_type=s, types=types)

    def _type(self, name: str) -> dict[str, Any]:
        return self.types.get(name) or {}

    def fields_of(self, type_name: str) -> list[GraphQLField]:
        t = self._type(type_name)
        out: list[GraphQLField] = []
        for f in t.get("fields") or []:
            ret, is_list, _ = _unwrap_type(f.get("type"))
            args: dict[str, dict[str, Any]] = {}
            for a in f.get("args") or []:
                a_type, a_list, a_nn = _unwrap_type(a.get("type"))
                args[a["name"]] = {
                    "type": a_type,
                    "is_list": a_list,
                    "non_null": a_nn,
                    "default": a.get("defaultValue"),
                }
            out.append(
                GraphQLField(
                    name=f["name"],
                    args=args,
                    return_type=ret,
                    is_list=is_list,
                    deprecated=bool(f.get("isDeprecated")),
                )
            )
        return out

    def query_fields(self) -> list[GraphQLField]:
        return self.fields_of(self.query_type) if self.query_type else []

    def mutation_fields(self) -> list[GraphQLField]:
        return self.fields_of(self.mutation_type) if self.mutation_type else []

    def idor_candidates(self) -> list[tuple[str, GraphQLField]]:
        """Find Query/Mutation fields that take an ``id`` / ``*Id`` arg.

        These are the classic GraphQL IDOR hunting grounds — the agent
        should test each one with an ID belonging to another tenant.
        """
        candidates: list[tuple[str, GraphQLField]] = []
        for kind, fields in (
            ("Query", self.query_fields()),
            ("Mutation", self.mutation_fields()),
        ):
            for fld in fields:
                for arg_name in fld.args:
                    if arg_name == "id" or arg_name.lower().endswith("id"):
                        candidates.append((kind, fld))
                        break
        return candidates

    def generate_query(self, field_name: str, *, kind: str = "query") -> str:
        """Emit a minimal-but-valid query/mutation document for a field.

        Arguments are stubbed with safe placeholders (``1`` for Int IDs,
        ``"test"`` for strings). The selection set is populated with up
        to 3 scalar sub-fields from the return type.
        """
        if kind == "query":
            fields = {f.name: f for f in self.query_fields()}
        elif kind == "mutation":
            fields = {f.name: f for f in self.mutation_fields()}
        else:
            raise ValueError("kind must be 'query' or 'mutation'")
        fld = fields.get(field_name)
        if fld is None:
            raise KeyError(f"no {kind} field named {field_name!r}")

        arg_strs: list[str] = []
        for name, meta in fld.args.items():
            placeholder = self._placeholder(
                meta["type"],
                is_list=bool(meta["is_list"]),
                non_null=bool(meta["non_null"]),
            )
            arg_strs.append(f"{name}: {placeholder}")

        selection = self._default_selection(fld.return_type, depth=2)

        head = f"{kind} {{ {field_name}"
        if arg_strs:
            head += "(" + ", ".join(arg_strs) + ")"
        if selection:
            head += " " + selection
        head += " }"
        return head

    def _placeholder(
        self,
        type_name: str,
        *,
        is_list: bool = False,
        non_null: bool = False,
        depth: int = 4,
    ) -> str:
        if is_list:
            item = self._placeholder(type_name, depth=depth - 1)
            return f"[{item}]"

        lower = type_name.lower()
        if lower in ("int", "float"):
            return "1"
        if lower == "boolean":
            return "true"
        if lower == "id":
            return '"1"'
        if lower == "string":
            return '"test"'

        type_meta = self._type(type_name)
        kind = type_meta.get("kind")
        if kind == "ENUM":
            enum_values = type_meta.get("enumValues") or []
            first = enum_values[0]["name"] if enum_values else None
            return first or "null"
        if kind == "INPUT_OBJECT":
            if depth <= 0:
                return "{}" if non_null else "null"
            required_fields: list[str] = []
            for field in type_meta.get("inputFields") or []:
                field_type, field_is_list, field_non_null = _unwrap_type(field.get("type"))
                if not field_non_null:
                    continue
                child = self._placeholder(
                    field_type,
                    is_list=field_is_list,
                    non_null=field_non_null,
                    depth=depth - 1,
                )
                required_fields.append(f"{field['name']}: {child}")
            if required_fields:
                return "{ " + ", ".join(required_fields) + " }"
            return "{}" if non_null else "null"
        if kind == "SCALAR":
            return '"test"'
        return '"test"' if non_null else "null"

    def _default_selection(self, type_name: str, *, depth: int) -> str:
        if depth <= 0:
            return ""
        t = self._type(type_name)
        if not t or t.get("kind") not in ("OBJECT", "INTERFACE"):
            return ""
        picks: list[str] = []
        # Built-in scalars that introspection responses don't always include
        # in the ``types`` array.
        builtin_scalars = {"String", "Int", "Float", "Boolean", "ID"}
        for f in (t.get("fields") or [])[:8]:
            ret, is_list, _ = _unwrap_type(f.get("type"))
            if is_list:
                continue
            ret_t = self._type(ret)
            is_scalar = (
                ret in builtin_scalars
                or (ret_t and ret_t.get("kind") == "SCALAR")
                or (ret_t and ret_t.get("kind") == "ENUM")
            )
            if is_scalar:
                picks.append(f["name"])
            if len(picks) >= 3:
                break
        if not picks:
            return ""
        return "{ " + " ".join(picks) + " }"
