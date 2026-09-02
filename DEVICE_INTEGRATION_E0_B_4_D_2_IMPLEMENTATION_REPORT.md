# Device Integration E0-B.4-D.2 — Piper Audio Validation 구현 보고서

상태: **완료 — 자동 검증 및 사용자 실제 청취 통과**
기준일: 2026-09-02
승인 패킷: `docs/work-packets/DEVICE_INTEGRATION_E0_B_4_D_2_PIPER_AUDIO_VALIDATION_WORK_PACKET.md`

## 1. 결과

SAPI를 현재 후보에서 제외하고 실제 `ko_KR-kss-medium` Piper voice를 우선 검증했다. 기존 production
Piper loader와 datapack synthesis 함수를 사용해 고정 한국어 두 문장을 합성하고, S0 reading session의
opaque `audio_ref`를 통해 인증 다운로드했다. Desktop client는 WAV를 파일로 저장하지 않고 1 KiB
chunk로 읽어 메모리에서 재생하도록 구성했다.

## 2. 자동 증거

실행 명령:

```bat
tools\windows\e0b-desktop-piper-transport-acceptance.bat D:\ASL_OCR_E0B --no-playback
```

결과:

- status: `manual_pending`
- environment: `desktop_piper_audio_transport`
- automated transport: `passed`
- voice: `ko_KR-kss-medium`
- model SHA-256: `624fd774e26895f24bebae1bd9a3379e3394baeade4b584924f83e414096e2c9`
- 두 WAV: 22,050 Hz, mono, 16-bit, 약 4.725초/3.947초
- authorized streams 2, missing/wrong key 401, unknown/cross-session 404
- distinct hashes, non-silent, Content-Length/ETag/chunk 검증 통과
- client persistent WAV: 0
- SAPI: `excluded`

증거 디렉터리:

```text
D:\Projects\OCR\tmp\e0b-audio-runs\e0b-audio-transport-20260902T081732Z-8a9f3c9a\evidence
```

## 3. 테스트

- Desktop audio transport/component decision unit: 8 passed
- 실제 Piper adapter/model 비재생 integration: 5 passed
- 실제 Piper synthesis + authenticated transport: passed, manual pending
- Device Runtime 전체: 128 passed
- Document Parser 전체(일반 검증 환경): 578 passed, 4 skipped

Piper 전용 환경에는 전체 suite용 `pytest/pypdf`가 없으므로 전체 회귀는 일반 Document Parser 환경에서,
실제 Piper 5개 integration은 Piper 전용 환경에서 분리 실행했다.

## 4. 사용자 청취 증거

다음 명령으로 짧은 beep 뒤 고정 한국어 Piper 문장 두 개를 실제 재생했다.

```bat
tools\windows\e0b-desktop-piper-transport-acceptance.bat D:\ASL_OCR_E0B
```

최신 수동 report 결과:

- status: `passed`
- automated transport: `passed`
- manual listening: `heard`
- attempts: 1
- beep: true
- 첫 번째 Piper 문장 audible/intelligible: true/true
- 두 번째 Piper 문장 audible/intelligible: true/true
- order correct: true
- client persistent WAV: false
- SAPI: `excluded`

증거 디렉터리:

```text
D:\Projects\OCR\tmp\e0b-audio-runs\e0b-audio-transport-20260902T081854Z-c6d953fa\evidence
```

## 5. 남은 범위

고정 두 문장의 Desktop 청취 통과는 전체 수학·표 음성 품질이나 Raspberry Pi 출력을 대표하지 않는다.
다음 구현은 Device Runtime에서
navigation generation과 audio fetch/playback을 결합하고 다음 이동 시 이전 재생을 중단하는 계약이다.
그 뒤 동일 계약을 Raspberry Pi ALSA/PipeWire backend에 연결한다.
