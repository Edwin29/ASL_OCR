# 데이터팩(Datapack) 스키마 설계

[[project_system_architecture_two_scenario]]의 확정 사항(버튼 트리거 / 상시 온라인 / 데이터팩=서빙 준비 완료 상태)을 구현하기 위한 저장 스키마 설계. 이 문서는 **스키마와 그 근거**만 다룬다 — ingest 잡(이미지→데이터팩 생성)과 서버(데이터팩→버튼 이벤트 서빙)의 실제 구현은 다음 단계.

## 설계 원칙: 무엇을 미리 계산하고, 무엇을 서빙 시점에 계산할 것인가

기존 코드를 확인한 결과, 서빙 경로에서 실제로 "느린" 연산은 **OCR(PaddleOCR-VL, 페이지당 평균 62초)**과 **TTS 합성(Piper)** 두 가지뿐이다. 내비게이션 상태 전이(`document_navigator`/`table_navigator`)와 점자 프레임 렌더링(`BraillePresenter`/`viewport.build_frame`)은 순수 Python 리스트 연산 + 비트 패킹으로, 이미 충분히 빠르다(모델 추론이 아님). 따라서:

- **미리 계산해서 저장**: OCR 결과(→ 평탄화된 문서 구조)와 **모든 발화(utterance)의 TTS 오디오**. 둘 다 생성형 모델 추론이라 서빙 중 지연을 유발한다.
- **서빙 시점에 그대로 계산**: 내비게이션 상태 전이와 점자 프레임. 기존 `document_navigator.py`/`table_navigator.py`/`braille_presenter.py` 코드를 서버에서 그대로 재사용하면 된다 — 이 로직을 데이터팩에 미리 구워 넣으면 오히려 오프셋/윈도우 조합이 폭발적으로 늘어나고(긴 수식일수록), 실제 코드와 캐시가 어긋날 위험만 생긴다.

즉 데이터팩은 "①OCR을 다시 돌리지 않아도 되는 평탄화된 문서 + ②TTS를 다시 합성하지 않아도 되는 오디오 인덱스"이고, 그 위에서 돌아가는 상태 기계 자체는 기존 코드를 그대로 쓴다.

## ① 문서 구조 — 새로 설계하지 않고 기존 `AccessibleDocument`를 그대로 저장

[`flatten_document(page_ir)`](../src/document_parser/accessibility/flattening/structure_nodes.py:49)가 만드는 `AccessibleDocument` 딕셔너리(`{document_id, pages: [{page_id, focus_items}], global_reading_order, issues}`, [`accessible_document.py`](../src/document_parser/accessibility/domain/accessible_document.py))가 이미 정확히 "OCR 이후, 평탄화까지 끝난 서빙 준비 상태"다. 이걸 그대로 `document.json`으로 저장한다 — 새 스키마를 만들면 `SpeechController`가 실제로 소비하는 구조와 별개로 관리해야 해서 드리프트 위험만 생긴다.

```
datapacks/{book_id}/document.json   # flatten_document(page_ir)의 출력, 그대로
```

## ② `manifest.json` — 책 단위 메타데이터

```jsonc
{
  "schema_version": 1,
  "book_id": "ebs_2027_math1",
  "title": "2027 수능특강 수학Ⅰ",              // 사용자에게 보여줄 표시명
  "page_ids": ["p003", "p004", "..."],           // document.json의 페이지 순서와 반드시 일치
  "created_at": "2026-08-21T21:20:24+09:00",
  "engine_manifest": { "...": "Page IR의 engine_manifest를 그대로 보존 (OCR 엔진/버전 추적용)" },
  "tts_manifest": { "engine_id": "piper", "voice": "ko_KR-kss-medium", "engine_version": "..." },
  "validation_summary": { "...": "Page IR의 validation_summary를 그대로 보존" }
}
```

`page_ids`를 별도로 갖는 이유: 서버가 "이 책이 몇 페이지짜리인지, 페이지 순서가 뭔지"를 알기 위해 매번 `document.json` 전체를 파싱하지 않아도 되게 하기 위함(책 목록 화면 등 가벼운 조회용).

## ③ 발화(utterance) 열거 — 오디오를 미리 합성할 대상 결정

지금 TTS 텍스트는 `SpeechController._focus_speech(state)`가 상태를 보고 그때그때 계산한다([speech_controller.py:193](../src/document_parser/accessibility/application/speech_controller.py#L193)). 이 디스패치 로직 자체는 순수 함수이므로, ingest 시점에 **문서에 존재하는 모든 focus item/inline 수식 span/표 셀에 대해 같은 디스패치를 미리 돌려서 오디오를 만들어두면** 서빙 중에는 Piper를 절대 호출할 필요가 없다.

**열거 규칙** (각 페이지의 각 `focus_item`에 대해):

| 대상 | key | 텍스트 산출 함수 |
|---|---|---|
| focus item 전체(최초 포커스 시 읽는 것) | `{item.id}` | kind별 분기 — `text_focus_item_to_speech`(TEXT) / `math_focus_item_to_speech`(MATH) / `table_entry_announcement`(TABLE) / `visual_focus_item_to_speech`(UNSUPPORTED_VISUAL) / `item["text"]`(UNKNOWN) — `_focus_speech`와 동일 분기 |
| TEXT item 안의 인라인 수식 span (좌우 연장 진입 시 안내) | `{item.id}#{span_index}` | `math_focus_item_to_speech(span)`, `span_index`는 `braille_scrollable_spans(item)`의 0부터 전부 |
| TABLE 셀 | `{cell.id}` (없으면 `{item.id}#r{row}c{col}`) | `table_cell_announcement(cell)` |

최상위 MATH item은 별도 span 엔트리가 필요 없다 — `braille_scrollable_spans(item)`이 `[item]` 자신을 반환하므로 item-level 엔트리가 곧 span 0의 텍스트와 동일하다.

**경계 메시지(boundary message)는 책과 무관한 고정 문자열 18종**이다(코드에서 전수 확인, `document_navigator.py`/`table_navigator.py`/`speech_controller.py`):

```
문서의 끝입니다. / 문서의 시작입니다. /
문서의 마지막 페이지입니다. / 문서의 첫 페이지입니다. /
이 버튼 입력은 아직 지원되지 않습니다. /
현재 항목을 찾을 수 없습니다. / 이 항목에는 점자로 표시할 수식이 없습니다. /
더 이상 표시할 수식이 없습니다. / 이전에 표시할 수식이 없습니다. /
표를 찾을 수 없습니다. / 표 구조를 인식하지 못했습니다. 표 탐색을 사용할 수 없습니다. /
첫 행입니다. / 마지막 행입니다. / 첫 열입니다. / 마지막 열입니다. /
셀을 찾을 수 없습니다. / 셀 내용의 끝입니다. / 셀 내용의 시작입니다.
```

이건 책마다 반복해서 합성할 이유가 없다 — **책과 무관한 공용 풀**로 한 번만 합성해서 모든 데이터팩이 공유한다.

```
datapacks/_system/audio_index.json   # 위 15개 문자열 -> 오디오, 전역 1벌
datapacks/_system/audio/*.wav
```

## ④ `audio_index.json` — 책별 발화 → 오디오 매핑

```jsonc
{
  "schema_version": 1,
  "utterances": {
    "p003-node-007":     { "text": "...", "wav": "audio/p003-node-007.wav", "duration_ms": 2140, "sample_rate": 22050 },
    "p003-node-007#0":   { "text": "...", "wav": "audio/p003-node-007#0.wav", "duration_ms": 1180, "sample_rate": 22050 },
    "p003-node-012-cell": { "text": "...", "wav": "audio/p003-node-012-cell.wav", "duration_ms": 900, "sample_rate": 22050 }
  }
}
```

`text` 필드를 같이 저장하는 이유: (a) 디버깅/QA 시 오디오를 안 열어봐도 뭐가 합성됐는지 바로 확인, (b) 서버가 오디오 캐시 미스 시 라이브 폴백으로 합성할 때 정확히 같은 텍스트를 재사용(아래 "캐시 미스 대응" 참고).

## 디렉터리 레이아웃

```
datapacks/
  _system/
    audio_index.json
    audio/*.wav
  {book_id}/
    manifest.json
    document.json
    audio_index.json
    audio/*.wav
```

## 캐시 미스 대응 (권장, 필수 아님)

열거 규칙이 `_focus_speech`의 실제 분기와 어긋나거나(코드 변경 후 데이터팩 재생성을 깜빡함 등) 예상 못한 상태에 도달하면, 서버가 오디오 인덱스에 없는 key를 만날 수 있다. 이 프로젝트의 "silent drop 금지" 원칙에 따라 **조용히 무시하기보다, 라이브 Piper 폴백으로 합성하고 즉시 `audio_index.json`에 추가해 다음부터는 캐시 히트가 되도록** 하는 걸 권장한다(자가 치유 캐시). 서버가 어차피 실물 TTS 엔진 어댑터를 하나는 들고 있어야 하므로 추가 의존성은 없다.

## ingest 잡 — 구현 완료 (2026-08-21)

[`src/document_parser/datapack/ingest.py`](../src/document_parser/datapack/ingest.py): `python -m document_parser.datapack.ingest {book_id} {이미지...} --piper-model ... --piper-espeak-data ...`. OCR(`build_document_ir_from_vl`) → `flatten_document` → `enumerate_utterances`(위 열거 규칙) → Piper 합성(`synthesize_all`) → `manifest.json`/`document.json`/`audio_index.json` 기록까지 전 과정을 수행한다. 진행 로그는 이번 GPU 서베이 때와 동일하게 `datetime.now()` 기반 실시간 타임스탬프(`log()`, unbuffered)로 남긴다.

- **재실행 시 이미 합성된 발화는 건너뜀** (`synthesize_all`이 `existing_index`의 텍스트가 같으면 재사용) — Piper 합성이 가장 느린 단계이므로, 중단됐다 재실행해도 처음부터 다시 하지 않는다.
- 잘못된(스키마 무효) Page IR이 들어오면 `ValueError`로 명시적으로 거부한다(조용히 진행하지 않음 — `flatten_document`의 "호출자가 먼저 검증" 규칙을 그대로 지킴).
- OCR에 의존하지 않는 부분(`build_datapack`)과 실제 OCR 호출(`main`)을 분리해뒀다 — 테스트는 `FixtureVlAdapter`(모델 가중치 없이 실제 프로덕션 경로로 Page IR을 만드는, `test_vl_page_ir.py`와 동일한 패턴)로 만든 Page IR을 넣고 페이크 synthesize 함수로 돌린다. `tests/unit/test_datapack_ingest.py`, 9개 테스트 통과(전체 스위트 432 passed / 4 skipped, 회귀 없음).
## 실제 GPU/Piper 환경 end-to-end 검증 — 완료 (2026-08-21)

실제 페이지 2장(p004, p008)으로 실제 GPU OCR(clean venv, `docs/gpu-inference-setup.md`) + 실제 Piper(`ko_KR-kss-medium`)를 써서 ingest를 끝까지 실행했다. GPU venv에 `piper-tts`를 추가 설치(`onnxruntime`/`pathvalidate`만 딸려옴, torch 없음, `pip check` 클린 — DLL 충돌 재발 없음 확인).

- 전체 소요: 1분 55초 (모델 로딩 포함 OCR 94초, 발화 101개 Piper 합성 19초, 시스템 풀 16개 <1초).
- 산출물 검증: `manifest.json`/`document.json`/`audio_index.json`/`audio/*.wav`(101개, 22050Hz mono, 정상 재생 가능) 전부 스키마대로 생성됨. `validation_summary.schema_valid: true`.
- 실제 텍스트/오디오 내용도 확인: item-level 텍스트("(1) 실수 a 의 n 제곱근")와 그 안의 인라인 수식 span 2개("a", "n")가 정확히 분리되어 각각 오디오가 생성됨 — 기존 세션에서 이미 braille로 검증했던 p004의 동일 지점(⠁/⠝)과 일치.
- **문제 없음.**

## 서버(Scenario B 서빙 코어) — 구현 완료 (2026-08-21)

[`src/document_parser/server/session.py`](../src/document_parser/server/session.py): `DatapackSession`이 로드된 `Datapack`(→ [`document_parser/datapack/loader.py`](../src/document_parser/datapack/loader.py)) 위에서 기존 `SpeechController`/`BraillePresenter`를 **그대로** 재사용해 버튼 이벤트를 처리한다 — 이 설계의 핵심 전제("내비게이션은 라이브로 돈다")가 실제로 그대로 구현됐다.

- `DatapackTtsEngineAdapter`: `TtsEngineAdapter` 프로토콜을 구현하되, 실제 합성 대신 `Datapack.audio_by_text`(발화 텍스트 → 오디오, 책+공용 풀 병합)에서 조회한다. **조회 실패 시 조용히 넘어가지 않고 `KeyError`로 즉시 실패** — ingest의 열거 로직과 라이브 내비게이터가 어긋났다는 뜻이므로 재-ingest가 필요하다는 신호.
- `DatapackSession.handle_button(command)`가 트랜스포트에 무관한 단일 진입점 — 향후 HTTP/WebSocket/시리얼 레이어가 이걸 감싸기만 하면 된다.
- **검증**: 실제 프로덕션 경로(`FixtureVlAdapter` + 가짜 synthesizer로 만든 데이터팩)로 문서 전체를 DOWN/UP으로 끝까지 왕복하고, 인라인 수식 span을 LEFT/RIGHT로 왕복하고, 표에 진입/이탈까지 — **`KeyError`가 한 번도 발생하지 않음을 확인**. 이게 이 설계의 핵심 보증(ingest가 만드는 발화 목록과 라이브 내비게이터가 실제로 요청할 수 있는 발화 목록이 정확히 일치)이 실제로 성립한다는 end-to-end 증거다. `tests/unit/test_datapack_loader.py`(2) + `tests/unit/test_server_session.py`(9), 전체 스위트 441 passed / 4 skipped(회귀 없음 — 무관한 기존 flaky 테스트 1개는 별도로 플래그해둠).
- `on_complete`가 즉시 발화한다(`ConsoleTtsEngineAdapter`와 동일 패턴) — 실제 재생은 원격 하드웨어에서 일어나고, 그 완료 ACK는 Phase 5(미구현)가 있어야 존재하므로, 지금은 연속 읽기가 실제 오디오 길이를 기다리지 않고 즉시 다음으로 넘어간다. Phase 5 구현 시 재검토 필요.

## 트랜스포트 접합부(joint) — 프로토콜 미정 상태에서도 고정된 경계 (2026-08-21)

실제 하드웨어 프로토콜(HTTP/WebSocket/시리얼)은 실험이 더 필요해 아직 미정이다. 프로토콜이 안 정해진 상태에서도, **어떤 프로토콜이 오든 절대 다시 안 바뀔 경계선**을 만들어뒀다 — 나중에 프로토콜을 실험/교체할 때 이 아래(`DatapackSession`, 내비게이션 로직)는 절대 다시 건드릴 필요가 없도록.

- [`src/document_parser/server/wire.py`](../src/document_parser/server/wire.py) — **유일하게 고정된 통합 지점**: `handle_wire_command(session, payload: dict) -> dict`. 어떤 트랜스포트든 "바이트 받기 → 이 dict payload로 파싱 → 이 함수 호출 → 반환된 dict를 바이트로 직렬화" 네 단계만 구현하면 된다.
  - 입력: `{"button": "RIGHT", "action": "SHORT"}` 같은 JSON-safe dict. 잘못된 버튼/액션은 예외를 던지지 않고 `{"error": "..."}`를 반환 — 트랜스포트 레이어가 이 호출 주변에 자기만의 try/except를 또 만들 필요가 없다.
  - 출력: `{"state": {...}, "braille_frame": {...}, "audio": {"text", "audio_ref", "duration_ms", "sample_rate"} | null}`. **오디오는 참조(절대경로 wav 파일)만 담고 실제 바이트는 안 담는다** — 바이트를 실제로 어떻게 전달할지(HTTP 응답 본문/WebSocket 바이너리 프레임/시리얼 청크)는 트랜스포트마다 다를 수밖에 없는 결정이라 이 경계가 일부러 관여하지 않는다.
- [`src/document_parser/server/store.py`](../src/document_parser/server/store.py) — `SessionStore`: `session_id`(트랜스포트가 뭐든 필요한, 기기/커넥션 식별자) → `DatapackSession` 관리, 데이터팩은 book_id별로 한 번만 로드해 재사용. 세션 도중 책을 바꾸면 기존 세션을 재사용하지 않고 새로 만든다(상태의 `document_id`가 실제로 몰고 있는 문서와 항상 일치해야 하므로).
- **접합부를 만들면서 발견해 같이 고친 실제 버그**: `DatapackTtsEngineAdapter`가 "가장 최근에 말한 오디오"를 그냥 반환하고 있었는데, 좌우 연장의 무음 스크롤(같은 span 안에서 창만 이동, Decision 2) 턴에는 `speak()`가 아예 호출되지 않는다 — 그런데도 `audio` 필드가 이전 턴의 오디오를 계속 반환하고 있었다. 트랜스포트가 이걸 그대로 썼다면 무음이어야 할 스크롤마다 이전 오디오를 잘못 재생했을 것이다. `state.generation`과 오디오가 실제로 발화된 generation을 비교해서, 이번 턴에 새로 말한 게 없으면 `audio: null`을 반환하도록 고쳤다(`tests/unit/test_server_session.py::test_silent_within_span_scroll_reports_no_new_audio`).

**검증**: `tests/unit/test_server_wire.py`(9) + `tests/unit/test_server_store.py`(6) + 위 무음-스크롤 회귀 테스트 1개 추가. 전체 스위트 **458 passed / 4 skipped**, 연속 2회 실행 모두 클린(회귀 없음, flaky 테스트도 이번엔 안 뜸).

## 이번 설계에서 의도적으로 제외한 것

- **실제 프로토콜 구현** (HTTP/WebSocket/시리얼 중 무엇을 쓸지, 프레이밍, 인증, 재연결): `handle_wire_command`가 있으므로 어느 쪽을 골라도 이 함수를 감싸는 아주 얇은 어댑터만 있으면 된다. 실험 후 결정.
- **하드웨어에서 캡처된 원본 이미지의 보관 위치/포맷**: 데이터팩 스키마와는 별개 문제.

## 코드 쪽 선행 작업 — 완료 (2026-08-21)

`_focus_speech`의 kind별 텍스트 분기를 `SpeechController`의 private 메서드에서 [`document_parser.accessibility.speech.focus_item_announcement`](../src/document_parser/accessibility/speech/__init__.py)로 뽑아냈다. `SpeechController._focus_speech`는 이제 이 함수를 호출만 한다. 향후 ingest 잡은 문서의 모든 focus item에 대해 같은 `focus_item_announcement(item)`을 호출해 오디오를 미리 합성하면 되고, 서버(`SpeechController`)와 로직이 어긋날 일이 없다. 전체 유닛 테스트(423 passed / 4 skipped) 회귀 없음 확인.

## 실제 트랜스포트(HTTP) 구현 — 완료 (2026-08-22)

위 "이번 설계에서 의도적으로 제외한 것"의 실제 프로토콜 구현이 STM32 하드웨어 연동 작업 중 실제로 필요해져서 만들어졌다(점자 프레임 쪽만 — 오디오는 여전히 미룸).

- [`src/document_parser/server/http_server.py`](../src/document_parser/server/http_server.py) — `handle_wire_command()`를 HTTP로 감싼 실제 구현. `POST /sessions`(세션 생성, `viewport_size` 지정 가능), `GET /sessions/<id>`(현재 상태 조회, 전진 없음 — HELLO용), `POST /sessions/<id>/command`(버튼 입력 처리). `X-API-Key` 인증, `remote_ingest.py`와 같은 Flask 패턴.
- `document_parser.datapack.remote_ingest`(이미지→데이터팩)와는 완전히 별개 서버다 — 포트도 다르다(8420 vs 8421). 같은 컴퓨터에서 동시에 띄워 쓸 수 있다.
- **왜 이 구조가 필요했는가**: `hardware/stm_pi_bridge/pi_bridge.py`(STM32 브리지)가 처음엔 로컬에 다운로드된 데이터팩 폴더를 직접 읽었는데, 실제 시연 환경엔 호스트 기기에 별도 저장장치가 없어서 이 방식이 안 맞았다. 데이터팩은 서버에만 있고, 호스트는 버튼마다 네트워크로 물어보는 구조로 바꿨다 — `pi_bridge.py`는 이제 완전한 stateless 프로토콜 통역기다.
- 실제 서버를 띄우고 curl로 세션 생성 → 버튼 입력 → 수식 있는 항목까지 이동 → `viewport_size` 정확히 반영 확인 → `pi_bridge.py`의 `format_frame_line()`으로 STM이 기대하는 정확한 `FRAME` 줄이 나오는지까지 실제로 확인했다(자세한 내용은 `hardware/stm_pi_bridge/README.md`).
- 검증: `tests/unit/test_server_http.py`(11, 실제 데이터팩 기반) + `hardware/stm_pi_bridge/test_pi_bridge.py`(12, 가짜 원격 세션 기반, 프로토콜 로직만). 전체 스위트 508 passed / 4 skipped.
- 여전히 미정: 오디오(wav) 실시간 전달 방식(`audio_ref`는 여전히 서버 로컬 파일 경로만 담음), WebSocket/시리얼 등 다른 프로토콜 대안(HTTP로 이미 요구사항을 충족해서 당장 필요성 없음).
