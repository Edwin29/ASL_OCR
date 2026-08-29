# Page Detection and Rectification Candidates

이 문서는 `book-scanner`의 배경 차감 기반 검출을 대체하거나 보완할 후보를 기록한다.

## 결론

현재 확인한 범위에서는 다음 조건을 동시에 보장하는 공개 프로젝트는 없다.

- 펼친 책의 좌/우 페이지를 자동으로 분리
- 책의 곡면까지 보정
- 디스플레이 없는 Raspberry Pi급 장치에서 실시간 동작
- 사전학습 가중치와 유지되는 배포 코드 제공

논문 벤치마크는 대부분 **이미 한 장의 문서가 입력된 상황**을 평가한다. 따라서 공개 점수만으로 현재 V자형 받침대 환경의 성능을 보장할 수 없으며, 실제 촬영 데이터로 후보 비교가 필요하다.

## 후보 우선순위

| 우선순위 | 후보 | 담당 역할 | 장점 | 주요 제약 |
|---|---|---|---|---|
| 1 | [DocScanner](https://github.com/fh2019ustc/DocScanner) | 문서 영역 검출 + 곡면 보정 | U2NETP 기반 위치 검출과 반복 보정 모델을 함께 제공하며 사전학습 가중치와 논문 성능이 있음 | 기본 추론 코드가 CUDA에 고정되고 구형 PyTorch를 사용함. 양면 펼침책 분리는 별도 검증/개조 필요. 비상업적 라이선스 |
| 2 | 좌/우/배경 3-class segmentation + [UVDoc](https://github.com/tanguymagne/UVDoc) | 좌우 페이지 분리 + 페이지별 곡면 보정 | 실제 받침대 데이터에 검출기를 맞출 수 있고 UVDoc은 MIT 라이선스, CPU 실행 경로, 약 8M 파라미터를 제공 | 좌/우 마스크 학습 데이터가 필요함. UVDoc 자체는 페이지 분리기가 아님 |
| 3 | [Scanbot Linux Document Scanner SDK](https://docs.scanbot.io/linux/document-scanner-sdk/introduction/) | 상용 문서 경계 검출 기준선 | 오프라인 동작과 Raspberry Pi OS 64-bit 지원을 명시한 제품 SDK | 유료 라이선스. 양면 책 및 페이지 곡률 보정 성능은 문서에 보장되지 않으므로 샘플 시험 필요 |
| 4 | 내부 프레임 ArUco 보정 | 카메라/받침대 기하 사전 보정 및 검출 실패 시 fallback | 헤드리스 자동 초기화가 가능하고 책 크기에 독립적인 고정 좌표계를 제공 | 책이 올라간 뒤 가려지는 마커는 페이지 경계를 직접 알려주지 않음. 45° 받침면과 카메라의 관계만 제공 |
| 5 | [DocTr++](https://github.com/fh2019ustc/DocTr-Plus) | 경계가 잘리거나 불완전한 단일 페이지 보정 연구 후보 | partial/no-boundary 문서 보정을 목표로 함 | CUDA 고정 구형 환경과 무거운 Transformer 계열. 양면 분리는 별도 |
| 참고 | [BOOK-CONTENT-SEGMENTATION-AND-DEWARPING](https://github.com/RaymondMcGuire/BOOK-CONTENT-SEGMENTATION-AND-DEWARPING) | 좌/우/배경 분할 구조 참고 | 문제 정의가 펼친 책과 가장 유사함 | 2018년 TensorFlow 코드, 약 500장 데이터, 미완성 TODO가 있어 제품 후보로 보기 어려움 |
| 참고 | [Voussoir](https://github.com/jglev/voussoir) | 마커 기반 양면 자동 분리 사례 | 한/두 페이지 spread 자동 분할을 구현 | 각 페이지 모서리 특수 glyph를 전제로 하고 페이지 곡률은 보정하지 않음 |

## 권장 구조

가장 현실적인 목표 구조는 다음과 같다.

1. 저해상도 프리뷰에서 lightweight segmentation으로 `left page / right page / background` 마스크를 구한다.
2. 마스크의 안정성, 면적, 겹침, 프레임 접촉 여부를 검사해 자동 촬영 여부를 판단한다.
3. 촬영된 고해상도 이미지에서 각 페이지를 분리한다.
4. 페이지별로 UVDoc 또는 DocScanner 계열 모델을 적용해 곡면을 편다.
5. 품질 검사에 실패하면 촬영을 강행하지 않고 재시도한다.
6. 내부 프레임 ArUco는 시작 시 카메라/받침대 자세 보정과 ROI 제한에 사용한다.

이 구조에서 OpenCV는 카메라 캘리브레이션, 마스크 후처리, 안정성 판단, 품질 게이트를 담당하고 CNN은 페이지 의미 분할과 곡면 보정을 담당한다.

## 1차 검증 계획

현재 예시 이미지로 먼저 zero-shot 비교한다.

- 펼친 책: 좌/우 두 마스크가 분리되고 서로 합쳐지지 않아야 함
- 빈 받침대: no-page 판정
- 손, 심한 그림자, 잘린 페이지: 잘못 촬영하지 않고 reject
- 평가값: page IoU, corner/edge 오차, 좌우 분리 성공률, false capture 수
- 최종 품질: 보정 결과의 OCR CER 또는 프로젝트 OCR 성공률
- 장치 성능: 실제 Raspberry Pi에서 preview FPS, 촬영 후 처리시간, peak RAM

### 통과 기준 제안

- 펼친 책 좌/우 분리 성공률: 95% 이상
- 빈 받침대 false capture: 0%
- 연속 프레임 안정성 통과 후 촬영
- 단일 보정 실패 시 원본 보존 및 자동 재시도
- Pi에서 프리뷰 검출은 저해상도, 고해상도 보정은 촬영 후 한 번만 실행

## 다음 실험 순서

1. DocScanner localization/rectification을 예시 이미지에 그대로 적용
2. UVDoc은 수동이 아닌 자동 임시 crop과 결합해 보정 품질만 평가
3. 결과가 부족하면 실제 촬영 이미지에 좌/우/배경 mask를 라벨링해 lightweight segmentation을 fine-tune
4. Scanbot trial을 같은 데이터에 적용하여 상용 기준선 확보
5. 내부 프레임 ArUco를 추가해 ROI와 카메라 자세를 고정한 뒤 동일 지표 재측정

DocScanner 또는 UVDoc을 최종 채택하기 전에 ONNX Runtime/OpenVINO/TFLite 변환 가능성과 라이선스를 별도로 확인해야 한다.
