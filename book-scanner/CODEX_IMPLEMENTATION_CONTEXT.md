# Codex Implementation Context: Book Page Detection and UVDoc Integration

## 1. 문서의 목적

이 문서는 `ASL_OCR/book-scanner`의 다음 구현 세션을 위한 인수인계 컨텍스트다.

다음 구현의 핵심 목표는 현재의 배경 차감과 회전 사각형 기반 페이지 검출을, **고정된 V자형 책받침을 활용한 좌우 ROI 분리 + 페이지 표면 segmentation + 페이지별 UVDoc 곡면 보정** 구조로 단계적으로 교체하는 것이다.

이 문서는 세부 API 계약을 확정하지 않는다. 먼저 실험 가능한 경계를 만들고, 실제 이미지와 Raspberry Pi에서 측정한 결과에 따라 모델·임곗값·배포 형식을 결정한다.

함께 읽을 문서:

- [README.md](./README.md): 현재 v2의 구조와 실행 방법
- [PAGE_DETECTION_CANDIDATES.md](./PAGE_DETECTION_CANDIDATES.md): 조사한 외부 프로젝트와 후보 비교
- [UVDoc](https://github.com/tanguymagne/UVDoc): 우선 검증할 곡면 보정 모델
- [UVDoc paper](https://arxiv.org/abs/2302.02887)

---

## 2. 프로젝트 목적과 실제 사용 환경

### 2.1 목적

문제집을 카메라로 자동 촬영하고, 좌우 페이지를 각각 읽기 가능한 평면 이미지로 보정한 뒤 `document-parser`에 전달한다.

최종 사용자는 화면을 보며 네 모서리를 지정할 수 없다. 시스템은 디스플레이 없는 온디바이스 장치에서 구동되므로, 런타임 과정은 자동이어야 한다.

### 2.2 확정된 물리 조건

- 카메라는 책받침 위에 고정된다.
- 책은 중심 위치가 정해진 V자형 받침대에 놓인다.
- V자의 양쪽 받침면 경사는 각각 45°이며 두 면의 내각은 90°다.
- 책 크기와 두께는 달라질 수 있다.
- 책등 중심이 고정되므로 전체 프레임을 좌우 페이지 영역으로 나누는 것은 가능하다.
- 각 페이지는 평면 사다리꼴이 아니라, 책등과 바깥쪽에서 휘어진 곡면일 수 있다.
- 받침대가 책보다 작아 외부에 둔 마커는 책에 가려질 수 있다.
- 내부 프레임 ArUco 마커는 후보로 유지하지만, 1차 구현의 필수 조건은 아니다.

### 2.3 제공된 예시 이미지에서 확인한 사항

예시 세트에는 펼친 책, 가까이 촬영되어 일부가 잘린 책, 강한 그림자, 빈 받침대 이미지가 포함되어 있다.

관찰된 특징:

- 밝은 페이지와 어두운 천 배경의 명도 차이는 대체로 크다.
- 배경 천은 광택과 주름이 강해 프레임 사이 밝기 변화가 크다.
- 책 전체와 배경의 분리는 비교적 쉽지만, 현재 펼쳐진 상단 페이지와 아래쪽 페이지 묶음의 경계는 모두 흰 종이라 모호할 수 있다.
- 페이지 내부의 글자·표·색상 블록은 물리적 페이지 경계보다 강한 edge를 만든다.
- 스마트폰/카메라 그림자나 조명 변화가 페이지를 크게 가릴 수 있다.
- 좌우 페이지는 책등 부근에서 실제 곡면을 형성한다.

---

## 3. 현재 구현의 출발점

현재 패키지는 Python 3.11 이상이며 주요 의존성은 NumPy, OpenCV, Pillow, requests다.

현재 핵심 흐름:

```text
첫 프레임을 빈 배경으로 등록
→ 전체 프레임을 고정 centerline_fraction에서 좌우 분리
→ 각 subframe을 빈 배경과 absdiff
→ morphology로 foreground mask 생성
→ 가장 큰 contour에 minAreaRect 적용
→ 네 모서리 homography
→ geometry / stability / document-parser quality 판정
→ 전송
```

관련 파일:

- `detect/background.py`: 회색조 blur + 절대 차분 + 고정 threshold
- `detect/corners.py`: 가장 큰 contour + `cv2.minAreaRect`
- `detect/spread.py`: `centerline_fraction` 기반 좌우 분할
- `correct/`: 4점 homography 및 저장
- `judge/geometry_judge.py`: 회전, 면적, frame edge 접촉 판정
- `judge/stability_judge.py`: 최근 프레임의 corner/면적 안정성 판정
- `judge/quality_judge.py`: document-parser의 품질 기준 재사용
- `session/loop.py`: 배경 등록, 좌/우 순차 처리, 보정, 전송 상태 흐름

### 3.1 보존 가치가 있는 부분

다음은 새 검출 방식에서도 가능한 한 유지한다.

- `CaptureSource` 추상화와 이미지 시퀀스 테스트 경로
- 반복 캡처 세션 구조
- 전송 전 기하·안정성·화질 판정이라는 책임 분리
- 원본 저장과 보정본 메타데이터
- document-parser 품질 게이트와 전송 래퍼
- 이벤트 기반 세션 출력
- 좌/우 페이지와 한 spread 완료 상태

### 3.2 교체하거나 재정의할 부분

- 배경 차감을 페이지 검출의 주 알고리즘으로 사용하지 않는다.
- 페이지를 회전 사각형으로 가정하지 않는다.
- `minAreaRect`의 네 점을 페이지의 실제 모서리로 간주하지 않는다.
- 곡면 페이지에 4점 homography를 최종 보정으로 적용하지 않는다.
- 좌우 subframe의 책등 쪽 경계 접촉을 `OUT_OF_FRAME`으로 처리하지 않는다.
- 안정성은 네 corner의 이동량만이 아니라 mask의 면적, centroid, IoU 또는 contour 변화로 판단할 수 있어야 한다.

기존 경로는 비교 기준이나 fallback으로 당분간 남길 수 있다. 새 경로의 실험 결과가 나오기 전에 관련 코드를 한꺼번에 삭제하지 않는다.

---

## 4. 채택할 문제 정의

### 4.1 좌우 분할

책등 중심이 물리적으로 고정되므로, 범용 spread 분리 모델을 만들지 않는다.

초기에는 현재의 `centerline_fraction`을 유지하되, 실제 장비에서는 단순히 이미지 폭의 50%라고 가정하지 말고 캘리브레이션된 중심선 또는 좌우 polygon ROI로 확장할 수 있게 한다.

좌우 분리 결과는 두 개의 독립적인 단일 페이지 검출 문제로 취급한다.

### 4.2 페이지 검출

각 좌우 ROI에서 다음 이진 segmentation을 수행한다.

- foreground: 현재 OCR해야 하는 상단 페이지 표면
- background: 받침대, 천, 아래쪽 페이지 묶음의 옆면, 반대쪽 페이지, 손, 기타 물체

모델이 네 모서리를 직접 출력할 필요는 없다. 사다리꼴이거나 곡선 경계를 가진 페이지도 픽셀 마스크로 표현한다.

정확한 종이 외곽 복원이 최종 목표는 아니다. 최종 목표는 다음과 같다.

> 현재 페이지의 인쇄 영역을 모두 포함하면서, UVDoc 입력에 방해되는 배경과 페이지 옆면을 가능한 한 제외한 자동 crop을 생성한다.

상단 페이지와 페이지 묶음 사이의 경계가 영상에서 완전히 사라지는 경우, RGB 영상만으로 물리적 경계를 정확하게 복원할 수 없다는 한계를 인정한다. OCR 목적에 지장이 없다면 안전 여백 또는 안쪽 crop으로 처리한다.

### 4.3 페이지 보정

기본 경로는 다음과 같다.

```text
좌우 ROI
→ 페이지 표면 segmentation
→ mask 검증 및 여백을 둔 crop
→ UVDoc
→ document-parser 품질 검사
→ 전송
```

UVDoc은 입력 이미지로부터 2D sampling grid를 예측하고 원본을 재매핑한다. 따라서 기본 경로에서는 UVDoc 전에 `minAreaRect` 기반 4점 homography를 적용하지 않는다.

고정된 45° 받침면을 이용한 coarse homography는 다음 두 용도로만 실험한다.

1. segmentation 입력을 정규화해 모델이 페이지를 찾기 쉽게 하는 방법
2. UVDoc 입력의 큰 원근 왜곡을 줄이는 A/B 실험

이는 곡면을 최종적으로 펴는 방법이 아니며, 효과는 실제 데이터로 비교한 뒤 채택한다. 반복 보간으로 OCR 선명도가 떨어지지 않는지도 확인한다.

---

## 5. 목표 파이프라인

```text
Camera frame
  ├─ lens undistortion (calibration이 있을 때)
  ├─ calibrated left/right ROI split
  ├─ low-resolution page segmentation per side
  ├─ mask post-processing
  ├─ mask validity + temporal stability
  └─ stable full-resolution capture
       ├─ page crop with padding
       ├─ optional neutralization of pixels outside mask
       ├─ UVDoc dense unwarping
       ├─ document-parser quality gate
       ├─ raw/crop/unwarped diagnostics
       └─ transmit or automatic retry
```

### 5.1 OpenCV의 책임

- 카메라 렌즈 왜곡 보정
- 좌우 ROI 절단 및 좌표 변환
- segmentation mask resize와 morphology
- connected component 및 작은 오검출 제거
- mask bounding region과 padding 계산
- 연속 프레임 안정성 계산
- 품질 게이트용 기초 통계
- 진단 overlay 생성
- 필요 시 ArUco 인식과 캘리브레이션

### 5.2 CNN의 책임

- 각 좌우 ROI에서 상단 페이지 표면 의미 분할
- UVDoc을 이용한 페이지의 원근·곡면 변형 복원

---

## 6. 구현 로드맵

각 단계는 앞 단계의 측정 결과를 확인한 뒤 진행한다.

### Stage 0. 기준선 보존과 재현

작업:

- 현재 unit test 전체 실행
- 예시 이미지에서 현재 background subtraction 경로의 실패 결과를 재현
- 기존 출력과 진단 결과를 저장할 평가 도구의 최소 골격 마련
- 기존 검출 경로를 즉시 삭제하지 않고 strategy 또는 adapter 경계 뒤에 둔다

완료 조건:

- 변경 전 테스트 결과가 기록되어 있다.
- 동일 입력을 기존 경로와 새 경로에 넣어 비교할 수 있다.
- 실패가 발생해도 raw 이미지가 보존된다.

### Stage 1. 페이지 마스크 경계 도입

세부 클래스명은 구현 중 조정할 수 있지만, 검출 결과가 네 모서리가 아닌 마스크를 중심으로 흐르도록 새 경계를 만든다.

예시 책임:

- `PageSegmenter`: 좌/우 ROI를 받아 mask, confidence, diagnostics 반환
- `PageMask` 또는 동등 결과: binary mask, bbox, area ratio, centroid, side, 원본 좌표 변환 정보
- fake/static segmenter: ML 런타임 없이 session과 test를 검증

완료 조건:

- session 코드를 실제 모델 없이도 mask 기반으로 시험할 수 있다.
- 좌우 ROI의 좌표가 full frame 좌표와 혼동되지 않는다.
- 기존 `PageGeometry`를 억지로 재사용하지 않고 필요한 adapter가 명확하다.

### Stage 2. 오프라인 segmentation 평가 도구

실시간 통합보다 먼저 예시 이미지에 대한 오프라인 도구를 만든다.

필수 기능:

- 이미지 또는 디렉터리 입력
- calibrated/fraction centerline으로 좌우 분리
- 각 side의 raw mask, overlay, crop 저장
- 빈 받침대 no-page 결과
- confidence, area ratio, centroid, edge contact, 처리시간 기록
- 정답 mask가 있으면 IoU/Dice/boundary metric 계산
- 모델을 교체할 수 있는 공통 실행 경로

초기 비교 후보:

- 명도/색상 기반 OpenCV baseline
- 범용 문서 segmentation 사전학습 모델이 확보되는 경우 zero-shot 결과
- 실제 장비 이미지로 fine-tune할 lightweight segmentation

OpenCV baseline은 최종 해법으로 단정하지 않는다. 라벨 초안을 자동 생성하고 사람이 수정하는 bootstrapping 용도로도 사용할 수 있다.

완료 조건:

- 예시 세트 전체의 결과를 한 번에 생성할 수 있다.
- 책 이미지와 빈 받침대에서 실패 유형이 구분되어 기록된다.
- 결과를 눈으로 검증할 overlay가 있다.

### Stage 3. 데이터 정의와 lightweight segmentation

라벨 정의:

- label 1: 현재 펼쳐진 한쪽의 상단 페이지 표면
- label 0: 나머지 전체
- 페이지 묶음의 옆면은 background
- 책등 쪽에서 반대 페이지가 보이면 background
- 손, 그림자 자체, 받침대, 외부 물체는 background
- 그림자는 페이지 표면 위에 드리워졌더라도 그 아래 페이지 영역은 foreground가 되어야 한다

데이터 수집 시 포함할 변화:

- 서로 다른 책 크기와 두께
- 흰색·미색·유색 페이지
- 표, 그림, 큰 색상 블록, 수식 밀도
- 책등 곡률과 바깥쪽 들림
- 조명 밝기, 색온도, 방향
- 그림자와 부분 반사
- 약간의 책 위치 오차
- 빈 받침대, 손, 페이지 넘김 중간 상태
- 정상 범위를 벗어난 잘린 페이지

주의:

- 같은 연속 촬영 세션의 인접 프레임을 train/test에 나누지 않는다.
- 책 또는 촬영 세션 단위로 split해 데이터 누수를 막는다.
- 현재 예시 이미지는 파이프라인 proof에는 유용하지만, 일반화 성능을 학습·평가하기에는 부족하다.
- 처음부터 모델을 새로 학습하기보다 MobileNet 계열 backbone의 segmentation 모델 fine-tuning을 우선 검토한다.
- 모델 종류는 정확도 확인 전에 확정하지 않는다. LR-ASPP, DeepLabV3-MobileNet, Fast-SCNN, 경량 U-Net류가 후보가 될 수 있다.

완료 조건:

- held-out 책/세션에서 mask 평가가 가능하다.
- 빈 받침대와 페이지 넘김 상태가 페이지로 오검출되지 않는다.
- mask가 OCR 본문을 잘라내지 않는다.
- 실패 샘플이 모델 confidence 또는 후처리 품질 게이트에서 reject된다.

### Stage 4. Mask 후처리와 자동 crop

후처리 후보:

- largest plausible component
- 작은 component 제거
- 내부 hole filling
- side별 허용 영역과 교차 검사
- mask dilation 또는 crop padding으로 페이지 여백 보존
- 바깥쪽 배경을 중립색으로 치환하는 방식과 원본 배경 유지 방식 A/B 비교

edge contact 정책:

- 왼쪽 ROI의 오른쪽 경계, 오른쪽 ROI의 왼쪽 경계는 책등 중심선이므로 접촉 가능하다.
- 이 접촉을 현재 코드처럼 무조건 `OUT_OF_FRAME`으로 처리하지 않는다.
- full-frame의 바깥 경계 접촉은 페이지가 잘렸을 가능성이 있으므로 별도로 판단한다.
- 캘리브레이션 ROI 경계와 물리 frame 경계를 구분한다.

완료 조건:

- 유효 페이지는 충분한 여백을 가진 crop으로 변환된다.
- 잘린 페이지와 정상적인 책등 접촉이 구분된다.
- crop 좌표와 mask가 raw 원본에 다시 매핑 가능하다.
- crop 실패는 예외로 세션을 종료하지 않고 진단 가능한 reject로 반환된다.

### Stage 5. UVDoc adapter와 품질 검증

구현 원칙:

- 모델은 프로세스당 한 번 lazy load하고 프레임마다 다시 읽지 않는다.
- CPU 경로를 우선 지원한다.
- 런타임 중 인터넷에서 weight를 다운로드하지 않는다.
- weight 경로와 device는 설정으로 주입한다.
- UVDoc 저장소 코드를 그대로 흩어 복사하기보다 작은 adapter 경계를 둔다.
- 원본, mask crop, unwarped 결과를 문제 추적 가능하도록 연결한다.
- 모델 부재 또는 추론 실패가 세션 전체 crash로 이어지지 않게 한다.
- 라이선스 고지와 weight 배포 방식을 확인한다.

A/B 비교:

1. mask bbox crop 그대로 UVDoc 입력
2. mask 밖을 중립색으로 치환한 crop
3. calibrated support-plane coarse warp 후 UVDoc
4. 기존 4점 homography 결과

평가:

- 본문 줄의 직선성
- 글자 획 보존
- 잘림 여부
- document-parser 품질 게이트
- OCR 성공률 또는 CER
- 처리시간과 peak RAM

완료 조건:

- UVDoc이 좌우 페이지 각각에 자동 적용된다.
- 실패 시 raw/crop이 보존되고 자동 재시도가 가능하다.
- 기존 homography보다 OCR 품질이 실제 샘플에서 개선되거나, 최소한 악화 여부가 수치로 확인된다.

### Stage 6. Session loop 통합

현재 세션은 왼쪽 페이지를 먼저 전송하고 이후 프레임에서 오른쪽 페이지를 처리한다. 초기에는 기존 상태 흐름을 보존할 수 있지만, 다음 위험을 검토한다.

- 왼쪽 처리 후 사용자가 페이지를 넘기면 오른쪽이 다른 spread에서 촬영될 수 있다.
- 좌우가 서로 다른 순간의 조명과 그림자를 가질 수 있다.

대안은 한 번 안정화된 full-spread frame을 고해상도로 저장하고, 동일 원본에서 좌우를 모두 분리·보정한 다음 두 결과를 검증·전송하는 것이다. 이 변경은 사용자 상호작용과 오류 복구 방식에 영향을 주므로 별도 설계 판단으로 남긴다.

안정성 판정 후보:

- 연속 mask IoU
- mask area 변화율
- centroid 이동
- crop bbox 이동
- blur/노출 변화
- 페이지 넘김 motion

완료 조건:

- 수동 모서리 지정 없이 자동 촬영·보정·전송된다.
- 불안정한 페이지, 손, 페이지 넘김 중에는 전송하지 않는다.
- 어느 한쪽 실패 시 전체 spread 상태와 재시도 동작이 일관된다.
- headless 장치에서 필요한 상태를 이벤트/로그/비프음용 reason으로 표현할 수 있다.

### Stage 7. Raspberry Pi 배포 최적화

정확성 검증 후 진행한다.

- preview segmentation은 저해상도로 수행
- 안정화 후 고해상도 이미지를 한 번만 보정
- PyTorch CPU baseline 측정
- 필요 시 ONNX Runtime, TFLite 또는 다른 Pi 적합 런타임 검토
- warm-up 시간, 단일 추론시간, peak RSS, 저장공간 측정
- 가능하면 `opencv-python-headless` 전환 검토
- ML 의존성은 optional dependency 또는 별도 runtime 구성으로 격리

완료 조건:

- 실제 목표 Raspberry Pi에서 메모리 초과 없이 동작한다.
- 허용 가능한 사용자 대기시간이 실측되어 있다.
- 모델 load 실패, weight 누락, 카메라 오류가 진단 가능한 상태로 보고된다.
- 네트워크 연결과 디스플레이 없이 정상 세션을 수행할 수 있다.

### Stage 8. ArUco 및 기하 보조 실험

주 검출 경로의 성능이 부족하거나 ROI 재현성이 필요할 때 진행한다.

ArUco의 역할:

- 빈 받침대 또는 노출된 내부 프레임에서 카메라 자세 추정
- 받침대 중심선과 좌우 45° 평면의 ROI 계산
- 카메라가 이동했는지 감지
- segmentation 탐색 영역 축소

ArUco가 하지 않는 일:

- 책에 가려진 뒤 현재 페이지 외곽을 직접 측정
- 페이지 곡면 복원
- 책 크기 추정만으로 상단 페이지 한 장의 정확한 경계 결정

마커가 서로 같은 평면에 없으면 단일 homography로 묶지 않고, 알려진 3D 좌표와 카메라 캘리브레이션을 이용한 pose estimation을 검토한다.

---

## 7. 검증 시나리오와 잠정 지표

### 7.1 필수 시나리오

| 시나리오 | 기대 결과 |
|---|---|
| 정상 펼친 책 | 좌우 페이지 mask 생성, 안정화 후 자동 처리 |
| 빈 받침대 | no-page, 전송 없음 |
| 페이지 넘김 중 | unstable/reject |
| 손이 페이지를 가림 | reject 또는 재시도 |
| 강한 그림자 | 페이지 mask 유지 또는 품질 실패로 reject |
| 책 일부가 frame 밖으로 나감 | cropped/out-of-frame reject |
| 두꺼운 책의 페이지 옆면 노출 | 상단 페이지 중심 crop, 옆면 최대한 제외 |
| 유색/그림 많은 페이지 | 내부 인쇄물을 배경으로 오인하지 않음 |
| UVDoc 실패/weight 누락 | raw 보존, 진단 reason, crash 없음 |
| 한쪽만 품질 실패 | spread 상태를 잃지 않고 정해진 정책으로 재시도 |

### 7.2 잠정 지표

아래 수치는 초기 목표이며 실제 데이터 분포와 사용성 측정 후 조정한다.

- 정상 spread의 좌우 페이지 분리 성공률: 95% 이상
- 빈 받침대 false capture: 평가 세트에서 0
- OCR 본문 잘림: 평가 세트에서 0을 목표
- 연속 프레임 안정성 통과 전 촬영: 0
- 보정 실패 시 raw 보존율: 100%
- 최종 기준은 mask IoU 단독이 아니라 document-parser/OCR 성공 여부와 함께 판단

---

## 8. 권장 모듈 경계 예시

다음은 방향을 설명하기 위한 예시이며, 구현 전 저장소 관례에 맞춰 조정할 수 있다.

```text
src/book_scanner/
  detect/
    segmenter.py          # PageSegmenter protocol / result
    mask_postprocess.py   # component, hole, padding, validity
    roi.py                # left/right calibrated ROI와 좌표 변환
    background.py         # 기존 baseline/fallback
    corners.py            # 기존 baseline adapter
  correct/
    uvdoc_adapter.py      # model load / inference / error mapping
    pipeline.py           # 기존 보존 후 전략별 경로
  judge/
    mask_geometry.py      # area, allowed edge, truncation
    mask_stability.py     # IoU/centroid/area history
    quality_judge.py      # 기존 document-parser 품질 기준
  session/
    loop.py               # 전략을 조합하되 ML 세부사항은 모르게 유지
tools/
  evaluate_page_masks.py
  run_uvdoc_experiment.py
tests/
  unit/
  integration/
```

ML 모델 구현체와 세션 상태 머신이 직접 결합되지 않도록 한다. 모델 변경이 전송·저장·이벤트 코드의 대규모 수정으로 이어지지 않아야 한다.

---

## 9. 구현 시 피해야 할 가정

- 책 페이지는 정확한 사각형이다.
- 가장 큰 contour가 항상 현재 페이지다.
- 책등 경계가 subframe edge에 닿으면 촬영 실패다.
- 빈 배경과 현재 프레임의 밝기가 동일하다.
- 한 번의 고정 threshold가 모든 조명에서 작동한다.
- 책 전체 silhouette와 현재 상단 페이지는 같은 영역이다.
- UVDoc이 좌우 페이지를 자동으로 나눠 준다.
- 논문 benchmark 점수가 이 받침대에서의 성능을 보장한다.
- Raspberry Pi에서 PyTorch 모델이 성능 측정 없이 충분히 빠르다.
- 런타임에서 사용자가 화면을 보고 corner를 지정할 수 있다.
- 마커가 페이지에 가려져도 현재 페이지 경계를 직접 알 수 있다.
- 같은 세션의 인접 프레임을 train/test로 나눈 결과가 일반화 성능이다.

---

## 10. 첫 구현 세션의 권장 작업 범위

첫 세션에서 모델 학습과 Pi 최적화까지 한꺼번에 진행하지 않는다. 다음 범위가 적절하다.

1. 현재 테스트를 실행하고 baseline 상태를 기록한다.
2. `PageSegmenter`와 mask 중심 결과 타입의 최소 경계를 설계한다.
3. fake segmenter를 이용해 좌우 ROI → mask → crop 경로의 unit test를 만든다.
4. 예시 이미지에 결과 overlay를 저장하는 오프라인 평가 CLI를 만든다.
5. 기존 background/minAreaRect 경로와 새 mask 경로를 선택할 수 있게 한다.
6. UVDoc adapter의 의존성·weight·입출력 규격을 조사하고 별도 실험 스크립트로 한 페이지 crop을 처리한다.
7. 실험 결과를 보고 session loop 통합과 학습 데이터 제작 범위를 확정한다.

첫 세션의 산출물은 “완성된 스캐너”가 아니라 다음 단계의 판단이 가능한 실험 기반이어야 한다.

- 재현 가능한 명령
- 입력/출력 디렉터리 규칙
- overlay와 진단값
- baseline 비교
- 테스트
- 확인된 실패 사례
- 다음 의사결정 항목

---

## 11. Codex 작업 지침

- 작업 전 이 문서, `README.md`, `PAGE_DETECTION_CANDIDATES.md`와 관련 source/test를 읽는다.
- 현재 동작을 추측하지 말고 테스트와 실제 코드를 기준으로 판단한다.
- 저장소에 사용자 변경이 있으면 보존하고 관련 없는 파일을 수정하지 않는다.
- 기존 세션/전송 구조를 유지할 수 있는 작은 경계부터 만든다.
- 실험 결과 없이 모델이나 threshold를 최종 결정하지 않는다.
- 구현 과정에서 관찰한 사실과 설계 판단을 구분한다.
- 새 의존성, weight, 라이선스, Pi 배포 비용을 명시한다.
- 실패를 예외 하나로 숨기지 말고 자동 재시도에 사용할 수 있는 reason과 diagnostics를 남긴다.
- 변경 후 unit test와 가능한 범위의 이미지 기반 검증을 실행한다.
- 실제 데이터나 하드웨어가 없어 검증하지 못한 사항을 완료로 표시하지 않는다.

## 12. 현재 결정 상태 요약

### 채택

- 책 중심 고정을 통한 좌우 분할
- 좌우 페이지를 독립적인 단일 페이지 문제로 처리
- 페이지 표면 segmentation
- mask 기반 crop
- 페이지별 UVDoc 적용
- OpenCV 기반 후처리와 안정성/품질 판정
- headless 자동 처리

### 후보 유지

- 내부 프레임 ArUco 캘리브레이션
- 45° 받침면 기반 coarse perspective normalization
- 기존 background subtraction fallback
- UVDoc 외 DocScanner 계열 비교
- 동일 full-spread frame에서 좌우를 함께 처리하는 세션 변경

### 미정

- 최종 segmentation 모델
- 학습 데이터 규모와 정확한 라벨링 도구
- mask 외부 픽셀 처리 방식
- UVDoc 모델 변환 및 Pi 런타임
- 실제 캘리브레이션 방식
- 최종 threshold와 처리시간 목표
- 좌우 중 한쪽만 실패했을 때의 spread 재시도 정책
