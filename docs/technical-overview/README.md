# Technical Overview — PASS 0–6 산출물

최신 후속 완료: 승인된 한국어 본문을 유지한 [영문·코드 용어 대응표](TERMINOLOGY_CROSSWALK.md)를 추가하고, [핵심 원리 보강 계획](CORE_PRINCIPLES_EXPANSION_PLAN_20260910.md)을 실행했다. [선정](CORE_PRINCIPLES_SELECTION.md)→[근거 카드](CORE_PRINCIPLES_EVIDENCE_CARDS.md)→[배치 설계](CORE_PRINCIPLES_BLUEPRINT.md)→본문 보강→[검증보고서와 교정](CORE_PRINCIPLES_VERIFICATION.md) 순서다. 현재 문서는 AST·페이지 해석·네 종류의 중복·검증 목적·상태 관리의 추가 설명과 통제 예제를 포함한다. 아래 이전 단계의 미착수·테스트 수·도식 수는 당시 기록이다.

2026-09-10 독자 피드백 후속: [도식·용어·사례 교정 기록](READER_FEEDBACK_REVISION_20260910.md). 현재 최종 문서는 이 교정을 포함한다. 네 Mermaid 도식은 실제 렌더링까지 확인했다. 아래 PASS5/6 해시·기록은 최초 완료 당시의 역사적 기록이며, 최신 문서의 해시·렌더링 검증은 후속 기록에서 확인한다. [핵심 원리 보강 계획](CORE_PRINCIPLES_EXPANSION_PLAN_20260910.md)은 계획 단계이고 심화 분석·본문 보강은 미착수다.

사용자 제공 prompt를 로컬 roadmap으로 복제하고, 현재 source에서 실행 원리를 복원한 뒤 blueprint, 최종 설명문, 구현 대조와 교정까지 완료했다. 처음 읽는 독자는 [최종 Technical Overview](../ASL_OCR_TECHNICAL_OVERVIEW.md)부터 읽으면 된다. 분석 목적의 표·카드, 수정 전 사본, 최종 문서를 구분한다.

## 순차 입력과 산출물

| 단계 | 입력 | 산출물 / 완료 범위 |
|---|---|---|
| Roadmap | 사용자 prompt 원문 | [ROADMAP_PROMPT.md](ROADMAP_PROMPT.md): 전체 PASS0–6 지침 보존 |
| PASS0 COMPLETE | roadmap + 현재 entrypoint/composition/dependency inventory | [Scope & Baseline](PASS_0_SCOPE_BASELINE.md): 목적·I/O·entrypoints·경로·components·dependencies/tests·legacy/alternative·questions |
| PASS1 COMPLETE | PASS0의 E0/E1/E2·primary paths·Q1/Q2/Q4 | [Execution Reconstruction](PASS_1_EXECUTION_RECONSTRUCTION.md): W01–W20 의미 있는 단계, 정상/주요 실패 연결 |
| PASS2 COMPLETE | PASS1의 W01–W20 | [Algorithms & Decisions](PASS_2_ALGORITHMS_AND_DECISIONS.md): 단계 분류, A01–A11 분석 카드, J01–J17 판단 inventory |
| PASS3 COMPLETE | PASS1 workflow + PASS2 algorithm/decision | [Data & Failures](PASS_3_DATA_AND_FAILURES.md): D01–D15 변환, I01–I03 ID/completion/owner, F01–F28 실패, X01–X05 사례 근거 |
| PASS4 COMPLETE | PASS0–3의 분석 결과 | [Documentation Blueprint](PASS_4_DOCUMENTATION_BLUEPRINT.md): 9개 concept 절·4.1–4.8 세부 설계, Mermaid 필수4/선택1 사양, M01–M17 source/test 연결, 7개 품질 질문 대응 |
| PASS5 COMPLETE | 완료된 PASS4 blueprint | [Technical Overview](../ASL_OCR_TECHNICAL_OVERVIEW.md): 9개 개념 절·4개 Mermaid. 검증 전 [원본 사본](PASS_5_DRAFT.md.snapshot)과 [완료 기록](pass5_record.json) 보존 |
| PASS6 COMPLETE | 완성된 PASS5 + 현재 source/tests | [검증보고서](PASS_6_VERIFICATION_REPORT.md)를 먼저 작성하고 8개 보완 사항 반영. [초기 보고서 사본](PASS_6_INITIAL_REPORT.md.snapshot) 보존 |

각 단계의 목적을 완료한 후 다음 산출물을 작성했다. 최초 PASS0–4 실행 기록은 [analysis_run_record.json](analysis_run_record.json)에 역사적 기록으로 유지한다. 후속 PASS5/6의 순서·검증·최종 hash는 [pass56_record.json](pass56_record.json)에 기록한다. `.md.snapshot`은 수정 전 byte 사본이며 그 안의 링크는 원래 문서 위치를 기준으로 해석한다.

## 현재 분석에서 고정한 핵심 구분

- Laptop footer M1 / Desktop 본문 PaddleOCR-VL.
- page contour 가중점수 / stable frame의 lexicographic ranking.
- raw identity DIFFERENT / page-change 촬영 허가.
- local durable outbox / V4 receipt / S1 page-ready / READY revision.
- AST 파싱 유효성 / OCR 원문 정확도 / 음성과 점자의 신뢰 정책.
- DOCUMENT text clear / TABLE cell buffer의 지원 범위.
- S0 generation / host audio epoch / FRAME version / 실제 physical cell.
- 현재 Windows production 경로 / H1·H2·H3 harness 경계 / 미검증 Pi4 배포 계획.

## 작업 범위와 검증

- 기준 HEAD: `b6005f13b0283cc6cac128a5016140613b7ee1ae`. [baseline.json](baseline.json)에 당시 tracked source247개의 SHA256 보존.
- product source·firmware·config·threshold·인증 정책 변경 없음. 문서와 분석 기록만 작성.
- PASS0–4에서는 source/문서 무결성만 확인했다. PASS6에서는 완성된 문장·도식을 source와 대조하고, fake adapter·임시 저장소·순수 변환의 선정 suite를 실행했다: 최종252 passed와3 subtests passed. Device 첫 실행의 임시 폴더 권한 오류와 격리 재실행을 모두 보존했다.
- 모델 inference, 실제 Piper 재생, production server upload, SSH, camera/serial/servo 실기기 실행 없음. 과거 H1 증거, 이번 fake/pure 테스트, 미래 hardware acceptance는 분리한다. Mermaid는 내용·구조를 검토했으며 별도 renderer 실행 여부는 검증보고서에 명시한다.
- hardware/Pi acceptance, 과거 liveness/native crash 미확정 원인은 그대로 남김. 이 문서 묶음의 완료를 integration-ready 또는 H4 PASS로 해석하지 않음.

권장 열람: 개념 이해는 최종 Technical Overview, 교정 근거는 PASS6, 설명 구조는 PASS4, 상세 분석은 PASS0→1→2→3 순서.

최신 후속 반영: [방정식 예제·용어 병기·도식 줄바꿈 검증](EQUATION_AND_BILINGUAL_REVISION_20260910.md). 현재 개요는 `(x+1)^2=9` 예제와 도식 5개를 사용한다. 이전 단계의 예제와 해시는 당시 기록으로 보존한다.
