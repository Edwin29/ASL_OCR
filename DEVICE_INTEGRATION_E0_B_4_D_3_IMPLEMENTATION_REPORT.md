# Device Integration E0-B.4-D.3 — Device Audio Playback Contract 구현 보고서

상태: **완료 — 자동 통합 검증 및 사용자 실제 청취 통과**
기준일: 2026-09-02
승인 패킷: `docs/work-packets/DEVICE_INTEGRATION_E0_B_4_D_3_DEVICE_AUDIO_PLAYBACK_CONTRACT_WORK_PACKET.md`

## 1. 구현 결과

Device Runtime reading 경로에 session-scoped `audio_ref` 자동 다운로드와 중단 가능한 PCM 재생을 연결했다.
오디오는 디스크에 저장하지 않고 최대 4 MiB resource로 검증한 뒤 8 MiB/4개 항목 RAM LRU cache에서
관리한다. 단일 worker와 latest-wins epoch를 사용하므로 이전 generation의 늦은 fetch/완료/오류는 새
generation의 재생 authority를 얻지 못한다.

`DeviceApplication`은 READING 상태의 navigation 입력을 Coordinator에 전달하기 전에 기존 재생을
중단한다. `LEVER`는 reading command가 아니므로 중단하지 않는다. application 종료 시 worker, output
stream과 cache를 함께 닫는다.

## 2. 주요 경계

- `AudioResourcePort`: API key를 포함한 S0 WAV byte transport를 application에서 분리
- `S0AudioResourceHttpAdapter`: opaque ref, status/content type/length/ETag, PCM WAV 형식과 duration 검증
- `AudioPlaybackPort`: 다른 thread에서 호출 가능한 idempotent stop/close
- `SoundDeviceWavPlayer`: 기본 출력장치로 16-bit PCM frame을 메모리에서 streaming
- `ReadingAudioController`: 중복 presentation 억제, stale cancellation, 단일 in-flight와 bounded cache
- secret-safe feedback: raw session/ref/path/WAV/API key 대신 generation과 짧은 ref digest만 출력
- config가 없으면 `reading_audio.enabled=false`여서 기존 replay 동작은 유지

## 3. 자동 검증

```bat
tools\windows\e0b-device-audio-playback-acceptance.bat D:\ASL_OCR_E0B --no-playback
```

실제 `ko_KR-kss-medium` Piper와 loopback S0를 사용한 결과:

- status: `passed`
- generations presented: `[0, 1, 2, 3, 4]`
- authenticated HTTP fetch: 2
- RAM cache hits: 3
- playback starts/completions: 5/3 (2개는 의도된 navigation interrupt)
- observed interruptions: 2
- audio failures: 0
- cache bytes: 424,024 / 8,388,608
- client persistent WAV: false
- Device Runtime unit: 142 passed; 전체: 145 passed

Evidence:

```text
tmp/e0b-audio-runs/e0b-device-audio-playback-20260902T084452Z-0c029e40/evidence
```

실제 Piper 환경에는 `sounddevice 0.5.6`을 설치했고 Windows 기본 출력장치가 PortAudio에서 조회되는 것도
확인했다.

## 4. 사용자 실제 통합 청취

사용자가 다음 명령을 저장소 루트에서 실행하고 실제 기본 출력장치를 청취했다.

```bat
tools\windows\e0b-device-audio-playback-acceptance.bat D:\ASL_OCR_E0B
```

최종 report는 `manual_listening.status=heard`이며 다음 다섯 항목이 모두 `true`다.

- 첫 Piper 음성 명료도
- navigation 시 이전 음성 중단
- 최신 cursor와 최신 음성 일치
- cache 재방문 음성 일치
- 빠른 연속 이동 뒤 stale 음성 부재

이 결과로 Desktop D.3 reading audio 계약은 완료됐다. Raspberry Pi ALSA/PipeWire 출력은 별도 후속
패킷에서 같은 Port 계약으로 검증한다.
