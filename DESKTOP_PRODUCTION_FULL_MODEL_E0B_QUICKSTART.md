# Desktop Production Full-Model E0-B 빠른 시작

## 준비물

- 저장소: `D:\Projects\OCR`
- prepared root: `D:\ASL_OCR_E0B`
- 고정 입력: prepared root의 pinned `test1.mp4`
- PaddleOCR-VL model home: `D:\ASL_OCR_E0B\models\paddleocr-vl`
- Piper: `D:\models\piper-korean\ko_KR-kss-medium.onnx`
- eSpeak data: `D:\espeak-ng-data`
- production Python: `D:\venvs\gpu_ocr_test\Scripts\python.exe`
- scanner Device Python: 저장소의 `.venv-e0b\Scripts\python.exe`

## 자동 검증

PowerShell 또는 cmd에서 먼저 저장소 루트로 이동한다.

```powershell
Set-Location D:\Projects\OCR
tools\windows\e0b-production-full-model-desktop-acceptance.bat D:\ASL_OCR_E0B --no-playback
```

성공 시 `status=manual_pending`, `automated_status=passed`, `spread_receipts=2`, `fragments=4`,
`duplicates=0`, `pages_with_nonempty_braille=4`, `ocr_engine_id=paddleocr-vl`,
`tts_engine_id=piper`가 출력되어야 한다.

## 실제 청취 포함

Windows 기본 출력장치의 음량을 안전한 수준으로 맞춘 후 실행한다.

```powershell
Set-Location D:\Projects\OCR
tools\windows\e0b-production-full-model-desktop-acceptance.bat D:\ASL_OCR_E0B
```

첫 왼쪽 p030의 머리말을 건너뛰고 첫 지수함수 문제까지 이동한 뒤 실제 Piper 한국어 음성을 재생한다.
터미널 질문에 `yes` 또는 `no`로 답하고, 마지막 빠른 이동에서 이전 음성이 중단되고 최신 페이지 음성만
남는지도 확인한다. 모두 `yes`면 최종 status가 `passed`다.

자동 결과에는 `p030_e2e.identified=true`, 정확한 footer `30`, 문제 코드 4개, 목표 focus ID와 실제
`braille_cells` 배열이 포함되어야 한다. `audio_transport.p030_target`의 focus ID가 같아야 p030의
점자와 오디오가 같은 읽기 위치에서 연결된 것이다.

실패하면 출력된 `evidence_dir`을 보존한다. API key, raw model binary와 raw image는 evidence에 복사되지
않는다.

## 성공한 자동 run의 오디오만 재검증

`--no-playback` run이 성공했다면 OCR을 다시 실행할 필요가 없다. 그 출력의 `work_dir`과 `datapack_id`를
사용한다.

```powershell
tools\windows\e0b-production-audio-replay.bat `
  D:\ASL_OCR_E0B `
  D:\Projects\OCR\tmp\e0b-production-runs\<run-id>\work `
  datapack-<id>
```

이 명령은 저장된 실제 revision의 p030 목표 focus로 이동해 인증 `audio_ref`만 다시 받아 재생하고 네 가지
청취 질문을 기록한다. 최신 evidence에 p030 요약이 없는 이전 run은 기존 페이지 첫 항목 방식으로 동작한다.
`Server evidence was not fully ready/accepted`로 full run이 끝났다면 해당 실행에서는 재생 단계에 도달하지
않았으므로 소리가 나지 않는 것이 맞다.

## 현재 검증 범위

이 명령은 live camera와 STM32/Raspberry Pi를 검증하지 않는다. 실제 카메라 입력과 STM32 firmware/bridge
검토는 후속 작업 패킷이다.
