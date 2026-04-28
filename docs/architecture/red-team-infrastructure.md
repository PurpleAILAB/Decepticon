# Decepticon 레드팀 인프라 아키텍처

> Decepticon의 레드팀 인프라 구성과 현업 레드팀 인프라와의 매핑을 정의하는 설계 문서.
> 분리형 C2(Command & Control) 모듈 아키텍처를 포함한 전체 공격 인프라 토폴로지를 다룬다.

---

## 1. 현업 레드팀 인프라 개념

### 1.1 Three-Space 모델

현업 레드팀 인프라는 세 개의 논리적 공간으로 분리된다:

| 공간 | 역할 | 구성 요소 |
|------|------|-----------|
| **Red Team Space** | 오퍼레이터 통제 영역 (On-Premise) | 팀 서버(C2), 도구, 설정, 크리덴셜, PCAP/로그 |
| **Gray Space** | 인터넷 노출 중계 영역 (Cloud/VPS) | 리다이렉터, CDN, Domain Fronting 서버 |
| **Victim Space** | 공격 대상 조직 네트워크 | 비콘/에이전트가 실행되는 타겟 시스템 |

```mermaid
graph LR
    subgraph RedTeamSpace["Red Team Space (On-Premise)"]
        OP[오퍼레이터]
        TS[팀 서버 / C2]
        TOOLS[공격 도구]
    end

    subgraph GraySpace["Gray Space (Cloud/VPS)"]
        RD[리다이렉터]
        CDN[CDN / Domain Fronting]
    end

    subgraph VictimSpace["Victim Space (Target Org)"]
        B1[Beacon 1]
        B2[Beacon 2]
        T1[타겟 서버 1]
        T2[타겟 서버 2]
    end

    OP --> TS
    TS -->|SSH 터널| RD
    RD -->|HTTPS| B1
    RD -->|DNS| B2
    B1 --- T1
    B2 --- T2
```

### 1.2 핵심 용어

| 용어 | 설명 |
|------|------|
| **C2 (Command & Control)** | 오퍼레이터가 타겟 내 비콘을 원격 제어하는 중앙 서버 |
| **팀 서버 (Team Server)** | C2 소프트웨어가 실행되는 물리/가상 호스트 |
| **리스너 (Listener)** | 비콘 콜백을 수신하는 핸들러 (프로토콜, 포트, 페이로드 타입 설정) |
| **비콘 (Beacon/Implant)** | 타겟 시스템에서 실행되는 에이전트. C2로 주기적 콜백하며 명령 수신 |
| **리다이렉터 (Redirector)** | C2 트래픽을 중계하여 팀 서버 IP를 은닉하는 프록시 |

---

## 2. Decepticon 인프라 매핑

### 2.1 현업 vs Decepticon 대응 관계

Decepticon은 통제된 Docker 환경에서 운영되므로 OPSEC 기반 인프라 분리(리다이렉터)는 적용하지 않는다. 단, 팀 서버(C2)는 **별도 컨테이너로 분리**하여 모듈 교체가 가능한 구조를 채택한다.

| 현업 구성 요소 | 현업 역할 | Decepticon 대응 | 비고 |
|---|---|---|---|
| **오퍼레이터 (사람)** | 전략 수립, 명령 결정 | **LLM Agent** (Decepticon/Recon/Exploit/PostExploit) | 사람 대신 LLM이 판단 |
| **미션 컨트롤** | 작전 계획, 목표 관리 | **Ralph Loop** (Decepticon Orchestrator) | opplan.json 기반 자동 오케스트레이션 |
| **공격 박스** | 도구 실행 (nmap, sqlmap 등) | **Kali Sandbox** | C2 클라이언트 포함 |
| **팀 서버** | C2 서버 운영 | **C2 컨테이너** (Sliver, Havoc 등) | docker compose profile로 교체 가능 |
| **리다이렉터** | 트래픽 은닉 | **없음** | 통제 환경이므로 불필요 |
| **비콘/Implant** | 타겟 내 원격 에이전트 | **Sliver beacon / Havoc demon** | PostExploit 단계에서 배포 |
| **타겟 네트워크** | 공격 대상 | **Victim 컨테이너** (msf2, DVWA 등) | sandbox-net에서 접근 가능 |

### 2.2 설계 결정: C2 분리 + 리다이렉터 제외

**C2를 별도 컨테이너로 분리하는 이유:**
- C2 프레임워크를 docker compose profile 스왑으로 교체 가능 (Sliver ↔ Havoc ↔ Mythic)
- Kali sandbox 이미지 리빌드 없이 C2만 교체
- 각 C2의 리소스를 독립 관리
- 현업의 팀 서버 분리 구조와 일치

**리다이렉터를 제외하는 이유:**

| 현업에서 리다이렉터가 필요한 이유 | Decepticon에서 불필요한 이유 |
|---|---|
| 블루팀이 비콘 트래픽을 역추적하여 C2 IP 식별 | Docker 네트워크 내 통제 환경, 역추적 위협 없음 |
| 팀 서버 IP가 노출되면 전체 작전 실패 | 단일 sandbox-net 내 통신, 외부 노출 없음 |
| ISP/CDN 레벨에서 C2 트래픽 차단 가능 | 네트워크 필터링 없는 격리 환경 |

---

## 3. 인프라 토폴로지

### 3.1 전체 구성도

```mermaid
graph TB
    subgraph HostMachine["Host Machine"]

        subgraph DecepticonNet["decepticon-net (인프라 네트워크)"]
            CLI["Ink CLI<br/>(사용자 인터페이스)"]
            LG["LangGraph Server :2024<br/>(에이전트 오케스트레이션)"]
            LLM["LiteLLM :4000<br/>(LLM API 게이트웨이)"]
            PG["PostgreSQL<br/>(메타데이터)"]

            CLI -->|HTTP| LG
            LG -->|HTTP| LLM
            LLM --> PG
        end

        SOCK["Docker Socket (RO)"]
        LG -->|docker exec| SOCK

        subgraph SandboxNet["sandbox-net (격리된 공격 네트워크)"]
            subgraph Kali["Kali Sandbox (공격 박스)"]
                TOOLS["공격 도구<br/>nmap, sqlmap, hydra,<br/>nikto, gobuster ..."]
                CLIENT["C2 클라이언트<br/>sliver-client"]
            end

            subgraph C2["C2 Server (팀 서버)"]
                C2_ENGINE["Sliver Server<br/>(profile: c2-sliver)"]
                LISTENER["Listeners<br/>HTTPS :443 | DNS :53<br/>mTLS :8888"]
                C2_ENGINE --> LISTENER
            end

            subgraph Targets["Victim Containers"]
                MSF2["Metasploitable 2<br/>(beacon 실행)"]
                DVWA["DVWA<br/>(beacon 실행)"]
                CUSTOM["Custom Target<br/>(확장 가능)"]
            end

            SOCK -->|docker exec| Kali
            CLIENT -->|gRPC :31337| C2_ENGINE
            TOOLS -->|직접 실행| Targets
            LISTENER <-->|beacon callback| MSF2
            LISTENER <-->|beacon callback| DVWA
        end

        WS["Bind Mount<br/>./workspace ↔ /workspace"]
        Kali --- WS
        C2 --- WS
        LG --- WS
    end
```

### 3.2 네트워크 격리 구조

```mermaid
graph LR
    subgraph decepticon-net
        A[LiteLLM :4000]
        B[PostgreSQL :5432]
        C[LangGraph :2024]
        D[Ink CLI]
    end

    subgraph sandbox-net
        E[Kali Sandbox]
        F[C2 Server]
        G[msf2]
        H[DVWA]
    end

    C -.->|docker.sock<br/>docker exec| E
    E -->|sliver-client<br/>gRPC| F
    F <-->|beacon| G
    F <-->|beacon| H

    style decepticon-net fill:#1a1a2e,stroke:#e94560,color:#fff
    style sandbox-net fill:#0f3460,stroke:#e94560,color:#fff
```

- **decepticon-net**: 인프라 서비스 전용. 외부 포트는 `127.0.0.1`에만 바인딩
- **sandbox-net**: 공격 환경 전용. 인프라 서비스에 대한 네트워크 접근 불가
- **연결 방식**: LangGraph → Docker socket(RO) → `docker exec` → Kali sandbox
- **C2 통신**: Kali의 `sliver-client` → C2 컨테이너 gRPC(:31337) → 비콘 관리

---

## 4. 모듈형 C2 아키텍처

### 4.1 설계 원칙

C2 프레임워크는 **docker compose profile**로 관리되며, profile 스왑으로 교체할 수 있다. LLM 에이전트는 스킬 파일을 통해 각 C2의 CLI를 학습하므로 코드 레벨 추상화 레이어가 불필요하다.

```
C2 교체 = 컨테이너 교체 + 스킬 파일 교체
```

### 4.2 지원 C2 프레임워크

```mermaid
graph LR
    subgraph sandbox-net
        KALI["Kali Sandbox<br/>(C2 클라이언트들)"]

        SLIVER["Sliver Server<br/>(profile: c2-sliver)"]
        HAVOC["Havoc Server<br/>(profile: c2-havoc)"]
        MYTHIC["Mythic Server<br/>(profile: c2-mythic)"]

        T["Targets"]
    end

    KALI -->|sliver-client| SLIVER
    KALI -.->|havoc-client| HAVOC
    KALI -.->|mythic-cli| MYTHIC
    SLIVER <-->|beacon| T
    HAVOC -.->|demon| T
    MYTHIC -.->|agent| T
```

| C2 | Profile | 상태 | 설명 |
|----|---------|------|------|
| **Sliver** | `c2-sliver` | 구현 완료 | BishopFox 오픈소스. mTLS/HTTPS/DNS/WireGuard 리스너 |
| **Havoc** | `c2-havoc` | 향후 | 최신 C2. Demon 페이로드, Sleep obfuscation, Indirect syscalls |
| **Mythic** | `c2-mythic` | 향후 | 모듈형 C2 플랫폼. 다양한 에이전트 프로필 |

### 4.3 C2 사용법

```bash
# Sliver로 engagement 시작
docker compose --profile c2-sliver --profile victims up -d

# C2 교체: Sliver → Havoc
docker compose --profile c2-sliver stop c2-sliver
docker compose --profile c2-havoc up -d c2-havoc

# C2 없이 (Recon/Exploit만)
docker compose up -d
```

### 4.4 컨테이너 구성

**Kali Sandbox (공격 박스)**:
- C2 **클라이언트**만 설치 (`sliver-client`)
- 서버는 실행하지 않음
- 모든 공격 도구 포함 (nmap, sqlmap, hydra, Impacket 등)

**C2 Server (팀 서버)**:
- C2 **서버**만 실행 (`sliver-server daemon`)
- 별도 컨테이너, 별도 이미지
- `sandbox-net`에서 Kali 및 타겟과 통신
- `/workspace` 마운트로 implant 파일 공유
- Named volume으로 C2 데이터(인증서, DB) 영속 보관

---

## 5. 에이전트 파이프라인과 인프라 사용

### 5.1 킬 체인 단계별 실행 모델

Decepticon은 5개 에이전트가 전체 레드팀 킬 체인을 커버한다. 각 단계에서 인프라 사용 방식이 다르다.

```mermaid
graph TD
    subgraph Orchestrator["Decepticon Orchestrator (Opus 4.6)"]
        RALPH["Ralph Loop<br/>opplan.json 읽기 → 목표 선택 → 위임"]
    end

    subgraph Agents["Sub-Agents"]
        PLAN["Planner<br/>(Opus 4.6)<br/>문서 생성"]
        RECON["Recon<br/>(Haiku 4.5)<br/>정찰"]
        EXPLOIT["Exploit<br/>(Sonnet 4.6)<br/>초기 침투"]
        POST["PostExploit<br/>(Sonnet 4.6)<br/>후속 작전 + C2"]
    end

    RALPH -->|task| PLAN
    RALPH -->|task| RECON
    RALPH -->|task| EXPLOIT
    RALPH -->|task| POST

    subgraph Infra["인프라 사용"]
        NONE["도구 없음<br/>(문서만 생성)"]
        DIRECT["Kali → 타겟<br/>직접 실행"]
        HYBRID["직접 실행 +<br/>비콘 배포"]
        BEACON["C2 클라이언트 →<br/>C2 서버 → 비콘"]
    end

    PLAN --- NONE
    RECON --- DIRECT
    EXPLOIT --- HYBRID
    POST --- BEACON

    style NONE fill:#2d3436,stroke:#636e72,color:#dfe6e9
    style DIRECT fill:#00b894,stroke:#00cec9,color:#fff
    style HYBRID fill:#fdcb6e,stroke:#f39c12,color:#2d3436
    style BEACON fill:#e17055,stroke:#d63031,color:#fff
```

### 5.2 단계별 실행 상세

#### Phase 1: Planning (도구 없음)

Planner 에이전트는 sandbox에 접근하지 않는다. 사용자와 대화하여 engagement 문서를 생성한다.

```
Planner Agent → write_file() → /workspace/plan/roe.json
                                /workspace/plan/conops.json
                                /workspace/plan/opplan.json
```

#### Phase 2: Reconnaissance (직접 실행)

Recon 에이전트는 Kali sandbox에서 타겟을 향해 직접 도구를 실행한다. C2는 사용하지 않는다.

```mermaid
sequenceDiagram
    participant LG as LangGraph
    participant K as Kali Sandbox
    participant T as msf2 (Target)

    LG->>K: docker exec: bash("nmap -sV msf2")
    K->>T: TCP SYN scan
    T-->>K: port 21,22,80,445 open
    K-->>LG: scan results

    LG->>K: docker exec: bash("nikto -h http://msf2")
    K->>T: HTTP vulnerability scan
    T-->>K: findings
    K-->>LG: vulnerabilities found

    Note over LG: 결과 → /workspace/recon/report_msf2.md
```

#### Phase 3: Exploitation (직접 실행 + 비콘 배포)

Exploit 에이전트는 취약점을 공격하여 초기 접근 권한을 확보한 후, C2 비콘을 배포한다.

```mermaid
sequenceDiagram
    participant LG as LangGraph
    participant K as Kali Sandbox
    participant C2 as C2 Server (Sliver)
    participant T as msf2 (Target)

    Note over K: Phase 3a: 취약점 공격 (직접 실행)
    LG->>K: docker exec: bash("sqlmap -u 'http://msf2/...'")
    K->>T: SQL Injection
    T-->>K: shell 획득

    Note over K,C2: Phase 3b: 비콘 배포 (C2 전환점)
    LG->>K: docker exec: bash("sliver-client generate --mtls c2-sliver")
    K->>C2: implant 생성 요청 (gRPC)
    C2-->>K: implant 바이너리
    LG->>K: docker exec: bash("획득한 셸로 implant 업로드")
    K->>T: implant 전송 + 실행
    T->>C2: beacon callback (HTTPS :443)

    Note over LG: 결과 → /workspace/exploit/shells.json
```

#### Phase 4: Post-Exploitation (C2 클라이언트 → 서버 → 비콘)

PostExploit 에이전트는 Kali의 `sliver-client`를 통해 C2 서버에 연결하고, C2 서버가 비콘에 명령을 전달한다.

```mermaid
sequenceDiagram
    participant LG as LangGraph
    participant K as Kali (sliver-client)
    participant C2 as C2 Server (Sliver)
    participant B as Beacon (msf2)

    Note over K,B: C2 클라이언트 → 서버 → 비콘 경로

    LG->>K: docker exec: bash("sliver-client", session="c2")
    K->>C2: gRPC 연결 (:31337)

    LG->>K: bash("use [session]", is_input=True, session="c2")
    LG->>K: bash("whoami", is_input=True, session="c2")
    K->>C2: 명령 전달 (gRPC)
    C2->>B: 명령 전달 (encrypted)
    B-->>C2: "root"
    C2-->>K: 결과 반환
    K-->>LG: "root"

    LG->>K: bash("hashdump", is_input=True, session="c2")
    K->>C2: credential dump 명령
    C2->>B: 실행
    B-->>C2: NTLM hashes
    C2-->>K: 결과 반환

    LG->>K: bash("socks5 start", is_input=True, session="c2")
    K->>C2: pivot 설정
    C2->>B: SOCKS proxy 활성화
    Note over B: 내부 네트워크 접근 가능

    Note over LG: 결과 → /workspace/post-exploit/
```

---

## 6. 컨테이너 상세 구성

### 6.1 Kali Sandbox (공격 박스)

| 항목 | 값 |
|------|-----|
| 이미지 | `decepticon-sandbox` (Kali rolling) |
| 메모리 | 4GB |
| CPU | 2코어 |
| PID 제한 | 1024 |
| 네트워크 | `sandbox-net` |
| 사용자 | `operator` (UID 1000, passwordless sudo) |
| 볼륨 | `./workspace:/workspace` |
| 역할 | 공격 도구 실행 + C2 클라이언트 |

**설치된 도구:**

| 카테고리 | 도구 |
|----------|------|
| 정찰 | nmap, dig, whois, subfinder, nikto, gobuster, dirb |
| 공격 | sqlmap, hydra, smbclient, exploitdb |
| C2 클라이언트 | sliver-client |
| 유틸리티 | python3, curl, wget, netcat, tmux |

### 6.2 C2 Server — Sliver (팀 서버)

| 항목 | 값 |
|------|-----|
| 이미지 | `decepticon-c2-sliver` (Kali rolling) |
| Profile | `c2-sliver` |
| 메모리 | 2GB |
| CPU | 1코어 |
| PID 제한 | 512 |
| 네트워크 | `sandbox-net` |
| 사용자 | `sliver` (UID 1000) |
| 볼륨 | `./workspace:/workspace`, `sliver_data:/home/sliver/.sliver` |
| CMD | `sliver-server daemon` |

**노출 포트 (sandbox-net 내부):**

| 포트 | 프로토콜 | 용도 |
|------|----------|------|
| 443 | HTTPS | 비콘 콜백 리스너 |
| 53 | DNS | DNS 터널링 리스너 |
| 8888 | mTLS | 암호화 리스너 |
| 31337 | gRPC | 오퍼레이터 클라이언트 연결 |

### 6.3 C2 데이터 영속성

C2 서버 데이터는 named volume(`sliver_data`)에 저장되어 컨테이너 재생성 시에도 유지된다:

```
sliver_data volume (/home/sliver/.sliver/):
├── certs/           ← TLS 인증서 (첫 실행 시 자동 생성)
├── configs/         ← 오퍼레이터 설정 파일
├── db/              ← SQLite (implant DB, session history)
└── logs/            ← 서버 로그
```

Implant 바이너리는 `/workspace`에 저장하여 Kali sandbox와 공유한다.

---

## 7. 네트워크 통신 흐름

### 7.1 전체 데이터 흐름

```mermaid
flowchart TB
    USER["사용자"] -->|HTTP| CLI["Ink CLI"]
    CLI -->|langgraph:2024| LG["LangGraph Server"]
    LG -->|http://litellm:4000| LITELLM["LiteLLM"]
    LITELLM -->|API| PROVIDERS["Anthropic / OpenAI / Google"]
    LITELLM --> PG["PostgreSQL"]

    LG -->|docker.sock| DOCKER["Docker Daemon"]
    DOCKER -->|docker exec| KALI["Kali Sandbox"]

    KALI -->|직접 스캔/공격| TARGET["Victim Containers"]
    KALI -->|sliver-client gRPC| C2["C2 Server"]
    C2 <-->|beacon callback| TARGET

    subgraph sandbox-net
        KALI
        C2
        TARGET
    end

    subgraph decepticon-net
        CLI
        LG
        LITELLM
        PG
    end
```

### 7.2 포트 매핑

| 서비스 | 포트 | 바인딩 | 네트워크 |
|--------|------|--------|----------|
| LangGraph API | 2024 | 127.0.0.1 | decepticon-net |
| LiteLLM Proxy | 4000 | 127.0.0.1 | decepticon-net |
| PostgreSQL | 5432 | 127.0.0.1 | decepticon-net |
| Sliver gRPC (operator) | 31337 | sandbox 내부 | sandbox-net |
| Sliver HTTPS Listener | 443 | sandbox 내부 | sandbox-net |
| Sliver DNS Listener | 53 | sandbox 내부 | sandbox-net |
| Sliver mTLS Listener | 8888 | sandbox 내부 | sandbox-net |

---

## 8. Engagement 실행 흐름

### 8.1 전체 워크플로우

```mermaid
flowchart TD
    START([Engagement 시작]) --> PLAN

    subgraph PLAN["Phase 1: Planning"]
        P1[사용자 인터뷰]
        P2[RoE 생성]
        P3[CONOPS 생성]
        P4[OPPLAN 생성]
        P1 --> P2 --> P3 --> P4
    end

    PLAN --> RALPH

    subgraph RALPH["Ralph Loop (자동 오케스트레이션)"]
        R1[opplan.json 로드]
        R2{다음 목표 선택}

        R1 --> R2
        R2 -->|Recon 목표| RECON_PHASE
        R2 -->|Exploit 목표| EXPLOIT_PHASE
        R2 -->|PostExploit 목표| POST_PHASE
        R2 -->|모두 완료| REPORT

        subgraph RECON_PHASE["Phase 2: Recon"]
            RE1["Kali → 타겟 직접 스캔"]
            RE2["결과 → recon/report_*.md"]
        end

        subgraph EXPLOIT_PHASE["Phase 3: Exploit"]
            EX1["Kali → 타겟 직접 공격"]
            EX2["초기 접근 확보"]
            EX3["sliver-client → C2 서버 → 비콘 배포"]
            EX1 --> EX2 --> EX3
        end

        subgraph POST_PHASE["Phase 4: PostExploit"]
            PO1["sliver-client → C2 서버 연결"]
            PO2["C2 서버 → 비콘 통해 명령 실행"]
            PO3["크리덴셜 수집"]
            PO4["권한 상승"]
            PO5["횡이동 → 새 비콘"]
            PO1 --> PO2 --> PO3 --> PO4 --> PO5
        end

        RECON_PHASE --> R4[findings.md 업데이트]
        EXPLOIT_PHASE --> R4
        POST_PHASE --> R4
        R4 --> R5[opplan.json 상태 업데이트]
        R5 --> R2
    end

    REPORT([Engagement 완료 리포트])
```

### 8.2 C2 세션 라이프사이클

```mermaid
stateDiagram-v2
    [*] --> NoC2: Recon/Exploit 단계

    NoC2 --> ClientConnect: PostExploit Agent가 sliver-client 시작
    ClientConnect --> C2Connected: gRPC로 C2 서버 연결
    C2Connected --> ListenerActive: listener 생성 (HTTPS/DNS/mTLS)
    ListenerActive --> BeaconDeployed: Exploit 결과로 비콘 배포
    BeaconDeployed --> SessionActive: 비콘 콜백 수신

    SessionActive --> CommandExec: 클라이언트 → 서버 → 비콘 명령 전달
    CommandExec --> SessionActive: 결과 반환

    SessionActive --> Pivot: 횡이동 시작
    Pivot --> NewBeacon: 새 타겟에 비콘 배포
    NewBeacon --> SessionActive: 다중 세션 관리

    SessionActive --> AgentDone: PostExploit Agent 종료
    AgentDone --> SessionPersist: C2 서버 컨테이너가 세션 유지
    SessionPersist --> SessionReattach: 새 Agent가 sliver-client로 재연결

    SessionReattach --> SessionActive

    note right of SessionPersist
        C2 서버는 별도 컨테이너로 항상 실행 중
        에이전트 lifecycle과 독립적
        sliver_data volume에 세션 영속 보관
    end note
```

---

## 9. Workspace 디렉토리 구조

```
/workspace/
├── plan/
│   ├── roe.json                  ← 스코프 정의 (매 단계에서 검증)
│   ├── conops.json               ← 위협 모델, 킬 체인
│   ├── opplan.json               ← 목표 목록 (Ralph Loop 드라이버)
│   └── deconfliction.json        ← 충돌 방지 절차
├── recon/
│   ├── report_<target>.md        ← 타겟별 정찰 보고서
│   └── [스캔 결과 파일]
├── exploit/
│   ├── creds_initial.json        ← 초기 크리덴셜
│   ├── shells.json               ← 셸 인벤토리
│   └── [공격 아티팩트]
├── post-exploit/
│   ├── creds/                    ← 수집된 크리덴셜
│   ├── privesc/                  ← 권한 상승 로그
│   ├── lateral/                  ← 횡이동 로그
│   ├── loot/                     ← 목표별 수집 데이터
│   └── network_map.json          ← 내부 네트워크 맵
├── findings.md                   ← Iteration간 누적 발견사항
└── lessons_learned.md            ← 차단된 목표의 교훈
```

---

## 10. 향후 확장 가능성

### 10.1 추가 C2 프레임워크

새 C2를 추가하려면:
1. `containers/c2-<name>.Dockerfile` 작성
2. `docker-compose.yml`에 profile `c2-<name>` 서비스 추가
3. `skills/post-exploit/c2/` 하위에 해당 C2 스킬 추가
4. Kali sandbox에 클라이언트 바이너리 추가

### 10.2 리다이렉터 도입

Defense Evasion 훈련이 필요할 경우, 리다이렉터 컨테이너를 추가할 수 있다.

```mermaid
graph LR
    subgraph sandbox-net
        KALI["Kali (공격 박스)"]
        C2["C2 Server"]
        RD["Redirector<br/>(socat/nginx)"]
        T["Target"]
    end

    KALI -->|sliver-client| C2
    C2 -->|listener| RD
    RD <-->|beacon callback| T
```

### 10.3 Purple Team 확장

Blue Team 에이전트를 추가하여 Red-Blue 피드백 루프를 구현할 수 있다. 상세는 별도 문서([purple-team-architecture.md](purple-team-architecture.md))에서 다룬다.
