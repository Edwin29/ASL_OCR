# Device Integration E0-B.5-D — Production Full-Model Desktop E2E 작업 패킷

상태: **구현 완료 — 자동/오디오 transport 통과, 비지원 교재 OCR 의미 품질 판정 보류**
기준일: 2026-09-02
성격: **고정 MP4 입력부터 실제 OCR·Piper·Device reading까지 production composition을 검증하는 Desktop E2E**
선행 조건: E0-B.4-D.3 Device audio playback contract 완료, 고정 `test1.mp4`, Book Scanner 및 production model bundle 준비
후속 조건: STM32 firmware/bridge 계약·빌드 패킷, PC live camera 입력 검증, Raspberry Pi 물리 통합

## 1. 배경

현재 E0-B replay는 고정 MP4에서 Book Scanner의 spread 선택, V4 전송, S1/S0 저장, reading navigation,
인증 audio 다운로드와 Desktop 재생까지 주요 연결 계약을 검증한다. 하지만 기존 E0-B bench server는
재현 가능한 경계 검증을 위해 의도적으로 `BenchFragmentParser`와 `BenchSynthesizer`를 사용한다.

따라서 현재 evidence가 증명하는 범위는 다음과 같다.

- spread 2건이 전송되고 ACK되었다.
- server에 fragment 4건이 중복 없이 저장되었다.
- reading cursor가 4개 페이지를 이동했다.
- `audio_ref` 다운로드, latest-generation 재생, 취소, bounded RAM cache가 동작한다.

반면 아래 사항은 아직 하나의 통합 실행으로 입증되지 않았다.

- 실제 PaddleOCR-VL 결과가 S1 Page IR과 accessibility tree로 변환되는가
- 실제 OCR content가 비어 있지 않은 점자 cell로 제공되는가
- 실제 Piper가 그 content에 대응하는 WAV를 생성하는가
- Device Runtime이 그 WAV를 인증 다운로드하고 현재 navigation과 일치시켜 재생하는가

이번 패킷은 replay의 결정론적 scanner 입력은 유지하되, parser와 synthesizer를 production 구현으로
교체하여 이 공백을 닫는다.

## 2. 목표

하나의 Desktop에서 다음 전체 경로를 실행하고 machine-readable evidence와 사용자 청취 결과를 남긴다.

```text
pinned test1.mp4 replay
  -> Book Scanner production recognition / spread selection
  -> V3-B durable outbox
  -> V4 server-owned upload
  -> S1 PaddleOCR-VL fragment parsing
  -> Page IR / accessibility / braille rendering
  -> Piper WAV synthesis and datapack revision publish
  -> S0 reading and authenticated audio resource API
  -> Device Runtime fetch / RAM cache / latest-wins playback
  -> Desktop default audio output
```

완료 판정은 단순히 프로세스가 끝난 것으로 하지 않는다. scanner 수량, server 영속화, 실제 engine
provenance, 접근 가능한 content, 비어 있지 않은 점자, 유효한 Piper WAV, Device 재생 lineage 및 사용자
청취를 모두 확인한다.

## 3. 우선순위와 패킷 크기

이 패킷은 현재 Desktop에서 물리 장치 없이 닫을 수 있는 가장 큰 production 통합 단위다. 작업을 다음
세 구현 묶음으로 나누되 하나의 acceptance로 완료한다.

1. production composition을 실행하는 격리 harness와 model preflight
2. full-model 결과의 provenance/content/audio evidence 수집기
3. 자동 검증 후 사용자 청취를 받는 Windows acceptance entrypoint

실제 모델 구동 문제와 scanner 실시간 카메라 문제를 동시에 다루지 않는다. 고정 MP4를 유지해야 실패가
OCR/parser/synthesizer 경계에 있는지 camera capture 경계에 있는지 구분할 수 있다.

## 4. 범위

### 4.1 포함

- 고정 `test1.mp4`를 사용하는 실제 Book Scanner replay
- run별로 격리된 outbox, server DB, datapack, S1 job/artifact 디렉터리
- production `PaddleOcrVlAdapter`와 `PaddleVlFragmentParser`
- production Piper synthesizer와 실제 한국어 voice bundle
- production V4/S1/S0 service composition
- E0-B.4-D.3 Device Runtime reading audio controller
- 4개 page fragment의 Page IR/accessibility/braille 검증
- 인증된 `audio_ref` 다운로드 및 WAV 무결성·비무음 검증
- Desktop 기본 출력장치의 실제 Piper 음성 사용자 청취
- 모델·입력·코드 revision·engine provenance evidence
- UTF-8 console log와 최종 JSON report

### 4.2 제외

- PC 실시간 camera capture 및 camera enumeration
- STM32 firmware, UART/USB bridge, GPIO/lever 물리 입력
- Raspberry Pi ALSA/PipeWire/I2S/USB 출력
- production 원격 배포, TLS 종료, credential provisioning
- OCR 모델 정확도 개선이나 Book Scanner threshold 조정
- 모든 교재·수식·표 유형에 대한 품질 보증
- Device 영구 WAV 저장 또는 datapack 전체 선다운로드

## 5. 고정 입력과 기대 경계

기준 입력은 E0-B에서 사용해 온 고정 `test1.mp4`다.

- expected SHA-256: `16c57970bc493abcef4a1db0f1917b22956bf5ca1a2ee8b4565fde1f6574e6f8`
- replay sample interval: 100 ms
- expected accepted spreads: 2
- expected page fragments: 4 (`1-L`, `1-R`, `2-L`, `2-R` 순서)
- expected accepted-upload duplicates: 0

실행 전 파일 hash가 다르면 즉시 실패한다. 다른 영상으로 대체하여 2/4/0 수량만 맞추는 것은 이 패킷의
acceptance가 아니다.

OCR 문구 자체는 모델 version과 runtime에 따라 달라질 수 있으므로 전체 문자열을 golden text로 고정하지
않는다. 대신 engine provenance, content 존재, page별 focus item과 braille 가능 content, text digest 및
오디오 lineage를 판정한다.

## 6. Production model preflight

acceptance 실행 전에 다음 자산을 명시적으로 확인한다.

### 6.1 Book Scanner

- 현재 개발 replay에서 사용하는 M1 recognition bundle
- UVDoc model bundle과 checksum
- 적용된 scanner config와 sample interval
- CPU/GPU provider와 library version

### 6.2 PaddleOCR-VL

- production server가 읽는 실제 PaddleOCR-VL model home
- 필요한 모든 model/config/tokenizer 파일
- model bundle checksum 또는 파일별 checksum manifest
- Paddle/PaddleOCR version과 명시적으로 선택된 device

CPU/GPU 선택은 report에 기록한다. GPU 초기화 실패 후 CPU로 자동 전환하거나 model 미존재 시 bench
parser로 대체하면 안 된다. 지원되는 CPU 실행을 선택하는 경우에도 사용자가 지정한 명시적 설정이어야 한다.

### 6.3 Piper

- `ko_KR-kss-medium.onnx`
- 대응하는 `.onnx.json`
- ASCII-only 경로로 준비된 eSpeak NG data
- Piper executable/library version
- voice/config/espeak asset checksum

실행 중 model을 인터넷에서 내려받지 않는다. preflight에 실패하면 어떤 자산이 없거나 hash가 다른지
secret 없이 보고하고 server를 시작하지 않는다.

## 7. Composition 계약

production acceptance는 기존 bench server에 조건문을 추가해 parser/synthesizer만 바꾸는 방식으로 만들지
않는다. production `combined_server`와 같은 composition root가 사용하는 실제 adapter와 service lifecycle을
직접 구성한다.

필수 구성은 다음과 같다.

- `PaddleOcrVlAdapter`
- `PaddleVlFragmentParser`
- production S1 worker lifecycle
- production Piper synthesizer
- durable V4 receipt/upload service
- S0 catalog, reading, navigation, audio resource endpoints
- production auth middleware

run별 state root 밖의 기존 DB나 datapack을 읽거나 변경하지 않는다. server가 준비되었다는 명시적 health
condition을 기다린 뒤 Device replay를 시작하고, 종료 시 S1 worker와 server를 정상 종료한다. 고정 sleep만
사용해서 준비 여부를 추정하지 않는다.

## 8. Fixture 우회 금지

다음 중 하나라도 발견되면 자동 실패한다.

- `BenchFragmentParser`, `BenchSynthesizer` 또는 동등한 fixture adapter 사용
- engine ID나 manifest에 `bench`, `fixture`, `deterministic-bench`가 포함됨
- focus item ID 또는 content에 기존 `-bench-item`, `remote bench content` 패턴이 남음
- model load/parse/synthesis 실패 뒤 fixture 결과로 fallback
- 비어 있는 OCR 결과를 synthetic text로 채움
- Piper 실패 뒤 tone/beep/SAPI WAV로 대체

bench acceptance 경로 자체는 회귀 검증을 위해 그대로 보존한다. 이번 패킷은 별도 production entrypoint와
evidence namespace를 사용한다.

## 9. Windows acceptance entrypoint

대표 진입점은 다음 형태로 제공한다.

```powershell
tools\windows\e0b-production-full-model-desktop-acceptance.bat D:\ASL_OCR_E0B
```

필요 시 model/config 경로는 state root의 versioned manifest 또는 명시적 인자로 받는다. source checkout
내 임의 절대경로를 하드코딩하지 않는다.

entrypoint는 다음을 자동 수행한다.

1. source tree, Git revision, 입력 MP4 hash 및 model bundle preflight
2. run root 생성과 isolated configuration 생성
3. production V4/S1/S0 server 시작 및 readiness 대기
4. Device replay 시작, `New Datapack` 선택 및 새로운 datapack ID 확인
5. 2개의 `candidate_verification`이 각각 5/5 `different`인지 확인
6. `spread_sent` sequence 1, 2 및 `queued_count=2`, `acked_count=2` 확인
7. pending S1 work와 datapack publish가 완료될 때까지 bounded condition wait
8. scan seal/confirm 및 reading session 시작
9. 4개 페이지에서 접근 가능한 content, braille 및 audio resource 확인
10. navigation을 진행하며 실제 audio 자동 재생
11. 사용자에게 각 페이지 음성 청취 결과 입력 요청
12. server DB/evidence/report 수집 후 모든 child process 종료

model 처리 시간은 host 성능에 따라 달라질 수 있으므로 단계별 timeout을 설정 가능하게 한다. timeout은
무한 대기하지 않도록 상한을 가지며, 실패 시 마지막 상태와 처리 중인 fragment/job을 report에 남긴다.

자동 transport만 재검증할 수 있는 `--no-playback` 또는 동등 옵션은 둘 수 있지만, 이 옵션의 결과만으로
패킷을 완료 처리하지 않는다.

## 10. 자동 판정 계약

### 10.1 Scanner와 upload

- `candidate_verification`: 정확히 2개의 5/5 `different`
- `spread_sent`: sequence `1`, `2` 각 1회
- `scan_input_exhausted`: `queued_count=2`, `acked_count=2`
- server spread receipts: 2
- accepted fragments: 4
- accepted-upload duplicates: 0
- 저장된 `spread_id`, `source_frame_id`, sequence, side lineage가 replay log와 일치

`page_change` identity decision은 새 spread가 아니며 spread 수량에 포함하지 않는다.

### 10.2 실제 OCR provenance

4개 fragment 모두 다음을 만족해야 한다.

- production PaddleOCR-VL engine ID/version 존재
- parse status가 성공 terminal state
- Page IR artifact가 존재하고 scan/sequence/side lineage가 일치
- synthetic/bench provenance가 없음
- bounded OCR content summary와 SHA-256 digest가 evidence에 존재

raw image, API key, 전체 model binary는 evidence에 복사하지 않는다.

### 10.3 Accessibility와 braille

- 4개의 고유 page ID가 datapack에 존재
- 각 page에 최소 1개의 focusable/accessible item 존재
- 각 page에서 braille 변환 가능한 item을 찾아 reading snapshot 생성
- 해당 snapshot의 `braille_cells`가 비어 있지 않음
- 모든 cell 값이 `0..63` 범위
- viewport 길이가 Device 설정 상한을 넘지 않음
- cursor의 document/page/focus/generation이 요청한 navigation과 일치

첫 focus item이 이미지나 지원되지 않는 노드라서 점자가 없을 수 있는 경우, harness는 같은 page 안에서
다음 braille-capable item을 탐색한다. page 전체에 점자 가능한 content가 없으면 성공으로 간주하지 않고
원인과 node 종류를 기록한다.

### 10.4 실제 Piper audio

검증 대상 reading resource는 다음을 만족해야 한다.

- TTS engine ID가 `piper`
- voice ID가 준비된 한국어 production voice와 일치
- `bench_only`가 없거나 `false`
- authenticated S0 audio endpoint를 통해서만 조회 가능
- unauthenticated, wrong-session, stale `audio_ref` 요청은 거부됨
- 응답이 parse 가능한 PCM WAV
- sample rate/channels/sample width/duration이 허용 범위
- payload와 declared content length가 일치
- RMS/peak 기준으로 비무음이며 clipping 기준을 넘지 않음
- resource SHA-256과 generation/audio-ref lineage가 report에 기록됨

server filesystem 경로는 Device response나 report에 노출하지 않는다. Device는 WAV를 영구 파일로 저장하지
않고 E0-B.4-D.3의 bounded RAM cache 계약을 유지한다.

### 10.5 Device playback

- reading snapshot을 받은 뒤 같은 session/generation의 `audio_ref`를 fetch
- navigation intent가 들어오면 선행 download/playback을 중단
- 늦게 도착한 이전 generation resource를 재생하거나 cache에 넣지 않음
- 최신 generation만 `playback_started`/`playback_completed`
- cache가 4항목/8 MiB 상한을 넘지 않음
- auth secret이나 audio bytes가 console log에 출력되지 않음

## 11. 사용자 청취 판정

자동 검증이 통과한 뒤 entrypoint가 page와 generation을 표시하고 실제 Piper audio를 Desktop 기본 출력장치로
재생한다. 사용자는 최소 다음을 확인한다.

1. 4개 page의 음성이 모두 들리는가
2. beep/tone/SAPI가 아니라 Piper 한국어 음성인가
3. 현재 표시된 page/focus content와 들리는 음성이 같은가
4. 빠르게 다음 페이지로 이동할 때 이전 음성이 중단되는가
5. 마지막 이동 뒤 이전 page 음성이 뒤늦게 재생되지 않는가

입력 값은 page별 `heard`, `content_matched`, `interruption_ok`와 선택적 메모다. 하나라도 명시적으로 실패하면
최종 status는 `failed`다. 사용자가 판정을 입력하지 않으면 `manual_listening_status=not_run`이며 패킷은
완료가 아니다.

## 12. Evidence 구조

기본 run root:

```text
tmp/e0b-production-runs/
  e0b-production-full-model-<UTC>-<suffix>/
    evidence/
      e0b-production-full-model-report.json
      e0b-production-run-manifest.json
      e0b-production-model-manifest.json
      e0b-replay-input.json
      e0b-replay-console.log
      e0b-server-console.log
      e0b-server-summary.json
      e0b-server-evidence.json
      e0b-page-content-summary.json
      e0b-braille-summary.json
      e0b-audio-summary.json
      e0b-manual-listening.json
```

`e0b-production-full-model-report.json` 최소 필드:

```json
{
  "status": "passed|failed",
  "automated_status": "passed|failed",
  "manual_listening_status": "passed|failed|not_run",
  "input_sha256": "...",
  "git_revision": "...",
  "scan_session_id": "scan-...",
  "datapack_id": "datapack-...",
  "spread_receipts": 2,
  "fragments": 4,
  "duplicates": 0,
  "page_count": 4,
  "pages_with_accessible_items": 4,
  "pages_with_nonempty_braille": 4,
  "ocr_engine_id": "...",
  "tts_engine_id": "piper",
  "audio_resources_verified": 4,
  "audio_resources_heard": 4,
  "failure": null
}
```

evidence에는 credential, raw authorization header, 전체 image frame, model binary, WAV payload를 넣지 않는다.
WAV는 hash·format·duration·level 요약으로 증명하고 실제 payload는 run 종료 후 RAM에서 해제한다. 디버깅을
위한 payload 보존이 필요하면 별도 명시 옵션과 민감정보 경고를 둔다.

## 13. 실패 처리

- model/config 미존재: preflight failure
- engine 초기화 실패: production composition failure
- OCR 실패/빈 Page IR: fragment별 failure, synthetic fallback 금지
- 접근 가능한 item 없음: page accessibility failure
- page 전체 braille 없음: braille acceptance failure
- Piper OOM/timeout/invalid WAV: synthesis failure와 마지막 job/resource 상태 기록
- S1 backlog timeout: pending job IDs와 retry/terminal status 기록
- audio auth/lineage 오류: 해당 HTTP status와 secret-safe reason 기록
- 사용자 미청취: 자동 결과는 보존하되 최종 완료 상태는 `not_run`

실패해도 run evidence를 삭제하지 않는다. child process는 `finally` 또는 동등 cleanup 경로에서 종료하고,
기존 사용자 DB/datapack/state는 변경하지 않는다.

## 14. 구현 후보 위치

구현 전 현재 composition 경계를 다시 확인하고 최소 변경으로 배치한다. 예상 후보는 다음과 같다.

- `document-parser/src/document_parser/server/combined_server.py`
- `document-parser/src/document_parser/server/` 아래 production composition helper
- `device-runtime/src/asl_device/` 아래 full-model acceptance orchestration/report 모듈
- `tools/windows/e0b-production-full-model-desktop-acceptance.bat`
- `tools/windows/` 아래 thin Python entrypoint
- `device-runtime/tests/` 및 `document-parser/tests/`의 production composition/report 계약 테스트
- `docs/quickstart/` 또는 기존 E0-B quickstart
- 별도 implementation/verification report

batch 파일은 환경 준비와 Python entrypoint 호출만 담당하고, 판정 로직을 batch에 중복 구현하지 않는다.

## 15. 검증 계획

### 15.1 정적·단위 검증

- production composition에 bench adapter가 주입되면 실패
- model manifest/preflight hash와 missing asset 판정
- run별 state isolation과 cleanup
- UTF-8/UTF-16 console input normalization
- provenance/content/braille/audio report 판정
- malformed/empty Page IR과 invalid WAV negative cases
- secret/path redaction

### 15.2 기존 회귀 검증

```powershell
.\.venv-e0b\Scripts\python.exe -m pytest book-scanner\tests -q
.\.venv-e0b\Scripts\python.exe -m pytest device-runtime\tests -q
.\document-parser.venv\Scripts\python.exe -m pytest document-parser\tests -q
```

환경별 interpreter 경로는 현재 quickstart에 맞게 조정할 수 있으나 세 suite의 결과와 skip 사유를 report에
남긴다. 실제 Piper/Paddle 모델 검증이 skip된 unit test만으로 완료 처리하지 않는다.

### 15.3 Host-only production acceptance

```powershell
tools\windows\e0b-production-full-model-desktop-acceptance.bat D:\ASL_OCR_E0B
```

heavy model이 없는 CI에서는 이 실행을 skip할 수 있지만, 패킷 완료에는 준비된 Desktop에서 실제 model
bundle을 사용한 evidence가 반드시 필요하다.

## 16. 완료 기준

다음을 모두 만족해야 완료다.

- 고정 MP4 hash가 일치한다.
- scanner/V4/S1 경계가 2 spreads / 4 fragments / 0 duplicates다.
- 4개 fragment 모두 실제 PaddleOCR-VL provenance와 성공 Page IR을 가진다.
- 4개 page 모두 accessible item과 non-empty valid braille snapshot을 가진다.
- 실제 Piper가 생성한 유효한 비무음 WAV가 S0 인증 API로 제공된다.
- Device Runtime이 session/generation lineage를 지키며 다운로드·cache·재생한다.
- navigation 시 이전 음성 중단 및 stale 음성 억제가 실제 production resource에서도 통과한다.
- 사용자 청취가 4개 page 및 interruption 항목에서 통과한다.
- 기존 Book Scanner, Device Runtime, Document Parser test suite에 회귀가 없다.
- evidence에 bench/synthetic fallback, secret, raw payload 또는 server path가 없다.
- 구현 보고서, 검증 보고서와 실행 quickstart가 작성된다.

## 17. 승인 경계와 다음 순서

이 문서는 작업 범위와 완료 기준만 정의한다. **사용자 승인 전에는 production composition이나 acceptance
코드를 변경하지 않는다.**

승인 후 이 패킷을 구현·검증하고, 사용자가 제공할 STM 프로젝트 파일을 기준으로 다음 패킷을 작성한다.
그 이후 권장 순서는 PC live camera 입력 검증, STM/bridge 물리 통합, Raspberry Pi audio adapter와 전체 E0
현장 시연이다.
