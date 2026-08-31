# Scanner Video V3-A.4 구현·실험 보고서

상태: **opaque raw-token 후보 확인 / 자료 부족 / production 활성화 안 함**  
실행일: 2026-08-31

## 결론

정확한 페이지 번호를 복원하지 않고 좌우 footer OCR 결과를 opaque identity pair로 비교하는
offline 실험을 구현했다. 같은 고정 영상에서 reference/query 구간을 겹치지 않게 나누고, query
관측 1건만을 1회 시행으로 계산했다. reference×query의 N² 비교는 표본 수로 부풀리지 않았다.

현재 만들 수 있었던 가장 큰 공통 은행은 **100ms cadence, N=5**였다. 이 조건에서 native preview의
selected raw pair는 same-spread query 10건 중 9건이 reference bank와 일치해 `p_same=0.90`,
p30↔p316 양방향 query 10건은 한 번도 충돌하지 않아 관찰 `p_diff=0.00`이었다. `K_diff=0`,
`K_same=1` any-match 판정은 네 relation 모두 오판·UNKNOWN 0이었고, 순차 판정의 relation별
first-decision median은 3 samples, 약 300ms였다.

그러나 different spread는 p30과 p316 두 identity뿐이다. 서로 다른 relation 두 건에서 오중복이
0회였다는 사실의 relation-level 95% zero-error upper bound는 **0.7764**로 매우 넓다. 따라서 결과를
`PROVISIONAL_CANDIDATE_DATA_INSUFFICIENT`로 기록하며 `validated=true`, engine integration,
기본 cadence 변경, 자동 중복 억제 활성화를 하지 않았다.

## 입력과 실행 경계

- 영상: `20260830_133526.mp4`
- SHA-256: `16c57970bc493abcef4a1db0f1917b22956bf5ca1a2ee8b4565fde1f6574e6f8`
- 3840×2160, 2,677 frames, 59.699650767fps
- disjoint blocks
  - p30 reference 690~744, query 756~810
  - p316 reference 2190~2214, query 2226~2250
- frozen records 160, CandidateGate eligible 160, reject 0
- Paddle 3.2.1 CPU, persistent model load 1회, ROI recognition call 640회
- wall time 76.88s, runtime download/network 0
- UVDoc, Document Parser, HTTP/server/Coordinator 호출 0

p30 왼쪽 `30`만 사용자 golden이다. p30 오른쪽 `309`, p316 `316/317`, stable block 경계는
diagnostic label이다. 숫자 의미의 정확도는 이 실험의 판정 목표가 아니다.

## N=5 결과

아래 `same`과 `different`는 각각 두 relation×query 5건, 총 10건이다.

| 입력/방법 | same match | p_same | different collision | p_diff |
|---|---:|---:|---:|---:|
| 1920 semantic key control | 8/10 | 0.80 | 0/10 | 0.00 |
| 1920 selected raw pair | 8/10 | 0.80 | 0/10 | 0.00 |
| 1920 original/CLAHE token-set | 8/10 | 0.80 | 0/10 | 0.00 |
| 1920 footer visual-only | 2/10 | 0.20 | 0/10 | 0.00 |
| 1920 hybrid | 4/10 | 0.40 | 0/10 | 0.00 |
| native semantic key control | 9/10 | 0.90 | 0/10 | 0.00 |
| native selected raw pair | 9/10 | 0.90 | 0/10 | 0.00 |
| native original/CLAHE token-set | 9/10 | 0.90 | 0/10 | 0.00 |
| native footer visual-only | 2/10 | 0.20 | 0/10 | 0.00 |
| native hybrid | 6/10 | 0.60 | 0/10 | 0.00 |
| 기존 full-page VisualGate baseline | 7/10 | 0.70 | 0/10 | 0.00 |

native selected raw의 same Wilson 95% 구간은 `[0.5958, 0.9821]`, different 충돌률 구간은
`[0.0000, 0.2775]`다. block bootstrap은 각각 `[0.8, 1.0]`, `[0.0, 0.0]`이지만 단일 영상의
짧은 연속 구간이므로 후자를 일반화 보장으로 해석하지 않는다. constant-zero different indicator의
보수적 effective N은 1로 보고했다.

독립 시행이라는 참고 가정 아래 `p_same=0.90`, N=5의 모두 불일치 확률은 0.001%이고,
1920의 `p_same=0.80`이면 0.032%다. 연속 프레임은 독립이 아니므로 이 값들은
`independence_reference_only`이며 실측 실패 확률이 아니다.

## stale `30` 가설 확인

native p316 은행의 왼쪽 selected raw는 다섯 표본 모두 현재 번호 `316`이 아니라 페이지 더미에
남은 `30`이었다. 즉 p30 왼쪽과 단일 side token은 실제로 충돌했다. 그러나 spread match는 좌우가
모두 일치해야 한다. p30 오른쪽 `309`와 p316 오른쪽 `317`이 달라 p30↔p316 양방향의 spread
collision은 0/10이었다.

이는 사용자의 “정확한 번호보다 반복되는 공통 포맷을 identity로 쓰자”는 가설을 지지한다. 동시에
한쪽 footer만으로는 안전하지 않으며 좌우 pair 또는 추가 visual contradiction이 필요하다는 증거다.

## 기존 VisualGate 및 ablation 해석

- full-page VisualGate baseline은 p_same 0.70, p_diff 0.00이었다.
- native raw pair는 동일 negative 결과에서 p_same을 0.90으로 높여 이 표본에서는 추가 가치가 있었다.
- original/CLAHE token-set은 selected raw와 같은 결과여서 별도 개선을 보이지 않았다.
- footer visual-only는 p_same 0.20으로 지나치게 엄격했다.
- 현재 hybrid는 visual 조건 때문에 raw-only보다 recall이 낮아 선호되지 않는다.
- native 전면 입력은 1920보다 same match 1건을 복구했지만 p316 왼쪽을 stale `30`으로 읽었다.
  의미 정확도는 나빠졌으나 opaque pair identity는 유지됐다.

visual descriptor 자체의 PC median은 1920 **0.575ms/side**, native **0.754ms/side**로 사전
10ms budget을 통과했다. 최종 동결본의 Paddle recognition median은 각각 **35.97ms/side**,
**46.04ms/side**였다. Pi 4 성능은 `NOT_MEASURED`다.

## 실험 완전성과 부족한 조합

manifest에는 cadence 100/250/500/750/1000ms와 N 3/5/8/10/14/20을 고정했다. 총 330 setting 중
22개만 측정 가능했고 308개는 `NOT_MEASURED_INSUFFICIENT_WINDOW`였다. p316의 각 disjoint block이
25 frames뿐이어서 100ms에서 N=5가 최대였으며, 부족한 N을 프레임 중복·보간·backfill로 만들지
않았다. 따라서 사용자가 예시로 든 N=10은 공식과 단위 테스트만 확인했으며 실제 영상 결과는 아니다.

## 구현 범위

- JSON-safe footer pHash/projection/NCC descriptor와 M0~M4 match
- missing-to-missing match 금지, 좌우 pair 필수, hybrid full-page contradiction
- fixed cadence의 non-backfill bank builder
- 모든 유효 `K_diff < K_same` threshold와 3상태 판정
- first-decision sample/delay, Wilson interval, deterministic block bootstrap
- lag autocorrelation, conservative effective N, zero-error upper bound
- 기존 full-page VisualGate baseline을 같은 bank로 replay
- model/video/manifest hash와 frozen observation provenance

production `video/engine.py`, session, delivery, outbox, HTTP 계약과 Document Parser는 변경하지 않았다.

## 검증

- V3-A.4 focused evaluation: **18 passed**
- frozen capture: **160/160 eligible**, Paddle load count 1, download 0
- replay: **330 settings**, measured 22, insufficient-window 308
- 같은 frozen input/seed 재실행 SHA-256: `b53f474d95765f77a70cd229599ce6bdc9ef2e2012f0e53c71cc001c76b12cd1`
- 전체 Book Scanner 회귀: **264 passed**

## 산출물

- `experiment_inputs/scanner_video_v3a4_footer_identity_manifest.json`
- `experiment_outputs/scanner_video_v3a4_20260831/frozen_footer_observations.json`
- `experiment_outputs/scanner_video_v3a4_20260831/replay_results.json`
- `experiment_outputs/scanner_video_v3a4_20260831/summary.json`
- `tools/run_scanner_video_v3a4_footer_capture.py`
- `tools/run_scanner_video_v3a4_footer_replay.py`
- `tools/summarize_scanner_video_v3a4_footer_identity.py`

`experiment_outputs`는 gitignore 대상이므로 로컬 재현 산출물이며, 보고서와 manifest/tool/test는
버전 관리 대상이다.

## 다음 작업 방향

다음 패킷은 engine 통합이 아니라 **held-out identity 확장 수집**이 우선이다. 최소 여러 다른
spread를 같은 고정 구도에서 각각 reference/query로 촬영하고, 그림자·부분 잘림·오배치 표본도
포함해야 한다. 선택할 1차 후보는 native selected raw 좌우 pair, 100ms, 최대 N=5,
`K_diff=0/K_same=1`이지만 이는 데이터 수집용 provisional 설정일 뿐이다. 새 자료에서 false
duplicate가 한 번이라도 나오면 K_same 상향 또는 full-page contradiction을 재평가해야 한다.

추가 자료 없이 production에 통합하면 현재 0/10 collision을 과대해석하게 된다. Pi 4 지연/RSS,
실제 page-turn 직후 은행 전환, ACK된 reference cache의 수명과 전원 복구는 모두 미검증이다.
