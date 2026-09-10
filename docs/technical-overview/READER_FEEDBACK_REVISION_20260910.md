# 독자 피드백 반영 기록

## 적용 범위

사용자 피드백에 따라 [Technical Overview](../ASL_OCR_TECHNICAL_OVERVIEW.md)의 도식 오류, 영어·내부 명칭 중심 표현, 대표 사례의 설명 방식을 수정했다. 핵심 솔루션의 신규 선정과 설계 이유의 심화 해설은 이번 본문 수정에 포함하지 않았다. 그 작업은 피드백 반영 후 [후속 계획](CORE_PRINCIPLES_EXPANSION_PLAN_20260910.md)으로만 작성한다.

## 도식 오류 재현과 수정

수정 전 문서의 SHA256은 `8e8fc96bb4dd0da6887a32aedf77b705b4aa884af226ac3f455572d03f93cfba`이며 [사본](READER_FEEDBACK_BEFORE.md.snapshot)을 보존했다.

Mermaid 11.12.0과 Microsoft Edge headless로 네 도식을 실제 파싱·렌더링했다. 두 번째 Workflow만 실패했다. 주석 `Note over P: ... 가능; 다음 spread와 overlap`의 세미콜론이 명령 구분자로 해석되어 뒤의 텍스트가 유효한 메시지 구문이 아니게 된 것이 재현 원인이다. [수정 전 오류 기록](evidence/reader-feedback-before/render-results.json)에 엔진의 오류 원문을 남겼다.

주석을 세미콜론 없는 한국어 문장으로 고치고 참여자·메시지 이름도 역할 중심으로 바꿨다. 수정 후 네 도식 모두 실제 엔진에서 파싱과 SVG·PNG 생성에 성공했다. [수정 후 결과](evidence/reader-feedback-after/render-results.json), [Workflow 이미지](evidence/reader-feedback-after/diagram-2.png), [Workflow SVG](evidence/reader-feedback-after/diagram-2.svg)를 보존했다. Workflow 이미지는 직접 열어 한글·화살표·주석 배치를 확인했다. 사용자가 보는 앱의 Mermaid 버전은 확인하지 않았으므로 특정 앱 버전 전체의 호환성까지 주장하지 않는다.

이전 PASS6는 정적 검토만 했으며 실제 렌더러 검증을 수행하지 않았다고 기록돼 있다. 이번 오류는 그 검증 공백을 보여 준다. 앞으로 도식 수정 완료 조건에는 실제 엔진 파싱·렌더링을 포함한다.

## 독자 관점의 수정

| 피드백 | 반영 |
|---|---|
| 용어 설명이 또 다른 영어 용어에 의존 | 한국어 역할 이름·코드 이름·뜻의 3열 용어표. 영상 frame과 점자 FRAME, 영상 snapshot과 읽기 상태 묶음의 차이 명시 |
| 각 파트가 내부 명칭 중심 | §2–6·8의 설명과 도식·표를 한국어 행동·결과 중심으로 다시 작성. 식별자·규약·모델명은 필요한 곳에 병기 |
| 대표 사례가 로그의 나열 | §7 촬영 사례를 사용자 상황→내부 처리→확인 결과로 구성. 긴 자료 ID는 원시 기록으로 연결 |
| 수식 예의 입력·출력이 생소 | 분수 ½→분자·분모 관계→‘2분의 1’→다섯 점자칸→표시 창 순으로 설명. 실제 코드 표기는 보조 열로 배치 |
| 구현 추적성이 사라질 우려 | §9의 source/test 링크와 exact 코드 식별자 유지. 개념 열은 한국어로 변경 |

현재 설명에 이미 있던 내용의 용어와 전달 순서를 고친 것이다. AST 채택 이유, 페이지 해석의 핵심 원리 선정, ‘강점’의 근거 수집 같은 추가 분석을 완료했다고 주장하지 않는다.

## 검증과 보존

- product source·펌웨어·실행 설정 수정 없음. source 기준 해시 점검은 [후속 무결성 결과](evidence/reader-feedback-validation.json)에 기록한다.
- 기존 PASS5/6 사본·검증보고서·시험 로그·실행 기록은 과거 결과로 유지한다. 이번 문서 해시는 수정 후 렌더링 기록에 별도로 남긴다.
- 이번에는 문서 링크·source 해시와 실제 도식만 검증했다. 기존252개 테스트를 새로 실행하지 않았고 실기기 동작도 수행하지 않았다.
- 렌더링 스크립트: [render_diagrams.cjs](evidence/render_diagrams.cjs). 문서 검증 폴더의 고정 버전 Mermaid만 사용했으며 product dependency·lockfile은 바꾸지 않았다.
