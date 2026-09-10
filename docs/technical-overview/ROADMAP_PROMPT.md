목적

이 작업의 목적은 프로젝트의 코드를 파일별 또는 함수별로 해설하는 것이 아니다.

최종 목표는 이 프로젝트를 처음 접하는 사람이 소스 코드를 직접 읽기 전에 다음을 논리적으로 이해할 수 있는 Technical Overview 문서를 만드는 것이다.

- 프로젝트가 해결하는 문제
- 전체 시스템의 작동 구조
- End-to-End Workflow
- 결과를 결정하는 핵심 알고리즘
- 주요 판단 기준과 분기
- 데이터가 단계별로 어떻게 변환되는지
- 실패와 fallback이 어떻게 처리되는지
- 이러한 개념이 실제 코드의 어느 부분에 구현되어 있는지

코드의 구조 자체가 문서의 설명 순서를 결정해서는 안 된다.

먼저 실제 구현에서 시스템의 작동 원리를 복원하고, 이를 독자가 이해하기 좋은 개념적 구조로 재구성한 뒤 최종 문서를 작성한다.

---

기본 원칙

1. 파일이나 클래스 순서대로 문서를 작성하지 않는다.
2. 모든 함수와 클래스를 설명하지 않는다.
3. 시스템의 행동과 결과를 결정하는 알고리즘, 데이터 변환, 판단 로직을 우선한다.
4. 단순 I/O, logging, wrapper, serialization 등의 구현 세부사항은 시스템 이해에 필요하지 않으면 축약한다.
5. 코드에서 확인되지 않는 설계 의도는 추측하지 않는다.
6. README나 기존 문서의 설명보다 현재 실행되는 코드를 우선한다.
7. legacy 또는 사용되지 않는 코드는 현재 핵심 구조와 분리한다.
8. 각 Pass의 목적을 완료하기 전에 다음 Pass의 작업을 미리 수행하지 않는다.
9. 분석 단계에서는 최종 문서 prose를 작성하지 않는다.
10. 최종 문서는 코드 해설서가 아니라 System / Algorithm Walkthrough가 되어야 한다.

---

PASS 0 — Scope & Baseline

프로젝트 전체를 빠르게 조사하여 분석 범위를 확정한다.

확인한다.

- 프로젝트 목적
- 주요 입력과 출력
- 실행 entry point
- 대표적인 실행 방법
- 주요 subsystem
- 외부 dependency
- 테스트
- 현재 사용되는 코드
- legacy / experimental / unused code
- 분석 과정에서 추가 확인이 필요한 사항

산출물:

Project Scope

Entry Points

Primary Execution Paths

Major Components

External Dependencies

Legacy / Unused Areas

Open Questions

이 단계에서는 핵심 알고리즘을 상세 분석하거나 최종 문서를 작성하지 않는다.

---

PASS 1 — End-to-End Execution Reconstruction

대표적인 정상 실행 경로를 entry point부터 최종 출력까지 실제 코드를 따라 추적한다.

필요하다면 주요 실패 경로도 추가한다.

모든 함수 호출을 나열하지 말고 시스템 작동을 이해하는 데 의미 있는 단계만 추출한다.

각 단계마다 다음을 기록한다.

- Step
- Purpose
- Input
- Operation
- Output
- Decision or branch
- Next step
- Relevant implementation

최종적으로 전체 실행 흐름을 하나의 End-to-End workflow로 재구성한다.

---

PASS 2 — Core Algorithm & Decision Analysis

PASS 1에서 확인한 각 처리 단계를 다음으로 분류한다.

- Core Algorithm
- Decision Logic
- Supporting Processing
- Infrastructure / Plumbing

Core Algorithm과 Decision Logic을 중심으로 상세 분석한다.

각 핵심 알고리즘에 대해:

- 해결하려는 문제
- 왜 이 단계가 필요한지
- 입력
- 사용되는 정보
- 핵심 아이디어
- 처리 과정
- 판단 기준
- 출력
- 다음 단계와의 관계

를 분석한다.

다음 종류의 판단 로직을 별도로 수집한다.

- threshold
- ranking
- filtering
- branching
- retry
- fallback
- early exit
- confidence handling

상수값 자체보다 해당 값이 어떤 시스템 행동을 통제하는지를 설명한다.

---

PASS 3 — Data Flow & Failure Analysis

주요 데이터 객체가 시스템을 통과하면서 어떻게 변환되는지 추적한다.

각 단계에서 확인한다.

- 입력 데이터의 형태와 의미
- 출력 데이터의 형태와 의미
- 추가되는 정보
- 제거되거나 손실되는 정보
- 추가되는 metadata
- 다음 단계가 기대하는 invariant 또는 전제조건

별도로 실패 흐름을 분석한다.

- 어떤 조건에서 실패하는가
- 실패를 어떻게 감지하는가
- retry가 존재하는가
- fallback이 존재하는가
- 결과를 포기하는 조건은 무엇인가
- exception과 정상적인 failure result를 어떻게 구분하는가

정상 흐름과 실패 흐름을 각각 구조화한다.

---

PASS 4 — Documentation Blueprint

PASS 0~3의 분석 결과를 이용해 최종 문서의 설명 구조를 설계한다.

아직 최종 문장을 작성하지 않는다.

다음 목차를 기준으로 각 절의 역할을 결정한다.

1. 프로젝트가 해결하는 문제

2. 시스템 전체 구조

3. End-to-End Workflow

4. 핵심 처리 단계
   4.1 입력 및 전처리
   4.2 핵심 알고리즘 A
   4.3 핵심 알고리즘 B
   4.4 결과 생성

5. 주요 데이터와 데이터 변환

6. 판단 로직
   
   - threshold
   - ranking
   - fallback
   - retry

7. 대표적인 실행 예시
   입력 → 중간 결과 → 최종 결과

8. 실패하는 경우와 한계

9. 코드 구조와의 대응
   
   - 어느 모듈이 어느 역할을 구현하는지

각 Section마다 다음을 정의한다.

- Purpose
- Reader should understand
- Required facts
- Required diagrams
- Evidence from previous passes
- Information that should not be included

필요한 경우 실제 프로젝트 특성에 맞게 4.x 세부 항목의 이름과 개수를 변경할 수 있다.

단, 전체 설명 구조를 코드 디렉터리 구조에 맞추지는 않는다.

---

PASS 5 — Final Technical Overview

PASS 4의 Blueprint를 기반으로 최종 문서를 작성한다.

대상 독자는:

- 개발 경험은 있을 수 있으나 이 프로젝트는 처음 접함
- 소스 코드 전체를 먼저 읽고 싶지는 않음
- 프로젝트의 핵심 원리와 처리 흐름을 먼저 이해하고 싶음

작성 순서는 가능한 한 다음 원칙을 따른다.

문제
→ 왜 해결이 어려운가
→ 프로젝트가 선택한 접근
→ 입력
→ 처리
→ 판단
→ 출력
→ 다음 단계

클래스명과 함수명보다 개념을 먼저 설명한다.

실제 코드 위치는 개념 설명 이후 연결한다.

필요한 곳에는 Mermaid diagram을 사용한다.

다음 종류의 diagram을 우선 고려한다.

- 전체 architecture / workflow
- 데이터 transformation
- 주요 decision flow
- 대표적인 실행 사례

코드 블록은 알고리즘 이해에 실제 도움이 될 때만 사용하고, 소스 코드를 장시간 그대로 복사하지 않는다.

---

PASS 6 — Verification Against Implementation

완성된 문서를 실제 코드, 테스트, 실행 경로와 다시 대조한다.

각 문장과 도식에서 다음 문제를 확인한다.

- Incorrect
- Unsupported
- Oversimplified
- Missing
- Outdated
- Ambiguous

특히 다음을 집중 점검한다.

- 실제 호출 순서와 다른 설명
- 사용되지 않는 legacy code를 현재 구조로 설명
- fallback을 정상 workflow로 오해
- 이전 README의 설계를 현재 구현으로 오해
- threshold 또는 상수의 의미를 근거 없이 추측
- failure path 누락
- 데이터 변환 단계 누락
- 핵심 알고리즘보다 주변 구현을 과도하게 설명

먼저 Verification Report를 작성한다.

각 문제에 대해:

- Finding
- Evidence
- Impact
- Required correction

을 기록한다.

이후 해당 문제를 반영하여 최종 문서를 수정한다.

---

최종 품질 기준

최종 문서를 읽은 사람이 소스 코드를 열기 전에 다음 질문에 답할 수 있어야 한다.

1. 이 프로젝트는 어떤 문제를 해결하는가?
2. 입력이 들어오면 어떤 단계를 거쳐 출력이 생성되는가?
3. 결과의 품질과 행동을 결정하는 핵심 알고리즘은 무엇인가?
4. 중요한 판단과 분기는 어디에서 발생하는가?
5. 데이터는 각 단계에서 어떤 형태로 바뀌는가?
6. 무엇이 실패할 수 있으며 실패 시 어떻게 처리되는가?
7. 각 개념은 실제 코드 어디에 구현되어 있는가?

이 질문에 답할 수 없다면 문서는 아직 완성된 것으로 간주하지 않는다.
