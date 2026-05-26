# AI 자율 Red Team 에이전트 — State of the Art (2024-2026)

> AI를 활용하여 실제 인프라/시스템을 대상으로 Red Team 운영을 자동화하는 기술 리서치 문서.
> 주의: 이 문서는 AI 모델 안전성 테스트(AI safety red teaming)가 아닌, AI를 "도구로 사용"하여 전통적 인프라를 공격하는 자율 Red Team 에이전트에 대한 것임.

---

## 1. AI 기반 자율 공격 에이전트 현황

### 1.1 핵심 프로그램 및 성과

**DARPA AIxCC** (AI Cyber Challenge, 2023-2025)
- 완전 자율 Cyber Reasoning System(CRS) 구축 최대 규모 경쟁
- DEF CON 33 결선: 7팀, 53개 핵심 인프라 SW 프로젝트, 143시간 자율 운영
- **합성 취약점 86% 발견** (예선 37% → 결선 86%), 68% 패치, 18개 실제 제로데이 발견 (평균 45분)
- 1위 Team Atlanta ($4M), 2위 Trail of Bits Buttercup ($3M), 3위 Theori ($1.5M)
- SoK 논문: [arxiv.org/abs/2602.07666](https://arxiv.org/abs/2602.07666)

**Anthropic**
- Claude Opus 4.7로 프로덕션 OSS 코드베이스에서 **500+ 취약점** 발견 (수십 년간 미탐지)
- 인간 사이버보안 경쟁에서 상위 25%

**인증 프로그램**
- Hack The Box: AI Red Teamer Certification (2026 Q1, Google 협업)
- OffSec: AI-300 Advanced AI Red Teaming

### 1.2 AIxCC 우승 아키텍처

**ATLANTIS (Team Atlanta)**
- LLM + 프로그램 분석 통합: 심볼릭 실행, 지향형 퍼징, 정적 분석
- 멀티에이전트 강화학습 — map/exploit/patch 실시간
- C/C++, Java별 특화 에이전트 분리

**Buttercup (Trail of Bits)** — 오픈소스
- libFuzzer/Jazzer + LLM 테스트케이스 생성
- tree-sitter + CodeQuery 정적 분석
- **7개 패치 생성 AI 에이전트**
- 28개 취약점, 20 CWE, 90% 정확도, $181/포인트
- GitHub: [trailofbits/buttercup](https://github.com/trailofbits/buttercup)

---

## 2. 자율 공격 에이전트

### 2.1 주요 에이전트 비교

| 에이전트 | 성과 | 아키텍처 | 출처 |
|---------|------|---------|------|
| **PentestGPT** | 86.5% 성공 (90/104), $1.11/벤치마크 | 자율 E2E 펜테스팅 | USENIX 2024 |
| **AutoPentester** | PentestGPT 대비 +27% 서브태스크, +39.5% 취약점 커버리지 | 18.7% 적은 스텝, 92.6% 적은 인간 개입 | arxiv 2510.05605 |
| **PentAGI** | 멀티에이전트 자율 펜테스팅 | Go API + PostgreSQL/pgvector + Neo4j + Docker | 오픈소스 |
| **HackSynth** | PicoCTF + OverTheWire (200 챌린지) | Planner + Summarizer 듀얼 모듈 | arxiv 2412.01778 |
| **Reaper** (Ghost Security) | 정찰→프록시→테스트→리포팅 통합 | 인간+AI 에이전트 지원 | 오픈소스 |

### 2.2 의사결정 및 계획 패러다임

**Planner-Executor-Perceptor (PEP)** 패턴이 지배적:
1. **Planner**: 공격 전략 생성, TTP 선택
2. **Executor**: 도구 실행, 출력 캡처
3. **Perceptor**: 결과 분석, 월드 모델 업데이트, Planner에 피드백

추론 프레임워크: **ReAct** (추론+행동 교차), **Tree-of-Thought** (분기 탐색), MITRE ATT&CK 기반 **구조화된 공격 트리**

### 2.3 구조화된 공격 트리 효과
- 정의된 TTP로 LLM 추론 제약 → **74.4% 서브태스크 완료** vs 비제약 35.2% (arxiv 2509.07939)
- Decepticon의 OPPLAN 목표 시퀀스와 직접 대응

---

## 3. AI 익스플로잇 개발

### 3.1 LLM 기반 취약점 발견
- **CyberExplorer 벤치마크**: 40개 취약한 웹 서비스, Claude Opus 4.5와 Gemini 3 Pro가 최다 고유 취약점 발견
- **FuzzingBrain** (AIxCC): 28개 취약점 자율 발견 (6개 제로데이), 14개 패치

### 3.2 AI 기반 퍼징
- **ChatAFL**: 자연어 프로토콜 스펙 → 테스트 입력 생성, 9개 새 취약점
- **LLM-Boofuzz**: 실제 트래픽 파싱 → 블랙박스 프로토콜 퍼징 스크립트 생성

### 3.3 LLM 익스플로잇 생성
- **PwnGPT** (ACL 2025): LLM 기반 자동 익스플로잇 생성 시스템
- LLM이 익스플로잇 가능성 이해 및 기능적 PoC 생성에 점점 능숙

---

## 4. AI 기반 적대자 에뮬레이션

### 4.1 AI 기반 TTP 선택
- MITRE ATT&CK 기반 학습된 시스템이 전체 공격 라이프사이클 이해
- 위협 인텔리전스 피드에서 실제 위협 행위자의 TTP 추출 → 자동 에뮬레이션 계획 생성

### 4.2 자동화된 공격 경로 계획
- 개별 취약점보다 **완전 공격 경로 분석** 우선
- 사람/프로세스/기술 전반의 경로 매핑
- 소규모 미스컨피그가 E2E 침해로 복합되는 방식 분석
- 자동 경로 매핑: Initial Access → Lateral Movement → Objective 달성까지 체인 구성

### 4.3 동적 vs 정적 접근
- 정적 플레이북 → AI 기반 적응적 의사결정으로 전환
- 멀티에이전트 시스템이 가설을 따르고 발견 정보에 따라 조정
- 타겟 환경의 방어 상태에 따라 TTP를 실시간으로 전환

---

## 5. Continuous Automated Red Teaming (CART)

### 5.1 CART 개요
- 인프라 진화에 맞춰 **지속적으로** 취약점 탐지 및 공격 경로 검증
- 정기 평가(분기/연간) → 실시간 공격 시뮬레이션으로 전환
- 새 서비스 배포, 설정 변경, 패치 적용 시 즉시 재검증

### 5.2 자동화된 Purple Team 피드백 루프
- Red Team 에이전트의 공격 실행 결과가 자동으로 Blue Team 탐지 시스템에 피드백
- 탐지 갭이 식별되면 자동으로 SIEM 룰/플레이북 권고 생성
- 지속적 공방 사이클: 공격 → 탐지 평가 → 방어 강화 → 재공격

### 5.3 인프라 공방 자동화 전망 (2026)
- 자율 Red Team 에이전트가 네트워크 매핑, 서비스 열거, 취약점 익스플로잇을 **수분 내** 수행
- 기존 1주일 소요 Red Team 작업 → 수시간으로 단축
- 방어자도 AI 기반 탐지/대응으로 맞대응 → 공방 모두 자동화되는 추세

---

## 6. 자율 공격 에이전트 안전 통제

### 6.1 가드레일

| 메커니즘 | 설명 |
|---------|------|
| **불변 RoE** | 매 반복마다 RoE 확인 — 범위/시간/허용기법 검증 (Decepticon 이미 구현) |
| **행동 범위 제한** | 승인된 도구/타겟만 허용, 최소 권한, 고위험 작업 HITL |
| **킬 스위치/격리** | 미승인 권한 상승 또는 범위 이탈 시 자동 중지; Docker 샌드박스 격리 |
| **세분화된 인가** | ABAC/RBAC, 민감 도구(C2 배포, 데이터 유출 등) 인간 승인 게이트 |
| **감사 추적** | 모든 에이전트 결정/도구 실행의 포괄적 로깅 (증거 보존 + 사후 분석) |
| **디컨플릭션** | 실제 공격과 테스트 활동 구분을 위한 SOC 통보 메커니즘 |

### 6.2 법적 고려사항
- **RoE/계약**: 모든 자율 공격은 서면 RoE + 법적 권한 위임 필수
- **범위 통제**: 에이전트가 인가되지 않은 시스템에 접근하지 않도록 기술적 제어 (IP 화이트리스트, 네트워크 격리)
- **데이터 처리**: 발견된 PII/PHI/PCI 데이터의 수집/저장/파기 정책
- **증거 보존**: 법적 분쟁 대비 모든 활동 로그 보존 (체인 오브 커스터디)
- **NIST SP 800-53 CA-8(2)**: 자율 에이전트도 Red Team 연습 통제 요구사항 적용

---

## 7. AI Red Team 에이전트 아키텍처 패턴

### 7.1 멀티에이전트 vs 싱글에이전트
> "하나의 범용 에이전트보다 특화된 에이전트 여러 개가 더 효과적" — Team Atlanta

**Red Team 에이전트 역할 분리 패턴**:
- **Planning 에이전트**: TTP 선택, 목표 분해, OPPLAN 생성
- **Recon 에이전트**: 정보 수집, 공격 표면 매핑
- **Exploitation 에이전트**: 취약점 테스트, 페이로드 생성, C2 운용
- **Post-Exploitation 에이전트**: 횡이동, 권한 상승, 자격증명 수집
- **Reporting 에이전트**: 공격 내러티브, 탐지 갭, 증거 정리

### 7.2 오케스트레이션 패턴

| 패턴 | 설명 | Red Team 적용 |
|------|------|-------------|
| **Sequential** | 체인형 정제 | 정찰 → 초기 접근 → 횡이동 → 목표 달성 |
| **Concurrent** | 동시 처리 | 병렬 타겟 정찰, 다중 공격 벡터 동시 시도 |
| **Handoff** | 동적 위임 | 발견에 따라 전문가 에이전트(AD, Web, Cloud)에 위임 |
| **Magentic** | 계획 우선 실행 | OPPLAN 전체 생성 → 단계별 실행 |

### 7.3 메모리 및 상태 관리

| 유형 | 저장소 | 용도 |
|------|--------|------|
| **단기 메모리** | 스크래치패드/워크스페이스 | 에이전트 간 활성 협업 (현재 타겟 상태) |
| **장기 메모리** | PostgreSQL + pgvector | Engagement 상태, 발견 이력, 자격증명 (시맨틱 검색) |
| **그래프 메모리** | Neo4j 등 | 네트워크 토폴로지, 호스트/서비스/자격증명 관계 |
| **Engagement State** | SQLite/외부 저장소 | 태스크 진행, 중간 결과, 에이전트 간 공유 상태 |

**PentAGI 패턴**: Go API + PostgreSQL/pgvector(시맨틱 검색) + Neo4j(관계 그래프) + Docker(격리)
**red-run 패턴**: SQLite Engagement State + state-interim(에이전트가 발견 즉시 기록) + JSONL 로그

### 7.4 컨텍스트 윈도우 관리
- 누적 컨텍스트 크기 모니터링; 에이전트 간 압축(요약, 선택적 프루닝)
- **Observation masking**: N턴 후 도구 출력 임계값 초과분 자동 마스킹
- **Per-iteration 컨텍스트 주입**: 관련 목표 + 범위 + 이전 발견만 주입 (Ralph loop)
- **Progressive disclosure**: 3단계 스킬 시스템 (메타데이터 → SKILL.md → references/)

### 7.5 도구 선택 및 체이닝
- 특화 에이전트를 통한 도구 선택/파라미터 조정/다음 단계 추론
- MITRE ATT&CK 기반 결정론적 태스크 트리 → 순환/막다른 로직 방지
- **RedTeamLLM 패턴**: 재귀적 계획 + 계획 수정 + 메모리 + 명시적 보안 통제

---

## 8. Decepticon 아키텍처와의 정합성

### 이미 정합하는 부분
- **멀티에이전트 특화 역할** (Planning + Recon) → AIxCC 우승 패턴과 일치
- **Ralph Loop** (반복당 목표+RoE+발견 주입) → PEP 패턴 미러링
- **불변 RoE 가드레일** → 자율 공격 에이전트 안전 통제 모범 사례
- **스킬 기반 progressive disclosure + observation masking** → 컨텍스트 윈도우 관리 해결
- **Docker 샌드박스 격리** → 공격 도구 실행 격리 요구사항 충족

### 리서치에서 도출된 보강 포인트

| 패턴 | 근거 | 우선순위 |
|------|------|---------|
| **그래프 메모리** (Neo4j) | PentAGI + ATLANTIS; 네트워크 토폴로지/자격증명 관계 추적 | HIGH |
| **구조화된 공격 트리** | ATT&CK TTP 제약 시 74.4% vs 35.2% 성공률 | HIGH |
| **킬 스위치 + 자동 격리** | RoE 위반/범위 이탈 시 자동 비활성화 | HIGH |
| **시맨틱 검색** (pgvector) | 크로스 세션 발견 회상 개선 | MEDIUM |
| **도메인별 특화 에이전트** | Web, AD, Cloud 등 전문가 분리 | MEDIUM |
| **CART 모드** | 지속적 자율 Red Teaming — 인프라 변경 시 자동 재검증 | LONG-TERM |

---

## 핵심 논문 및 리소스

| 리소스 | 참조 |
|--------|------|
| SoK: AIxCC Competition | arxiv.org/abs/2602.07666 |
| ATLANTIS (Team Atlanta) | arxiv.org/abs/2509.14589 |
| Buttercup (Trail of Bits, OSS) | github.com/trailofbits/buttercup |
| CyberExplorer Benchmark | arxiv.org/html/2602.08023 |
| HackSynth | arxiv.org/abs/2412.01778 |
| AutoPentester | arxiv.org/abs/2510.05605 |
| Structured Attack Trees | arxiv.org/abs/2509.07939 |
| PentAGI (OSS) | github.com/vxcontrol/pentagi |
| PwnGPT | ACL 2025 |
| Survey: Agentic AI + Cybersecurity | arxiv.org/html/2601.05293v1 |
| AWS Security Agent Architecture | aws.amazon.com/blogs/security/inside-aws-security-agent |
| Azure AI Agent Design Patterns | learn.microsoft.com/azure/architecture/ai-ml/guide/ai-agent-design-patterns |
