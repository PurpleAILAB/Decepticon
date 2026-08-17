---
name: reverser-protocol-reverse
description: Reverse engineering of custom binary protocols, Protobuf/gRPC, WebSocket frames, and private RPC — PCAP-driven frame-layout recovery, message dictionaries, and state-machine reconstruction.
metadata:
  subdomain: reverse-engineering
  when_to_use: "protocol reverse custom binary protocol protobuf grpc flatbuffers messagepack websocket mqtt pcap frame layout kaitai imhex dissector message format state machine"
  mitre_attack: T1040
  upstream_ref: "reverse-skill:skills/protocol-reverse (github.com/zhaoxuya520/reverse-skill @ ea582f3, MIT)"
---

# Protocol Reverse Engineering

For custom TCP/UDP binary protocols, Protobuf/gRPC/FlatBuffers/
MessagePack payloads, WebSocket/MQTT/private RPC, and PCAP-driven
format recovery. Pure HTTP parameter signing goes to
`/skills/standard/reverser/js-reverse/SKILL.md`; firmware-resident
protocol stacks pair with `/skills/standard/reverser/firmware/SKILL.md`.

Any live interaction with a remote endpoint requires the engagement
scope to cover it — capture and offline analysis first; replay only
what RoE allows.

## 1. Capture and triage

```bash
# Sources: PCAP / proxy export / client logs / the client binary itself
tshark -r /workspace/cap.pcap -T fields \
  -e frame.number -e ip.src -e tcp.payload > /workspace/proto/frames.txt
```

```text
□ Mark direction (C→S / S→C); note handshake, heartbeat, reconnect
□ Fixed header? Magic bytes? Length field? TLV? Fixed-size records?
□ Compression (zlib/gzip/lz4) or in-frame encryption (AES/ChaCha)?
```

## 2. Recover the frame layout

```text
□ Align many same-type messages; mark invariant bytes vs
  auto-incrementing sequence fields
□ Length field: big/little endian, header included or not
□ Integrity: CRC16/32, checksum, or HMAC — locate its position
□ Sketch the state machine: Connect → Auth → Ready → Req/Resp → Close
```

Tooling: Wireshark draft dissector, ImHex or 010 Editor templates, or
Kaitai Struct for a compilable spec. Iterate the template until it
parses every captured frame of that type cleanly.

## 3. Serialization and crypto layers

```bash
# Unknown protobuf → decode without .proto
protoc --decode_raw < payload.bin
# blackboxprotobuf / pbtk to infer a .proto from samples
```

- gRPC = HTTP/2 headers + length-prefixed protobuf bodies; split at the
  5-byte message prefix
- Encrypted frames: find key derivation in the client — native side via
  `/skills/standard/reverser/ghidra/SKILL.md`, JS side via
  `js-reverse`, mobile via the mobile lane
- Replay testing: in-scope only, harmless fields first, sensitive
  operations last and only if authorized

## 4. Deliverables (mandatory)

```text
- Message-type table: name / opcode / direction / fields
- At least one reproducible decode command or script
- Evidence: raw hex excerpt + decoded result, sanitized of real
  target identifiers
```

## 5. Record

```
kg_add_node("service", label="<protocol> on <host:port>",
  props={"layout_spec": "/workspace/proto/", "msg_types": N,
         "state_machine": "Connect-Auth-Ready-ReqResp-Close",
         "key": "proto-reverse:<host>-<port>"})
```

C2-shaped protocols found during malware work: cross-link with
`/skills/standard/reverser/malware-triage/SKILL.md` findings.
