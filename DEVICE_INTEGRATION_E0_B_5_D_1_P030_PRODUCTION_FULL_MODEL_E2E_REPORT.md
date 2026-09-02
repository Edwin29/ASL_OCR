# E0-B.5-D.1 p030 Production Full-Model Desktop E2E Report

## 결론

사용자 확인 고정 MP4의 p030을 중심으로 Book Scanner → V4 → S1 → S0 → Device Runtime 경로를
실제 PaddleOCR-VL과 Piper로 실행했다. 자동 acceptance는 통과했고 Desktop 스피커의 실제 청취만
남았다. 수식 의미 정확도 개선과 카메라 보정 튜닝은 이 단계에서 제외해 프로토타입 이후 품질 작업으로
이관했다.

## 실행 결과

- run: `tmp/e0b-production-runs/e0b-production-full-model-20260902T104900Z-474c52ee`
- scan session: `scan-9aabde177e3946ec84566f10b88f486e`
- datapack: `datapack-1b8752f7c26a472f91e7a897f24382f9`
- 자동 상태: `passed`
- 수동 청취: `not_run`

| 경계 | 증거 |
|---|---|
| Book Scanner/V4 | 고정 MP4 hash 일치, spread receipt 2 |
| S1 | fragment 4, duplicate 0, 모두 PaddleOCR-VL |
| S0 | revision 1, accessible page 4, Piper resource 154 |
| p030 식별 | footer 30, 코드 26008-0042/0043/0044/0045 |
| p030 audio | 15 focus item 모두 item-level Piper resource 보유 |
| Device braille | 목표 문제 focus에서 실제 11 cells, non-empty |
| Device audio | 인증 다운로드, session 격리, bounded RAM cache, interruption 통과 |

## p030 동일 포커스 증거

- page: `pg-f9598d0f5d0f-00000001-L`
- focus: `pg-f9598d0f5d0f-00000001-L-vl003-L01`
- node index: 2
- 내용: 첫 번째 지수함수 문제
- transport `braille_cells`:
  `[11, 38, 45, 52, 18, 18, 60, 3, 24, 20, 45]`
- replay console viewport `braille_cells`:
  `[11, 38, 45, 52, 18, 18, 60, 3, 24, 20]`
- opaque `audio_ref` digest: `9828c8a85048`

두 점자 길이 차이는 transport가 20-cell viewport, replay console이 10-cell viewport를 사용하기
때문이다. 둘 다 같은 p030 문제 focus에서 비어 있지 않은 실제 점자를 반환한다.

## 오디오 transport

- authenticated: true
- unauthorized request rejected: true
- cross-session request rejected: true
- fetch count: 4
- cache hits: 3
- playback starts/completions: 7/6
- intentional interruption: 1
- failures: 0
- cache: 4 entries, 1,958,576 bytes / 8 MiB
- client WAV persisted: false

이번 실행은 `--no-playback`이므로 자동 player가 다운로드·cache·재생 lifecycle을 검증했으며 실제
스피커 소리를 들었다는 주장은 하지 않는다.

## 수동 청취 명령

OCR과 Piper 합성을 다시 하지 않고 이번 저장 revision만 재생하려면 저장소 루트에서 실행한다.

```powershell
tools\windows\e0b-production-audio-replay.bat `
  D:\ASL_OCR_E0B `
  D:\Projects\OCR\tmp\e0b-production-runs\e0b-production-full-model-20260902T104900Z-474c52ee\work `
  datapack-1b8752f7c26a472f91e7a897f24382f9
```

첫 p030 문제까지 자동 이동한 뒤 음성을 재생한다. 터미널의 네 질문에 직접 `yes/no`로 답하면 같은
evidence 디렉터리에 수동 청취 결과가 추가된다.

### 재실행 커서 수정

첫 수동 재생 시 기존 자동 검증과 같은 Device ID의 저장 커서를 이어받아
`p030 audio target focus lineage differs`가 발생했다. 재생마다 고유 Device ID를 생성하도록 수정했고,
동일 저장 revision을 대상으로 재검증해 p030 node index 2와 동일 focus ID, 11개 점자 셀을 다시
확인했다. OCR/Piper 재합성은 필요하지 않다.

## 검증

- Full-Model/p030 transport 단위 테스트: 9 passed
- p030 OCR 보조 비교 단위 테스트: 9 passed
- 실제 생산 E2E: automated passed
- model home 실행 전후 불변

## 남은 범위

- Desktop 실제 스피커 청취
- PC live camera 입력 검증
- STM32/bridge 물리 입력 검증
- Raspberry Pi ALSA/PipeWire 출력 검증
- 프로토타입 이후 OCR 성공률 및 카메라 보정 품질 개선
