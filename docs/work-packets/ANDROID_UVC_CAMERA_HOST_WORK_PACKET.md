# Android UVC Camera Host Work Packet

상태: **승인됨 / software implementation 완료 / physical acceptance 대기**

기준일: 2026-09-02

선행 조건: Integration Baseline Closure, Piper System Prompt Transport, Device Integration E0-B

## 1. 목표

Android 휴대폰이 USB를 통해 운영체제의 표준 카메라 장치로 노출될 때, Device Runtime의 Book
Scanner가 그 장치를 명시적으로 식별하고 검증된 live frame을 기존 Scanner 파이프라인에 공급하도록
한다. MP4 replay에서 검증한 후보 선택, 페이지 변경 판정, UVDoc 보정, V4 업로드, S1 변환, S0
리딩 계약은 변경하지 않는다.

이 패킷이 완료되면 다음 경계가 구분된다.

```text
Android rear camera
  -> USB UVC 또는 OS에 등록된 승인된 virtual-camera device
  -> Windows camera backend / Linux V4L2
  -> AndroidUvcCameraSource
  -> 기존 SampledFrameEngine
  -> UVDoc -> durable outbox -> V4 -> S1 -> S0
```

## 2. 핵심 결정

1. Android 휴대폰은 정식 파이프라인에서 **운영체제 카메라 장치**로 취급한다. Android 앱 내부
   프로토콜, ADB 명령, Wi-Fi 영상 URL은 이 패킷의 신뢰 경계에 포함하지 않는다.
2. 불안정한 정수 `camera_index`만으로 장치를 선택하지 않는다. 가능한 경우 device name/path,
   backend와 USB 식별자를 조합한 persistent selector를 사용하고, index는 사용자가 명시한 fallback으로만
   허용한다.
3. 장치가 없거나 selector가 둘 이상과 일치하면 임의의 첫 카메라를 열지 않고 fail closed한다. 내장
   노트북 카메라로 조용히 대체하지 않는다.
4. 요청한 width, height, FPS, FOURCC와 backend뿐 아니라 드라이버가 실제 적용한 값을 읽어 증거에
   남긴다. 구성된 필수 mode를 충족하지 못하면 scan을 시작하지 않는다.
5. 회전과 mirror는 명시적 host 설정으로만 보정한다. 기본값은 회전 없음, mirror 없음이며 자동 추정으로
   원본 방향을 바꾸지 않는다.
6. camera transport 검증과 OCR 정확도 개선을 분리한다. 흐림, 왜곡, 조명, 수식 인식률 튜닝은 live
   frame 전달이 입증된 뒤 별도 후속 작업으로 둔다.

## 3. 현재 기준선과 결손

현재 `pc_camera` profile은 OpenCV `VideoCapture(camera_index)`를 열고 width, height, FPS를 설정한
뒤 실제 값을 비교한다. latest-frame drain과 `release()` lifecycle은 이미 존재한다. 그러나 다음은 아직
정식 계약이나 실증 근거가 없다.

- Android UVC 장치를 다른 카메라와 구별하는 장치 열거 및 persistent selector
- Windows backend와 Linux V4L2 device path의 명시적 선택
- effective FOURCC/backend/장치 식별 정보의 evidence 기록
- warm-up, invalid frame, unplug/replug, read failure에 대한 bounded recovery 정책
- 회전/mirror 정규화와 그 결과 크기 검증
- Android live camera로 생성한 Scanner artifact 및 전체 upload/read pipeline 증거

따라서 기존 MP4 Production Full-Model Desktop E2E 성공은 회귀 기준으로 유지하되 live-camera 완료
근거로 사용하지 않는다.

## 4. 포함 범위

### 4.1 구성 계약

`ScannerHostConfig`와 `LocalScannerRuntimeConfig`에 Android UVC host 설정을 추가한다. 구체 필드명은
구현 시 기존 unknown-key 거부 규칙과 맞추되, 다음 의미를 반드시 표현한다.

- profile: `android_uvc`
- selector: persistent device name/path 또는 USB identity 조건
- backend: Windows `dshow`/`msmf`, Linux `v4l2` 중 명시값 또는 검증된 platform default
- fallback index: 기본 비활성, 사용자가 명시한 경우에만 허용
- requested width, height, FPS, FOURCC
- rotation: `0`, `90`, `180`, `270`
- mirror: boolean
- warm-up frame 수, open/read retry 횟수와 bounded backoff

`android_uvc`에서 selector 없이 임의 index만 사용하는 구성은 production acceptance에서 거부한다.
기존 `replay`, `image_sequence`, `pc_camera` 구성은 그대로 동작해야 한다.

### 4.2 장치 열거와 probe

Windows와 Linux에서 사용 가능한 video capture device를 열거하는 read-only probe를 제공한다.

- Windows: friendly name, backend, stable device path/instance identity가 제공되는 범위
- Linux/Raspberry Pi: `/dev/v4l/by-id` 우선, `/dev/videoN`과 V4L2 capability 연결
- 지원 mode 또는 실제 open 후 확인 가능한 width, height, FPS, FOURCC
- selector match가 0개 또는 복수인 경우 명확한 오류
- serial, API key, image bytes를 출력하지 않는 secret-safe JSON report

운영체제가 Android 폰을 카메라로 열거하지 못하면 `camera_unavailable`로 종료한다. vendor driver 설치나
휴대폰 설정 변경을 자동 수행하지 않는다.

### 4.3 capture adapter

기존 `OpenCVCameraSource`의 공통 frame/lifecycle 기능을 재사용하되 Android UVC용 선택 및 진단 경계를
분리한다.

- 선택된 device와 backend를 `VideoCapture`에 명시적으로 전달
- 설정 요청 뒤 effective width, height, FPS, FOURCC를 read-back
- bounded warm-up 후 첫 유효 frame만 Scanner에 전달
- 빈 frame, 잘못된 channel/dimension, read 실패를 EOF와 구별
- 모든 start 실패와 정상/비정상 stop에서 handle을 정확히 한 번 release
- unplug/read failure 시 현재 scan을 무기한 block하지 않고 bounded reopen 후 명시적 session error
- frame마다 host monotonic timestamp를 부여하고 오래된 application queue는 기존 방식대로 drain
- rotation/mirror 적용 뒤 Scanner에 전달되는 최종 크기를 검증

정지된 책 페이지는 정상 입력이므로 동일한 image hash만으로 일반 scan을 실패시키지 않는다. 대신 probe
단계의 사용자 liveness 동작에서 반복 hash 비율과 frame 도착 간격을 진단값으로 기록한다.

### 4.4 Device Runtime 연결

- `_default_scanner_factory`와 local composition이 `android_uvc` source를 생성
- source start 실패가 Coordinator의 기존 fatal `session_error(camera_unavailable)` 경계까지 전달
- camera retry가 새 scan/session/spread identity를 만들거나 이미 ACK된 spread를 재전송하지 않음
- capture 화면 진입, page guidance, spread ACK, capture-complete Piper prompt 순서를 그대로 보존
- scan 종료 후 capture mode의 데이터팩 선택창으로 복귀하고 camera handle을 해제

### 4.5 실행 도구와 문서

다음 두 단계를 분리한 Windows entry point를 제공한다.

1. `probe`: 장치 열거, selector match, mode 협상, 짧은 liveness 확인만 수행
2. `acceptance`: 실제 Android frame으로 scan을 수행하고 기존 boundary/server evidence를 결합

Linux/Raspberry Pi에는 동일 selector와 report schema를 사용하는 probe entry point를 마련하되, 실제 Pi
USB 포트와 카메라의 physical acceptance는 하드웨어 확보 후 수행한다.

## 5. 제외 범위

- Android 전용 카메라 앱 제작 또는 수정
- ADB, RTSP, HTTP/MJPEG, NDI 등 network camera transport
- DroidCam, Iriun, Camo 등 특정 vendor 설치 자동화와 그 vendor protocol 보증
- autofocus/exposure/white-balance 알고리즘 개발 및 카메라 화질 튜닝
- UVDoc, 페이지 검출, 수식/OCR 모델의 정확도 변경
- S1/S0 schema, Piper 합성, Device audio transport 변경
- STM firmware/GPIO/점자 display physical acceptance
- 전체 카메라 영상을 기본 저장하거나 서버로 전송하는 기능

특정 Android 기기가 native USB webcam mode를 제공하지 않아 vendor virtual-camera driver가 필요한 경우,
운영체제에 정상 등록된 capture device라는 동일 host 계약까지만 지원한다. vendor별 설치 및 장애 대응은
별도 compatibility packet으로 분리한다.

## 6. 구현 순서

1. typed config, selector와 backend 모델, unknown/invalid 조합 거부 테스트
2. Windows/Linux device enumeration abstraction과 fake-based unit tests
3. Android UVC capture adapter, mode read-back, orientation과 lifecycle 테스트
4. bounded warm-up/reopen/error propagation 및 Coordinator 회귀 테스트
5. probe JSON schema, Windows/Linux entry point와 example config
6. fake capture를 이용한 software acceptance와 전체 회귀 suite
7. Windows desktop에 Android 휴대폰을 USB 연결한 physical probe
8. live page capture에서 V4→S1→S0와 capture-complete/catalog 복귀 증거 수집
9. Raspberry Pi physical acceptance를 위한 handoff 기록

## 7. 자동 검증 행렬

- selector가 정확히 한 장치를 선택하고 0개/복수 match를 거부
- production `android_uvc` 구성에서 암묵적 index fallback 거부
- Windows/Linux backend mapping과 unsupported platform/backend 조합 거부
- 요청 mode 설정 및 effective width/height/FPS/FOURCC read-back
- 필수 mode 불일치 시 handle release 후 start 실패
- warm-up frame은 Scanner에 노출하지 않고 이후 frame ID가 단조 증가
- rotation 90/270에서 최종 width/height 교환, mirror의 deterministic pixel 결과
- invalid/empty frame과 camera EOF를 구분
- bounded reopen 성공/소진, stop 중 추가 reopen 없음
- start/read failure가 Coordinator diagnostic까지 손실 없이 도달
- camera handle을 성공, 실패, cancel 경로에서 정확히 한 번 release
- scan 종료 후 capture catalog 복귀와 capture-complete Piper prompt 유지
- `replay`, `image_sequence`, `pc_camera` 및 Production Full-Model Desktop E2E 회귀 없음
- Book Scanner, Device Runtime, Document Parser 전체 suite 통과

## 8. Desktop physical acceptance

실제 Android 휴대폰과 데이터 전송 가능한 USB 케이블을 연결한 뒤 다음을 모두 만족해야 한다.

1. 운영체제가 휴대폰을 camera capture device로 열거하고 probe selector가 정확히 한 장치와 일치
2. report에 OS, backend, 비밀값이 제거된 device identity, requested/effective mode가 기록
3. rear camera, landscape mounting, rotation/mirror 설정 결과가 live preview 또는 저장된 단일 진단 frame과
   일치
4. liveness 안내에 따라 휴대폰 앞의 표식을 한 번 움직였을 때 새 frame 도착이 확인
5. MP4/image fallback 없이 실제 page spread 한 개 이상이 기존 Scanner candidate를 거쳐 전송
6. 전송마다 ACK 이후에만 `spread_sent`가 발생하고 server evidence의 duplicate가 0
7. scan 종료 후 datapack이 저장되고 capture mode 데이터팩 선택창으로 복귀
8. 저장한 datapack을 reading mode에서 열어 non-empty accessible item, `braille_cells`, Piper audio를 확인
9. scan 중 USB 분리 시 bounded error가 발생하고 임의 다른 카메라로 전환되지 않음
10. 재연결 후 새 scan을 시작할 수 있고 이전 session/spread identity를 재사용하지 않음

OCR 결과의 의미 정확도는 이 합격 판정에 포함하지 않는다. 다만 artifact가 빈 이미지이거나 방향이 틀려
파이프라인 입력 자체가 무효인 경우에는 실패다.

## 9. Physical acceptance 증거

한 run directory에 최소 다음을 보존한다.

- `android-uvc-probe.json`: selector, backend, requested/effective mode, liveness 통계
- `android-uvc-console.log`: JSONL feedback와 camera lifecycle 진단
- `android-uvc-boundary.json`: candidate, spread, ACK, exhaustion 순서 요약
- `e0b-server-summary.json`: spread receipt, fragment, duplicate 수
- `e0b-server-evidence.json`: scan-session-scoped server rows
- `android-uvc-acceptance-report.json`: 자동/수동 판정과 artifact 경로
- 사용자 승인 시에만 저장한 단일 redacted diagnostic frame 및 SHA-256; 기본값은 저장 안 함

report는 실제 source가 `android_uvc`였음을 표시하고 replay path가 사용되지 않았음을 증명해야 한다.

## 10. 휴대폰 수동 준비 가이드

- native USB webcam/UVC mode를 지원하면 해당 mode를 선택한다.
- rear camera를 사용하고 화면 잠금 및 절전으로 stream이 중단되지 않게 한다.
- 충전 전용이 아닌 데이터 케이블과 안정된 거치대를 사용한다.
- 촬영면 전체가 보이도록 landscape로 고정하고 앱이 mirror preview를 하더라도 host 결과를 별도로 확인한다.
- autofocus가 글자 위에서 안정되는지 확인하되, 본 패킷에서 자동 초점 품질을 합격 기준으로 오인하지 않는다.
- Windows 카메라 개인정보 설정에서 desktop app 접근이 허용되어 있는지 확인한다.
- acceptance 도중 다른 화상회의/카메라 앱이 장치를 점유하지 않게 종료한다.

## 11. 완료 조건

다음 세 상태를 구분해서 기록한다.

- `software_passed`: fake device와 기존 replay 회귀를 포함한 자동 검증 완료
- `desktop_physical_passed`: 실제 Android USB camera로 8절과 9절 완료
- `pi_physical_pending`: Raspberry Pi에서 같은 UVC/V4L2 계약의 실증이 아직 남음

이 패킷은 `software_passed`만으로 Android camera 연결이 완성됐다고 선언하지 않는다. 정식 desktop
camera 경계 완료는 `desktop_physical_passed`까지 필요하며, Raspberry Pi 배포 완료는 별도 physical
acceptance 후 판정한다.
