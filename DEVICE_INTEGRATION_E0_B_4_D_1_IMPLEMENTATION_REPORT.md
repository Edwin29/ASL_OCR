# Device Integration E0-B.4-D.1 — Desktop Audio Transport 구현 보고서

상태: **구현 및 자동 검증 완료 / 사용자 실제 청취 대기**
기준일: 2026-09-02
승인 패킷: `docs/work-packets/DEVICE_INTEGRATION_E0_B_4_D_1_DESKTOP_AUDIO_TRANSPORT_WORK_PACKET.md`

## 1. 결과

S0 reading response의 기존 `s0-audio:<opaque-id>` wire 형식을 유지하면서, 해당 reading session에
고정된 datapack revision의 WAV만 인증해 반환하는 HTTP resource 경계를 추가했다. Desktop acceptance는
실제 loopback HTTP를 통해 두 WAV를 1 KiB chunk로 읽고 형식, 상한, hash, 비무음, 세션 격리를 검사한다.

Windows 재생은 내려받은 bounded WAV bytes를 `winsound.SND_MEMORY`와 기본 동기 모드로 직접 소비한다. Device
쪽에 WAV 파일을 쓰지 않으므로 외장 저장장치가 없는 Raspberry Pi의 후속 streaming/player 계약을
막지 않는다.

자동 검증 결과는 `passed`다. 실제 출력장치에서 소리가 들렸다는 사람의 판정은 자동화하지 않았으며,
현재 전체 상태는 `manual_pending`이다.

## 2. 구현 경계

- `GET /api/v1/reading-sessions/{reading_session_id}/audio/{audio_id}` 추가
- `X-API-Key` 인증, 존재하지 않는 resource와 session mismatch `404`
- opaque ID에 reading session namespace를 포함해 다른 session에서 재사용 불가
- published revision root 또는 공유 `_system` pool 내부 경로만 허용
- PCM 16-bit, mono/stereo, 8–48 kHz, 최대 4 MiB/120초 검사
- `Content-Length`, content SHA-256 `ETag`, private cache, `nosniff` 응답
- Bench synthesizer를 16 kHz mono 500 ms의 결정론적 440/880 Hz 비무음 tone으로 교체
- 실제 HTTP, chunk consume, in-memory Windows 재생, 구성요소별 `yes/no`와 명시적
  `heard/not-heard/retry` 도구 추가
- SAPI는 실제 Piper reading content가 아니며 사용자 청취에서 누락된 것이 확인되어 현재 후보와 성공
  조건에서 제외
- `--no-playback`은 transport만 검증하며 최종 상태를 `passed`로 승격하지 않음

## 3. 실행 진입점

자동 transport만 검사하고 소리를 내지 않는다.

```bat
tools\windows\e0b-desktop-audio-transport-acceptance.bat D:\ASL_OCR_E0B --no-playback
```

사용자가 직접 청취할 때는 `--no-playback`을 제거한다.

```bat
tools\windows\e0b-desktop-audio-transport-acceptance.bat D:\ASL_OCR_E0B
```

기대 순서는 짧은 beep, 낮은 tone, 높은 tone이다. 도구는 beep·저음·고음·두 tone 구분을 각각 묻고,
네 질문이 모두 `yes`인 경우에만 `heard`를 허용한다. 출력장치를 조정하고 다시 들으려면 `retry`, 하나라도
듣지 못했으면 `not-heard`를 입력한다. Enter만으로는 통과하지 않는다.

## 4. 자동 증거

2026-09-02 실제 prepared root `D:\ASL_OCR_E0B`를 사용한 무재생 실행:

- 상태: `manual_pending`
- automated transport: `passed`
- authorized streams: 2
- missing/wrong key: 401
- unknown ID: 404
- 다른 reading session의 ID 재사용: 404
- WAV: 각 16,044 bytes, 16 kHz, mono, 16-bit, 500 ms
- peak: 6,000, RMS 약 4,127
- 두 content SHA-256 상이
- 각 resource 16 chunks로 소비
- client WAV persistent file: 0

증거 디렉터리:

```text
D:\Projects\OCR\tmp\e0b-audio-runs\e0b-audio-transport-20260902T074524Z-41cb1101\evidence
```

같은 변경 상태에서 E0-B.4-D replay 회귀도 통과했다.

- scan: `scan-683a89c81cd644fb9a3193c010645430`
- boundary: `passed`
- spread sequences: `[1, 2]`
- Server: 2 receipts / 4 fragments / 0 duplicates
- revision 1 저장, 4페이지 순방향과 마지막 역방향 이동 통과
- evidence:
  `D:\Projects\OCR\tmp\e0b-loopback-runs\e0b-loopback-20260902T073623Z-e0365980\evidence`

## 5. 테스트

| 범위 | 결과 |
|---|---:|
| Desktop audio transport 신규 unit/actual HTTP | 8 passed |
| S0 audio/HTTP/Bench 집중 | 20 passed |
| Device Runtime 전체 | 126 passed |
| Document Parser 전체 | 607 passed, 4 skipped |
| E0-B.4-D actual loopback | passed |

`git diff --check`에서 whitespace 오류는 없었다. 기존 Windows line-ending 안내와 `.codex-temp/`는 이
패킷의 제품 오류나 변경 대상이 아니다.

## 6. 남은 승인과 후속 범위

이번 패킷을 최종 `passed`로 닫으려면 사용자가 Desktop 기본 출력장치에서 실제 명령을 실행하고
`heard`를 입력한 report가 한 번 필요하다. 그 전까지 자동 transport 구현은 완료지만 physical audible
acceptance는 완료가 아니다.

후속 패킷은 다음 책임을 갖는다.

1. Device Runtime reading generation과 fetch/playback 연결
2. 다음 navigation에서 이전 fetch와 재생 취소
3. bounded RAM cache 및 실패 격리
4. Raspberry Pi ALSA/PipeWire/I2S/USB backend
5. production Piper의 확대된 한국어·수학·표 TTS 품질 검증

E0-B.4-D.2에서는 우선 실제 `ko_KR-kss-medium` 고정 한국어 두 문장의 합성·전송 자동 검증을 통과했다.
별도 구현 보고서와 수동 청취 명령을 따른다.
