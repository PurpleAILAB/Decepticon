# Decepticon Context Engineering Architecture

> Decepticon 에이전트 프레임워크의 컨텍스트 엔지니어링 설계 문서.
> 적용 스킬: context-fundamentals, context-optimization, context-compression,
> tool-design, filesystem-context, deep-agents-core, deep-agents-memory

---

## 1. 설계 원칙

### 1.1 컨텍스트는 유한 자원이다

레드팀 recon 에이전트는 긴 세션 동안 대량의 tool output(nmap 스캔, DNS 레코드, 서브도메인 목록)을 생성합니다. 이 출력은 컨텍스트 윈도우의 80%+를 차지할 수 있으며, 에이전트의 추론 능력을 점진적으로 저하시킵니다.

**핵심 메트릭**: tokens-per-task (요청당 토큰이 아닌, 작업 완료까지의 총 토큰)

### 1.2 Progressive Disclosure

모든 지식을 시스템 프롬프트에 넣지 않습니다:
- **정적 컨텍스트**: 시스템 프롬프트 (페르소나, 핵심 규칙, 도구 가이드) — 항상 로드
- **동적 컨텍스트**: SKILL.md 파일 — 에이전트가 해당 작업 수행 시에만 로드

```
정적 로드 (항상):
  ├── recon.md 시스템 프롬프트 (~2K tokens)
  └── bash tool description (~500 tokens)

동적 로드 (on-demand):
  ├── /skills/passive-recon/SKILL.md   → WHOIS/DNS/서브도메인 작업 시
  ├── /skills/active-recon/SKILL.md    → nmap/서비스열거 작업 시
  └── /skills/reporting/SKILL.md       → 보고서 작성 시
```

### 1.3 Attention-Favored Positioning

모델은 컨텍스트의 시작과 끝에 더 집중합니다:

```
시스템 프롬프트 구조:
  <IDENTITY>          ← 시작: 핵심 페르소나
  <CRITICAL_RULES>    ← 시작 근처: 절대 위반 불가 규칙
  <ENVIRONMENT>       ← 중간: 참조 정보
  <TOOL_GUIDANCE>     ← 중간: 도구 사용법
  <RESPONSE_RULES>    ← 중간-끝: 출력 형식
  <WORKFLOW>          ← 끝 근처: 작업 순서
  <OPSEC_REMINDERS>   ← 끝: 보안 리마인더 (recency bias 활용)
```

---

## 2. 컨텍스트 최적화 전략

### 2.1 Observation Masking

Tool output은 컨텍스트 소비의 최대 원인입니다. Decepticon은 두 레벨에서 masking을 적용합니다:

**Level 1 — DockerSandbox Truncation** (`docker_sandbox.py`):
- 30,000자 초과 출력을 비대칭 절단 (head 60% / tail 40%)
- 에이전트에게 파일 저장 유도: "save full output with -oN or redirect"

**Level 2 — StreamingEngine Auto-Masking** (`streaming.py`):
- 3턴 이전 + 5,000자 초과 ToolMessage → compact summary로 자동 교체
- Preview (200자) + 메타데이터 (command, session) 유지
- 원본 데이터는 sandbox `/workspace/`에 파일로 보존

```python
# Masking 결과 예시
[Observation masked — 847 lines / 42,350 chars]
Command: nmap -sS -sV --top-ports 1000 10.0.1.50
Session: scan-1
Preview: Starting Nmap 7.94SVN ( https://nmap.org ) at 2025-...
[Use bash(session="scan-1") to re-read or check /workspace/ for saved files]
```

### 2.2 Filesystem as Scratch Pad

filesystem-context 스킬의 핵심 패턴: 대용량 tool output을 파일에 저장하고, 컨텍스트에는 참조만 유지.

**Recon 에이전트 파일 구조**:
```
/workspace/                          ← Docker sandbox 내부
├── recon_<target>_passive.txt       ← 패시브 리컨 raw 출력
├── recon_<target>_subdomains.txt    ← 서브도메인 목록
├── nmap_<target>_<type>.txt         ← nmap 결과 (human-readable)
├── nmap_<target>_<type>.xml         ← nmap 결과 (tool 연동)
└── report_<target>_final.md         ← 최종 보고서
```

**에이전트 학습**: 시스템 프롬프트와 tool description 모두에서 파일 저장을 유도:
- bash tool 에러 복구: "save full output to file with -oN"
- 시스템 프롬프트: "Long-running scans, save output to files"
- SKILL.md: 각 도구 명령어에 `-oN /workspace/` 포함

### 2.3 KV-Cache 최적화

시스템 프롬프트와 도구 정의는 모든 요청에서 동일합니다. 이를 활용하여 KV-cache 적중률을 극대화합니다:

```
캐시 안정 영역 (변경 없음):
  [시스템 프롬프트] [도구 정의] [스킬 메타데이터]

캐시 불안정 영역 (매 턴 변경):
  [메시지 히스토리] [현재 요청]
```

안정 요소를 앞에, 동적 요소를 뒤에 배치하여 prefix caching 효율을 높입니다.

---

## 3. 컨텍스트 압축 전략

### 3.1 /compact 명령어

CLI에서 수동으로 컨텍스트 압축을 트리거합니다:

```
you> /compact
Compacted 12 tool outputs (~8,500 tokens freed).
```

**동작**:
1. 최근 2턴을 제외한 모든 ToolMessage 검사
2. 5,000자 초과 출력을 compact summary로 교체
3. agent.update_state()로 상태 업데이트

### 3.2 자동 경고

15턴 도달 시 컨텍스트 열화 경고를 표시합니다:

```
[Context Warning] Long conversation detected.
Use /compact to free context budget or /clear to start fresh.
```

### 3.3 Anchored Iterative Summarization (향후)

향후 구현 예정인 구조화된 요약 전략:

```markdown
## Session Intent
[사용자가 달성하려는 목표]

## Targets Discovered
- example.com → 93.184.216.34 (Cloudflare CDN)
- api.example.com → 10.0.1.50 (직접 노출)

## Scans Completed
- Passive recon: WHOIS, DNS, subfinder, CT logs ✓
- Active recon: nmap top-1000 on api.example.com ✓
- UDP scan: pending

## High Priority Findings
1. [CRITICAL] MySQL 3306 exposed on api.example.com
2. [HIGH] Dangling CNAME: staging.example.com

## Files in /workspace/
- nmap_api_10.0.1.50_syn.txt (포트 스캔 결과)
- subdomains.txt (47 서브도메인)
- report_example.com_final.md (진행 중)

## Next Steps
1. UDP 스캔 실행
2. 최종 보고서 완성
```

이 구조는 artifact trail (파일 추적)을 명시적 섹션으로 유지하여 압축 시 정보 손실을 방지합니다.

---

## 4. 도구 설계 원칙

### 4.1 What/When/Returns 패턴

모든 도구 description은 4가지 질문에 답합니다:

| 질문 | bash tool 예시 |
|---|---|
| **WHAT** | Docker sandbox에서 bash 명령어 실행 |
| **WHEN** | recon 도구 실행, 파일 조작, 패키지 설치, 실행 상태 확인 |
| **RETURNS** | stdout, [STALLED], [TIMEOUT], [IDLE], [RUNNING] |
| **ERROR RECOVERY** | [STALLED] → wait/kill, [TIMEOUT] → check later, not found → apt install |

### 4.2 Consolidation Principle

도구 수를 최소화합니다. 현재 recon 에이전트는 단 1개의 커스텀 도구(bash)만 사용합니다.
이는 architectural reduction 원칙에 부합합니다:

- `bash()` 하나로 모든 recon 도구 실행 가능 (nmap, dig, curl 등)
- deepagents 내장 도구 (ls, read_file, write_file, grep, glob)로 파일 조작
- 별도 래퍼 도구 없이 에이전트의 추론 능력에 의존

### 4.3 에러 메시지 → 자가 복구

에러 메시지를 에이전트가 복구할 수 있도록 설계:

```
[STALLED] → "Options: 1. Wait 2. Interactive prompt 3. Kill: bash(command='C-c', is_input=True)"
[TIMEOUT] → "Check later: bash(session='scan-1')"
Command not found → (도구 description에 apt-get install 패턴 명시)
```

---

## 5. 메모리 아키텍처

### 5.1 Backend Routing (CompositeBackend)

```
CompositeBackend
├── /skills/* → FilesystemBackend (호스트 FS, read-only)
│   └── passive-recon/, active-recon/, reporting/ SKILL.md
└── default → DockerSandbox (컨테이너 내부)
    └── /workspace/* (스캔 결과, 보고서)
```

### 5.2 InMemoryStore (크로스세션 메모리)

```python
store = InMemoryStore()
agent = create_deep_agent(
    ...
    store=store,   # 세션 간 데이터 유지
)
```

사용 사례:
- 이전 세션의 타겟 정보 유지
- 에이전트 학습 내용 (사용자 선호, 과거 발견사항) 지속

### 5.3 Checkpointer (대화 히스토리)

```python
checkpointer = MemorySaver()  # 스레드 내 대화 상태 유지
```

- thread_id로 대화 분리
- /clear 시 새 thread_id 생성

---

## 6. Skills 시스템

### 6.1 Progressive Disclosure 흐름

```
1. 에이전트 시작 → SKILL.md frontmatter (name + description)만 로드
2. 사용자 요청 수신 → description 기반으로 관련 스킬 판단
3. 관련 스킬 활성화 → SKILL.md 전체 내용 로드
4. 스킬 지식으로 작업 수행
```

### 6.2 Description 설계

description은 에이전트의 스킬 선택을 결정하는 유일한 기준입니다.
구체적이고 행동 유발적이어야 합니다:

```yaml
# 나쁜 예
description: "Passive recon techniques"

# 좋은 예
description: "Use when gathering intelligence WITHOUT touching the target:
  WHOIS lookups, DNS record queries (dig), subdomain enumeration (subfinder),
  Certificate Transparency (crt.sh), HTTP header fingerprinting, and Google dorking.
  Includes command templates and analysis patterns."
```

### 6.3 Quick Reference 패턴

각 SKILL.md 상단에 복사-붙여넣기 가능한 Quick Reference 섹션을 배치합니다.
에이전트가 스킬을 로드하자마자 즉시 사용할 수 있는 명령어 템플릿을 제공합니다:

```bash
# Quick Reference — Common Scan Patterns
nmap -sS -sV -p 22,80,443,8080,8443 <TARGET> -oN /workspace/nmap_<TARGET>.txt
```

---

## 7. 데이터 흐름 요약

```
사용자 입력
  ↓
CLI (cli.py)
  ├── /compact → _compact_context() → observation masking
  ├── /clear → 새 thread_id → 컨텍스트 리셋
  └── 일반 입력 → StreamingEngine.run()
      ↓
StreamingEngine
  ├── _mask_old_observations() → 오래된 verbose output 압축
  └── agent.stream() → deepagents 에이전트 실행
      ↓
Recon Agent (deepagents)
  ├── 시스템 프롬프트 (recon.md) → XML 태그 구조
  ├── 스킬 로드 (progressive disclosure)
  └── bash() tool call
      ↓
DockerSandbox.execute_tmux()
  ├── tmux 세션 관리 (병렬 실행)
  ├── PS1 마커 기반 완료 탐지
  ├── _truncate() → 비대칭 출력 절단
  └── 결과 → 에이전트 컨텍스트로 반환
      ↓
CLIRenderer
  └── Kali Linux 스타일 출력 렌더링
```
