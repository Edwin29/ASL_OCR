# Scanner Video V2 — seam-conservative + UVDoc artifact 작업 패킷

상태: **승인됨 — 미구현**
작성일: 2026-08-30
선행 조건: V0 계약, V1 연속 프레임 엔진 및 V1.1 runtime 하드닝 완료
채택 경로: `seam-conservative + UVDoc bilinear`

## 1. 목표

검증된 오프라인 spine seam/ownership 및 UVDoc adapter를 V1의 `SpreadProcessor`에 연결해,
같은 full-spread frame에서 좌우 보정본과 provenance가 완전한 atomic artifact bundle을 만든다.

V2의 완료는 로컬 artifact 준비 완료를 뜻한다. Document Parser 서버 전달 완료나 OCR 성공을
뜻하지 않는다.

## 2. 재사용 원칙

- seam 계산: 기존 `detect/spine_seam.py`
- 보수 좌우 소유권: `left_conservative_mask`, `right_conservative_mask`
- crop 방식과 padding: 기존 paired/p30 실험의 고정 설정
- UVDoc: 기존 `correct/uvdoc_adapter.py`
- sampling: `bilinear`
- checkpoint 자동 다운로드 금지
- 기존 4-corner correction과 `none`은 진단 경로로 보존

오프라인 구현을 복사해 runtime 전용 변형을 만들지 않는다. 필요한 경우 작은 adapter만 둔다.

## 3. 구현 범위

### 3.1 Runtime spread processor

입력:

- full-resolution BGR frame
- source frame ID/timestamp
- session/spread ID
- 고정 pipeline config와 evaluator versions

처리:

1. 고정 구도 spread ROI 및 page foreground 산출
2. luminance-valley spine seam 계산
3. conservative ownership mask 생성
4. 같은 원본에서 좌우 crop 생성
5. 좌우 각각 UVDoc bilinear 실행
6. local artifact readiness 평가
7. bundle을 atomic commit

출력은 좌우 경로만이 아니라 `SpreadArtifact`와 `ReadinessDecision`이다.

### 3.2 UVDoc lifecycle

- process-wide 또는 worker-wide lazy load
- 같은 session에서 frame마다 checkpoint reload 금지
- runtime/checkpoint/device/hash 기록
- unsupported device와 missing checkpoint는 명시적 fatal/config error
- inference 실패는 `UVDOC_FAILED`이며 `none`으로 silent fallback하지 않음
- 취소 시 새 inference 시작 금지

모델이 중간 취소를 지원하지 않으면 현재 inference 완료 후 artifact를 publish하지 않고 정리한다.

### 3.3 Atomic artifact bundle

최소 구성:

```text
spread artifact directory/
  manifest.json
  source_frame.jpg
  left/
    mask.png
    crop.jpg
    uvdoc.jpg
    diagnostics.json
  right/
    mask.png
    crop.jpg
    uvdoc.jpg
    diagnostics.json
```

manifest:

- schema/pipeline/evaluator version
- session, spread, source frame ID와 capture timestamp
- 원본/crop/UVDoc SHA-256와 이미지 크기
- seam path/confidence/fallback reason
- mask/crop bbox, padding, frame edge contacts
- UVDoc runtime/checkpoint hash, sampling, device, load count
- 좌우 local readiness와 reason
- atomic commit timestamp

좌우 모두 완료되기 전에는 ready manifest를 publish하지 않는다. 임시 디렉터리에서 작성 후
rename하며 실패한 시도도 별도 diagnostic bundle로 보존할 수 있다.

### 3.4 Local artifact readiness

검사:

- 좌우가 같은 source frame에서 생성됨
- seam/mask/crop 존재와 non-empty
- crop 및 UVDoc decode 가능
- 최소 해상도와 비정상 aspect
- 물리 frame 쪽 외곽 잘림
- 반대 페이지 유입/본문 잘림을 위한 기존 diagnostics
- blur, exposure, glare/shadow 진단
- 모든 hash와 lineage 존재

local quality는 Document Parser acceptance를 흉내 내지 않는다. parser 수준의 내용/구조 판단은
V4 서버 preflight에 남긴다.

## 4. 검증 행렬

### 4.1 단위 검증

- fake seam/fake UVDoc로 좌우 동일 frame lineage
- 한쪽 seam/crop/UVDoc 실패 시 ready 미발행
- UVDoc load count가 session frame 수에 비례해 증가하지 않음
- checkpoint missing/invalid device/invalid output reason
- hash mismatch와 손상 이미지 거부
- atomic commit 도중 예외 시 partial ready bundle 없음
- cancel 중 완료된 inference 결과 미발행

### 4.2 기존 이미지 회귀

- 기존 라벨 이미지의 seam-conservative mask metric 재현
- p30 세 촬영의 기존 offline crop/UVDoc hash 또는 허용된 pixel/diagnostic 동등성 비교
- p30 human golden 기반 기존 Document Parser 결과는 참고하되 V2에서 GPU OCR을 무조건 재실행하지 않음
- runtime adapter 때문에 본문·수식·선택지 잘림이 새로 생기지 않았는지 contact sheet 검토

### 4.3 실제 영상 replay

V1에서 등록한 `20260830_133526.mp4`의 사람이 확인한 `STABLE_SPREAD` 구간만 사용한다.

- 서로 다른 안정 구간에서 선택한 frame의 좌우 artifact 생성
- POSITIONING/PAGE_TURN frame이 processing 후보가 되었다면 명시적 V1 회귀
- 한 spread에서 좌우 source frame ID 일치
- UVDoc model load reuse
- 처리시간, peak RAM, artifact 크기 기록

영상이 여전히 재생·다운로드 불가하면 실제 replay 항목은 blocked로 남기고 synthetic/기존 JPEG
검증만으로 영상 검증 완료를 선언하지 않는다.

## 5. 완료 기준

- default runtime processor가 seam-conservative + UVDoc bilinear를 실행
- 선택된 각 spread에서 동일 frame 좌우 artifact 생성
- 좌우 hash/provenance 100%
- 한쪽 실패 시 ready bundle 및 업로드 요청 0
- UVDoc model 재사용 확인
- 기존 오프라인 결과와 설명 가능한 범위에서 동등
- legacy loop와 기존 전체 unit test 회귀 없음
- actual MP4 결과가 없으면 PC 영상 통합은 부분 완료로 기록

## 6. 성능 기록

PC에서 다음을 측정하지만 임의의 합격 숫자는 두지 않는다.

- seam/crop latency
- 좌우 UVDoc 개별/총 latency
- model initial load latency
- steady-state peak RAM/VRAM
- source/crop/UVDoc bundle 크기
- 후보 실패 후 다음 frame까지 회복 시간

이 값은 Pi 4 가능성을 증명하지 않는다. V5에서 local UVDoc과 server UVDoc 배치를 별도로
비교한다.

## 7. 비범위

- 실제 Document Parser 서버 preflight와 OCR
- durable outbox와 idempotent upload
- 성공음·TTS·guidance hysteresis
- page-change/중복 전송 방지
- Raspberry Pi camera/GPIO/systemd
- sharpen, denoise, super-resolution 자동 추가
- threshold, seam, padding, UVDoc 후보의 새 sweep

## 8. 중단 조건

- runtime 연결을 위해 기존 seam/UVDoc 알고리즘을 복제해야 함
- UVDoc 실패를 무보정 성공으로 가장해야 함
- 좌우 artifact를 서로 다른 frame에서 조합해야 함
- 기존 p30/라벨 회귀가 발생했는데 threshold를 같은 검증 자료에 맞춰 즉석 수정해야 함
- 모델 또는 checkpoint를 승인 없이 다운로드해야 함
