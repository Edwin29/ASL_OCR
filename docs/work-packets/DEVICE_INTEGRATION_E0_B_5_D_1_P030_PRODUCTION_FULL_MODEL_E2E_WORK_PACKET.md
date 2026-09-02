# E0-B.5-D.1 p030 Production Full-Model Desktop E2E Work Packet

## 상태

- 승인: 2026-09-02 사용자 지시 `작업 시작해` 및 범위 정정
- 구현: 완료
- 자동 acceptance: 통과
- 수동 스피커 청취: 대기
- 대상: p030 중심의 Desktop production full-model E2E

## 목적

고정 MP4에서 사용자가 확인한 첫 펼침면 왼쪽 p030을 실제 Book Scanner, V4, S1, S0,
Device Runtime 경로로 처리한다. PaddleOCR-VL이 만든 접근성 문서와 점자를 확인하고 Piper WAV를
인증된 `audio_ref`로 내려받아 Desktop 출력 장치로 재생한다.

이번 패킷의 합격 기준은 프로토타입 통합 경로다. 수식 의미 정확도 개선, OCR 재시도, 카메라 보정
튜닝은 포함하지 않으며 프로토타입 완성 이후 품질 개선 단계로 넘긴다.

## 입력과 프로토콜 경계

- 입력 SHA-256: `16c57970bc493abcef4a1db0f1917b22956bf5ca1a2ee8b4565fde1f6574e6f8`
- 첫 안정 펼침면: 왼쪽 p030 (`USER_CONFIRMED`), 오른쪽 페이지는 spread 계약상 함께 처리
- 두 번째 펼침면도 기존 고정 replay acceptance의 sequence 2를 유지
- 생산 OCR: PaddleOCR-VL
- 생산 TTS: Piper
- 영속 경로: V4 receipt → S1 fragment/assembly → S0 revision/read session
- Device 경로: opaque `audio_ref` → 인증 다운로드 → bounded RAM cache → 재생/중단

## 구현 작업

1. 저장된 첫 왼쪽 페이지에서 정확한 `30` footer와 지수함수 문제 항목을 찾아 p030 계보를 기록한다.
2. p030의 첫 실제 문제 항목까지 `DOWN` 이동해 머리말이 아닌 문제 본문을 오디오 대상으로 삼는다.
3. 같은 포커스에서 반환된 실제 `braille_cells` 값을 evidence에 보존하고 비어 있으면 실패한다.
4. 해당 `audio_ref`의 인증 다운로드, Piper WAV 비무음, Desktop 재생을 기존 transport 계약으로 검증한다.
5. V4/S1/S0 계수 `2 spread / 4 fragment / 0 duplicate`, revision 1, 네 페이지 접근성을 유지한다.
6. 수식 인식 오류는 관찰값으로만 남기고 이 패킷의 실패나 재인식 작업으로 확대하지 않는다.

## 자동 합격 기준

- `spread_receipts=2`, `fragments=4`, `duplicates=0`
- OCR engine `paddleocr-vl`, TTS engine `piper`
- p030 식별 및 해당 focus item의 item-level Piper audio 존재
- p030 문제 focus의 `braille_cells`가 실제 정수 배열이며 길이 1 이상
- 네 저장 페이지 모두 접근성 항목과 비어 있지 않은 점자 snapshot 보유
- 오디오 인증/세션 격리/cache/중단 불변식 통과
- 모델 폴더 실행 전후 불변

## 수동 청취 기준

실행 중 다음 네 질문에 직접 `yes` 또는 `no`로 답한다.

1. 30페이지 첫 문제의 Piper 한국어 음성이 들렸는가
2. 음성이 30페이지 지수함수 문제 내용과 일치하는가
3. beep/tone/SAPI가 아닌 실제 Piper 음성인가
4. 이동 후 이전 음성이 뒤늦게 재생되지 않는가

## 실행

저장소 루트 `D:\Projects\OCR`에서:

```powershell
tools\windows\e0b-production-full-model-desktop-acceptance.bat D:\ASL_OCR_E0B
```

자동 경로만 먼저 확인하려면:

```powershell
tools\windows\e0b-production-full-model-desktop-acceptance.bat D:\ASL_OCR_E0B --no-playback
```

## 보조 진단

`tools\windows\e0b-p030-production-ocr-diagnostic.bat`은 동일 p030의 OCR 결과를 human golden과
비교하는 보조 도구다. 그 결과는 통합 프로토타입의 합격 기준이나 현재 우선 작업이 아니다.

## 자동 실행 결과

- run: `e0b-production-full-model-20260902T104900Z-474c52ee`
- scan: `scan-9aabde177e3946ec84566f10b88f486e`
- datapack: `datapack-1b8752f7c26a472f91e7a897f24382f9`
- V4/S1: `2 spread / 4 fragment / 0 duplicate`
- S0: revision 1, 4 accessible pages, 154 Piper audio resources
- p030: footer 30, 문제 코드 `0042–0045`, 15 focus items와 item audio 15개
- p030 목표 focus: node index 2, 첫 지수함수 문제
- Device transport 점자: 11 cells, 실제 값
  `[11, 38, 45, 52, 18, 18, 60, 3, 24, 20, 45]`
- replay console 점자 viewport: 10 cells, non-empty
- audio transport: 인증/세션 격리/cache/중단 통과, failure 0
- 결과: `automated_status=passed`, `status=manual_pending`
