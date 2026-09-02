# Device Integration E0-B.4-D.1 — Desktop Audio Transport 작업 패킷

상태: **구현 및 자동 검증 완료 / Desktop 실제 청취 승인 대기**
기준일: 2026-09-02
성격: **Server 생성 WAV의 secret-safe 스트리밍 경계와 Desktop 실제 청취 증거 확립**
선행 조건: E0-B.4-D Desktop loopback acceptance 완료 (`b0780bd`)
후속 조건: Device Audio Playback Contract, E0-B.4-L 실제 Laptop/Tailscale 증거 closure, Physical E0-B

## 1. 배경

E0-B.4-D는 Scanner에서 Server 저장, reading session 생성과 `reading_snapshot.audio_ref` 반환까지
검증했다. 그러나 현재 `audio_ref`는 `s0-audio:<digest>` 형태의 불투명 참조일 뿐이고, Device가 해당
WAV 바이트를 가져오는 HTTP 경계와 실제 출력장치 재생은 통합 파이프라인에서 검증되지 않았다.

현재 Windows feedback 경로의 beep는 기본 출력장치 smoke일 뿐 reading content WAV와는 별도다. SAPI는
2026-09-02 사용자 결정으로 이 패킷의 후보와 성공 조건에서 제외했다. E0-B Bench synthesizer도 식별 가능한
소리가 아니라 무음 fixture를 생성한다. 따라서 현재 로그의
`audio_ref` 존재나 playback 함수 호출만으로 사용자가 소리를 들었다고 판정할 수 없다.

외장 저장장치가 없는 Raspberry Pi에서도 사용할 수 있도록 transport는 영구 파일 저장을 요구하지 않아야
한다. Server가 WAV를 보관하고 Device는 요청 시 byte stream을 받아 RAM buffer 또는 player stdin으로
소비할 수 있어야 한다.

## 2. 우선순위와 패킷 경계

| 순서 | 패킷 | 범위 | 완료 권한 |
|---:|---|---|---|
| 1 | **E0-B.4-D.1 Desktop Audio Transport** | Windows audio smoke, 비무음 Bench WAV, 인증 streaming API, Desktop 직접 청취 | 이번 패킷 |
| 2 | **Device Audio Playback Contract** | Device fetch/player adapter, generation 일치, 이전 재생 취소, bounded RAM cache | 후속 패킷 |
| 3 | **Raspberry Pi Audio Adapter** | ALSA/PipeWire/I2S/USB 출력 backend와 Pi resource 측정 | 후속 패킷 |
| 4 | **Production TTS Quality** | 실제 Piper voice, 한국어·수학·표 발화 품질 | E0-B.4-D.2부터 시작 |

Windows beep smoke는 즉시 수행 가능하지만 transport 성공을 대신하지 않는다. 이번 패킷은 작은
smoke를 먼저 확인한 뒤 비무음 fixture와 HTTP resource 경계를 함께 구현한다.

## 3. 목표

이번 패킷은 다음을 입증한다.

1. Desktop의 선택된 기본 출력장치에서 Windows beep가 실제 들린다.
2. E0-B Bench Server가 짧고 식별 가능한 비무음 WAV를 결정론적으로 생성한다.
3. reading response의 불투명 `audio_ref`를 실제 Server 경로 노출 없이 인증된 HTTP resource로 가져올 수
   있다.
4. WAV 응답은 chunk 단위로 읽을 수 있고 클라이언트 영구 저장을 요구하지 않는다.
5. 자동 검사는 WAV 구조, 크기, duration, non-silence, 인증과 lineage를 검증한다.
6. 실제 소리가 들렸다는 판정은 사용자가 직접 입력하며 자동화가 대신 추정하지 않는다.

## 4. Server audio resource 계약

### 4.1 Resource URL

reading session 범위 안에서 opaque audio ID를 조회한다.

```http
GET /api/v1/reading-sessions/{reading_session_id}/audio/{audio_id}
X-API-Key: <device key>
Accept: audio/wav
```

`reading_snapshot.audio_ref`는 계속 파일 경로를 노출하지 않는다. wire 값은 다음 두 형태 중 하나로
정규화하되 구현 시 한 가지를 선택하고 모든 client/test를 같은 계약으로 고정한다.

```text
s0-audio:<opaque-id>
```

또는

```text
/api/v1/reading-sessions/<session-id>/audio/<opaque-id>
```

권장안은 기존 wire 호환성을 유지하는 `s0-audio:<opaque-id>`다. Device/acceptance client가 현재
`reading_session_id`와 결합해 URL을 구성한다.

### 4.2 성공 응답

```http
HTTP/1.1 200 OK
Content-Type: audio/wav
Content-Length: <bounded bytes>
ETag: "<content sha256>"
Cache-Control: private, max-age=...
X-Content-Type-Options: nosniff
```

- WAV는 RIFF/WAVE header가 유효해야 한다.
- 허용 channel, sample width, sample rate와 최대 byte/duration을 Server에서 검증한다.
- 응답 body는 streaming iterator 또는 framework의 bounded file response로 전송한다.
- 전체 datapack archive 또는 Server 절대경로를 반환하지 않는다.
- 첫 구현에서는 Range request를 필수로 하지 않는다. 중단은 client가 연결을 닫는 것으로 충분하다.

### 4.3 권한과 lineage

- API key가 없거나 틀리면 `401`이다.
- 존재하지 않는 session/audio ID는 path 존재 여부를 누설하지 않는 `404`다.
- audio ID는 해당 reading session의 고정 datapack revision에 속해야 한다.
- 다른 reading session이나 다른 revision의 audio ID 재사용을 거부한다.
- 경로 정규화 후 datapack root 밖으로 나가는 값은 항상 거부한다.
- raw filesystem path, API key와 TTS 원문 전체를 access/error log에 남기지 않는다.
- Server restart 뒤에도 같은 published revision의 audio resource를 다시 해석할 수 있어야 한다.

### 4.4 저장장치 비의존 계약

Server가 합성 WAV를 datapack에 보관하는 것과 Device가 WAV를 영구 저장하는 것은 별개다. client는 다음
두 방식 모두 구현 가능해야 한다.

```text
HTTP response chunks -> bounded RAM/ring buffer -> audio player
```

```text
HTTP response stream -> ALSA/aplay stdin
```

이번 Desktop verifier가 Windows API 제약 때문에 임시 WAV를 사용한다면 OS temp의 실행별 파일만
허용하고 다음을 강제한다.

- datapack 또는 repository 안에 저장하지 않음
- 재생 성공·실패·중단 뒤 즉시 삭제
- 실패 시 남은 경로를 보고하고 다음 실행 시작 전 정리 가능
- 이 임시 파일 사용을 Raspberry Pi transport 요구사항으로 승격하지 않음

## 5. 결정론적 비무음 Bench WAV

현재 무음 `BenchSynthesizer`를 짧은 식별 tone fixture로 바꾼다. production voice 품질을 모사하지 않고
transport와 실제 출력만 검증한다.

권장 fixture:

| 항목 | 값 |
|---|---|
| encoding | PCM WAV |
| channels | mono |
| sample width | 16-bit |
| sample rate | 16 kHz |
| duration | 400~700 ms |
| amplitude | clipping을 피하는 고정 진폭 |
| 식별 | utterance key 또는 page position에서 결정한 고정 주파수 |

최소 두 resource는 귀로 구별되는 서로 다른 tone이어야 한다. 같은 입력은 언제나 같은 WAV content hash를
생성해야 한다. 자동 검사는 sample peak/RMS가 0보다 크고 duration/format이 bounds 안에 있음을 판정한다.

tone은 오직 `e0b-deterministic-bench`에만 적용한다. production Piper adapter와 TTS manifest 의미는
변경하지 않는다.

## 6. Desktop acceptance 도구

다음 단일 진입점을 추가한다.

```bat
tools\windows\e0b-desktop-audio-transport-acceptance.bat D:\ASL_OCR_E0B
```

도구는 다음 순서로 실행한다.

1. repository revision/dirty 상태와 prepared root를 기록한다.
2. Windows 기본 출력장치 smoke용 beep를 재생한다.
3. 실행별 loopback Server/state와 reading session을 준비한다.
4. 서로 다른 두 opaque audio resource를 인증 요청한다.
5. WAV header, `Content-Length`, ETag/content hash, duration과 non-silence를 자동 검증한다.
6. 첫 번째 tone, 300~500ms 간격, 두 번째 tone 순으로 재생한다.
7. beep·저음·고음·음높이 구분을 각각 확인하고 사용자에게 최종 판정을 입력받는다.
8. secret-safe JSON evidence를 기록한다.

자동 CI/무인 실행을 위해 `--no-playback` 또는 동등한 모드를 제공한다. 이 모드는 transport 자동 검사는
수행하지만 manual listening 상태를 `not_run`으로 남기며 전체 physical-audible acceptance를 `passed`로
표시하지 않는다.

## 7. 사용자 직접 청취 가이드

### 7.1 실행 전

1. Windows **설정 → 시스템 → 소리 → 출력**에서 시연할 스피커·이어폰을 기본 출력장치로 선택한다.
2. 출력 음량을 먼저 20~30% 정도로 낮춘다.
3. Bluetooth 장치라면 `연결됨, 오디오` 상태인지 확인한다.
4. Windows 자체 `테스트` 버튼으로 좌우 또는 기본 테스트 소리가 들리는지 확인한다.
5. 원격 데스크톱 사용 중이면 소리가 원격 PC로 redirect되지 않았는지 확인한다. 가능하면 시연 Desktop
   앞에서 직접 실행한다.
6. 다른 앱의 독점 모드나 mute가 의심되면 해당 앱을 종료하고 Windows volume mixer를 확인한다.

### 7.2 실행

저장소 root의 일반 PowerShell 또는 CMD에서 다음을 실행한다.

```bat
tools\windows\e0b-desktop-audio-transport-acceptance.bat D:\ASL_OCR_E0B
```

정상적인 청취 순서는 다음과 같다.

```text
1. 짧은 beep
2. 첫 번째 짧은 tone
3. 짧은 간격
4. 높이가 다른 두 번째 짧은 tone
```

도구가 물으면 사용자가 직접 다음 중 하나를 입력한다.

```text
heard       모두 명확히 들었고 두 tone을 구분함
not-heard   하나 이상 들리지 않거나 구분할 수 없음
retry       출력장치/음량을 조정하고 한 번 더 재생
```

`heard`는 자동 기본값이 아니며 beep·저음·고음·두 tone 구분 질문이 모두 `yes`일 때만 선택할 수 있다.
Enter만 눌러 통과할 수 없고, `retry`는 bounded 횟수만 허용하며 각 구성요소 결과를 evidence에 남긴다.

### 7.3 실패 시 분류

| 관찰 | 우선 확인 | 판정 |
|---|---|---|
| beep와 tone 모두 안 들림 | 기본 출력장치, mute, RDP redirect | Windows output smoke 실패 |
| beep만 들리고 tone이 안 들림 | WAV fetch/player | transport 또는 WAV player 실패 |
| tone 하나만 들림 | 두 번째 resource fetch, 재생 completion | resource sequence 실패 |
| 두 tone이 같은 높이 | fixture identity/hash | deterministic fixture 실패 |
| 소리는 들리나 자동 검사가 실패 | header/hash/lineage 로그 | 계약 실패; 수동 청취로 덮지 않음 |

사용자가 `heard`를 입력해도 자동 transport/security 검사가 실패하면 최종 상태는 `failed`다. 반대로 자동
검사가 모두 통과해도 사용자가 `not-heard` 또는 `not_run`이면 실제 청취 상태는 완료되지 않는다.

## 8. 증거 형식

실행별 evidence directory에 최소 다음을 저장한다.

```text
e0b-audio-transport-<UTC timestamp>-<suffix>/
  e0b-audio-transport-report.json
  e0b-audio-server.log
  e0b-audio-client.log
  e0b-audio-resource-manifest.json
```

최종 report 예시:

```json
{
  "schema_version": 2,
  "environment": "desktop_audio_transport",
  "status": "passed",
  "repository_revision": "...",
  "automated": {
    "windows_beep_invoked": true,
    "sapi_status": "excluded",
    "authorized_streams": 2,
    "unauthorized_request_rejected": true,
    "wav_valid": true,
    "non_silent": true,
    "distinct_content_hashes": true,
    "path_not_disclosed": true,
    "temporary_files_remaining": 0
  },
  "manual_listening": {
    "status": "heard",
    "attempts": 1,
    "expected_sequence": "beep,tone-low,tone-high",
    "confirmed_at": "..."
  }
}
```

사용자 이름, API key, 로컬 WAV 절대경로와 raw 음성 byte는 evidence에 넣지 않는다. 출력장치 이름은
best-effort diagnostic으로 기록할 수 있지만 pass authority로 사용하지 않는다.

## 9. 성공 조건

### 9.1 자동 성공 조건

- Windows beep backend 호출이 예외 없이 완료
- Bench WAV 두 개 이상이 유효한 PCM WAV
- 각 WAV가 non-silent이고 서로 다른 content hash
- 올바른 API key의 audio request가 `200 audio/wav`
- 잘못된 key가 `401`
- 다른 session/revision의 audio ID가 거부됨
- response에 Server filesystem path가 없음
- WAV가 chunk 단위로 소비 가능
- 구성된 최대 byte/duration 초과 resource가 거부됨
- Desktop verifier 종료 후 임시 WAV가 남지 않음

### 9.2 사용자 청취 성공 조건

- 사용자가 beep를 들음
- 사용자가 두 tone을 모두 들음
- 사용자가 두 tone의 높이가 다름을 구분함
- 사용자가 명시적으로 `heard` 입력

최종 `status=passed`는 자동 조건과 사용자 청취 조건이 모두 통과한 경우에만 허용한다.

## 10. 테스트 행렬

| 범위 | 필수 검증 |
|---|---|
| Bench synthesizer unit | deterministic, valid WAV inputs, nonzero peak/RMS, bounded duration |
| S0 resource resolver unit | session/revision lineage, path containment, restart-safe lookup |
| S0 HTTP | 200/content headers, 401, 404, size bound, no path leak |
| Streaming | 작은 chunk reader, 중도 close, 전체 hash 일치 |
| Desktop verifier unit | fake beep/player, 구성요소별 yes/no와 heard/not-heard/retry 상태기계 |
| Desktop actual | 연결 출력장치에서 사용자 직접 청취 |
| Regression | Document Parser, Device Runtime, E0-B.4-D loopback |

E0-B.4-D loopback은 audio transport 추가 후에도 기존 spread `[1,2]`, Server 2/4/0, reading
`[0,1,2,3,2]`를 유지해야 한다.

## 11. 실패 및 안전 경계

- 실제 소리 재생 전 사용자에게 실행 예정임을 명확히 표시한다.
- 첫 음량은 짧고 보수적으로 설정하며 갑작스러운 고음량을 사용하지 않는다.
- audio fetch/playback 실패가 Server reading cursor를 되돌리거나 손상시키지 않는다.
- 잘못된 resource가 로컬 파일 read primitive로 변하지 않게 한다.
- API key, raw path와 secret을 console/evidence에 출력하지 않는다.
- 사용자가 듣지 못한 결과를 자동 성공으로 보정하지 않는다.
- 테스트 tone을 production TTS 품질 증거로 사용하지 않는다.

## 12. 제외 범위

- Device Runtime reading presenter와 실제 audio fetch/player 연결
- navigation generation에 따른 이전 fetch/playback 취소
- Raspberry Pi ALSA/PipeWire/I2S/USB backend
- GPIO PWM으로 TTS waveform 직접 출력
- 전체 datapack audio의 offline 선다운로드
- production Piper의 전체 한국어·수학·표 발화 품질 평가(D.2는 두 고정 한국어 문장만 검증)
- Bluetooth speaker pairing 자동화
- E0-B.4-L Laptop/Tailscale 및 Physical E0-B 완료 판정

## 13. 예상 변경 파일

구현 시 실제 구조에 따라 조정하되 최소 변경 후보는 다음과 같다.

```text
document-parser/src/document_parser/server/e0b_bench_server.py
document-parser/src/document_parser/server/s0_http.py
document-parser/src/document_parser/server/s0_services.py
document-parser/tests/unit/test_server_s0.py
document-parser/tests/unit/test_server_http.py
device-runtime/src/asl_device/desktop_audio_transport_acceptance.py
device-runtime/tests/unit/test_desktop_audio_transport_acceptance.py
tools/windows/e0b-desktop-audio-transport-acceptance.bat
tools/windows/e0b_desktop_audio_transport_acceptance.py
LAPTOP_E0B_QUICKSTART.md
PROJECT_HANDOFF_20260831.md
```

기존 `audio_ref` wire 계약을 불필요하게 깨지 않고, transport endpoint와 resolver를 S0 경계에 추가하는
방향을 우선한다.

## 14. 완료 정의

- 작업 패킷 범위의 unit/integration/full regression이 통과한다.
- clean checkout에서 Desktop audio transport 자동 검사를 재현한다.
- 사용자가 연결된 Desktop 출력장치에서 기대 순서의 소리를 직접 듣고 `heard`를 입력한다.
- 자동 결과와 수동 청취 결과가 하나의 secret-safe report에 분리되어 기록된다.
- Device가 영구 WAV 파일을 저장해야 한다는 요구를 만들지 않는다.
- Device playback/generation cancellation과 Raspberry Pi 구현은 후속 미완료 범위로 명시한다.
