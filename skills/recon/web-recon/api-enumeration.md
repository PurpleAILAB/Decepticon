---
name: web-api-enumeration
description: "REST API discovery, GraphQL detection, parameter fuzzing."
allowed-tools: Bash Read Write
metadata:
  subdomain: reconnaissance
  when_to_use: "API enumeration, swagger, openapi, GraphQL, introspection, parameter fuzzing, REST endpoints"
  tags: api-enum, graphql, swagger, parameter-discovery
  mitre_attack: T1595.003
---

# Web API Enumeration & Parameter Discovery

Surface REST/GraphQL endpoints and the parameter surface of known endpoints. This sub-skill covers everything between "the directory tree is mapped" and "I know what to fuzz".

## 1. API Endpoint Enumeration

### REST API Discovery
```bash
# Common API paths
ffuf -u https://<target>/api/FUZZ -w /usr/share/wordlists/api-endpoints.txt -mc 200,201,401,403,405

# Version enumeration
for v in v1 v2 v3; do
    ffuf -u "https://<target>/api/$v/FUZZ" -w api-wordlist.txt -mc 200,201,401,403
done

# Check for Swagger/OpenAPI docs
for doc in swagger.json openapi.json api-docs docs/api swagger/v1/swagger.json; do
    code=$(curl -s -o /dev/null -w "%{http_code}" "https://<target>/$doc")
    echo "$code $doc"
done
```

### GraphQL Detection
```bash
# Common GraphQL endpoints
for path in graphql graphiql playground api/graphql; do
    # Introspection query
    curl -s -X POST "https://<target>/$path" \
        -H "Content-Type: application/json" \
        -d '{"query":"{__schema{types{name}}}"}' | head -c 200
    echo " → $path"
done
```

### API Key/Token Patterns
Look for in responses:
- `api_key`, `apiKey`, `access_token`, `bearer`, `jwt`
- Base64-encoded blobs in cookies or headers
- `Authorization` header patterns

## 2. Parameter Discovery

```bash
# GET parameter fuzzing
ffuf -u "https://<target>/page?FUZZ=test" -w /usr/share/wordlists/params.txt -mc 200 -fs <default_size>

# POST parameter fuzzing
ffuf -u "https://<target>/login" -X POST \
    -d "FUZZ=test" -H "Content-Type: application/x-www-form-urlencoded" \
    -w /usr/share/wordlists/params.txt -mc 200 -fs <default_size>

# Header fuzzing
ffuf -u "https://<target>/" -H "FUZZ: test" \
    -w /usr/share/wordlists/headers.txt -mc 200 -fs <default_size>
```
