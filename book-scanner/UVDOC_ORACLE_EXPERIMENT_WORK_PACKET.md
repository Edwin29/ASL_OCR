# UVDoc Oracle Crop Feasibility Experiment — Work Packet

상태: **IMPLEMENTED — 실제 CPU 검증 완료, 판정 CONDITIONAL**
작성일: 2026-08-29
승인: 2026-08-29
검증 완료: 2026-08-30
근거 문서: `CODEX_IMPLEMENTATION_CONTEXT.md` Stage 5 및 첫 구현 세션 권장 범위

## 1. 목적

페이지 검출 모델을 개발하기 전에, 손수 라벨링한 정답 page mask를 oracle detector
결과로 사용해 UVDoc이 현재의 고정 V자형 책받침 이미지에서 실제로 유효한 곡면
보정을 수행하는지 검증한다.

이 작업은 다음 세 문제를 분리한다.

1. 좌우 페이지 구분: full-spread frame에서 좌/우 처리 영역과 좌표계를 정한다.
2. 페이지 검출: 각 영역에서 현재 상단 페이지 표면 mask를 찾는다.
3. 페이지 보정: 주어진 page crop을 평면화한다.

이번 패킷은 3번만 실험한다. 1번과 2번은 손수 만든 정답 라벨로 대체한다. UVDoc이
oracle crop에서도 부적합하면 페이지 검출 학습이나 session 통합으로 진행하지 않는다.

## 2. 승인 시 확정되는 결정

- 실험 입력은 `TESTIMAGES/20260826_175109.jpg`와 같은 이름의 LabelMe JSON이다.
- `left_page`, `right_page` polygon을 각 페이지의 oracle mask로 취급한다.
- UVDoc 전에 `minAreaRect` 또는 4점 homography를 적용하지 않는다.
- 기존 session loop, transmit client, stability/quality 정책은 변경하지 않는다.
- UVDoc 소스와 pretrained weight는 저장소에 복사해 커밋하지 않는다.
- PyTorch는 `book-scanner` 기본 의존성에 추가하지 않고 격리된 실험 런타임에서만
  사용한다.
- 실제 추론과 출력 검토가 이루어지지 않은 상태에서는 UVDoc 검증을 완료로 표시하지
  않는다.

## 3. 입력과 알려진 제약

### 입력

- 원본: `TESTIMAGES/20260826_175109.jpg` (4000×3000)
- 정답: `TESTIMAGES/20260826_175109.json`
- 라벨: `left_page`, `right_page`
- UVDoc 공식 checkpoint: `model/best_model.pkl` 또는 사용자가 지정한 동등 checkpoint

### 현재 라벨에서 이미 확인한 점

- 두 polygon은 자기교차가 없고 원본 좌표계와 일치한다.
- 좌우 mask는 책등에서 소량 겹친다.
- 바깥쪽 page stack 옆면이 일부 포함되어 있을 수 있다.
- 이 문제들은 결과 해석에 기록한다. 코드는 임의로 polygon을 고치거나 정답을
  재정의하지 않는다.

라벨이 UVDoc 입력으로 명백히 부적합하다고 판단되면 해당 사실과 overlay를 보고하고,
사용자 수정 없이 자동 erosion이나 임의 boundary 변경으로 실험을 계속하지 않는다.

## 4. 구현 범위

### WP-1. LabelMe oracle loader

계획 파일:

- `src/book_scanner/annotations/__init__.py`
- `src/book_scanner/annotations/labelme.py`

책임:

- JSON의 image path/width/height와 실제 이미지 검증
- 필요한 좌우 label 존재와 polygon 형식 검증
- full-frame binary mask rasterize
- 좌우 overlap, self-intersection, frame-edge contact, 면적 진단
- 원본 좌표계 bbox와 crop-local mask 생성
- 비ASCII Windows 경로 지원

### WP-2. Oracle crop 생성

계획 파일:

- 기존 `detect/page_mask.py`의 검증된 crop 경계를 재사용하거나 작은 adapter 추가

필수 입력 변형:

1. `bbox_original`
   - oracle mask bbox에 설정 가능한 padding 적용
   - mask 밖의 원본 픽셀 유지
2. `bbox_neutralized`
   - 동일 bbox와 padding
   - mask 밖을 흰색 또는 명시적으로 지정한 중립색으로 치환

두 입력은 같은 bbox와 해상도를 사용해 배경 처리의 영향만 비교한다. 반복 보간을
피하기 위해 crop 생성 단계에서는 perspective warp를 수행하지 않는다.

### WP-3. 보정기 공통 계약

계획 파일:

- `src/book_scanner/correct/unwarper.py`

예정 계약:

```python
class PageUnwarper(Protocol):
    def unwarp(self, image: np.ndarray) -> UnwarpResult: ...
```

`UnwarpResult`는 최소한 다음을 포함한다.

- 성공 여부
- 출력 이미지 또는 `None`
- 모델/adapter 이름
- device
- 처리 시간
- 입력/출력 크기
- 실패 reason
- diagnostics

실패 reason은 최소한 다음을 구분한다.

- `MODEL_NOT_FOUND`
- `MODEL_LOAD_FAILED`
- `INVALID_INPUT`
- `INFERENCE_FAILED`
- `INVALID_OUTPUT`

### WP-4. UVDoc adapter

계획 파일:

- `src/book_scanner/correct/uvdoc_adapter.py`

원칙:

- 공식 UVDoc 코드를 여러 모듈에 복사하지 않고 adapter 한 곳에 격리한다.
- checkpoint 경로, UVDoc runtime/source 경로, device를 설정으로 주입한다.
- 모델은 adapter 인스턴스에서 lazy load하고 페이지마다 다시 읽지 않는다.
- `auto` device는 CUDA 사용 가능 시 CUDA, 아니면 CPU로 해석한다.
- import, weight load, inference, output validation 실패를 위 reason으로 변환한다.
- 런타임 인터넷 다운로드를 수행하지 않는다.
- 입력을 UVDoc의 488×712 model input으로 축소해 grid를 예측하되, 공식 demo와 같이
  sampling grid는 원본 crop 해상도에 적용한다.
- 원본 crop을 수정하지 않는다.

공식 참고:

- <https://github.com/tanguymagne/UVDoc>
- <https://github.com/tanguymagne/UVDoc/blob/main/demo.py>
- <https://github.com/tanguymagne/UVDoc/blob/main/utils.py>
- 공식 코드 라이선스: MIT

### WP-5. 일괄 실험 CLI

계획 파일:

- `tools/run_oracle_uvdoc_experiment.py`

예정 사용법:

```bash
python tools/run_oracle_uvdoc_experiment.py \
  --image TESTIMAGES/20260826_175109.jpg \
  --label TESTIMAGES/20260826_175109.json \
  --uvdoc-runtime PATH_TO_UVDOC \
  --checkpoint PATH_TO_BEST_MODEL \
  --device auto \
  --output-dir OUTPUT_DIR
```

각 side/variant에 대해 다음을 저장한다.

- oracle mask
- mask overlay
- 원본 bbox crop
- neutralized crop
- UVDoc 결과
- 처리시간과 diagnostics JSON
- 원본/라벨/checkpoint SHA-256
- adapter/runtime version 또는 UVDoc commit

실패하더라도 raw crop, mask, overlay, diagnostics는 보존한다.

### WP-6. 비교와 보고

비교 대상:

- oracle crop 그대로
- neutralized oracle crop
- 각 입력의 UVDoc 결과
- 기존 homography는 독립 참고 결과로만 생성하며 UVDoc 앞에는 연결하지 않는다.

자동 기록:

- document-parser image quality gate 결과
- 입력/출력 해상도
- 처리시간
- mask/crop의 본문 포함 여부를 검토할 overlay
- 가능하면 OCR token 수/confidence 및 text-line straightness 보조 지표

OCR 정답 transcription 또는 같은 페이지의 평면 스캔이 없으므로 CER, MS-SSIM,
절대 보정 정확도를 완료 지표로 주장하지 않는다. 최종 산출물에는 좌/우 × 입력 변형의
contact sheet와 사람이 확인할 항목을 포함한다.

계획 파일:

- `UVDOC_ORACLE_EXPERIMENT_REPORT.md`

보고서는 실제 실행 뒤 관찰된 사실, 해석, 미검증 항목을 분리한다.

## 5. 테스트 범위

### Unit tests

계획 파일:

- `tests/unit/test_labelme_annotations.py`
- `tests/unit/test_uvdoc_adapter.py`
- `tests/unit/test_oracle_uvdoc_experiment.py`

검증 항목:

- 정상 LabelMe polygon → mask/bbox
- 이미지와 JSON 크기 불일치 reject
- label 누락, 잘못된 polygon, overlap diagnostics
- bbox padding과 full/local 좌표 round-trip
- neutralization이 mask 내부를 변경하지 않음
- fake model을 사용한 adapter lazy-load 1회 보장
- checkpoint 누락과 inference 오류 reason 매핑
- output size/dtype/channel validation
- 한쪽 실패 시 반대쪽 산출물과 raw가 보존됨

### Integration verification

- 기존 `book-scanner` unit test 전체 통과
- 실제 UVDoc checkpoint로 left/right 각각 추론
- CPU 경로 최소 1회 실행
- CUDA가 사용 가능한 경우 CUDA 결과도 별도 기록하되 필수 완료 조건은 아님
- 생성 이미지와 metadata 파일 존재/해시 확인
- `git diff --check`, `compileall`

## 6. 완료 조건

다음을 모두 만족해야 이 작업 패킷을 구현 완료로 처리한다.

- LabelMe 정답에서 좌우 oracle crop이 재현 가능하게 생성된다.
- 두 입력 변형이 좌우 각각 UVDoc에 실제로 전달된다.
- 최소 CPU 경로에서 실제 checkpoint 추론 결과가 생성된다.
- 모델을 한 번만 load한 사실이 테스트 또는 diagnostics로 확인된다.
- raw/mask/crop/unwarped/metadata의 lineage가 해시로 연결된다.
- 모델/weight 누락과 추론 실패가 crash 대신 명시적 reason으로 남는다.
- 기존 unit test와 신규 unit test가 통과한다.
- 좌우 결과를 육안 검토할 contact sheet와 실험 보고서가 있다.
- OCR 개선, 본문 잘림, line straightness에 대해 확인한 것과 확인하지 못한 것이
  분리되어 기록된다.

이 조건은 UVDoc의 최종 채택을 의미하지 않는다. 실험 결과에 따라 아래 셋 중 하나로
판정한다.

- `PROCEED`: oracle crop에서 명백한 보정 이득이 있고 치명적 잘림/왜곡이 없음
- `CONDITIONAL`: 특정 입력 변형 또는 side에서만 유효하여 추가 라벨/입력 정책 필요
- `STOP`: oracle crop에서도 불안정하거나 OCR/가독성이 악화됨

## 7. 비범위

- segmentation 모델 학습 또는 선택
- SAM/SAM 2 pseudo-label 생성
- synthetic dataset 생성
- 추가 이미지 수작업 라벨링
- 자동 centerline/spine 검출
- mask stability judge
- session loop 또는 transmit 통합
- 동일 spread 원본에서 좌우 동시 전송 정책 변경
- UVDoc fine-tuning
- ONNX/TFLite/OpenVINO 변환
- Raspberry Pi 성능 최적화 또는 배포 완료 판정
- coarse support-plane homography + UVDoc 실험

## 8. 의존성과 재현성 계획

공식 demo 요구사항은 `numpy==1.23.4`, `opencv-python-headless==4.7.0.68`,
`torch==1.13.0`이다. 현재 프로젝트는 Python 3.11 이상이므로 공식 pin을 기본 환경에
직접 합치지 않는다.

승인 후 다음 순서로 런타임을 확인한다.

1. 공식 UVDoc commit과 checkpoint SHA-256을 기록한다.
2. 별도 virtual environment에서 현재 지원되는 PyTorch로 checkpoint load와 단일
   inference를 먼저 시험한다.
3. 호환되지 않으면 공식 요구사항을 만족하는 Python 3.10 격리 환경을 사용한다.
4. 실제 성공한 버전을 `requirements-uvdoc-experiment.txt` 또는 동등 lock 파일에
   기록한다.

가중치, virtual environment, 대형 출력 이미지는 Git에 추가하지 않는다. 라이선스
고지와 공식 소스 URL은 보고서에 남긴다.

## 9. 중단 및 승인 재요청 조건

다음 상황에서는 임의 해결로 범위를 넓히지 않고 중단해 사용자 승인을 다시 받는다.

- oracle label 수정이 필요함
- 공식 checkpoint가 현재/격리 환경에서 load되지 않음
- UVDoc 소스 수정 또는 코드 vendoring이 필요함
- 새 외부 모델/weight를 사용해야 함
- coarse homography, fine-tuning 또는 다른 dewarper 비교가 필요함
- document-parser OCR 실행을 위해 대형 신규 의존성이나 외부 서비스가 필요함
- 실험 결과가 side마다 상충해 채택 기준을 바꿔야 함

## 10. 예상 변경 파일 요약

신규:

- `src/book_scanner/annotations/__init__.py`
- `src/book_scanner/annotations/labelme.py`
- `src/book_scanner/correct/unwarper.py`
- `src/book_scanner/correct/uvdoc_adapter.py`
- `src/book_scanner/evaluation/unwarp_experiment.py`
- `tools/run_oracle_uvdoc_experiment.py`
- `tests/unit/test_labelme_annotations.py`
- `tests/unit/test_uvdoc_adapter.py`
- `tests/unit/test_oracle_uvdoc_experiment.py`
- 실제 실행 후 `UVDOC_ORACLE_EXPERIMENT_REPORT.md`

필요 시 최소 수정:

- `.gitignore`: runtime/output/weight 제외 규칙
- `README.md`: 승인된 실험 명령과 결과 문서 링크

수정 금지:

- `src/book_scanner/session/loop.py`
- `src/book_scanner/transmit/client.py`
- 기존 사용자 이미지와 LabelMe JSON
- 기존 perspective correction의 동작 계약

## 11. 승인 요청

이 패킷 승인 시 다음을 허용하는 것으로 해석한다.

1. 위 구현 파일과 테스트를 추가한다.
2. 공식 UVDoc 소스와 checkpoint를 실험용으로 내려받고 버전/해시를 기록한다.
3. 저장소 밖 또는 Git에서 제외되는 격리 환경에 PyTorch 등 실험 의존성을 설치한다.
4. `175109`의 기존 라벨을 수정하지 않고 oracle 입력으로 사용한다.
5. 실제 좌우 결과와 보고서가 나온 뒤에만 다음 단계 진행 여부를 판단한다.

승인 후 구현 및 검증 결과는 `UVDOC_ORACLE_EXPERIMENT_REPORT.md`에 기록했다.
