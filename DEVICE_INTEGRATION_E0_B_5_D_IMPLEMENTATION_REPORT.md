# Device Integration E0-B.5-D — Production Full-Model Desktop E2E 구현 보고서

상태: **자동 검증 및 실제 오디오 출력 확인 — 비지원 교재 OCR 의미 품질 판정 보류**
기준일: 2026-09-02
승인 패킷: `docs/work-packets/DEVICE_INTEGRATION_E0_B_5_D_PRODUCTION_FULL_MODEL_DESKTOP_E2E_WORK_PACKET.md`

## 1. 구현 결과

고정 `test1.mp4`의 결정론적 scanner 입력은 유지하면서 Server를 실제 PaddleOCR-VL과 실제 한국어
Piper composition으로 교체하는 Desktop acceptance를 추가했다. Scanner Device subprocess는 기존
`.venv-e0b`, OCR·Piper Server와 후속 오디오 재생은 `D:\venvs\gpu_ocr_test`를 사용해 서로 다른 의존성
환경을 오염시키지 않는다.

reading 검증은 첫 focus item만 검사하지 않는다. 일반 텍스트가 의도적인 clear-frame을 반환하면 같은
페이지 안에서 다음 focus item으로 이동하여 수식 점자 frame을 찾고, 페이지 ID/side/generation과 6-dot
cell 범위를 검증한다.

저장 완료 뒤에는 같은 SQLite/datapack revision을 S0 read-only 사용 경계로 다시 열어 실제 `audio_ref`를
인증 다운로드한다. Device의 `ReadingAudioController`, 4항목/8 MiB RAM LRU cache, latest-wins 중단 계약을
그대로 사용하며 클라이언트 WAV 파일을 만들지 않는다.

## 2. 실행 명령

저장소 루트 `D:\Projects\OCR`에서 실행한다.

```bat
tools\windows\e0b-production-full-model-desktop-acceptance.bat D:\ASL_OCR_E0B --no-playback
```

실제 청취까지 포함하려면 `--no-playback`을 제거한다. 기본 출력장치로 네 페이지의 실제 Piper 음성이
순서대로 들리고, 마지막에는 빠른 페이지 이동으로 선행 재생 중단을 검증한다.

## 3. 실제 자동 검증 결과

Evidence:

```text
tmp/e0b-production-runs/e0b-production-full-model-20260902T094124Z-40e936b6/evidence
```

- input SHA-256: `16c57970bc493abcef4a1db0f1917b22956bf5ca1a2ee8b4565fde1f6574e6f8`
- scan session: `scan-a859b72e0af243b29a3bda5da9dfa79f`
- 새 datapack: `datapack-4095f8707d1a4a3695e062248e14a370`, revision 1
- spread receipts/fragments/duplicates: `2/4/0`
- OCR engine: `paddleocr-vl`; 네 fragment 모두 ready
- TTS engine: `piper`; 비무음 WAV resource 154개 검증
- 접근 가능한 page: 4/4
- non-empty braille page: 4/4; 선택 frame cell 수 `10, 4, 4, 10`
- authenticated audio fetch: 4; unauthenticated 401, cross-session 404
- playback starts/completions/intentional interruption/failures: `7/6/1/0`
- RAM cache: 4항목, 1,222,832 bytes / 8,388,608 bytes
- client persistent WAV: false
- model home: 56 files, tree SHA-256
  `40411d09e06e9631687c1527a4c9555f84f633538e68635030c458ef456ebd66`
- regression tests: Device Runtime 152 passed; Document Parser 580 passed, 4 skipped

초기 화면에서 보였던 한글 깨짐 가능성도 저장 document의 69개 text를 직접 검사했다. U+FFFD replacement
character는 0개였으므로 데이터 손상이 아니라 해당 콘솔 표시 경계였다.

실제 반복 실행에서 첫 spread가 한 차례 안전하게 재시도되어 `attempt_count=2`였지만 최종 상태가
`accepted`, server 결과가 `2/4/0`인 실행을 기존 공통 판정기가 실패 처리하는 문제가 발견됐다. durable
outbox 계약에 맞게 accepted attempt count는 1 이상을 허용하고, sequence 집합과 duplicate 0을 별도로
검증하도록 수정했다. 이미 성공한 무재생 run은 `e0b-production-audio-replay.bat`로 OCR 재실행 없이 실제
청취 evidence를 추가할 수 있다.

## 4. 범위와 남은 판정

이 결과는 Desktop, 고정 MP4, 실제 OCR/Piper, loopback S0와 Desktop audio adapter까지 증명한다. live
camera, STM32/bridge, Raspberry Pi ALSA/PipeWire와 GPIO는 포함하지 않는다.

자동 계층은 통과했다. 최종 `passed` 판정에는 사용자가 실제 재생에서 다음을 확인해 청취 결과를 기록해야
한다.

- 네 페이지 음성이 모두 들리는가
- 음성이 현재 페이지 내용과 일치하는가
- beep/tone/SAPI가 아닌 실제 Piper 한국어 음성인가
- 빠른 이동 뒤 이전 페이지 음성이 뒤늦게 남지 않는가

## 5. 사용자 청취 관찰과 corpus 제한

사용자는 실제 재생 자체는 들렸고 일반 문장인 “연립일차방정식”은 알아들을 수 있었으나, 다수 수식은
“수식 인식이 불확실합니다”로 안내됐다고 보고했다. 따라서 Desktop audio transport와 Piper 출력은
실청취 확인됐지만 OCR 수식 의미 품질은 통과로 기록하지 않는다.

현재 고정 MP4의 SHA-256은 기존 `scanner_video_v3a2_temporal_labels.json`과 일치한다. 이 영상의 첫
spread 왼쪽은 사용자 확인 page 30이며, 오른쪽 page 309 및 두 번째 spread page 316/317은 같은 수준의
사용자 golden이 아니다. 정식 지원 대상 수능특강을 확보하기 전에는 page 30 왼쪽만 분리해 기존 사람
검증 `p030.json`과 텍스트·수식 구조·점자 cell·음성을 비교하는 제한된 regression으로 사용한다. 이
결과를 정식 지원 corpus acceptance로 확대 해석하지 않는다.
