# Benchmark Framework

xbow validation-benchmarks 기반 모듈형 벤치마크 프레임워크.
Decepticon 메인 에이전트의 전체 파이프라인(OPPLAN 생성 → sub-agent 위임 → 플래그 캡처)을 CTF 챌린지에 대해 평가한다.

## 사전 요구사항

- Docker + Docker Compose
- `uv` (Python 패키지 매니저)
- xbow 벤치마크 서브모듈 초기화:

```bash
git submodule add https://github.com/PurpleAILAB/xbow-validation-benchmarks benchmark/xbow-validation-benchmarks
git submodule update --init
```

- LangGraph 서버 실행 중 (`http://localhost:2024` 기본)

## 실행 방법

### Makefile (권장)

```bash
# 전체 벤치마크 실행
make benchmark

# 옵션 전달
make benchmark ARGS="--level 1 --batch-size 5"
```

### 직접 실행

```bash
# python -m 으로 실행
uv run python -m benchmark.runner run

# 또는 직접 모듈 호출
uv run python -m benchmark
```

## CLI 옵션

| 옵션 | 단축 | 설명 | 기본값 |
|------|------|------|--------|
| `--level` | `-l` | 난이도 필터 (1-3), 복수 지정 가능 | 전체 |
| `--tags` | `-t` | 태그 필터 (sql-injection, xss 등), 복수 지정 가능 | 전체 |
| `--range-start` | | 시작 인덱스 (1-based) | 처음부터 |
| `--range-end` | | 끝 인덱스 (1-based) | 끝까지 |
| `--batch-size` | `-b` | 배치당 챌린지 수 | 10 |
| `--timeout` | | 챌린지당 타임아웃 (초) | 1800 (30분) |
| `--parallel` | `-p` | 동시 실행 챌린지 수 (1=순차) | 1 |

## 사용 예시

```bash
# 레벨 1 챌린지만 실행
make benchmark ARGS="--level 1"

# SQL injection 태그 챌린지만
make benchmark ARGS="--tags sql-injection"

# 레벨 1 + 레벨 2, 5개씩 배치
make benchmark ARGS="--level 1 --level 2 --batch-size 5"

# 1번~5번 챌린지만 (1-based)
make benchmark ARGS="--range-start 1 --range-end 5"

# 타임아웃 5분으로 줄이기
make benchmark ARGS="--timeout 300"

# 복합 필터
make benchmark ARGS="--level 1 --tags xss --range-start 1 --range-end 10 --batch-size 5 --timeout 600"
```

## 실행 흐름

각 챌린지는 다음 순서로 실행된다:

```
1. setup()           Docker 환경 빌드 및 ��작 (FLAG 주입)
2. _invoke_agent()   LangGraph API를 통해 decepticon 메인 에이전트 호출
                     - 에이전트가 OPPLAN 생성 (RECON + INITIAL_ACCESS)
                     - sub-agent 위임 (recon → exploit)
                     - 플래그 캡처
3. evaluate()        에이전트 응답 + workspace에서 FLAG{...} 패턴 매칭
4. teardown()        Docker 환경 정리 (docker compose down -v)
```

- 타임아웃 발생 시 자동 실패 처리
- teardown은 성공/실패/에러 모든 경우에 실행됨 (finally)

## 스코어링

- **바이너리 판정**: FLAG 캡처 성공 = pass, 실패 = fail
- FLAG 포맷: `FLAG{sha256(CHALLENGE_ID_UPPER)}`
- 결과 집계: 전체 pass rate + 레벨별/태그별 breakdown

## 출력

실행 완료 후 `benchmark/results/`에 두 가지 리포트가 생성된다:

- `{timestamp}.json` — 프로그래밍용 JSON
- `{timestamp}.md` — 리뷰용 Markdown 테이블

## 프로젝트 구조

```
benchmark/
  __init__.py          패키지 엔트리 + 퍼블릭 타입 export
  __main__.py          python -m benchmark 엔트리포인트
  config.py            BenchmarkConfig (timeout, batch_size 등)
  schemas.py           Challenge, ChallengeResult, BenchmarkReport 등 Pydantic 모델
  harness.py           챌린지 실행 오케스트레이터
  runner.py            typer CLI
  reporter.py          JSON/Markdown 리포트 생성
  scorer.py            결과 집계 (레벨별, 태그별)
  providers/
    base.py            BaseBenchmarkProvider ABC
    xbow.py            XBOWProvider (xbow validation-benchmarks)
  results/             리포트 출력 디렉토리
  workspaces/          챌린지별 임시 작업 디렉토리 (gitignored)
```

## Provider 확장

새로운 벤치마크 소스를 추가하려면 `BaseBenchmarkProvider`를 구현한다:

```python
from benchmark.providers.base import BaseBenchmarkProvider

class MyProvider(BaseBenchmarkProvider):
    @property
    def name(self) -> str:
        return "my-benchmark"

    def load_challenges(self, filters: FilterConfig) -> list[Challenge]:
        ...

    def setup(self, challenge: Challenge) -> SetupResult:
        ...

    def evaluate(self, challenge: Challenge, state: EngagementState, workspace: Path) -> ChallengeResult:
        ...

    def teardown(self, challenge: Challenge) -> None:
        ...
```

## 테스트

```bash
# 유닛 테스트 (Docker 불필요, 전부 mocked)
uv run pytest tests/unit/benchmark/ -v

# 린트
uv run ruff check benchmark/ tests/unit/benchmark/
uv run ruff format --check benchmark/ tests/unit/benchmark/
```
