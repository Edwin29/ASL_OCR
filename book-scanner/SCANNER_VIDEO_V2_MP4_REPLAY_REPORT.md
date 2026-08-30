# Scanner Video V2 실제 MP4 replay 보고서

상태: **V2 수동 안정 프레임 2/2 성공 / V1 자동 선택 검증 실패**
실행일: 2026-08-30

## 결론

Drive에서 확보한 실제 4K 영상의 손 없는 정지 프레임을 production
`seam-conservative + UVDoc bilinear + atomic bundle` 경로로 처리했다. 2개 spread 모두
좌우 artifact 생성과 commit에 성공했으며 네 페이지 동안 모델은 한 번만 로드됐다.

그러나 이 결과는 자동 전송가능 판정 성공이 아니다. 기본 V1 후보 판정은 영상의 모든 표본을
거부했고, 단순 threshold 완화는 정지한 손이 페이지를 가린 프레임을 수락할 수 있어 채택하지
않았다.

## 입력 무결성

- 파일: `20260830_133526.mp4`
- 크기: 242,882,956 bytes
- SHA-256: `16c57970bc493abcef4a1db0f1917b22956bf5ca1a2ee8b4565fde1f6574e6f8`
- 영상: 3840×2160, 59.699650767 fps, 2,677 frames, 44.841 seconds

OpenCV 임의 seek가 후반부에서 실패했기 때문에 실험 도구는 모든 요청 프레임을 한 번의 순차
decode로 먼저 확보한다. 이는 실제 `VideoFileCameraSource`의 순차 sampling과도 일치한다.

## V1 재생 판정

500ms 간격 90개 표본의 기본 결과는 stable 0건, hard reject 90건이었다.

- 후보 직접 사유: `OUT_OF_FRAME` 82, `PAGE_NOT_FOUND + SEAM_FAILED` 8
- `OUT_OF_FRAME`을 진단으로만 취급한 재평가: stable 0
- rolling assessment: `PAGE_MOVING` 40, `HAND_OR_PAGE_TURN` 35,
  `PAGE_NOT_FOUND + SEAM_FAILED` 13, warm-up 2

외곽 접촉 오탐은 페이지가 실제로 잘린 것이 아니라 foreground mask가 검은 천의 주름과 연결돼
preview 상·하단까지 번진 결과였다. 모션 임계값을 0.2로 완화한 탐색에서는 21개 안정 판정이
생겼지만, 19.60초·23.12초·32.66초 등의 정지 손 가림도 일부 포함됐다. 이 sweep은 결함 확인용일
뿐 production 설정 변경 근거로 사용하지 않는다.

## V2 결과

| timestamp | frame | 페이지 | 상태 | 총 처리 | bundle | load count |
|---:|---:|---|---|---:|---:|---:|
| 13.065s | 780 | p30 / p309 | PREPARED | 2,875.657ms | 2,794,024 bytes | 1 |
| 37.186s | 2220 | p316 / p317 | PREPARED | 1,032.237ms | 2,665,800 bytes | 1 |

두 bundle 모두 다음을 만족했다.

- 좌우 `source_frame_id` 동일
- seam/mask/crop/UVDoc/diagnostics/manifest 존재
- 좌우 UVDoc decode 및 hash 검증 성공
- atomic ready commit 성공
- silent uncorrected fallback 없음

육안상 네 페이지 본문은 읽을 수 있고 좌우가 분리되었다. 다만 rectangular crop에는 inner edge의
제본부나 맞은편 페이지가 좁게 남을 수 있고 UVDoc 출력은 원본 crop보다 부드러워진다. 이 두
현상이 Document Parser OCR에 미치는 영향은 이번 V2 범위에서 재측정하지 않았다.

## 남은 문제

1. mask frame 접촉을 곧바로 `OUT_OF_FRAME`으로 만드는 규칙을 물리 잘림 근거와 분리한다.
2. 전역 노출 변화·미세 진동에 강한 motion metric을 별도 자료로 검증한다.
3. 움직임이 멎은 손도 본문 가림으로 거부할 수 있는 obstruction 신호를 추가한다.
4. 위 세 조건을 만족한 뒤 이 영상에서 자동 선택된 frame을 같은 V2 경로로 다시 replay한다.
5. Document Parser preflight/전송 및 OCR 비교는 후속 패킷에서 수행한다.

세부 hash, bbox, 처리시간과 bundle 경로는
`experiment_outputs/scanner_video_v2_mp4_20260830_forward_decode/summary.json`에 있다.
