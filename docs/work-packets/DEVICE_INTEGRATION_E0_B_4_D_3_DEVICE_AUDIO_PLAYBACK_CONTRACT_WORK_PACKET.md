# Device Integration E0-B.4-D.3 — Device Audio Playback Contract 작업 패킷

상태: **구현 완료 / 자동 통합 검증 통과 / 실제 통합 청취 대기**
기준일: 2026-09-02
성격: **Device Runtime의 reading audio 자동 다운로드·최신 generation 재생·bounded RAM cache 계약**
선행 조건: E0-B.4-D.2 실제 Piper 합성·전송·Desktop 청취 통과
후속 조건: E0-B.4-L 원격 closure, Raspberry Pi ALSA/PipeWire 재생 어댑터

구현 결과: `DEVICE_INTEGRATION_E0_B_4_D_3_IMPLEMENTATION_REPORT.md`
자동 evidence: `tmp/e0b-audio-runs/e0b-device-audio-playback-20260902T083822Z-9d63e698/evidence`

## 1. 배경

E0-B.4-D.2는 실제 `ko_KR-kss-medium` Piper 음성이 Server datapack에 생성되고, S0의 session-scoped
`audio_ref`로 인증 다운로드되며, Desktop 기본 출력장치에서 들리는 것까지 입증했다. 그러나 이 검증은
별도 acceptance 도구가 두 resource를 직접 선택해 순차 재생한 결과다.

현재 Device Runtime의 실제 reading 경로는 다음까지만 수행한다.

```text
S0 reading response
  -> ReadingSnapshot(audio_ref 포함)
  -> JsonLine/STM ReadingPresenter
```

즉, `DeviceApplication`이 `audio_ref`를 자동 다운로드하거나 재생하지 않는다. 또한 이전 음성이 재생되는
도중 다음 navigation이 들어올 때 이를 즉시 멈추고 늦게 도착한 이전 응답을 폐기하는 계약, 제한된 RAM
안에서 재방문 음성을 재사용하는 계약도 없다.

## 2. 목표와 우선순위

이번 패킷은 다음 세 책임을 하나의 구현 단위로 닫는다.

1. 실제 reading snapshot의 `audio_ref`를 인증 다운로드해 자동 재생한다.
2. navigation intent가 들어오면 이전 download/playback을 즉시 취소하고 최신 generation만 재생한다.
3. 검증 완료 WAV만 8 MiB/4개 항목 이내의 RAM LRU cache에 보관한다.

이 세 책임은 서로 분리 구현하되 acceptance는 함께 수행한다. 다운로드만 연결하고 stale 음성 취소를
미루면 사용자가 이미 이동한 페이지의 음성을 듣게 되므로 generation 계약은 MVP 필수 안전성이다.

## 3. 범위 결정

### 3.1 포함

- Device Runtime `AudioResourcePort`
- S0 authenticated WAV streaming adapter
- Device Runtime `AudioPlaybackPort`
- Windows 기본 출력장치용 중단 가능한 in-memory PCM WAV player
- latest-wins 비동기 `ReadingAudioController`
- navigation intent 시 선행 interrupt
- session/generation/audio-ref lineage 검사
- bounded in-memory LRU cache
- secret-safe 진단 event와 acceptance evidence
- Desktop 실제 Piper integrated reading/navigation 청취

### 3.2 제외

- SAPI 합성 또는 SAPI 성공 조건
- Device에서 Piper model을 실행하는 on-device 합성
- WAV의 Device 영구 파일 저장 또는 전체 datapack 선다운로드
- Raspberry Pi ALSA/PipeWire/I2S/USB 구현
- Bluetooth pairing 자동화
- 전체 수학·표 발화 언어 품질 평가
- 다중 동시 reading session 재생
- speculative prefetch와 persistent cache

Piper 합성은 계속 Server/datapack 생성 책임이다. Device는 이미 합성된 WAV를 가져와 재생할 뿐이며 Piper
model bundle은 Device에 배포하지 않는다.

## 4. 도메인 및 Port 계약

### 4.1 Reading generation

`ReadingSnapshot.cursor`의 `generation`을 임의 dictionary lookup으로 여러 곳에서 해석하지 않는다.
`ReadingSnapshot`에 검증된 accessor 또는 명시 필드를 추가한다.

- generation은 `bool`이 아닌 0 이상의 정수여야 한다.
- S0 response에 generation이 없거나 잘못된 타입이면 malformed response로 처리한다.
- 재생 identity는 다음 tuple이다.

```text
(reading_session_id, generation, audio_ref)
```

같은 snapshot의 반복 presentation은 새 download나 새 playback을 만들지 않는다.

### 4.2 AudioResourcePort

Device application 계층이 HTTP와 API key를 직접 알지 않도록 Port를 둔다.

```python
class AudioResourcePort(Protocol):
    def fetch(
        self,
        reading_session_id: ReadingSessionId,
        audio_ref: str,
        cancelled: Callable[[], bool],
    ) -> AudioResource: ...
```

`AudioResource` 최소 필드:

- verified WAV bytes
- content SHA-256 또는 normalized ETag
- content length
- sample rate, channels, sample width, duration

취소 predicate는 연결 전과 각 chunk read 사이에서 검사한다. 취소된 resource는 성공이나 실패로 보고하지
않고 cache에도 넣지 않는다.

### 4.3 AudioPlaybackPort

```python
class AudioPlaybackPort(Protocol):
    def play(self, resource: AudioResource, cancelled: Callable[[], bool]) -> None: ...
    def stop(self) -> None: ...
    def close(self) -> None: ...
```

- `play`는 하나의 verified PCM WAV만 소비한다.
- `stop`은 idempotent하며 다른 thread에서 호출할 수 있다.
- `stop` 반환 뒤 이전 음성의 추가 sample 출력은 bounded backend latency 이내에 끝나야 한다.
- `close`는 stop을 포함하며 worker와 출력 stream을 남기지 않는다.
- callback이나 worker 예외가 Device main loop를 종료시키면 안 된다.

### 4.4 ReadingAudioController

Controller는 단일 worker와 latest-wins slot만 사용한다. navigation 횟수만큼 future/thread를 쌓지 않는다.

```text
interrupt()
  -> local epoch 증가
  -> pending request 폐기
  -> active download cancellation 표시
  -> player.stop()

present(snapshot)
  -> 중복 identity면 no-op
  -> 새 identity를 latest slot에 기록
  -> cache hit면 최신성 재검사 후 play
  -> cache miss면 fetch/검증/cache insert
  -> play 직전 최신 session+generation+epoch 재검사
```

worker가 완료 callback이나 오류를 반환할 때도 동일 최신성 검사를 거친다. 오래된 작업의 완료가 최신
재생 상태를 `idle` 또는 `failed`로 덮어쓰면 안 된다.

## 5. S0 audio download adapter

기존 `S0HttpClient`의 base URL, API key, timeout 설정을 재사용하되 JSON transport와 WAV byte transport는
명시적으로 분리한다.

```http
GET /api/v1/reading-sessions/{reading_session_id}/audio/{audio_id}
X-API-Key: <device key>
Accept: audio/wav
```

검증 순서:

1. `audio_ref`가 정확히 `s0-audio:<opaque-id>` 형식인지 검사한다.
2. session ID와 opaque ID를 URL quote한다.
3. redirect를 허용하지 않거나 최종 origin이 구성된 Server origin과 동일함을 검사한다.
4. status `200`, `Content-Type: audio/wav`를 요구한다.
5. `Content-Length`가 있으면 1..4 MiB 범위인지 선검사한다.
6. 64 KiB chunk로 읽으며 누적 4 MiB 초과 즉시 중단한다.
7. response bytes와 `Content-Length`, SHA-256 ETag를 대조한다.
8. `wave` parser로 PCM 16-bit, mono/stereo, 8–48 kHz, 0초 초과·120초 이하를 검사한다.
9. 검증 완료 resource만 반환한다.

HTTP 408/429/5xx, timeout과 일시적 연결 오류는 recoverable audio failure다. 401, malformed ref/WAV,
hash mismatch와 크기 초과는 해당 resource의 non-retryable failure다. 어느 경우에도 reading cursor나 점자
출력을 rollback하지 않는다.

API key, Authorization header, raw WAV, 로컬 path와 전체 URL query는 console/evidence에 기록하지 않는다.

## 6. navigation cancellation 계약

### 6.1 선행 interrupt

현재 `DeviceApplication.step()`은 input을 `coordinator.handle_input()`에 넘긴 뒤 snapshot을 present한다.
이번 패킷은 `DeviceFlowState.READING`에서 다음 입력을 처리하기 **직전** audio controller의 `interrupt()`를
호출한다.

- `UP`, `DOWN`, `LEFT`, `RIGHT`
- `PAGE_NEXT`, `PAGE_PREVIOUS`
- Server reading command로 전달되는 short/long control
- reading을 빠져나가는 long `CONFIRM`

`LEVER`처럼 reading command를 만들지 않는 입력은 interrupt하지 않는다. 동일 event가 retry되더라도
`interrupt()`는 idempotent해야 한다.

Server command가 실패해 기존 snapshot이 유지된 경우 이전 음성을 자동 재개하지 않는다. 다음 성공한
snapshot 또는 명시적 replay action이 새 재생 authority다.

### 6.2 stale response 억제

다음 모든 경계에서 `(session, generation, epoch)` 최신성을 검사한다.

- cache lookup 뒤
- HTTP 연결 직전
- 각 response chunk 뒤
- WAV 검증 뒤
- cache insert 직전
- player 호출 직전
- playback 완료/실패 처리 시

generation 1 download가 generation 2 이후 완료돼도 cache insert와 playback을 수행하지 않는다. 이미
검증돼 cache에 존재하는 generation 1 resource도 최신 snapshot이 아니면 재생하지 않는다.

## 7. bounded RAM cache

초기 값을 다음으로 고정한다.

| 항목 | 값 |
|---|---:|
| 단일 resource 최대 | 4 MiB |
| cache 전체 최대 | 8 MiB |
| cache 항목 최대 | 4 |
| 동시 in-flight download | 1 |
| download chunk | 64 KiB |
| WAV duration 최대 | 120초 |

cache key:

```text
(reading_session_id, audio_ref, etag_or_sha256)
```

동작 규칙:

- 검증 완료된 immutable `bytes`만 저장한다.
- 미완성/취소/실패 response는 저장하지 않는다.
- hit마다 LRU 순서를 갱신한다.
- insert 전에 항목 수와 byte 상한을 모두 만족할 때까지 oldest entry를 제거한다.
- 동일 audio identity 재삽입은 byte accounting을 중복 증가시키지 않는다.
- reading session이 바뀌거나 selection으로 돌아가면 이전 session entry를 제거한다.
- application stop/close 시 전체 cache와 pending bytes를 해제한다.
- 디스크 fallback을 만들지 않는다.

cache 8 MiB와 단일 in-flight 4 MiB를 분리 계상하고, controller가 직접 보유하는 bounded audio byte 총량은
12 MiB를 넘지 않아야 한다. playback backend 내부 버퍼는 별도 측정해 evidence에 기록한다.

## 8. Windows playback adapter

E0-B.4-D.2의 `winsound.SND_MEMORY` 동기 player는 청취 acceptance에는 충분하지만 재생 도중 중단 계약을
제공하지 않는다. 실제 Device Runtime adapter는 in-memory PCM을 중단 가능한 output stream으로 보내야
한다.

우선 구현은 `sounddevice.RawOutputStream`을 사용한다.

- WAV header를 메모리에서 해석하고 PCM frame만 stream에 쓴다.
- Windows 기본 출력장치를 사용한다.
- 고정된 작은 frame chunk로 쓰며 각 chunk 전에 cancellation을 검사한다.
- `stop()`은 active stream을 abort/stop해 queued audio를 제거한다.
- 재생마다 파일을 만들지 않는다.
- PortAudio/sounddevice가 없거나 장치를 열 수 없으면 명시적 audio failure로 격리한다.

`sounddevice`와 Windows PortAudio availability를 Desktop setup/preflight에 추가한다. SAPI와 임시 WAV
파일 player로 fallback해 acceptance를 통과시키지 않는다.

## 9. 구성

Device config의 `local_io` 아래에 다음 bounded 설정을 추가한다. 기존 config에 section이 없으면
`enabled=false`로 유지해 과거 replay/JSONL 테스트를 깨지 않는다. Desktop integrated acceptance profile은
명시적으로 활성화한다.

```toml
[local_io.reading_audio]
enabled = true
backend = "sounddevice"
max_resource_bytes = 4194304
max_cache_bytes = 8388608
max_cache_entries = 4
download_chunk_bytes = 65536
request_timeout_seconds = 10.0
```

상한은 config에서 더 크게 올릴 수 없도록 hard ceiling을 둔다. 초기 hard ceiling은 resource 4 MiB,
cache 16 MiB, entries 8, timeout 30초다.

## 10. 진단 event

다음 event를 bounded JSONL 또는 기존 feedback sink로 보낸다.

- `reading_audio_fetch_started`
- `reading_audio_cache_hit`
- `reading_audio_playback_started`
- `reading_audio_interrupted`
- `reading_audio_playback_completed`
- `reading_audio_failed`

공통 detail은 reading session의 raw 값 대신 필요 최소 lineage를 사용한다.

- generation
- audio resource의 짧은 비가역 digest
- cache hit 여부
- content bytes/duration
- failure class와 retryable 여부

API key, raw `audio_ref`, raw WAV, 전체 session ID, filesystem path는 출력하지 않는다. cancellation은 정상
흐름이므로 error로 승격하지 않는다.

## 11. 구현 후보 파일

```text
device-runtime/src/asl_device/types.py
device-runtime/src/asl_device/protocols.py
device-runtime/src/asl_device/application.py
device-runtime/src/asl_device/events.py
device-runtime/src/asl_device/app_config.py
device-runtime/src/asl_device/local_composition.py
device-runtime/src/asl_device/adapters/http_s0.py
device-runtime/src/asl_device/adapters/reading_audio.py                 # 신규
device-runtime/src/asl_device/reading_audio.py                          # 신규
device-runtime/tests/unit/test_reading_audio.py                         # 신규
device-runtime/tests/unit/test_http_s0_audio.py                         # 신규
device-runtime/tests/unit/test_application.py
device-runtime/tests/unit/test_app_config.py
device-runtime/tests/integration/test_reading_audio_loopback.py         # 신규 또는 기존 실제 harness 확장
tools/windows/e0b-device-audio-playback-acceptance.bat                  # 신규
tools/windows/e0b_device_audio_playback_acceptance.py                   # 신규
LAPTOP_E0B_QUICKSTART.md
DEVICE_INTEGRATION_E0_B_4_D_3_IMPLEMENTATION_REPORT.md                  # 완료 시
PROJECT_HANDOFF_20260831.md
```

실제 구조에 맞춰 파일을 합치거나 이름을 조정할 수 있지만 Port, controller, HTTP adapter, player의 책임을
하나의 거대 presenter에 섞지 않는다.

## 12. 테스트 행렬

### 12.1 Unit

| 범위 | 필수 검증 |
|---|---|
| Snapshot generation | missing/bool/negative/valid generation |
| HTTP audio | ref parsing, URL quote, auth, 200/401/404/5xx, timeout |
| Bounds | Content-Length 선거부, chunk 누적 초과, 0 byte, duration/PCM 거부 |
| Integrity | ETag/hash 일치·불일치, malformed WAV |
| Cache | hit, LRU 갱신, byte/entry eviction, duplicate accounting, session clear |
| Controller | duplicate snapshot no-op, cache miss/hit, close idempotency |
| Cancellation | download 중, 검증 직후, play 직전, play 중 interrupt |
| Race | generation 1 late success/failure가 generation 2 상태를 덮지 않음 |
| Application | reading input 전에 interrupt, lever no interrupt, selection/stop close |
| Playback fake | stop 후 이전 sample/complete가 authority를 얻지 못함 |

### 12.2 Integration

- 실제 S0 loopback에서 Piper WAV 두 resource fetch
- navigation `[generation 0, 1, 2]`와 재생 identity 일치
- 같은 페이지 재방문 cache hit 및 추가 HTTP fetch 없음
- 느린 generation 1 download 도중 generation 2 이동 후 generation 1 미재생
- 긴 generation 1 재생 도중 generation 2 이동 후 stop 관찰
- audio 401/404/timeout에서도 최신 braille snapshot과 추가 navigation 유지
- application stop 뒤 audio worker/thread/stream 0
- client persistent WAV 0

### 12.3 전체 회귀

- Device Runtime 전체
- Document Parser S0 audio/HTTP 집중 및 전체
- E0-B.4-D Desktop loopback
- E0-B.4-D.2 실제 Piper synthesis/transport
- `git diff --check`

## 13. Desktop 실제 acceptance

실제 Piper datapack과 prepared root를 사용하는 단일 진입점을 제공한다.

```bat
tools\windows\e0b-device-audio-playback-acceptance.bat D:\ASL_OCR_E0B
```

도구는 실제 speaker 재생 전에 경고하고 다음 수동 순서를 안내한다.

1. generation 0 첫 문장 재생을 듣는다.
2. 재생 도중 `down` 또는 지정된 navigation을 입력한다.
3. 이전 문장이 중단되고 generation 1 문장만 이어지는지 확인한다.
4. 이전 페이지로 돌아가 cache hit 상태에서 올바른 음성이 재생되는지 확인한다.
5. 다시 빠르게 두 번 이동해 중간 generation 음성이 들리지 않는지 확인한다.

사용자는 다음 항목을 각각 `yes/no`로 기록한다.

- 최초 Piper 음성 audible/intelligible
- navigation 시 이전 음성 중단
- 최신 cursor와 최신 음성 일치
- cache 재방문 음성 일치
- 빠른 연속 이동에서 stale 음성 없음

모두 `yes`이고 자동 조건도 통과한 경우에만 최종 `status=passed`다. 자동화가 사람의 청취를 추정하거나
기본 `heard`를 넣지 않는다.

## 14. Evidence 계약

실행별 evidence에 최소 다음을 기록한다.

```text
e0b-device-audio-playback-<UTC>-<suffix>/evidence/
  e0b-device-audio-playback-report.json
  e0b-device-audio-events.jsonl
  e0b-device-audio-http-summary.json
  e0b-device-audio-cache-summary.json
```

최종 report 최소 필드:

```json
{
  "schema_version": 1,
  "environment": "desktop_integrated_reading_audio",
  "status": "passed",
  "automated": {
    "generations_presented": [0, 1, 2],
    "generations_played": [0, 1, 2],
    "stale_playback_count": 0,
    "interruptions_observed": 2,
    "cache_hits": 1,
    "cache_peak_bytes": 400000,
    "cache_limit_bytes": 8388608,
    "client_wav_persisted": false,
    "worker_threads_remaining": 0
  },
  "manual_listening": {
    "status": "heard",
    "component_checks": {
      "initial_intelligible": true,
      "previous_stopped": true,
      "latest_matches_cursor": true,
      "cache_revisit_correct": true,
      "no_stale_audio": true
    }
  }
}
```

## 15. 성공 조건

다음을 모두 만족해야 이 패킷을 완료한다.

- 실제 Device Runtime reading snapshot이 자동 audio fetch/playback을 시작한다.
- 점자와 음성의 session/generation이 일치한다.
- navigation intent 직후 이전 재생이 중단된다.
- 이전 download/complete/error callback이 최신 상태나 재생을 덮지 않는다.
- cache가 byte/entry 상한을 넘지 않고 session/close 시 정리된다.
- Device persistent WAV 파일이 생성되지 않는다.
- audio 오류가 cursor, 점자, 추가 navigation을 막거나 rollback하지 않는다.
- 실제 Piper Desktop 통합 청취의 모든 구성요소가 통과한다.
- 전체 회귀가 통과하고 secret-safe evidence가 남는다.

## 16. 중단 조건

다음 중 하나가 나타나면 `passed`로 기록하지 않고 로그를 보존한다.

- stale generation 음성이 한 번이라도 재생됨
- `stop()` 뒤 이전 음성이 계속 출력되거나 late completion이 최신 상태를 변경함
- cache 또는 in-flight byte 상한 초과
- client persistent WAV 생성
- API key, raw path 또는 raw audio가 진단에 노출됨
- audio 실패 때문에 Device reading/navigation이 중단되거나 cursor가 되돌아감
- 실제 speaker에서 최신 문장과 cursor 대응을 사용자가 확인하지 못함

## 17. 완료 후 다음 순서

```text
E0-B.4-D.3 Device Audio Playback Contract
  -> E0-B.4-L role-complete Laptop/Server evidence closure
  -> Raspberry Pi Audio Adapter (동일 Port, ALSA/PipeWire backend)
  -> Physical E0-B camera + STM + braille + Piper audio
```

Raspberry Pi 패킷은 이번 controller/cache/HTTP 계약을 변경하지 않고 `AudioPlaybackPort` 구현과 실제
resource/latency 측정만 교체하는 것을 원칙으로 한다.
