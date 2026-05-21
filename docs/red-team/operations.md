# Red Team Operations — 전체 가이드

> Decepticon 에이전트의 운영 프레임워크 문서.
> 참조: MITRE ATT&CK, TIBER-EU, NIST SP 800-53 CA-8, DORA, PTES

---

## 1. Red Team vs Penetration Testing

| 차원 | Penetration Testing | Red Team Operations |
|------|-------------------|-------------------|
| **목적** | 정해진 범위 내 취약점 최대한 발견 | 특정 목표(crown jewels 접근 등) 달성을 통한 조직 전체 회복력 검증 |
| **범위** | 좁음 — 특정 시스템/앱/네트워크 | 넓음 — 사람, 프로세스, 물리, 기술 전체 |
| **기간** | 1-2주 | 3-4주 ~ 수개월 (지속적 운영 포함) |
| **은밀성** | 일반적으로 불필요; 조직이 인지 | 핵심 — 탐지/대응 능력 검증; Blue Team은 미인지 |
| **방법론** | 체계적 취약점 식별 (자동+수동) | 목표 지향 적대적 에뮬레이션; 단일 진입점 → 횡이동 → 목표 달성 |
| **검증 대상** | 기술적 통제만 | 기술 + 인적 요소 + 절차(IR) + 물리 보안 |
| **산출물** | 취약점 목록 + 심각도 + 개선 권고 | 공격 내러티브, 탐지 갭 분석, 조직 대응 평가, 전략적 권고 |
| **통보** | IT/보안팀 전체 인지 | White Team(Control Team)만 인지 |

**Decepticon 관점**: 스캐너가 아닌 Red Team 에이전트. 목표 지향 운영, OPSEC, 다단계 공격 체인, 조직 대응 검증이 핵심.

---

## 2. Red Team Operations Lifecycle

### Phase 0: Planning & Preparation
- 이해관계자 합의, 위협 모델링, RoE 작성
- 성공 기준/범위/디컨플릭션 정의
- 산업별 위협 환경 기반 적대자 프로필 선택
- **Decepticon**: Planning Agent → RoE → CONOPS → OPPLAN → Deconfliction Plan

### Phase 1: Reconnaissance (TA0043)
- Passive: OSINT, DNS, 소셜 미디어, 유출 자격증명, CT 로그
- Active: 포트 스캔, 서비스 핑거프린팅, 웹 크롤링, API 디스커버리
- **산출물**: 타겟 프로필, 공격 표면 맵, 진입점 식별

### Phase 2: Resource Development (TA0042)
- C2 서버, 리다이렉터, 도메인 등 인프라 구축
- 커스텀 페이로드, 피싱 템플릿, 임플란트 준비
- 자격증명 수집 인프라 구성

### Phase 3: Initial Access (TA0001)
- 피싱(스피어피싱 링크/첨부), 자격증명 스터핑, 외부 노출 시스템 익스플로잇
- 소셜 엔지니어링, 공급망 침해, 유효한 계정 사용
- 2025 DBIR: **74% 침해가 손상된 자격 증명** 관련

### Phase 4: Execution (TA0002)
- 커맨드/스크립팅 인터프리터, 클라이언트 실행 익스플로잇
- 사용자 실행, 시스템 서비스, 예약 작업

### Phase 5: Persistence (TA0003)
- 백도어, 새 계정, 부팅/로그인 자동시작, 예약 작업
- 임플란트 배포, 설정 변경
- 초기 진입점 발견 시에도 접근 유지 보장

### Phase 6: Privilege Escalation (TA0004)
- 취약점 익스플로잇, 토큰 조작, 프로세스 인젝션
- 권한 상승 제어 우회, 도메인 정책 수정

### Phase 7: Defense Evasion (TA0005)
- 난독화, 지표 제거, 위장, 프로세스 인젝션
- 보안 도구 비활성화, 인증 프로세스 수정
- **모든 단계에 OPSEC 내장 필수**

### Phase 8: Credential Access (TA0006)
- 자격증명 덤프, 브루트포스, Kerberoasting, NTLM 릴레이
- 입력 캡처, 패스워드 저장소, 미보호 자격증명

### Phase 9: Discovery (TA0007)
- 네트워크/시스템/계정/도메인 디스커버리, 권한 그룹
- 소프트웨어, 서비스, 파일/디렉토리 열거

### Phase 10: Lateral Movement (TA0008)
- SMB 릴레이, RDP 피벗, WMI 실행, Pass-the-Hash/Ticket
- 원격 서비스, 내부 스피어피싱

### Phase 11: Collection (TA0009)
- 정보 저장소/로컬 시스템/네트워크 공유의 데이터 수집
- 이메일, 입력 캡처, 화면 캡처

### Phase 12: Command and Control (TA0011)
- 애플리케이션 레이어 프로토콜, 암호화 채널, 프록시
- 데이터 인코딩, 멀티스테이지 채널, 트래픽 시그널링

### Phase 13: Exfiltration (TA0010)
- C2 채널/대안 프로토콜/웹 서비스를 통한 유출
- 예약 전송, 물리 매체

### Phase 14: Impact (TA0040)
- 데이터 파괴/암호화, 서비스 중지, 리소스 하이재킹
- Red Team에서는 보통 **파괴 실행 없이 가능성만 입증**

---

## 3. MITRE ATT&CK Enterprise Matrix (2025)

**14 tactics, 216 techniques, 475 sub-techniques**

| Tactic ID | Name | 목적 | Technique 수 |
|-----------|------|------|-------------|
| TA0043 | Reconnaissance | 계획 정보 수집 | ~10 |
| TA0042 | Resource Development | 운영 리소스 확보 | ~8 |
| TA0001 | Initial Access | 네트워크 진입 | ~10 |
| TA0002 | Execution | 악성 코드 실행 | ~14 |
| TA0003 | Persistence | 발판 유지 | ~20 |
| TA0004 | Privilege Escalation | 상위 권한 획득 | ~14 |
| TA0005 | Defense Evasion | 탐지 회피 | ~43 |
| TA0006 | Credential Access | 자격증명 탈취 | ~17 |
| TA0007 | Discovery | 환경 파악 | ~32 |
| TA0008 | Lateral Movement | 환경 내 이동 | ~9 |
| TA0009 | Collection | 목표 데이터 수집 | ~17 |
| TA0011 | Command and Control | 침해 시스템 통신 | ~16 |
| TA0010 | Exfiltration | 데이터 탈취 | ~9 |
| TA0040 | Impact | 시스템/데이터 조작/파괴 | ~14 |

**생태계**: 172 Groups, 784 Software, 52 Campaigns, 691 Detection Strategies

---

## 4. Adversary Emulation vs Adversary Simulation

| 측면 | Adversary Emulation | Adversary Simulation |
|------|-------------------|---------------------|
| **정의** | 특정 위협 행위자의 문서화된 TTP를 정확히 재현 | 가상의 공격 시나리오로 적대자 행동 근사 |
| **충실도** | 높음 — 실제 행동 미러링 | 중간 — 근사치 |
| **소스** | CTI 보고서, ATT&CK 그룹 프로필 | 일반 공격 패턴, 역량 평가 |
| **용도** | "APT29의 SolarWinds 공격 체인을 탐지할 수 있나?" | "일반적 횡이동을 탐지할 수 있나?" |

### MITRE CTID (Center for Threat-Informed Defense)
- **Adversary Emulation Library**: 문서화된 위협 행위자 캠페인 재현 계획 모음
- **Micro Emulation Plans**: 소규모 자동화 가능한 일반 위협 행동 계획
- **프로세스**: 인텔 수집 → 계획 개발 → 에뮬레이션 실행 → 탐지 평가 → 갭 분석

**Decepticon 적용**: CONOPS의 위협 행위자 프로필이 ATT&CK 그룹에 매핑되어야 하며, OPPLAN은 에뮬레이션급 TTP 시퀀스를 포함해야 함.

---

## 5. 규제 프레임워크 비교

### TIBER-EU (Threat Intelligence-Based Ethical Red Teaming)
- **발행**: ECB, 2025년 2월 업데이트 (DORA TLPT RTS 정렬)
- **대상**: EU 시스템적으로 중요한 금융기관
- **핵심**: TI 제공자와 Red Team 의무 분리, 3단계(준비→테스트→종료), **Purple teaming 의무화 (2025)**

### CBEST (UK)
- **발행**: Bank of England
- **핵심**: CREST 인증 팀 필수, TI/RT 분리 의무

### CORIE v2 (Australia)
- **발행**: CFR
- **핵심**: 목표 기반 시나리오, 규모별 계층화, 탐지/대응/복구 능력 측정

### AASE (Singapore) / iCAST (Hong Kong) / FEER (Saudi Arabia)
- 내부 팀 허용 여부, 인증 요구 등에서 차이

### 프레임워크 비교 매트릭스

| 기능 | TIBER-EU | CBEST | CORIE | AASE | iCAST | FEER |
|------|----------|-------|-------|------|-------|------|
| 외부 팀 필수 | Yes | Yes | Yes | No | No | Yes |
| TI/RT 분리 | Yes | Yes | Varies | No | No | Varies |
| 인증 요구 | Optional | CREST | No | No | No | Yes |
| Purple team 의무 | **Yes (2025)** | No | No | No | No | No |
| DORA 정렬 | Yes | No | No | No | No | No |

---

## 6. 규제 표준

### NIST SP 800-53 CA-8 / CA-8(2)
- **CA-8**: 정기적 + 주요 변경 후 침투 테스트
- **CA-8(2)**: RoE에 따른 Red Team 연습 (적대자 시뮬레이션)
- **FedRAMP**: High/Moderate 시스템에 CA-8(2) 의무화

### PCI DSS 4.0 Requirement 11.4
- 최소 12개월 + 주요 변경 후
- NIST SP 800-115, PTES, OWASP, OSSTMM 참조 방법론 필수
- 서비스 제공자: 6개월마다 세그멘테이션 테스트

### DORA (Digital Operational Resilience Act)
- **시행**: 2025년 1월 17일
- TLPT RTS: 2025년 7월 8일 시행
- 최소 3년마다 TLPT; 핵심 기능 연간 테스트
- **라이브 프로덕션 환경**에서 수행, Purple teaming 의무
- 2026년부터 규제기관 통지 시작

### CISA 주요 권고 (2024)
- AA24-326A: 기본 비밀번호 제거, 특권 사용자 MFA, 정기적 피싱 훈련
- AA24-193A: Defense-in-depth, DC 및 OT/HMI 침해 공격 경로 문서화

---

## 7. Purple Team 통합

### Test-Analyze-Refine (TAR) 사이클
1. Red Team이 특정 TTP 실행
2. Blue Team이 탐지/로깅 여부 검토
3. 공동 탐지 갭 분석
4. 탐지 룰/플레이북 조정
5. 점진적 복잡도 증가하며 반복

### 통합 모델
- **Episodic**: Red Team 연습 후 예정된 Purple Team 세션
- **Continuous** (2024-2025 트렌드): 24/7 적대자 에뮬레이션 + 탐지 엔지니어링 피드백 루프
- **Automated**: BAS 플랫폼 기반 지속적 에뮬레이션 계획 실행

### 데이터 플로우: Red → Purple → Blue
- **Red** 산출: 공격 경로, TTP 실행 로그, 탐지 갭 증거
- **Purple** 산출: 탐지 룰 권고, 플레이북 업데이트, 우선순위 매트릭스
- **Blue** 실행: 새 SIEM 룰, 대응 절차 업데이트, 설정 강화

---

## 8. Red Team 성숙도 모델 (RTCMM)

| Level | Name | 특성 |
|-------|------|------|
| **1** | Initial/Ad Hoc | 비정기적, 비체계적, OPSEC 미고려 |
| **2** | Managed | 직관적이나 미문서화, 필요시 수행, 제한된 OPSEC |
| **3** | Defined | 문서화된 프로세스, 일관된 방법론, 표준화된 도구, TI 기반 |
| **4** | Measured | 메트릭 기반, 고급 역량, 커스텀 도구, 적대자 에뮬레이션급 |
| **5** | Optimizing | 지속 개선, 비즈니스 리스크 정렬, 최첨단 역량, 업계 기여 |

### 평가 차원
- **People**: 기술, 교육, 경험, 인증
- **Processes**: 운영 계획, 방법론, 보고, QA
- **Technology**: 도구, 인프라, 자동화, 커스텀 개발
- **Program Management**: 전략 정렬, 메트릭, 이해관계자, 개선

**현실**: 대부분 조직은 Level 1-2. Level 4 이상은 다년간 투자 필요.

---

## 9. Decepticon 에이전트 역량 갭 분석

### 현재 커버리지 (스킬 기준)

| Phase | 상태 | 커버리지 |
|-------|------|---------|
| Planning | ✅ 완전 | RoE, Threat Profile, CONOPS, OPPLAN |
| Reconnaissance | ✅ 대부분 | Passive, OSINT, Cloud, Active, Web |
| OPSEC | ✅ 완전 | 네트워크/HTTP/도구/소스 관리 |
| Initial Access | ❌ 미구현 | 피싱, 페이로드, 소셜 엔지니어링 없음 |
| Execution | ❌ 미구현 | C2 에이전트, BOF, 스크립팅 없음 |
| Persistence | ❌ 미구현 | (red-run 레퍼런스 16개 기법 존재) |
| Privilege Escalation | ❌ 미구현 | (red-run 레퍼런스 11개 기법 존재) |
| Defense Evasion | ⚠️ 부분 | OPSEC 스킬만 (AV/EDR 회피 없음) |
| Credential Access | ❌ 미구현 | (red-run 레퍼런스 존재) |
| Lateral Movement | ❌ 미구현 | (red-run 레퍼런스 존재) |
| Collection/Exfil | ❌ 미구현 | |
| C2 | ❌ 미구현 | |
| Reporting | ⚠️ 부분 | Recon 보고만 (공격 내러티브 없음) |

### red-run 레퍼런스에서 활용 가능한 스킬 (67개)
- **Web (33)**: SQLi, XSS, SSTI, SSRF, LFI, 커맨드 인젝션, XXE, 역직렬화 등
- **AD (16)**: Kerberoasting, PTH, ADCS, ACL 남용, 신뢰 공격 등
- **Privesc (11)**: Windows 토큰 위장, UAC 우회, Linux SUID/sudo 남용 등
- **Network (4)**: 피벗/터널링, 컨테이너 탈출, SMB 익스플로잇
- **Evasion (1)**: AMSI 우회, ETW 패칭, LOLBin

### 우선 확장 로드맵
1. **즉시**: Initial Access 스킬 (피싱 오케스트레이션, 페이로드)
2. **단기**: red-run 익스플로잇 스킬 Decepticon 포맷 적응
3. **중기**: C2 인프라, 지속성/횡이동 체이닝, Purple Team 워크플로우
4. **장기**: 클라우드 Red Team (AWS/Azure), 물리 보안, 위협 인텔 피드 통합

---

## 참조

- MITRE ATT&CK Enterprise Matrix: https://attack.mitre.org/matrices/enterprise/
- MITRE CTID Adversary Emulation Library: https://ctid.mitre.org/resources/adversary-emulation-library/
- ECB TIBER-EU Framework 2025: https://www.ecb.europa.eu/paym/cyber-resilience/tiber-eu/
- NIST SP 800-53 CA-8(2): https://csf.tools/reference/nist-sp-800-53/r5/ca/ca-8/ca-8-2/
- DORA TLPT RTS (2025): https://www.blazeinfosec.com/post/threat-led-penetration-testing-for-dora/
- PCI DSS 4.0 Req 11.4: https://deepstrike.io/blog/pci-dss-penetration-testing-2025-guide
- CISA AA24-326A: https://www.cisa.gov/news-events/cybersecurity-advisories/aa24-326a
- Red Team Capability Maturity Model: https://www.redteammaturity.com/
- Verizon DBIR 2025: 74% 침해가 손상된 자격 증명 관련
