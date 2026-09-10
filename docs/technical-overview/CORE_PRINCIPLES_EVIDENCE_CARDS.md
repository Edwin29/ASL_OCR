# 핵심 원리 근거 카드

입력: [선정표](CORE_PRINCIPLES_SELECTION.md), PASS2/3 분석, 현재 소스. 이 문서는 본문 초안이 아닌 분석 카드다. [격리 예제](evidence/core_principles_examples.py)와 [실행 결과](evidence/core-principles-examples.json)는 모델 결과를 통제한 예제이며 실제 OCR/Piper/카메라/하드웨어는 실행하지 않았다.

## K1 — AST의 실제 역할

| 항목 | 근거 |
|---|---|
| 문제·필요성 | 문자열의 기호 순서와 분자·분모 같은 관계를 구별하고 두 출력 규칙이 같은 구조를 사용해야 함 |
| 입력·정보 | LaTeX, token, parser issues, unconsumed tokens |
| 처리·판단 | parse_latex_to_ast→구조와 오류; classify_ast_status→VALID/PARTIAL/INVALID; 음성과 점자 소비 정책 분리 |
| 출력·다음 단계 | AST→한국어 발화와 logical braille; 수식 구간/점자 buffer가 탐색 대상 |
| 코드 | [latex_ast:78](../../document-parser/src/document_parser/math/latex_ast.py#L78), [VL formula:230](../../document-parser/src/document_parser/serialization/vl_page_ir.py#L230), [상태 분류:37](../../document-parser/src/document_parser/accessibility/flattening/structure_nodes.py#L37), [speech:54](../../document-parser/src/document_parser/accessibility/speech/math_rules.py#L54), [braille:43](../../document-parser/src/document_parser/accessibility/braille/math_translator.py#L43), [navigation:114](../../document-parser/src/document_parser/accessibility/application/document_navigator.py#L114) |
| 실행 | 분수1/2→VALID/‘2분의 1’/[60,3,12,60,1]; 미지원 command→PARTIAL·경고 발화·점자[]; 깨진 분수→INVALID·경고만·점자[] |
| 실패·한계 | 원문 인식 오류를 AST가 증명하지 못함. VALID라도 점자 기호 미지원 가능. navigation은 AST node traversal이 아니라 item/span/window 기반 |
| 의도와 효과 | parser·출력 코드/주석이 구조·정책 분리를 직접 보여 줌. 최초 채택 당시 대안 비교·성능 우위는 확인하지 않음 |

## K2 — 페이지를 읽을 구조로 바꾸는 경로

| 항목 | 근거 |
|---|---|
| 문제·필요성 | 인식 문자열의 평면 목록만으로는 표·수식·문제 구성·선택 순서가 정해지지 않음 |
| 입력·정보 | VL block_label/content/order/bbox; text·LaTeX·HTML |
| 처리·판단 | 명시 순서 정렬, 순서 없는 header/footer 분리; bbox 불가 block skip; 종류별 Page IR; 문제 marker/answer structure 근거로 grouping; 형식 검증 후 flatten |
| 출력·다음 단계 | Page IR의 노드와 읽기 순서→AccessiblePage의 항목·문제 ID·표 구조→S0 탐색 |
| 코드 | [production parser:37](../../document-parser/src/document_parser/server/s1_parser.py#L37), [VL 순서:104](../../document-parser/src/document_parser/serialization/vl_page_ir.py#L104), [문제 분류](../../document-parser/src/document_parser/structure/problem_units.py), [table_html](../../document-parser/src/document_parser/serialization/table_html.py), [flatten:70](../../document-parser/src/document_parser/accessibility/flattening/structure_nodes.py#L70) |
| 실행 | 뒤섞인 입력 block3/4/1/2→문제표식·지문·분수·선택지 4개 focus, 모두 같은 problem_id. schema_valid=true |
| 반례 | formula bbox를 없앤 동일 fixture→수식 영역 skip→TEXT 3개, schema_valid=true. 형식 적합이 이미지 내용 보존 증명은 아님 |
| 한계 | 순서 모델의 오류·silent omission, 추정 표 좌표, 제한된 grouping 규칙. ‘AI가 문제 의미를 이해’ 또는 범용 문서 이해라고 주장 불가 |
| 의도와 효과 | 실질 효과는 종류·위치·관계 보존과 탐색 표현 분리. no-silent-loss 주석이 있어도 입력 block skip의 한계는 별도임 |

## K3 — 네 종류의 중복

| 경계 | 입력·처리·판단 | 결과·근거 | 한계 |
|---|---|---|---|
| K3a 재촬영 억제 | 다른 frame의 raw L/R pair와 전송된 reference, exact match·고정N consensus·visual/numeric gate | [collector:134](../../book-scanner/src/book_scanner/video/opaque_identity.py#L134), [engine:651](../../book-scanner/src/book_scanner/video/engine.py#L651). 기준26/27, 동일 쌍1개→same; 28/29 5개→different+numeric; 제각각5개→unknown | 반복된 오인식·장기 대기 가능. raw 판정 예제는 live capture 전체 수용이 아님 |
| K3b 좌우 겹침 | 페이지 mask와 seam, ambiguous 띠를 양 conservative mask에 합침 | [ownership:296](../../book-scanner/src/book_scanner/detect/spine_seam.py#L296), [production extraction:193](../../book-scanner/src/book_scanner/detect/spread_extraction.py#L193). 좁은 경계 겹침은 내용 보존 처리 | OCR 내용의 전역 dedupe가 아님. 겹친 본문이 어떻게 보이는지는 실제 결과 확인 필요 |
| K3c 요청 재실행 | 작업 식별자와 요청 digest를 비교하고 저장된 응답/논리 작업 재사용 | [V4:90](../../document-parser/src/document_parser/server/v4_upload.py#L90), [S0:460](../../document-parser/src/document_parser/server/s0_services.py#L460). 같은 request replay와 다른 내용 conflict tests 통과 | 새로 촬영해 다른 작업으로 보낸 이미지가 같은 책장인지 판정하는 기능과 다름 |
| K3d 항목 중복 | 문제 역할 목록·추가 membership 합친 뒤 node ID/visited로 중복 제거 | [flatten:165](../../document-parser/src/document_parser/accessibility/flattening/structure_nodes.py#L165). 같은 member ID를 reading_order에 추가해도4개 유지 | 동일 문자열을 가진 별개 node ID까지 지우지 않음. 반복 웹 주소는 이동 실패 증거 아님 |

K3a의 쌍 비교는 해시 유사도가 아니라 raw 문자열 exact match다. pHash/ORB는 page-change의 추가 영상 조건이다. ‘관측5개가 모두 다르니 새 페이지’는 구현상 성립하지 않는다. 선택된 테스트가 이 반례를 막는다.

## K4 — 검증은 어느 보장을 넘겨주는가

| 경계 | 막는 실패 | 통과 의미 | 남는 한계·근거 |
|---|---|---|---|
| 카메라 decode/limit | 깨진 이미지·과도한 크기 | 해독 가능한 영상 | 선명한 내용·맞는 방향과 다름. [sources](../../book-scanner/src/book_scanner/video/sources.py) |
| 촬영 readiness·양쪽 보정 | 한쪽 부재·부적합 보정 | 전송할 L/R 준비 | OCR 정확성은 아님. [preparer](../../book-scanner/src/book_scanner/video/spread_preparer.py) |
| hash·수신 identity | 파일 손상·다른 요청의 확인서 | 의도한 파일의 저장 확인 | 해석 완료와 다름. [V4](../../document-parser/src/document_parser/server/v4_upload.py), [delivery](../../device-runtime/src/asl_device/delivery.py) |
| Page IR schema·참조 | 필수값·좌표·참조 구조 오류 | 다음 코드가 사용할 구조 | 누락 내용·잘못 읽은 식은 통과 가능. K2 반례 |
| cutoff/revision inventory | 미처리 페이지·음성 누락·변조 파일 게시 | 읽을 수 있는 버전 구성 | 교재 원문 전수 일치는 아님. [assembler](../../document-parser/src/document_parser/server/s1_assembler.py), S1 finalize tests |
| audio scope/format/hash | 다른 작업 파일·잘못된 WAV | 해당 재생 작업의 유효 resource | 귀에 들림과 다름. [audio adapter](../../device-runtime/src/asl_device/adapters/reading_audio.py) |
| FRAME grammar/range | 잘린 줄·잘못된 필드·범위 밖 셀 | firmware가 수락할 요청 | 실제 돌출 보장은 없음. [firmware:766](../../hardware/stm32/kitel2026final/Core/Src/main.c#L766) |

핵심 효과는 큰 하나의 PASS 대신 다음 단계가 의존할 조건을 나누는 것이다. 각 검증을 제거한 product mutation 실험은 하지 않았다. 막는 실패 설명은 실제 reject 분기·기존 targeted tests·격리 반례에 근거한다.

## K5 — 지속 상태와 최신 출력 권한

| 항목 | 근거 |
|---|---|
| 문제·입력 | 입력이 처리됐으나 응답이 유실됨, 앱 재시작, 이전 음성 fetch가 늦게 완료됨 |
| 저장 원리 | transaction 안 임시 session에서 계산→progress+command receipt 동시 commit→응답. replay는 저장 응답 반환 |
| 복구 원리 | stable device/datapack progress, page/focus anchors, 조건이 같은 열린 session 재사용. 손상 상태 conflict |
| 출력 원리 | 서버 generation과 host epoch를 분리. 취소 후 늦은 결과는 current job이 아니므로 재생/완료 권한을 갖지 못함. serial은 latest desired frame version 사용 |
| 코드 | [S0:348](../../document-parser/src/document_parser/server/s0_services.py#L348), [S0:460](../../document-parser/src/document_parser/server/s0_services.py#L460), [audio:199](../../device-runtime/src/asl_device/reading_audio.py#L199), [audio current:308](../../device-runtime/src/asl_device/reading_audio.py#L308), [serial:154](../../device-runtime/src/asl_device/adapters/stm_serial.py#L154) |
| 테스트 | S0 restart/receipt/resume, late-fetch cancellation, native owner/cancel lifecycle, serial fake tests |
| 한계 | 응답 유실 후 서로 다른 command ID로 다시 보내면 같은 replay가 아님. 취소는 native 강제종료 보장이 아니며 physical FRAME feedback도 없음 |

## 실행 증거

- [Scanner](evidence/core-scanner-pytest.txt): 26 passed (identity/page-change/seam).
- [Parser](evidence/core-parser-pytest.txt): 109 passed (AST/VL/problems/flatten/finalize/S0).
- [Device](evidence/core-device-pytest.txt): 52 passed (audio/native lifecycle/serial).
- [V4](evidence/core-v4-pytest.txt): 4 passed (같은 key replay, 다른 key 논리 replay, conflict, hash reject).
- 총191 passed. package별 별도 process, bytecode/cacheprovider 비활성화, 새 진단 임시 폴더 사용. 실제 production I/O·모델·hardware 없이 fake/pure/임시 저장소로 확인했다.
- 신규 incident 원인 확정 또는 G3-A/H1–H4 재수용이 아니다. K2 누락 반례는 기존 한계를 구체화한 것이며 product 수정을 수행하지 않는다.

완료: K1–K5의 입력·처리·판단·출력·실패·source·test 범위를 확인했다. 다음 단계는 설명 배치 설계이며 그 완료 후 본문을 보강한다.
