# OPPLANMiddleware Design Document (v2)

## Context

**Claude Code : Coding = Decepticon : Red Team Testing**

Claude Code의 V2 Task 시스템(`TaskCreate`, `TaskGet`, `TaskUpdate`, `TaskList`)은
코딩 작업을 위한 개별 CRUD 기반 태스크 추적 도구다.
Decepticon은 레드팀 테스트 도메인에 특화된 에이전트이므로,
**OPPLAN(Operations Plan)** 이라는 도메인 특화 태스크 추적 시스템을 구현한다.

### Claude Code Task 시스템 → OPPLAN 매핑

| Claude Code Task Tool | OPPLAN Tool | 패턴 |
|---|---|---|
| `TaskCreate(subject, description, ...)` | `add_objective(title, phase, ...)` | 개별 항목 생성, 자동 ID 부여 |
| `TaskGet(taskId)` | `get_objective(objective_id)` | 단일 항목 상세 조회 (staleness 방지) |
| `TaskList()` | `list_objectives()` | 전체 목록 + 진행률 요약 |
| `TaskUpdate(taskId, status, ...)` | `update_objective(objective_id, status, ...)` | 상태/메타데이터 변경 |
| *(implicit: project init)* | `create_opplan(engagement_name, ...)` | 인게이지먼트 초기화 |
| `EnterPlanMode` / `ExitPlanMode` | Planning Phase → Execution Phase | 오케스트레이터가 직접 계획 |

### 핵심 설계 원칙 (Claude Code에서 차용)

1. **개별 CRUD** — 전체 덮어쓰기가 아닌 개별 생성/조회/수정
2. **읽기 후 쓰기** — `get_objective` → `update_objective` (staleness 방지)
3. **의존성 그래프** — `blocked_by` 필드로 kill chain 의존성 표현
4. **소유자 추적** — 어떤 서브에이전트가 실행 중인지 기록
5. **메인 에이전트가 OPPLAN 제어** — 서브에이전트는 OPPLAN 도구 없음
6. **동적 상태 주입** — 매 LLM 호출마다 진행 테이블을 시스템 프롬프트에 삽입

### 변경 동기

현재 오케스트레이터(`decepticon.py`)는:
1. `TodoListMiddleware` — 범용 todo 추적 (도메인 맥락 없음)
2. `write_file("opplan.json")` — 수동 JSON 파일 작성으로 OPPLAN 업데이트
3. 별도 `planner` 서브에이전트 — OPPLAN 생성을 포함한 모든 계획 문서 담당

OPPLANMiddleware로 전환하면:
- **단일 소스** — OPPLAN이 LangGraph state에 존재 (opplan.json 파일 불필요)
- **오케스트레이터 직접 제어** — Claude Code처럼 메인 에이전트가 OPPLAN 관리
- **Soundwave 분리** — planner에서 OPPLAN 책임 제거, 문서작성 전문으로 축소
- **Pydantic 검증** — `core/schemas.py`의 `Objective` 스키마 재사용
- **Claude Code Task 패턴** — 5개 CRUD 도구로 세밀한 제어

---

## Architecture

### 에이전트 역할 재정의

```
Decepticon (오케스트레이터) — 메가트론
    │
    │  OPPLAN 직접 제어: create_opplan, add_objective,
    │  get_objective, list_objectives, update_objective
    │
    ├─ Soundwave (정보/문서 작성) — 정보장교
    │   └─ RoE, CONOPS, Deconfliction Plan 생성
    │       (OPPLAN은 담당하지 않음)
    │
    ├─ Recon (정찰 에이전트)
    ├─ Exploit (침투 에이전트)
    └─ PostExploit (후속 작전 에이전트)
```

**Soundwave**: 트랜스포머 세계관의 디셉티콘 정보장교.
데이터 수집/처리/보고서 작성 전문. 기존 `planner`에서 이름 변경 및 역할 축소.
OPPLAN 생성 책임은 오케스트레이터로 이전.

### 전체 흐름

```
┌─────────────────────────────────────────────────────────────────┐
│ Decepticon Orchestrator                                         │
│                                                                 │
│ [Planning Phase] — Claude Code EnterPlanMode 대응               │
│   1. 사용자 인터뷰 (타겟, 범위, 위협 모델)                       │
│   2. task("soundwave") → RoE, CONOPS, Deconfliction 문서 생성   │
│   3. create_opplan() → 인게이지먼트 초기화                       │
│   4. add_objective() × N → 개별 objective 추가                  │
│   5. 사용자에게 OPPLAN 리뷰 요청 (선택적)                        │
│                                                                 │
│ [Execution Phase] — Claude Code ExitPlanMode 대응               │
│   1. list_objectives() → 전체 현황 파악                         │
│   2. get_objective(next) → 다음 objective 상세 확인              │
│   3. update_objective(id, "in-progress") → 실행 시작 표시        │
│   4. task("recon/exploit/...") → 서브에이전트 위임               │
│   5. get_objective(id) → 최신 상태 확인 (staleness 방지)         │
│   6. update_objective(id, "passed/blocked", notes) → 결과 반영  │
│   7. 반복: 모든 objective 완료까지                               │
│                                                                 │
│ [Re-planning] — 실행 중 OPPLAN 수정                             │
│   add_objective() → 새 objective 추가                           │
│   update_objective(id, "out-of-scope") → 범위 밖 표시           │
│                                                                 │
│ OPPLANMiddleware:                                               │
│   wrap_model_call → 동적 OPPLAN 진행 테이블 시스템 프롬프트 주입  │
│   awrap_tool_call → state 기반 도구 인터셉트                     │
│   after_model → 병렬 update 검증                                │
└─────────────────────────────────────────────────────────────────┘
```

### 서브에이전트에는 미들웨어 불필요

서브에이전트(soundwave, recon, exploit, postexploit)는 OPPLANMiddleware가 **필요 없다**.
- 오케스트레이터가 `task()` 위임 시 objective 컨텍스트를 프롬프트에 포함
- 서브에이전트는 자신의 임무만 실행하고 결과를 반환
- OPPLAN 상태 업데이트는 **오케스트레이터만** 수행

### opplan.json 파일 불필요

OPPLAN이 LangGraph state에 존재하므로:
- 파일시스템에 별도 JSON 파일 불필요
- LangGraph checkpointer가 state 영속성 보장

---

## Implementation

### File: `decepticon/middleware/opplan.py`

#### State Schema

```python
class OPPLANState(AgentState):
    """Extended agent state with OPPLAN objectives."""

    objectives: Annotated[NotRequired[list[dict]], OmitFromInput]
    """List of OPPLAN objectives (serialized Objective models)."""

    engagement_name: Annotated[NotRequired[str], OmitFromInput]
    """Current engagement name."""

    threat_profile: Annotated[NotRequired[str], OmitFromInput]
    """Threat actor profile for context injection."""

    objective_counter: Annotated[NotRequired[int], OmitFromInput]
    """Auto-increment counter for objective IDs (like Task high water mark)."""
```

#### Tool 1: `create_opplan` — 인게이지먼트 초기화

Claude Code의 "프로젝트/태스크 리스트 초기화"에 대응.

```python
@tool(description=(
    "Initialize a new OPPLAN for a red team engagement. "
    "Sets engagement metadata. Call this before adding objectives. "
    "If an OPPLAN already exists, this replaces it (objectives cleared)."
))
def create_opplan(
    engagement_name: str,
    threat_profile: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command[Any]:
    """Initialize OPPLAN — engagement metadata only, objectives added separately."""
    return Command(update={
        "objectives": [],
        "engagement_name": engagement_name,
        "threat_profile": threat_profile,
        "objective_counter": 0,
        "messages": [ToolMessage(
            content=(
                f"OPPLAN initialized: {engagement_name}. "
                f"Threat profile: {threat_profile}. "
                f"Use add_objective() to add objectives."
            ),
            tool_call_id=tool_call_id,
        )],
    })
```

#### Tool 2: `add_objective` — 개별 objective 추가

Claude Code `TaskCreate` 패턴. 개별 생성, 자동 ID 부여.

```python
@tool(description=(
    "Add a single objective to the OPPLAN. Auto-generates an ID (OBJ-001, OBJ-002, ...). "
    "Each objective must be completable in ONE sub-agent context window. "
    "Use blocked_by to set kill chain dependencies."
))
def add_objective(
    title: str,
    phase: str,
    description: str,
    acceptance_criteria: list[str],
    priority: int,
    mitre: str = "",
    risk_level: str = "low",
    opsec_notes: str = "",
    blocked_by: list[str] | None = None,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command[Any]:
    """Add one objective — intercepted by middleware for ID generation."""
    # Intercepted by awrap_tool_call (needs state for counter + objectives list)
    ...
```

미들웨어에서 인터셉트:
```python
def _handle_add_objective(self, state, args, tool_call_id):
    counter = state.get("objective_counter", 0) + 1
    obj_id = f"OBJ-{counter:03d}"

    obj_dict = {
        "id": obj_id,
        "title": args["title"],
        "phase": args["phase"],
        "description": args["description"],
        "acceptance_criteria": args["acceptance_criteria"],
        "priority": args["priority"],
        "status": "pending",
        "mitre": args.get("mitre", ""),
        "risk_level": args.get("risk_level", "low"),
        "opsec_notes": args.get("opsec_notes", ""),
        "blocked_by": args.get("blocked_by", []),
        "owner": "",
        "notes": "",
    }

    # Pydantic validation
    try:
        Objective(**obj_dict)
    except Exception as e:
        return ToolMessage(
            content=f"Validation failed: {e}",
            tool_call_id=tool_call_id,
            status="error",
        )

    objectives = list(state.get("objectives", []))
    objectives.append(obj_dict)

    return Command(update={
        "objectives": objectives,
        "objective_counter": counter,
        "messages": [ToolMessage(
            content=f"Added {obj_id}: {args['title']} (phase: {args['phase']}, priority: {args['priority']})",
            tool_call_id=tool_call_id,
        )],
    })
```

#### Tool 3: `get_objective` — 단일 objective 상세 조회

Claude Code `TaskGet` 패턴. staleness 방지를 위해 update 전에 호출.

```python
@tool(description=(
    "Read a single objective's full details. "
    "ALWAYS call this before update_objective to check current state (staleness prevention)."
))
def get_objective(
    objective_id: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command[Any]:
    """Read one objective — intercepted by middleware to read from state."""
    ...
```

미들웨어에서 인터셉트:
```python
def _handle_get_objective(self, state, objective_id, tool_call_id):
    objectives = state.get("objectives", [])
    target = next((o for o in objectives if o.get("id") == objective_id), None)

    if not target:
        available = ", ".join(o.get("id", "?") for o in objectives)
        return ToolMessage(
            content=f"Objective '{objective_id}' not found. Available: {available}",
            tool_call_id=tool_call_id,
            status="error",
        )

    # Detailed single-objective view
    lines = [
        f"## {target['id']} [{target.get('status', 'pending').upper()}]",
        f"Title: {target['title']}",
        f"Phase: {target['phase']} | Priority: {target['priority']}",
        f"MITRE: {target.get('mitre', 'n/a')} | Risk: {target.get('risk_level', 'n/a')}",
        f"Description: {target['description']}",
    ]

    criteria = target.get("acceptance_criteria", [])
    if criteria:
        lines.append("Acceptance Criteria:")
        check = "x" if target.get("status") == "passed" else " "
        for c in criteria:
            lines.append(f"  - [{check}] {c}")

    blocked_by = target.get("blocked_by", [])
    if blocked_by:
        lines.append(f"Blocked By: {', '.join(blocked_by)}")

    owner = target.get("owner", "")
    if owner:
        lines.append(f"Owner: {owner}")

    opsec = target.get("opsec_notes", "")
    if opsec:
        lines.append(f"OPSEC: {opsec}")

    notes = target.get("notes", "")
    if notes:
        lines.append(f"Notes: {notes}")

    return ToolMessage(content="\n".join(lines), tool_call_id=tool_call_id)
```

#### Tool 4: `list_objectives` — 전체 목록 + 진행률

Claude Code `TaskList` 패턴. 빠른 상황 파악용.

```python
@tool(description=(
    "List all OPPLAN objectives with progress summary. "
    "Returns engagement overview, objective table, and next recommended objective."
))
def list_objectives(
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command[Any]:
    """List all objectives — intercepted by middleware to read from state."""
    ...
```

미들웨어에서 인터셉트 — 기존 `_format_opplan_for_agent()` 재사용.

#### Tool 5: `update_objective` — 상태/메타데이터 변경

Claude Code `TaskUpdate` 패턴. 상태 전이 검증 + 의존성 관리.

```python
@tool(description=(
    "Update a single objective. MUST call get_objective first (staleness prevention). "
    "Valid transitions: pending→in-progress, in-progress→passed/blocked/out-of-scope, "
    "blocked→in-progress (retry). "
    "Include evidence when marking passed, failure reason when marking blocked."
))
def update_objective(
    objective_id: str,
    status: str | None = None,
    notes: str | None = None,
    owner: str | None = None,
    add_blocked_by: list[str] | None = None,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command[Any]:
    """Update one objective — intercepted by middleware for state access."""
    ...
```

미들웨어에서 인터셉트:
```python
def _handle_update_objective(self, state, args, tool_call_id):
    objective_id = args["objective_id"]
    objectives = [dict(o) for o in state.get("objectives", [])]
    target = next((o for o in objectives if o.get("id") == objective_id), None)

    if not target:
        return ToolMessage(...)  # not found error

    updated_fields = []

    # Status change with transition validation
    new_status = args.get("status")
    if new_status is not None:
        current = target.get("status", "pending")
        if not self._is_valid_transition(current, new_status):
            return ToolMessage(
                content=f"Invalid transition: {current} → {new_status}. "
                        f"Valid: {self._valid_next(current)}",
                tool_call_id=tool_call_id,
                status="error",
            )

        # Check blocked_by dependencies (like Claude Code's blocker check)
        if new_status == "in-progress":
            blocked_by = target.get("blocked_by", [])
            unresolved = [
                bid for bid in blocked_by
                if any(
                    o.get("id") == bid and o.get("status") not in ("passed", "out-of-scope")
                    for o in objectives
                )
            ]
            if unresolved:
                return ToolMessage(
                    content=f"Cannot start {objective_id}: blocked by {', '.join(unresolved)}",
                    tool_call_id=tool_call_id,
                    status="error",
                )

        target["status"] = new_status
        updated_fields.append("status")

    # Notes
    if args.get("notes") is not None:
        target["notes"] = args["notes"]
        updated_fields.append("notes")

    # Owner (which sub-agent is executing)
    if args.get("owner") is not None:
        target["owner"] = args["owner"]
        updated_fields.append("owner")

    # Add blocked_by dependencies
    if args.get("add_blocked_by"):
        existing = set(target.get("blocked_by", []))
        for bid in args["add_blocked_by"]:
            existing.add(bid)
        target["blocked_by"] = sorted(existing)
        updated_fields.append("blocked_by")

    total = len(objectives)
    passed = sum(1 for o in objectives if o.get("status") == "passed")

    return Command(update={
        "objectives": objectives,
        "messages": [ToolMessage(
            content=(
                f"Updated {objective_id}: {', '.join(updated_fields)}. "
                f"Progress: {passed}/{total} passed."
            ),
            tool_call_id=tool_call_id,
        )],
    })
```

### State Transition Rules

```
                     create_opplan() + add_objective()
                          │
                          ↓
                    ┌──────────┐
                    │ PENDING  │
                    └────┬─────┘
                         │ update_objective(status="in-progress")
                         │ (checks blocked_by dependencies)
                         ↓
                    ┌──────────────┐
            ┌──────│ IN-PROGRESS   │──────┐
            │      └──────┬────────┘      │
            │             │               │
            ↓             ↓               ↓
      ┌──────────┐  ┌──────────┐  ┌──────────────┐
      │  PASSED  │  │ BLOCKED  │  │ OUT-OF-SCOPE │
      │(terminal)│  │          │  │  (terminal)  │
      └──────────┘  └────┬─────┘  └──────────────┘
                         │
                         │ retry (different approach)
                         ↓
                    ┌──────────────┐
                    │ IN-PROGRESS  │
                    └──────────────┘
```

`blocked → in-progress` 재시도 허용 이유: 레드팀에서는 다른 공격 벡터로
재시도하는 것이 일반적이다.

### Middleware Class

```python
class OPPLANMiddleware(AgentMiddleware):
    state_schema = OPPLANState

    def __init__(self):
        super().__init__()
        self.tools = _make_tools()

    # wrap_model_call: 동적 OPPLAN 진행 테이블 주입
    # awrap_tool_call: add_objective, get_objective, list_objectives, update_objective 인터셉트
    # after_model: 병렬 update_objective 호출 검증
```

### wrap_model_call: 동적 상태 주입

Claude Code `TodoListMiddleware`는 정적 도구 사용법만 주입.
OPPLANMiddleware는 매 LLM 호출마다 **동적 진행 테이블**을 주입:

```
<OPPLAN_STATUS>
Engagement: acme-external-2026
Threat Profile: APT29-like, nation-state sophistication
Progress: 3/7 passed, 1 blocked, 1 in-progress, 2 pending

| ID | Phase | Title | Status | Priority | Owner |
|---|---|---|---|---|---|
| OBJ-001 | recon | Subdomain Enum | PASSED | 1 | recon |
| OBJ-002 | recon | Port Scan | >>IN-PROGRESS<< | 2 | recon |
...

**Next Objective**: OBJ-003 — Web Vuln Scan
  Acceptance Criteria:
    - [ ] Identify OWASP Top 10 vulnerabilities
    - [ ] Validate at least one exploitable finding
</OPPLAN_STATUS>
```

### awrap_tool_call: 도구 인터셉트

5개 도구 중 4개는 state 접근이 필요하므로 미들웨어에서 인터셉트:

| 도구 | 인터셉트 | 이유 |
|---|---|---|
| `create_opplan` | **아니오** — 패스스루 | Command가 직접 state 업데이트 |
| `add_objective` | **예** | state에서 counter 읽기 + objectives에 추가 |
| `get_objective` | **예** | state에서 단일 objective 읽기 |
| `list_objectives` | **예** | state에서 전체 objectives 읽기 |
| `update_objective` | **예** | state에서 읽고 → 검증 → 수정 → Command 반환 |

### after_model: 병렬 호출 검증

Claude Code `TaskUpdate`는 `isConcurrencySafe: true`로 병렬 호출 허용.
OPPLAN `update_objective`는 **병렬 호출 금지** (state 충돌 방지):

```python
def after_model(self, state, runtime):
    # ... last AI message의 tool_calls 검사
    update_calls = [tc for tc in tool_calls if tc["name"] == "update_objective"]
    if len(update_calls) > 1:
        return {"messages": [ToolMessage(status="error", ...) for tc in update_calls]}
```

---

## Integration

### File Changes

#### New Files

| File | Description |
|---|---|
| `decepticon/middleware/opplan.py` | OPPLANMiddleware 구현 (5-tool CRUD) |
| `decepticon/agents/soundwave.py` | Soundwave 에이전트 (planner.py에서 리네임 + 역할 축소) |
| `decepticon/agents/prompts/soundwave.md` | Soundwave 프롬프트 |

#### Modified Files

| File | Change |
|---|---|
| `decepticon/middleware/__init__.py` | `OPPLANMiddleware` export 추가 |
| `decepticon/agents/decepticon.py` | `TodoListMiddleware` → `OPPLANMiddleware`, planner → soundwave |
| `decepticon/agents/prompts/decepticon.md` | OPPLAN 도구 사용 + Soundwave 역할 반영 |

#### Removed Files

| File | Reason |
|---|---|
| `decepticon/agents/planner.py` | `soundwave.py`로 교체 |
| `decepticon/agents/prompts/planning.md` | `soundwave.md`로 교체 |

#### Unchanged Files

| File | Reason |
|---|---|
| `decepticon/core/schemas.py` | `Objective`, `OPPLAN` 스키마 재사용 (변경 없음) |
| `decepticon/agents/recon.py` | OPPLANMiddleware 불필요 (서브에이전트) |
| `decepticon/agents/exploit.py` | OPPLANMiddleware 불필요 (서브에이전트) |
| `decepticon/agents/postexploit.py` | OPPLANMiddleware 불필요 (서브에이전트) |

### Orchestrator Middleware Stack

```python
# Before
middleware = [
    DecepticonSkillsMiddleware(...),
    FilesystemMiddlewareNoExecute(...),
    SubAgentMiddleware(..., subagents=[planner, recon, exploit, postexploit]),
    TodoListMiddleware(),  # ← 제거
]

# After
middleware = [
    EngagementContextMiddleware(),
    DecepticonSkillsMiddleware(...),
    FilesystemMiddlewareNoExecute(...),
    SubAgentMiddleware(..., subagents=[recon, exploit, postexploit, analyst, reverser, contract_auditor, cloud_hunter, ad_operator]),
    OPPLANMiddleware(),  # ← 교체 (5-tool CRUD)
]
```

### Prompt Update: `agents/prompts/decepticon.md`

```markdown
## Execution Loop (Before)
1. **Read** `/workspace/plan/opplan.json`
2. **Select** next pending objective
3. **Delegate** via task()
4. **Evaluate** result
5. **Update** opplan.json via write_file

## Execution Loop (After)
1. **list_objectives()** → 전체 현황 + 다음 objective 확인
2. **get_objective(id)** → 상세 정보 확인 (staleness 방지)
3. **update_objective(id, "in-progress", owner="recon")** → 실행 시작
4. **task("recon", ...)** → 서브에이전트 위임
5. **get_objective(id)** → 최신 상태 확인
6. **update_objective(id, "passed/blocked", notes="...")** → 결과 반영
```

---

## Claude Code 패턴과의 상세 비교

### 1. TaskCreate vs add_objective

| 속성 | Claude Code `TaskCreate` | Decepticon `add_objective` |
|---|---|---|
| ID 생성 | auto-increment (1, 2, 3, ...) | `OBJ-{counter:03d}` (OBJ-001, OBJ-002, ...) |
| 스키마 | `{subject, description, activeForm}` | `{title, phase, description, acceptance_criteria, priority, mitre, risk_level, ...}` |
| 의존성 | `addBlockedBy` (TaskUpdate에서) | `blocked_by` (생성 시 설정 가능) |
| 검증 | Zod schema | Pydantic `Objective` model |
| 저장 | 파일시스템 (`~/.claude/tasks/`) | LangGraph state |

### 2. TaskGet vs get_objective

| 속성 | Claude Code `TaskGet` | Decepticon `get_objective` |
|---|---|---|
| 조회 | 단일 task by ID | 단일 objective by ID |
| 용도 | staleness 방지 (update 전 조회) | 동일 |
| 응답 | `{id, subject, description, status, blocks, blockedBy}` | 상세 objective (criteria, MITRE, OPSEC 포함) |

### 3. TaskList vs list_objectives

| 속성 | Claude Code `TaskList` | Decepticon `list_objectives` |
|---|---|---|
| 응답 | `tasks: Array<{id, subject, status, owner, blockedBy}>` | 진행 테이블 + 다음 objective 추천 |
| 필터 | 없음 (전체 반환) | 선택적 phase/status 필터 가능 |

### 4. TaskUpdate vs update_objective

| 속성 | Claude Code `TaskUpdate` | Decepticon `update_objective` |
|---|---|---|
| 상태 | pending/in_progress/completed/deleted | pending/in-progress/passed/blocked/out-of-scope |
| 전이 검증 | 없음 (자유 전이) | 엄격한 FSM (blocked→in-progress 재시도만 허용) |
| 의존성 검사 | blocker가 있으면 claim 실패 | in-progress 전환 시 blocked_by 검사 |
| 소유자 | `owner` (에이전트 이름) | `owner` (서브에이전트 이름) |
| 병렬 안전 | `isConcurrencySafe: true` | **병렬 금지** (after_model에서 검증) |
| 삭제 | `status: "deleted"` | `status: "out-of-scope"` (soft delete) |

### 5. 동적 상태 주입

```
Claude Code TodoListMiddleware:
  wrap_model_call → 정적 시스템 프롬프트만 주입 (도구 사용법)
  현재 tasks는 프롬프트에 주입되지 않음

Decepticon OPPLANMiddleware:
  wrap_model_call → 정적 프롬프트 + 동적 OPPLAN 진행 테이블
  매 LLM 호출마다 objectives 상태, progress, next objective 포함
```

이것이 Claude Code 대비 **도메인 특화 개선점**. 레드팀 오케스트레이터는
매 판단마다 현재 전장 상황을 알아야 한다.

### 6. Verification Nudge

Claude Code는 3+ 태스크 완료 시 검증 에이전트 spawn 권고.
Decepticon은 모든 objective 완료 시 최종 보고서 생성 권고:

```python
# list_objectives 응답에서
if all_passed:
    "→ ALL OBJECTIVES COMPLETE — Generate final engagement report."
```

---

## Schemas

### Objective model 확장 (core/schemas.py)

기존 `Objective` 모델에 `blocked_by`와 `owner` 필드 추가:

```python
class Objective(BaseModel):
    id: str
    phase: ObjectivePhase
    title: str
    description: str
    acceptance_criteria: list[str]
    priority: int
    status: ObjectiveStatus = ObjectiveStatus.PENDING
    mitre: str = ""
    risk_level: RiskLevel = RiskLevel.LOW
    opsec_notes: str = ""
    notes: str = ""
    # New fields (Claude Code Task patterns)
    blocked_by: list[str] = Field(default_factory=list, description="Objective IDs that must complete first")
    owner: str = Field(default="", description="Sub-agent currently executing this objective")
```
