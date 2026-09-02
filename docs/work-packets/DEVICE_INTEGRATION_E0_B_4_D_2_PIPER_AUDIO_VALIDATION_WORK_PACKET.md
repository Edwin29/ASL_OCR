# Device Integration E0-B.4-D.2 — Piper Audio Validation 작업 패킷

상태: **완료 — 실제 Piper 합성·전송·Desktop 청취 통과**
기준일: 2026-09-02
선행 조건: E0-B.4-D.1 authenticated audio transport
후속 조건: Device Audio Playback Contract, Raspberry Pi ALSA/PipeWire adapter

## 1. 결정과 목적

Windows SAPI는 실제 reading content 합성기가 아니므로 현재 후보와 성공 조건에서 제외한다. 이 패킷은
개발 과정에서 사용한 실제 `ko_KR-kss-medium` Piper voice가 다음 경로를 통과함을 검증한다.

```text
Piper 한국어 합성
  -> serving-ready datapack의 Server WAV
  -> reading_snapshot.audio_ref
  -> session-scoped authenticated GET
  -> bounded memory buffer
  -> Windows 기본 출력장치 재생
```

Device는 WAV를 영구 저장하지 않는다. Server가 데이터팩 WAV를 보관하고 Desktop verifier는 응답 bytes를
메모리에서 동기 재생한다.

## 2. 고정 환경

- 기본 voice: `D:\models\piper-korean\ko_KR-kss-medium.onnx`
- voice config: 같은 위치의 `.onnx.json`
- eSpeak data: `D:\espeak-ng-data`
- 기본 Piper Python: `D:\venvs\gpu_ocr_test\Scripts\python.exe`
- override: `E0B_PIPER_MODEL`, `E0B_PIPER_ESPEAK_DATA`, `E0B_PIPER_PYTHON`

모델 파일은 Git에 추가하지 않는다. eSpeak 경로는 Windows piper native crash를 피하도록 ASCII-only여야 한다.

## 3. 검증 문장

1. `첫 번째 음성입니다. 데스크탑 파이퍼 검증을 시작합니다.`
2. `두 번째 음성입니다. 다음 페이지로 이동했습니다.`

두 문장은 실제 `load_piper_voice`와 `make_piper_synthesize_fn`을 통해 합성한다. Bench tone이나 fake
synthesizer로 대체하지 않는다.

## 4. 실행

소리 없이 실제 합성·전송 자동 검사:

```bat
tools\windows\e0b-desktop-piper-transport-acceptance.bat D:\ASL_OCR_E0B --no-playback
```

사용자 직접 청취:

```bat
tools\windows\e0b-desktop-piper-transport-acceptance.bat D:\ASL_OCR_E0B
```

실제 재생 전 Windows 기본 출력장치를 선택하고 음량을 20~30%로 낮춘다. 기대 순서는 짧은 beep, 첫 번째
Piper 문장, 약 0.4초 간격, 두 번째 Piper 문장이다. 도구는 다음을 각각 `yes/no`로 묻는다.

- beep 청취
- 첫 번째 문장 청취 및 문구 이해
- 두 번째 문장 청취 및 문구 이해
- 두 문장의 순서

모든 항목이 `yes`일 때만 최종 `heard`를 입력할 수 있다. 출력장치를 조정하려면 `retry`, 하나라도 실패하면
`not-heard`를 입력한다.

## 5. 자동 성공 조건

- 실제 Piper model/config 및 ASCII eSpeak data로 합성 성공
- 서로 다른 두 유효 16-bit PCM WAV, nonzero peak/RMS와 서로 다른 SHA-256
- 올바른 API key로 두 resource `200 audio/wav`
- missing/wrong key `401`, unknown/cross-session resource `404`
- `Content-Length` 및 SHA-256 ETag 일치
- 1 KiB 단위 복수 chunk 소비
- response/evidence에 Server filesystem path와 API key 미노출
- client persistent WAV 0
- SAPI status `excluded`

`--no-playback` 성공 상태는 `manual_pending`이며 청취 성공을 의미하지 않는다.

## 6. 증거

기본 경로:

```text
tmp\e0b-audio-runs\<run-id>\evidence
```

report에는 voice 이름, model/config SHA-256, WAV 분석치, HTTP/security 결과와 구성요소별 수동 응답을
기록한다. raw WAV, model 절대경로, API key는 evidence에 넣지 않는다.

## 7. 제외 범위

- 모든 한국어·수학·표 발화의 언어 품질 평가
- navigation generation과 재생 음성 일치 및 다음 이동 시 이전 재생 취소
- Device Runtime 상시 fetch/cache/player adapter
- Raspberry Pi ALSA/PipeWire/I2S/USB 출력
- 실제 Laptop/Tailscale 및 물리 speaker 증거

## 8. 다음 패킷

수동 청취까지 통과했으므로 다음 구현 우선순위는 Device Audio Playback Contract다. reading response generation과
`audio_ref` fetch를 묶고, 다음 navigation에서 이전 download/playback을 취소하며, bounded RAM cache와 오류
격리를 구현한다. 같은 계약을 이후 Raspberry Pi ALSA/PipeWire backend로 이식한다.
