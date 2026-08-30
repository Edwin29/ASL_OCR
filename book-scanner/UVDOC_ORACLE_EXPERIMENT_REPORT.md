# UVDoc Oracle Crop 실험 보고서

실행일: 2026-08-30
판정: **CONDITIONAL**

## 결론

손수 라벨링한 좌우 페이지를 사용하면 UVDoc 공식 checkpoint는 Windows CPU에서
정상적으로 로드되고, 좌우 페이지의 두 crop 변형을 모두 crash 없이 보정했다. 결과는
원본 crop과 기존 4점 homography보다 페이지의 큰 투시 왜곡과 책등 방향의 휨을 줄여
본문을 더 정면에 가깝게 만들었다. 치명적인 본문 잘림이나 뒤집힘은 관찰되지 않았다.

다만 이 결론은 spread 한 장에만 근거한다. 출력의 상단 제목 띠와 일부 수평 테두리에
잔여 곡률이 보이며, OCR/CER와 text-line straightness를 수치로 검증하지 않았다.
따라서 UVDoc을 최종 채택하거나 session loop에 통합하지 않고, 추가 수작업 라벨
이미지에서 같은 실험을 반복하는 조건으로 다음 검증 단계에 진행한다.

## 재현 환경과 입력 계보

- Python 3.11.8
- NumPy 2.3.5
- opencv-python-headless 5.0.0.93 (`cv2.__version__ == 5.0.0`)
- PyTorch 2.13.0+cpu, CUDA 사용 불가
- UVDoc 공식 저장소 commit:
  `4c9b82b537057aff2526e6dd118a847cdd072e82`
- UVDoc 공식 라이선스: MIT
- checkpoint SHA-256:
  `7e90861b8a516eb4bc51f84bd889cb77275743d2d1d3ca8091951ec9f2b7da23`
- 입력 이미지 SHA-256:
  `22b51152e67dc668ffe053ddbb30da14ad78839026b60ea5a2e54d9239b5ea93`
- LabelMe JSON SHA-256:
  `afb4ddc1a816ad78ba8fc3f40eb892876015e834c15284f7484cf8ee48e7df44`

공식 UVDoc 소스와 checkpoint는 `D:\Projects\OCR\tmp\uvdoc-runtime`에서 사용했으며
프로젝트에 복사하거나 커밋하지 않았다. 실제 성공한 Python 의존성은
`requirements-uvdoc-experiment.txt`에 별도로 기록했다.

## 실행 방법

```powershell
$env:PYTHONPATH='D:\Projects\OCR\book-scanner\src;D:\Projects\OCR\document-parser\src'
& 'D:\Projects\OCR\document-parser\.venv\Scripts\python.exe' `
  tools\run_oracle_uvdoc_experiment.py `
  --image TESTIMAGES\20260826_175109.jpg `
  --label TESTIMAGES\20260826_175109.json `
  --uvdoc-runtime D:\Projects\OCR\tmp\uvdoc-runtime `
  --checkpoint D:\Projects\OCR\tmp\uvdoc-runtime\model\best_model.pkl `
  --device cpu `
  --output-dir experiment_outputs\uvdoc_oracle_20260826_175109
```

대형 출력은 `.gitignore`의 `experiment_outputs/`에 보존된다. 실행 시점의 전체
artifact 경로, 크기, SHA-256, quality gate 결과는
`experiment_outputs/uvdoc_oracle_20260826_175109/summary.json`에 있다.

## 라벨 진단

- 원본 해상도: 4000×3000
- 좌측 mask bbox: `(603, 92, 1480, 2639)`
- 우측 mask bbox: `(2022, 14, 1563, 2682)`
- 두 mask 겹침: 1,785 px, 전체 프레임의 0.014875%
- 좌우 polygon winding은 서로 다르다.
- 알 수 없는 라벨이나 자기교차는 없다.
- 두 mask 모두 물리 frame edge에 닿지 않는다.

겹침과 winding 차이는 진단값으로만 기록했다. 원본 polygon을 자동 수정하거나 erosion
하지 않았다. overlay 육안 검사에서 양쪽 본문은 포함되지만 바깥쪽 page stack 일부가
포함될 수 있음을 확인했다.

## 실제 추론 결과

모델 입력은 공식 demo 규격인 488×712로 grid를 예측하고, sampling grid를 원본 crop
해상도에 적용했다. 모델 load는 한 번만 수행되었고 `load_count=1`, 초기 load 시간은
약 1,244.2ms였다.

| Side | 입력 변형 | Crop/출력 해상도 | CPU 추론 | 품질 게이트 |
|---|---|---:|---:|---|
| left | bbox_original | 1568×2797 | 329.8ms | 통과 |
| left | bbox_neutralized | 1568×2797 | 306.8ms | 통과 |
| right | bbox_original | 1657×2776 | 294.0ms | 통과 |
| right | bbox_neutralized | 1657×2776 | 254.0ms | 통과 |

네 번의 평균 추론 시간은 약 296.2ms다. 이 값에는 최초 모델 load 시간이 포함되지
않는다. desktop CPU에서 측정한 값이므로 Raspberry Pi 성능으로 해석하지 않는다.

## 시각 검토

contact sheet:
`experiment_outputs/uvdoc_oracle_20260826_175109/contact_sheet.png`
SHA-256:
`918062c72bd643f8b605e20f98d6377519c29e37eddc23a8dae8467cd402e411`

관찰된 사실:

- 좌우 두 페이지 모두 원본보다 정면에 가까운 직사각형 구도로 변환되었다.
- 본문, 페이지 번호, 바깥쪽 세로 인덱스 등 주요 인쇄 영역의 치명적 잘림은 보이지
  않았다.
- `bbox_neutralized`는 mask 밖의 검은 천과 반대 페이지 조각을 흰색으로 제거한 입력을
  제공하며, 결과 가장자리도 더 일관된 배경을 보였다.
- `bbox_original`도 네 경우 모두 성공했으며, 이 한 장에서는 배경 유지가 모델 실패를
  일으키지 않았다.
- 기존 homography는 전체적인 투시는 줄이지만 책등과 외곽의 곡면을 그대로 남긴다.
- UVDoc 결과에도 상단 제목 띠와 일부 문제 박스 수평선의 잔여 곡률이 남는다. 완전한
  평탄화로 판정할 수 없다.
- 우측 라벨에는 바깥쪽 page stack이 일부 포함되어 결과 오른쪽 가장자리에 남는다.
  이는 보정기와 page-surface 검출 품질을 분리해서 평가해야 하는 근거다.

## 자동 검증

- 전체 단위 테스트: **64 passed**
- 실제 공식 checkpoint CPU 추론: 좌/우 × 2 변형 **4/4 성공**
- 출력의 크기, dtype, channel, sampling grid 유한성 검증
- 모델/weight 누락, load 실패, inference 실패, invalid output을 구분하는 reason 제공
- 한 호출 실패 시에도 반대쪽 raw/crop/result와 contact sheet를 보존하는 테스트 통과
- 모든 raw/mask/crop/unwarped/metadata artifact에 SHA-256 기록
- document-parser image quality gate: 네 UVDoc 결과 모두 block reason 없음

품질 게이트 통과는 노출/선명도 등 기존 수용 조건을 만족했다는 뜻이며, UVDoc의 기하
보정 정확도나 OCR 개선을 증명하지 않는다.

## 확인하지 못한 항목

- OCR token 수, confidence, CER 및 보정 전후 OCR 정확도
- 객관적인 text-line straightness 또는 곡률 감소량
- 다른 책, 두께, 페이지 색상, 그림, 그림자, 부분 가림에 대한 일반화
- 수작업 라벨 경계 오차에 대한 민감도
- `bbox_original`과 `bbox_neutralized` 중 최종 입력 정책
- CUDA 결과
- Raspberry Pi 추론 시간, peak RAM, 모델 변환 가능성
- session loop의 재시도/전송 정책과의 통합

위 항목은 완료로 처리하지 않는다.

## 다음 승인 후보

1. 사용자가 제공 가능한 약 10개 spread에 동일한 좌/우 polygon 라벨을 만들고, 책 또는
   촬영 세션 단위로 oracle UVDoc 실험을 일괄 실행한다.
2. 본문 잘림 여부와 잔여 곡률을 사람이 채점할 간단한 검증표를 먼저 확정한다.
3. 가능하면 document-parser의 실제 OCR 경로로 crop/homography/UVDoc 결과의 token 수와
   confidence를 비교한다. 정답 transcription이 있는 일부 페이지만 CER을 계산한다.
4. 다수 샘플에서 neutralized 입력이 일관되게 유리한지 확인한 뒤 입력 정책을 정한다.
5. UVDoc 적합성이 확인된 후에만 좌우 페이지 검출/segmentation 데이터 전략과 모델
   비교로 진행한다. session/transmit 통합과 Pi 최적화는 계속 별도 승인 범위로 둔다.

공식 참고: <https://github.com/tanguymagne/UVDoc>
