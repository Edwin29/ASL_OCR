# 페이지 번호 인식 시점 paired 실험 보고서

상태: **원인 분리 완료 / 보수적 dual-resolution fallback 가능성 확인 / production 변경 보류**  
실행일: 2026-08-31

## 결론

페이지 번호 인식을 `현재 1920 preview`, `원본 해상도 preview`, `seam-conservative crop 후`,
`seam-conservative crop + UVDoc 후`의 네 시점에서 같은 프레임·같은 ROI 비율·같은 Paddle 모델·
같은 confidence/variant-agreement 조건으로 비교했다.

누락의 주원인은 UVDoc 부재가 아니었다. p30 frame 780의 오른쪽 `309`는 1920 축소 과정에서
연결요소가 숫자열로 묶이지 않아 Paddle에 올바른 후보가 전달되지 않았다. 원본 해상도에서는
`309`가 하나의 후보로 형성되어 완전 키가 복구됐다. 그러나 원본 해상도를 항상 사용하면 p316
frame 2190·2220에서 현재 페이지 `316`보다 바깥에 보이는 페이지 더미의 이전 번호 `30`을 먼저
선택해 `30/317`이라는 잘못된 complete key를 만들었다.

따라서 `preview_native` 전면 전환은 채택할 수 없다. 반면 1920에서 이미 관측된 쪽은 보존하고,
관측되지 않은 쪽만 native ROI로 다시 읽는 보수적 fallback은 이 표본에서 exact spread를
5/8에서 6/8로 늘리면서 잘못된 complete key를 만들지 않았다. 이 결과는 다음 구현 후보를
뒷받침하지만 표본과 golden이 부족하므로 아직 production 설정을 바꾸지 않는다.

UVDoc 뒤 번호 인식은 개선되지 않았다. p30에서 왼쪽 golden `30` 정답은 2/5로 감소했고,
frame 720·750에서는 copyright/footer 연결요소가 먼저 선택되어 conflict가 됐다. 번호 식별을
UVDoc 뒤로 일괄 이동하는 방안은 현재 근거로 기각한다.

## 고정 조건

- 영상: `20260830_133526.mp4`
  - SHA-256 `16c57970bc493abcef4a1db0f1917b22956bf5ca1a2ee8b4565fde1f6574e6f8`
  - 3840×2160, 약 59.70fps
- 표본: p30 진단 구간 720, 750, 765, 780, 810; p316 진단 구간 2190, 2220, 2250
- recognizer: 로컬 `en_PP-OCRv5_mobile_rec`, asset 5개 SHA-256 검증, CPU, load 1
- bottom ROI: 좌측 바깥 35%, 우측 바깥 35%, 하단 20%
- confidence 0.62, original/CLAHE agreement 2, 자리수 1~4
- UVDoc: 기존 checkpoint, bilinear, CPU, load 1
- 단계별 threshold 재조정 없음

p30 왼쪽 `30`만 명시적인 사용자 golden으로 센다. p30 오른쪽 `309`와 p316의 `316/317`,
stable-run 경계는 기존 라벨 파일의 diagnostic 지위를 유지한다.

## 집계 결과

| 인식 입력 시점 | p30 왼쪽 `30` golden | p30 spread exact* | p316 spread exact* | 전체 complete | 전체 exact* | wrong complete* | 중앙 OCR 시간 |
|---|---:|---:|---:|---:|---:|---:|---:|
| preview 1920 (현재) | 4/5 | 3/5 | 2/3 | 5/8 | 5/8 | 0 | 65.9ms |
| preview native | 4/5 | 4/5 | 0/3 | 6/8 | 4/8 | 2 | 99.0ms |
| seam crop 후 | 3/5 | 3/5 | 0/3 | 5/7 | 3/7 | 2 | 93.3ms |
| seam crop + UVDoc 후 | 2/5 | 2/5 | 0/3 | 4/7 | 2/7 | 2 | 94.1ms |
| 1920 + missing-side native fallback | 4/5 | 4/5 | 2/3 | 6/8 | 6/8 | 0 | 106.5ms** |

\* 오른쪽 p30 및 p316 번호가 diagnostic label이므로 검증 완료 지표가 아니다.  
\** frozen paired 결과에서 계산한 조건부 실행 추정치다. 모든 프레임에 native를 호출한 실측값이
아니며 Pi 4 지연으로 일반화하지 않는다.

2250은 preview 평가는 가능했지만 seam-conservative extraction이 `PAGE_NOT_FOUND`여서 crop/UVDoc
집계의 분모가 7이다. 이는 번호 인식 개선 여부와 별개로 V2 extraction fallback 표본으로 남긴다.

## 프레임별 해석

### p30

- 720: 현재 경로는 `30/309` complete. crop 후도 complete이나 UVDoc 후 왼쪽은
  original/CLAHE가 `244` 계열과 다른 값으로 갈려 conflict.
- 750: 현재 경로는 complete. seam crop 왼쪽은 `7` conflict, UVDoc 왼쪽은 `2441` conflict.
- 765: 네 시점 모두 `30/309` complete.
- 780: 현재 1920은 왼쪽 `30`만 partial. 오른쪽 ROI 자체는 존재하지만 숫자 후보가 잘못 분해되어
  Paddle numeric prediction이 없었다. native/crop/UVDoc은 모두 `30/309` complete.
- 810: 현재 왼쪽은 raw `30`이 한 variant에서만 유효해 conflict, 오른쪽은 숫자 prediction 없음.
  native는 오른쪽 `309`를 복구하지만 왼쪽이 raw `4` conflict라 spread는 여전히 conflict.

### p316 진단 구간

- 2190·2220: 1920은 `316/317` complete. native/crop/UVDoc은 왼쪽 페이지 바깥에 함께 보이는
  이전 `30`을 우선해 `30/317` wrong complete.
- 2250: 1920은 왼쪽 `316`만 partial. native도 오른쪽을 복구하지 못하며, crop 자체는
  `PAGE_NOT_FOUND`.

## 원인 판정

1. **1920 누락은 주로 candidate locator/scale 문제다.**
   frame 780 오른쪽은 mask와 ROI 생성에는 성공했다. 1920 ROI에서는 `309`가 하나의 숫자열 후보로
   구성되지 않았고, native ROI에서는 구성됐다. 따라서 이 건을 Paddle 언어 인식 능력 부족이나
   UVDoc 부재로 설명할 수 없다.
2. **native 전환의 실패는 페이지 더미와 현재 페이지의 소유권 문제다.**
   고해상도 p316 왼쪽 ROI에는 이전 페이지 `30`과 현재 페이지 `316`이 동시에 후보로 남는다.
   기존 “물리적 바깥쪽 우선” 규칙이 `30`을 선택한다. 해상도 증가는 recall과 함께 stale footer
   recall도 높였다.
3. **crop/UVDoc은 번호 후보의 의미적 소유권을 해결하지 않는다.**
   seam-conservative crop은 본문 보존용이며 아래에 노출된 page stack의 footer를 항상 제거하지
   않는다. UVDoc은 기하 보정기이지 페이지 번호 후보 선택기나 화질 복원기가 아니다.
4. **variant conflict가 실제로 존재한다.**
   frame 810의 왼쪽 current path와 frame 720·750의 UVDoc 왼쪽은 original/CLAHE 두 판독이
   합의하지 못했다. 이를 단순 NOT_OBSERVED와 분리해 기록했다.

## 다음 구현 후보

우선순위는 `missing-side native fallback`이다.

1. 1920 preview로 양쪽을 먼저 판독한다.
2. complete이면 native 호출 없이 종료한다.
3. NOT_OBSERVED인 쪽만 원본 해상도 ROI로 재판독한다.
4. 1920에서 OBSERVED인 값을 native 결과로 덮어쓰지 않는다.
5. 기존 conflict를 native 한 번으로 observed로 승격하지 않는다.
6. fallback 결과도 temporal K회 합의와 visual fallback을 통과해야 하며,
   `allow_number_only_duplicate=false`를 유지한다.

이후 held-out 표본에는 현재 페이지 번호와 페이지 더미의 이전 번호가 동시에 보이는 장면을
의도적으로 포함한다. 후보의 x 위치만으로 소유권을 판단하지 말고, 현재 페이지 하단 contour와의
접촉, baseline 대비 양쪽 번호의 변화 일관성, 연속 프레임의 같은 후보 궤적을 보조 근거로 평가한다.

## 산출물과 검증 한계

- 재현 도구: `tools/run_page_number_stage_paired_experiment.py`
- 구조화 결과: `experiment_outputs/page_number_stage_paired_20260831/summary.json`
- 각 frame/stage/side별 ROI, adaptive binary, 후보 overlay, seam crop, UVDoc 이미지 저장
- 실행 runtime: Paddle 3.3.1, Torch 2.13.0+cpu, OpenCV 5.0.0
- 전체 paired 실행 wall time 13.2초(영상 frame decode와 이미지 저장 포함)

이 실험은 한 영상 8개 프레임의 원인 분석이다. Raspberry Pi 4 처리 시간, 다른 책/조명/그림자,
사람 확인 different-page negative, temporal false-duplicate rate는 검증하지 않았다. 따라서
recognizer의 `validated=false`, 번호-only duplicate suppression 비활성, 기존 visual fallback을
그대로 유지한다.
