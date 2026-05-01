[![English](https://img.shields.io/badge/Language-English-blue?style=for-the-badge)](README.md)
[![한국어](https://img.shields.io/badge/Language-한국어-red?style=for-the-badge)](README_KO.md)

<div align="center">
  <img src="assets/logo_banner.png" alt="Decepticon Logo">
</div>

<h1 align="center">Decepticon — 자율 레드팀 에이전트</h1>

<p align="center"><i>"또 AI 해킹 툴이야? nmap 돌리고 리포트 쓰는 거 아니야?"</i></p>

<div align="center">

<a href="https://github.com/PurpleAILAB/Decepticon/blob/main/LICENSE">
  <img src="https://img.shields.io/github/license/PurpleAILAB/Decepticon?style=for-the-badge&color=blue" alt="License: Apache 2.0">
</a>
<a href="https://github.com/PurpleAILAB/Decepticon/stargazers">
  <img src="https://img.shields.io/github/stars/PurpleAILAB/Decepticon?style=for-the-badge&color=yellow" alt="Stargazers">
</a>
<a href="https://github.com/PurpleAILAB/Decepticon/graphs/contributors">
  <img src="https://img.shields.io/github/contributors/PurpleAILAB/Decepticon?style=for-the-badge&color=orange" alt="Contributors">
</a>

<br/>

<a href="https://discord.gg/TZUYsZgrRG">
  <img src="https://img.shields.io/badge/Discord-참여하기-7289DA?logo=discord&logoColor=white&style=for-the-badge" alt="Discord">
</a>
<a href="https://decepticon.red">
  <img src="https://img.shields.io/badge/웹사이트-decepticon.red-brightgreen?logo=vercel&logoColor=white&style=for-the-badge" alt="Website">
</a>
<a href="https://docs.decepticon.red">
  <img src="https://img.shields.io/badge/문서-docs.decepticon.red-8B5CF6?logo=bookstack&logoColor=white&style=for-the-badge" alt="Docs">
</a>

</div>

<br/>

<div align="center">
  <video src="https://github.com/user-attachments/assets/b3fd40d8-e859-4a39-97f4-bd825694ad96" width="800" controls></video>
</div>

---

## 설치

**사전 요구사항**: [Docker](https://docs.docker.com/get-docker/) 와 Docker Compose v2.

```bash
curl -fsSL https://decepticon.red/install | bash
decepticon onboard   # 대화형 설정 위자드 (프로바이더, API 키, 모델 프로필)
decepticon           # 전체 실행: 터미널 CLI + 웹 대시보드 (http://localhost:3000)
```

→ **[빠른 시작](docs/getting-started.md)** · **[전체 셋업 가이드](docs/setup-guide.md)**

---

## 💖 Decepticon 후원

[![Sponsor](https://img.shields.io/badge/후원하기-Decepticon-red?style=for-the-badge&logo=github)](https://github.com/sponsors/PurpleCHOIms)

AI 기반 위협 환경에 맞선 **공격형 백신**을 만들고 있습니다. 자율 레드팀이 더 강한 방어로 이어진다고 믿으신다면 후원으로 함께해 주세요.

---

## 벤치마크 결과

| 벤치마크 | 난이도 | 통과율 |
|---------|--------|--------|
| [XBOW validation-benchmarks](https://github.com/PurpleAILAB/xbow-validation-benchmarks) | Hard (Level 3) | **7 / 8** |

→ **[벤치마크 전체 인덱스](benchmark/results/README.md)**

---

## Decepticon이란?

AI + 해킹 도구들은 대부분 nmap 돌리고 리포트 출력하는 데모입니다. Decepticon은 다릅니다.

**Decepticon은 전문 자율 레드팀 에이전트입니다.** 실제 공격자처럼 현실적인 공격 체인을 실행합니다 — 정찰, 초기 침투, 권한 상승, 횡이동, C2 — 스캐너가 아닌 실제 공격자의 방식으로.

더 중요한 것은: 스크립트 키디와 레드티머를 구분하는 전문성을 갖추고 있다는 점입니다. 첫 번째 패킷이 나가기 전에 Decepticon은 완전한 인게이지먼트 패키지 — **RoE**, **ConOps**, **디컨플릭션 플랜**, MITRE ATT&CK 매핑이 포함된 **OPPLAN** — 을 생성하고, 모든 행동은 그 규칙 안에서만 동작합니다.

→ **[인게이지먼트 워크플로 상세](docs/engagement-workflow.md)**

---

## 왜 Decepticon인가?

**체크리스트 스캔이 아닌 실제 킬체인.** Decepticon은 OPPLAN을 읽고 열린 경로를 통해 목표를 추적합니다 — 피벗, 적응, 기술 체이닝.

**진짜 인터랙티브 셸.** 실제 공격 도구들은 인터랙티브합니다 (`msfconsole`, `sliver-client`, `evil-winrm`). Decepticon은 영구 tmux 세션에서 명령을 실행하고 인터랙티브 프롬프트를 자동 감지합니다 — 도구가 프롬프트를 띄우면 우회책 없이 후속 명령을 보냅니다.

**하드닝된 샌드박스 격리.** 모든 명령은 운영 네트워크(`sandbox-net`)의 Kali Linux 샌드박스에서 실행되며, 관리망(`decepticon-net`)과 분리되어 있습니다. LangGraph는 Docker 소켓으로 샌드박스를 제어합니다. → **[아키텍처](docs/architecture.md)**

**공격이 방어를 만든다.** [공격형 백신](docs/offensive-vaccine.md) 루프는 발견된 모든 취약점을 자동으로 방어 개선으로 전환합니다. 공격 → 방어 → 검증, 머신 속도로.

---

## 아키텍처

<div align="center">
  <img src="assets/decepticon_infra.svg" alt="Decepticon Infrastructure" width="680">
</div>

두 개의 네트워크로 분리된 설계 — 관리 서비스(LiteLLM, PostgreSQL, LangGraph, Web)는 `decepticon-net`, 샌드박스 / C2 서버 / 타깃은 `sandbox-net`. Neo4j는 양 네트워크에 듀얼-홈으로 두어 관리망의 에이전트가 샌드박스 내부에서 기록한 발견 사항을 영속화할 수 있게 합니다.

→ **[아키텍처 상세](docs/architecture.md)** · **[지식 그래프](docs/knowledge-graph.md)**

---

## 에이전트

킬체인 단계별로 구성된 17개의 전문 에이전트. 각 에이전트는 목표마다 새로운 컨텍스트 윈도우로 시작 — 누적 노이즈 없음.

오케스트레이션 · 정찰 · 초기 침투 · 사후 익스플로잇 · 취약점 연구 · 방어 · 도메인 스페셜리스트 (AD, Cloud, 스마트 컨트랙트, 리버싱, Analyst).

→ **[에이전트 전체 목록 및 미들웨어 스택](docs/agents.md)**

---

## 모델 & 프로바이더

Tier 기반 자격증명-aware 폴백 체인. 사용 가능한 자격증명을 우선순위 순으로 알려주면, 모든 tier에서 primary→fallback 체인이 자동 구성됩니다.

| 프로파일 | 에이전트당 tier | 사용 케이스 |
|----------|------------------|-------------|
| **eco** (기본) | 에이전트별 (orchestrator/exploiter/patcher/analyst=HIGH, execution=MID, recon/soundwave=LOW) | 프로덕션 |
| **max** | 모든 에이전트 HIGH | 고가치 타깃 |
| **test** | 모든 에이전트 LOW | 개발 / CI |

**Tier가 매핑된 프로바이더**: Anthropic, OpenAI, Google Gemini, MiniMax, DeepSeek, xAI, Mistral, OpenRouter, Nvidia NIM, Ollama (로컬).
**구독 OAuth**: Claude Max/Pro/Team, ChatGPT Pro/Plus/Team, Gemini Advanced, Copilot Pro, SuperGrok, Perplexity Pro.

`decepticon onboard`로 설정. → **[모델 전체 레퍼런스 및 폴백 예시](docs/models.md)**

---

## 문서

| 주제 | 문서 |
|------|------|
| 설치 및 첫 인게이지먼트 | [시작하기](docs/getting-started.md) |
| 셋업 / OAuth / 프로바이더 / 대시보드 전체 | [셋업 가이드](docs/setup-guide.md) |
| 모든 CLI 커맨드와 단축키 | [CLI 레퍼런스](docs/cli-reference.md) |
| 모든 `make` 타깃 | [Makefile 레퍼런스](docs/makefile-reference.md) |
| 에이전트 목록 및 미들웨어 | [에이전트](docs/agents.md) |
| 모델 프로필과 폴백 체인 | [모델](docs/models.md) |
| 스킬 시스템과 포맷 스펙 | [스킬](docs/skills.md) |
| 웹 대시보드 기능 및 설정 | [웹 대시보드](docs/web-dashboard.md) |
| 시스템 아키텍처와 네트워크 격리 | [아키텍처](docs/architecture.md) |
| Neo4j 지식 그래프 | [지식 그래프](docs/knowledge-graph.md) |
| 엔드투엔드 인게이지먼트 워크플로 | [인게이지먼트 워크플로](docs/engagement-workflow.md) |
| 공격형 백신 루프 | [공격형 백신](docs/offensive-vaccine.md) |
| Decepticon 기여하기 | [기여 가이드](docs/contributing.md) |

---

## 기여하기

```bash
git clone https://github.com/PurpleAILAB/Decepticon.git
cd Decepticon
make dev     # 핫 리로드로 시작
make cli     # 인터랙티브 CLI 열기 (별도 터미널)
```

→ **[기여 가이드](docs/contributing.md)**

---

## 커뮤니티

[Discord](https://discord.gg/TZUYsZgrRG)에서 질문하고, 인게이지먼트 로그를 공유하고, 기술을 토론하세요.

---

## 면책조항

시스템 소유자로부터 명시적인 서면 허가 없이 어떠한 시스템이나 네트워크에도 이 프로젝트를 사용하지 마십시오. 컴퓨터 시스템에 대한 무단 접근은 불법입니다. 귀하의 행동에 대한 책임은 전적으로 귀하에게 있습니다. 이 프로젝트의 저자와 기여자는 오용에 대한 어떠한 책임도 지지 않습니다.

---

## 라이선스

[Apache-2.0](LICENSE)

---

<div align="center">
  <img src="assets/main.png" alt="Decepticon">
</div>
