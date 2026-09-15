# 쪽 식별 전처리 개선 조사 — 2026-09-15

## 결론

사용자가 제안한 threshold·CLAHE는 **숫자의 대비와 후보 분리 상태를 개선할 수 있는 접근**이다. 그러나 흐림을 제거하고 원래 획을 복원하는 기능과는 구분해야 한다. 저장된 실제 ROI에서 후보 추출 전 CLAHE가 일부 27을 복구했지만, 다른 시점의 ROI에서는 효과가 재현되지 않았다. 지금 바로 production 기본값으로 적용할 근거는 부족하다.

이번 조사에서 더 구체적인 실패 메커니즘을 확인했다. **흐린 27이 하나의 연결 성분이 된 상태에서, 주변 글자가 여러 성분의 후보를 만들면 현재 `multi or clusters` 규칙이 27 후보를 제거한다.** 이후 숫자 crop에 적용하는 기존 CLAHE는 이미 제외된 위치를 복구할 수 없다. 다만 위치를 수동으로 지정해도 OCR 결과가 불안정하므로, 후보 규칙 하나를 바꾸면 완전히 해결된다고 결론 내리지 않는다.

현재 실행 설정의 쪽 변경은 정확한 숫자 판독과 별개로 **좌우 OCR 원문 문자열 쌍의 반복성**을 이용한다. 따라서 아래 결과는 숫자 정확도, 문자열 획득, 시간 안의 쪽 구분을 분리해서 읽어야 한다. 제품 수정 **0건**. 새 진단 코드와 evidence·보고서만 작성했다.

## 1. 현재 실행되는 쪽 식별 메커니즘

1. **같은 프레임에서 좌우 하단 영역 선택**: 페이지 마스크와 책의 가운데 경계를 이용해 각 페이지의 바깥쪽 하단을 자른다. 페이지 밖 픽셀은 페이지 내부의 중간 밝기로 채운다. 현재 H1 설정의 opaque 입력은 `preview_native`다. `page_number.preview_max_dimension=1920`이 존재한다는 이유만으로 이 경로가 1920으로 축소된다고 해석하면 안 된다.
2. **글자 후보 추출**: ROI를 3×3 Gaussian으로 처리하고 adaptive Gaussian threshold를 적용한다. C=9이며, 영역 크기에 따라 block size를 결정한다. 연결 성분의 높이·가로세로 비·채움 비율을 검사하고, 간격과 높이·기준선이 맞는 성분을 묶는다.
3. **위치 우선 후보 선택**: 여러 성분의 묶음이 하나라도 있으면 단일 성분 후보를 제외한다. 남은 후보를 페이지 바깥쪽부터 정렬한다. 이는 번호보다 신뢰도가 높은 연도·단원 숫자를 선택하지 않기 위한 위치 우선 동작이다.
4. **숫자 인식**: 상위 최대 4개 후보마다 여백을 넣고 원본 crop 및 CLAHE 처리 crop을 Paddle 숫자 인식 모델에 보낸다. 기존 CLAHE는 `clipLimit=1.5`, `tileGridSize=(4,4)`이며 **후보 추출 이후**다. 두 출력의 일치 수와 신뢰도를 기록하고, 숫자로 읽힌 후보 중 위치 순서상 첫 후보를 반환한다.
5. **두 가지 결과 사용처**:
   - 정규화한 페이지 번호 관측: 두 variant 일치, confidence 0.62 이상 등의 상태 검사를 거친다.
   - 현재 `m1_selected_raw_pair` 쪽 식별: `token_pair_from_page_observation`은 좌우 `raw_text`가 모두 비어 있지 않으면 쌍을 만든다. **정규화 상태·confidence·variant agreement를 여기서 다시 검사하지 않는다.** 신뢰도 기준을 낮추지 않았다는 사실이 이 경로의 원문 오인식까지 차단한다는 뜻은 아니다.
6. **시간에 걸친 같은 쪽/새 쪽 판단**: 처음에는 유효 원문 쌍 5개 및 과반 동일 쌍이 필요하다. 기존 reference bank와 비교할 때는 K_same=1의 일치로 same을 조기에 결정할 수 있다. different는 N5, 모든 bank와의 일치 수 K_different=0 이하, 과반 일치 조건을 사용한다. 8초 내 결정하지 못하면 unknown이다. 정확한 27 대신 일정하게 다른 문자열이 나오는 것이 이 raw-token 계약에서 곧바로 오류인 것은 아니지만, 여러 페이지가 같은 문자열로 읽히면 구분 실패 위험이 있다.

구현 근거:

| 개념 | 현재 코드 |
|---|---|
| native/1920 입력 분기 | [engine.py](../book-scanner/src/book_scanner/video/engine.py), `_observe_opaque_pair` 약 899행, `_page_number_preview_inputs` 약 2102행 |
| 하단·바깥쪽 ROI와 마스크 | [page_number_roi.py](../book-scanner/src/book_scanner/video/page_number_roi.py), `preview_page_number_roi`, `corrected_page_number_roi` |
| 후보 추출·단일 성분 제외 | [page_number_recognizer.py](../book-scanner/src/book_scanner/video/page_number_recognizer.py), `_candidate_clusters` 약 460–523행 |
| 기존 CLAHE와 OCR 후보 반환 | 같은 파일 `PaddleRoiDigitRecognizer.recognize` 약 335–371행 |
| 정규화 상태와 원문 보존 | [page_number_provider.py](../book-scanner/src/book_scanner/video/page_number_provider.py), 약 124–153행 |
| 원문 쌍 생성·반복 관측 | [opaque_identity.py](../book-scanner/src/book_scanner/video/opaque_identity.py), 약 90행, 151행 |

`_normalize_roi`와 `_threshold_variants` 같은 별도 helper가 존재하더라도 현재 Paddle `recognize`가 호출하지 않는 처리를 현재 경로에 포함하지 않았다.

## 2. 사용자가 제안한 방법의 의미와 한계

| 방법 | 기대할 수 있는 효과 | 이번 문제에서 주의할 점 |
|---|---|---|
| CLAHE | 작은 영역별 밝기 분포를 늘려 흐릿한 획과 배경의 대비를 높임 | 초점 흐림의 역연산은 아니다. 잡음과 이미 붙은 획도 강조할 수 있다. 적용 위치가 후보 추출 전인지 후인지가 중요하다. |
| 영상 threshold | 회색 영상을 잉크/배경으로 분리해 후보 위치를 찾음 | 획이 붙거나 끊기는 결과가 달라진다. OCR 입력까지 흑백화하면 회색조 정보가 사라진다. |
| 약한 선명화 | 남아 있는 경계를 강조 | 손실된 정보를 생성하지 않으며 잡음·테두리도 강조할 수 있다. |
| 확대 | 작은 글자의 샘플링 및 모델 입력 형태를 바꿈 | 이미 흐려진 crop의 확대는 새로운 원본 해상도를 얻는 것과 다르다. |
| 복원 필터 | 가정한 흐림 모델에 맞으면 경계 복원 가능 | PSF·잡음에 대한 가정이 필요하다. 현재 초점·움직임·압축 중 원인이 확정되지 않아 우선순위가 낮다. |

OpenCV는 CLAHE를 지역 대비 보정으로 설명하며 잡음 증폭을 제한하기 위해 clipping을 사용한다. [CLAHE 공식 문서](https://docs.opencv.org/4.13.0/d5/daf/tutorial_py_histogram_equalization.html). Adaptive threshold의 C는 주변 가중 평균에서 빼는 값으로, 숫자 판독의 confidence와는 다른 영상 분리 변수다. [Threshold 공식 문서](https://docs.opencv.org/4.13.0/d7/d4d/tutorial_py_thresholding.html). 흐림 복원은 PSF와 잡음 가정을 사용하는 별도 문제다. [Out-of-focus deblur 공식 문서](https://docs.opencv.org/4.13.0/de/d3c/tutorial_out_of_focus_deblur_filter.html).

목표는 글꼴을 임의로 바꾸거나 27 모양으로 강제하는 것이 아니라, **실제 영상에 남아 있는 획을 후보 단계에서 잃지 않고 모델에 전달하는 것**이어야 한다. 왼쪽이 26이므로 오른쪽을 27로 보정하는 방식은 이번 해결책으로 사용하지 않았다.

## 3. 독립 실험 설계

- 이전 Laptop 라이브 검사에서 보존한 무손실 ROI 12개: 26이 있는 왼쪽 6개, 27이 있는 오른쪽 6개.
- development 6개는 미리보기 켬 run `laptop-live-1789477771141334500`, holdout 6개는 미리보기 끔 run `laptop-live-1789478171636106300`에서 가져왔다. 같은 책·같은 배치의 서로 가까운 관측이므로 독립적인 일반화 데이터셋이 아니다. holdout도 8개 고정 방식 모두를 평가했으므로 최종 미사용 검증 집합으로 재사용하지 않는다.
- 합성 26/28/29와 빈 배경 4개를 추가해 총 16개 × 8방식 = **128회** 인식. 합성 숫자는 한 글꼴·한 흐림 수준의 작은 대조군이며 실제 28/29 대체가 아니다.
- 동일 Laptop Python/Paddle 모델, 동일 원본 ROI hash. 정답은 결과 집계에만 사용했으며 전처리·OCR에 전달하지 않았다.
- direct recognizer 호출로 캐시 우회. 실험용 함수에서 C=5/13을 비교하되 기존 파일은 수정하지 않았다. N/K/8초 및 production config는 변경하지 않았다.
- 카메라 요청, DeviceApplication, outbox, 업로드, READY, 오디오, STM/PCA는 실행하지 않았다. 이번 결과는 H1/H4 통과 evidence가 아니다.

비교 방식은 기본, 후보 추출 전 CLAHE 1.5/2.0(8×8), unsharp 0.6, 전체 ROI Otsu, 후보 분리 C5/C13(OCR 입력은 회색조 유지), 2배 Lanczos 확대다. Otsu는 후속 기본 adaptive 분리도 거치는 실험이므로 모든 가능한 이진화 방식의 대표 결과로 일반화하지 않는다. 확대 역시 절대 픽셀 크기 필터에 영향을 줄 수 있다.

실행 원본: [study.py](evidence/footer-preprocessing-study-20260915/study.py), [dataset.json](evidence/footer-preprocessing-study-20260915/dataset.json), [manifest](evidence/footer-preprocessing-study-20260915/results-1789478771166490100/manifest.json), [원시 결과 128행](evidence/footer-preprocessing-study-20260915/results-1789478771166490100/results.jsonl), [Laptop source/config hashes](evidence/footer-preprocessing-study-20260915/laptop-source-hashes.json).

## 4. 비교 결과

아래 '품질 조건 충족'은 observed·두 출력 일치·confidence≥0.62인 숫자 결과다. 원시 JSON의 `accepted/correct/wrong_accept`도 **이 숫자 품질 지표**이며, 현재 opaque 쪽 식별기의 최종 수용을 의미하지 않는다.

| 처리 | 원문이 27 / 오른쪽 6개 | 품질 조건을 충족한 정확한 27 / 6 | development / holdout의 정확한 27 | 품질 조건을 충족한 잘못된 오른쪽 숫자 |
|---|---:|---:|---:|---:|
| 기본 | 0 | 0 | 0 / 0 | 0 |
| 후보 전 CLAHE 1.5 | 3 | 2 | 2 / 0 | 0 |
| 후보 전 CLAHE 2.0 | 1 | 1 | 1 / 0 | 0 |
| 약한 선명화 | 0 | 0 | 0 / 0 | 0 |
| 전체 Otsu | 0 | 0 | 0 / 0 | **1: 27→5** |
| 후보 분리 C5 | **4** | 0 | 0 / 0 | 0 |
| 후보 분리 C13 | 0 | 0 | 0 / 0 | 0 |
| 2배 확대 | 1 | 0 | 0 / 0 | 0 |

- 왼쪽 26은 모든 방식에서 6/6 정확하게 품질 조건을 충족했다.
- 합성 26/28/29는 모든 방식에서 맞았고 빈 배경에서는 숫자가 나오지 않았다. 대조군이 작아 오탐 안전성을 보증하지 못한다.
- CLAHE 1.5의 두 성공 confidence는 약 0.983과 0.637이다. 더 강한 CLAHE가 항상 더 좋은 결과를 주지는 않았다.
- C5는 원문 27을 4/6 얻었으나 전부 두 variant가 불일치했다. 이 결과를 0점으로만 버릴 수도, 쪽 식별 해결로 선언할 수도 없다. 현재 raw-token 경로의 안정성과 다른 페이지 간 충돌을 추가로 확인해야 한다.
- Otsu의 holdout 27→5는 confidence 약 0.639, 두 출력 일치였다. 두 variant가 일치해도 정답 보증은 아니다. 이 한 건은 최종 duplicate/READY 오판 incident가 아니라 저장 ROI 인식 결과다.

Laptop에서 holdout 전체 ROI 평균 인식 시간은 기본 약 253ms, CLAHE 1.5 약 397ms, C5 약 474ms였다. CLAHE 자체의 평균 비용은 약 1.7ms지만 후보 수와 모델 호출량 변화가 전체 비용에 영향을 준다. 고정 순서·단일 반복이고 기본의 첫 호출에는 cold 비용도 포함되므로 정밀 benchmark로 사용하지 않는다. **Pi에서 비용이 같다는 근거는 없으며**, 8초 관측 수집에 미치는 영향은 별도 측정해야 한다.

## 5. 실패 지점의 구체적인 재현

대상: `holdout-roi-1-right.png`, SHA256 `71173d65388c27b75716f086b39c8702b0bf818a7db918dc12a694eaa932d2fb`.

1. 실제 영상의 27 위치에 연결 성분 `(x=428,y=282,w=27,h=26,area=314)`가 생긴다.
2. 이 성분은 높이·가로세로 비·채움 비율 필터를 모두 통과한다. 즉 **숫자 성분이 처음부터 전혀 없는 경우가 아니다.**
3. 27의 두 글자가 하나의 성분으로 이어져 있다. 옆 글자는 두 성분 묶음을 만든다.
4. `multi or clusters`에서 단일 성분인 27이 빠지고, 기본 OCR 후보에는 x=284와306의 옆 글자 묶음만 남는다.
5. 후보 전 CLAHE 1.5에서도 27은 `(427,279,29,30)`의 한 성분이며 필터 통과 후 같은 이유로 제외된다.

![기본 후보 선택: 박스는 옆 글자에 있으며 오른쪽 27은 후보에서 빠짐](evidence/footer-preprocessing-study-20260915/results-1789478771166490100/baseline-candidates.png)

위 그림은 저장 ROI의 진단용 후보 표시다. 실시간 미리보기나 손 검출 표시에 사용한 것이 아니다.

추가로 27 위치를 수동 지정한 40×41 crop을 모델에 넣었다. 기본 crop의 두 결과는 빈 문자열/2, 후보 전 CLAHE crop은 2/27이었다. **수동 위치 지정은 자동 후보 검출 성공 증거가 아니며**, 이 crop 조건에서도 두 출력은 일치하지 않았다. 다른 여백·crop이 더 잘 될 가능성은 남는다.

근거: [candidate_trace.py](evidence/footer-preprocessing-study-20260915/candidate_trace.py), [성분 및 수동 crop 결과](evidence/footer-preprocessing-study-20260915/candidate-trace.json).

## 6. 원인 판정과 남은 불확실성

| 항목 | 판정 및 근거 |
|---|---|
| 흐려진 27 후보가 OCR 전에 제외됨 | 해당 ROI의 **확인된 실패 메커니즘**. reachable trigger는 숫자 획 병합과 주변 다중 성분 글자의 공존이다. 필터의 단일 성분 제외가 원인임을 source와 성분 trace로 확인했다. |
| 후보 규칙이 흐린 숫자를 보존하지 못할 위험 | `probable_product_risk`. 바깥쪽에 존재하고 기하 필터를 통과한 실제 번호도 후보 집합에서 사라진다. 위치 우선이라는 기존 목적과 단일 성분 제외의 상호작용을 재검토할 근거다. 기존 severity를 상향하지 않는다. |
| 기존 CLAHE만 강하게 하면 해결 | 지지되지 않음. 적용 시점이 늦으며, 후보 전 적용도 holdout의 정확 판독을 확보하지 못했다. |
| Pi CPU만이 정확도 실패 원인 | 지지되지 않음. 이번 Laptop 저장 ROI에서도 실패를 재현했다. Pi의 별도 지연 문제는 유지한다. |
| 흐림의 최초 발생원 | `insufficient_evidence`. 초점·피사계 심도·흔들림·압축·마스크 영향 등을 이번 잘린 ROI만으로 분리할 수 없다. 현재 opaque native 경로에 1920 축소를 원인으로 단정할 근거도 없다. |
| 원문 결과가 틀렸으면 반드시 쪽 판단 실패 | 성립하지 않음. 현재 raw-token 반복성 계약에서는 안정적인 비정답 문자열도 식별에 쓰일 수 있다. 실제 양쪽·연속 프레임·다른 spread와의 구분을 시험해야 한다. |
| 기존 H1 성공 무효화 또는 현 변경으로 H4 가능 | 둘 다 주장 불가. 과거 live 성공 evidence는 유지하며 이번 저장 ROI 실험은 H1 전체 재수용이 아니다. |

점검한 관련 단위 테스트는 ROI 좌표/마스크 해상도, 정규화, cache, fixed recognizer, 모델 hash 및 runtime 옵션 등을 검증한다. **흐린 실제 두 자리 숫자가 한 성분이 되고 주변 글자는 다중 성분인 사례를 production Paddle 후보 추출과 함께 검증하는 회귀는 확인하지 못했다.** 검색 범위는 `book-scanner/tests`의 Paddle/candidate helper 사용처와 `tests/unit/video/test_page_number.py`, `test_composition_v3a5.py`, `test_paddle_runtime_threads.py`다. 테스트 전반이 아무 품질도 검증하지 않는다는 주장은 아니다.

## 7. 권장 순서와 bounded 후속 작업

### 우선 1 — 후보 생성과 OCR 입력을 분리한 진단

- 같은 프레임 원본→마스크→ROI→이진 성분→제외 사유→후보 순위→각 모델 출력까지 frame ID로 연결한다. 기존 저장 원본과 ROI는 무조건 동일 프레임의 전후쌍이라고 가정할 수 없다.
- 다음 후보는 **약한 CLAHE/C 조정은 위치 탐색용으로 사용하고, OCR에는 보존한 원래 회색조 crop을 주는 방식**이다. 이번 pre-CLAHE는 OCR 픽셀도 바꿨으므로 효과를 둘로 분리할 필요가 있다. C5는 분리한 접근의 부분 예지만 단독으로 완료 조건을 만족하지 않았다.
- 단일 성분을 무조건 되살리는 변경을 바로 적용하지 않는다. 병합된 번호 후보를 보존할 때 옆 글자·단원 숫자·연도를 잘못 선택하지 않는 후보 우선순위가 필요한지 진단한다. 위치 우선 contract와 최대 후보 수를 유지할 수 있는지 먼저 확인한다.
- 완료 조건: 원본이 보존된 같은 입력에서 후보 누락과 crop 내부 판독 실패를 각각 재현·분리하고, 예상 숫자를 강제하지 않아도 개선되는지 증명한다.

### 우선 2 — 미사용 실제 영상으로 안정성 검증

- 26/27뿐 아니라 28/29, 번호가 없거나 가려진 경우, 반복된 footer 문구, 선명/흐림 조건을 포함한다. 현재 12개 ROI로 파라미터를 계속 고르면 과적합 위험이 커진다.
- 정확 숫자 비율, 좌우 원문 쌍 누락/변동, 동일 spread의 일관성, 다른 spread의 문자열 충돌, 기존 reference bank와의 same/different 결과를 따로 기록한다.
- 완료 조건: 정답률 개선만이 아니라 기존 N5/K/8초에서 fresh 서로 다른 프레임을 수집하고 실제 page-change를 결정해야 한다. 고정 ROI 반복이나 synthetic 숫자로 대체하지 않는다.

### 우선 3 — Pi 시간 비용과 실제 경로

- 후보 증가로 모델 호출이 늘지 않는지 Pi에서 측정한다. 필요하다면 위치상 이미 반환 대상이 확정된 이후 불필요한 후보 계산을 생략할 수 있는지 별도 동등성 진단을 한다. 아직 수정안으로 확정하지 않는다.
- 같은 계측 방식으로 현재 설정의 Scanner 첫 artifact → 두 spread → durable V4 receipt → finalize/READY → 실제 읽기 출력 순으로 다시 검증한다.
- 품질 때문에 걸린 실패와 처리 속도 때문에 N5를 채우지 못한 실패를 별도로 유지한다. timeout 연장이나 confidence/N/K 완화로 PASS 처리하지 않는다.

현재 권고는 **CLAHE 즉시 적용이 아니라 후보 단계의 정보 보존을 우선 조사**하는 것이다. 새 architecture layer, OCR 모델 교체, template로 27 강제, broad dependency upgrade는 이 작업 범위에 포함하지 않는다.

## 8. 실행 경계 및 보존 상태

- 실행 환경: Laptop `C:\ASL_OCR_INTEGRATION\.venv-e0b\Scripts\python.exe`; Paddle 3.3.1, OpenCV 5.0.0. 모델 5개 파일 hash는 manifest에 보존했다.
- Laptop recognizer source SHA256: `28f40e925cb0883d184e7f46fbcf929075af3cf04d9da2bff2899b35610b32a6`. Desktop/Pi의 ARM thread 수정본과 파일 전체 hash가 다를 수 있으므로 같은 commit 이름만으로 동일 파일이라 하지 않는다.
- config SHA256: `847f07d87f65789359902b4545168a85e513bc6aeed070bdf984d61ce723e11c`.
- 두 진단 Python process 정상 exit 0. 제품 source/config/firmware/production state 변경 0. 카메라·TLS·인증 설정 변경 0. Laptop D: 접근 0.
- 미리보기는 사용자 요청대로 닫힌 상태를 유지했다. 추가 사용자 관측은 요구하지 않았다.
- 관련 이전 보고서: [Laptop 라이브 재검증](LAPTOP_LIVE_RECHECK_20260915.md), [Pi/Laptop 동일 ROI 비교](PI4_LAPTOP_IDENTICAL_ROI_COMPARISON_20260915.md).
