# H1 Camera/Fresh Run — 2026-09-08

Run ID: `h1-camera-fresh-20260908-101447`

이 기록은 승인된 1A / 2B 절차를 따른다. 공통 source, server, device, audio, camera 및 completion 계약은 `DEMO_RUN_COMMON_MANIFEST_20260908.md`를 상속한다.

## 실행 원칙

- Android IP Camera만 사용하며 webcam fallback은 사용하지 않는다.
- Scanner의 N/K/identity/duplicate threshold와 8초 collection 값은 변경하지 않는다.
- camera 인증값은 출력하거나 evidence에 저장하지 않는다.
- 별도 실패가 발생해도 독립적인 후속 단계는 계속한다.
- 선행조건 실패로 수행할 수 없는 단계는 실패 경계와 생략 사유를 기록한다.
- console control은 DeviceApplication/Coordinator 이후 의미를 보존하지만 STM/GPIO/V3 packet 경계를 증명하지 않는다.

## 단계와 현재 상태

| 단계 | 목적 | 상태 | evidence |
|---|---|---|---|
| C1 | strict source snapshot read-only probe | PASS (3/3) | Laptop run `evidence/camera-probe.json`; Desktop mirror `camera-probe.json` |
| C2 | preview-enabled acquisition/page-change timing | COMPLETE — liveness failure observed | production console timing + `footer-liveness-analysis.json` |
| H1-1 | pages 26/27 same-frame spread → durable V4 receipt | PASS | sequence 1, HTTP 201, outbox `acked` |
| H1-2 | pages 28/29 page-change → durable V4 receipt | FAIL | valid 5 timeout unknown 및 반복 valid 4 timeout; sequence 2 없음 |
| H1-F | console CONFIRM LONG → fresh READY revision | SKIP | sequence 2 durable receipt 선행조건 실패; incomplete finalize 금지 |
| H1-A | first receipt guidance and actual audio completion | PARTIAL | catalog 및 page-change guidance 실제 청취; `spread_sent` cue 직접 청취 확인 없음 |

## 사용자 관측 체크포인트

Interactive production process는 Windows session 2에서 실행됐고 사용자가 종료 절차를 완료했다. Product process 잔류는 없으며 sequence 1의 receipt/draft는 보존했다. 이 문단의 과거 operator 단계는 아래 결과 기록으로 대체한다.

## 결과 기록

- C1은 2026-09-08T01:17:24Z부터 01:17:31Z까지 수행했다. 현재 authoritative import에서 `HttpSnapshotCameraSource`를 사용했다.
- 세 frame 모두 4000×3000으로 decode되었고 1.859초, 1.344초, 1.360초가 걸렸다. 서로 다른 frame ID와 pixel hash를 얻었다.
- 각 frame에서 JPEG decoder가 `Invalid SOS parameters for sequential JPEG`를 출력했다. decode 및 최소 해상도 검증은 성공했으므로 H1 절차는 계속한다. 경고의 image-content 영향은 아직 `insufficient_evidence`다.
- camera probe는 image 저장, upload 및 serial packet을 수행하지 않았다.
- Interactive production entrypoint는 2026-09-08T01:21:25Z에 Windows interactive session 2에서 시작되었다. Python process와 새 isolated delivery SQLite 생성을 확인했다.
- PowerShell 5 transcript에는 launcher 문구만 보이고 Python native stdout은 아직 포착되지 않았다. 사용자가 보는 console feedback과 server/outbox evidence를 함께 사용하며, 이 관측 제약 때문에 capture 절차를 중단하지 않는다.
- 사용자는 pages 26/27이 선명하게 보이지만 위치 조정 안내가 반복되었고, 가림 등 조건 변화에 따라 안내 종류가 적절히 바뀌었다고 관측했다. 이는 candidate hard-gate 및 reason-specific guidance의 정상 동작으로 분류했다.
- 물리 framing을 한 번 조정한 뒤 sequence 1이 생성되었다. `phone-snapshot-00000146` 한 frame에서 L/R inventory를 포함한 9개 파일, 5,738,682 bytes가 구성되었다. V4는 첫 시도에 HTTP 201과 receipt `spread-receipt-3cefb9a9719d9c9eb92e4dd811ed1510`를 반환했고 outbox가 `acked`가 되었다.
- pages 28/29 전환 후 sequence 2는 아직 생성되지 않았다. 기존 sequence 1 receipt는 유지된다. page-change identity 세부 JSON은 operator console 관측이 필요하다.
- Operator는 pages 28/29가 선명하고 spread 1과 같은 각도임에도 engine state가 `waiting_for_page_change`에 머물며 위치 조정 안내가 반복된다고 확인했다. Source상 이 상태의 위치 안내는 `_poll_opaque_page_change()`가 candidate retry reason을 받아 해당 frame을 identity 및 visual-change 판단에 부적격으로 처리할 때 발생한다. 따라서 현재 first failing boundary는 transport가 아니라 page-change candidate eligibility다.
- 절차를 중단하지 않고 accepted baseline을 다시 제시한 뒤 실제 page-turn을 관측시키는 bounded 추가 절차를 적용한다: pages 26/27 재제시 및 정지 → pages 28/29로 눈에 보이게 전환 → 손 제거 후 정지. Threshold와 timeout은 유지한다.
- 추가 절차에서 page-turn 중 손은 `content_occluded`로 검출됐고 대응 system cue가 cache hit → playback started → playback completed로 끝났다. Camera acquisition, guidance classification 및 실제 audio lifecycle은 이 구간에서 통과했다.
- Page-change footer identity는 여러 frame에서 valid observation 1개만으로 `same`을 반복 결정했다. 이후 한 collection은 valid 3개에서 8초 timeout `unknown`, 다음 collection은 valid 5개까지 도달했다. 후자의 terminal decision은 operator excerpt에 포함되지 않았고 sequence 2도 아직 없다.
- `recognition_processing_ms`는 약 512–838ms, 관측된 `effective_interval_ms`는 약 1.656–3.281초였다. 따라서 전 구간을 단순 camera transport 실패로 분류할 수 없다. 5개 valid token pair의 novel consensus가 충족되지 않았는지 확인할 terminal event 또는 isolated ROI/token evidence가 필요하다.
- 반복되는 `InsecureRequestWarning`은 Android camera profile에 한정된 명시적 self-signed TLS 허용과 일치하며 실제 snapshot transport는 성공했다. Console noise 관측 후보로 기록하되 인증/TLS 정책은 변경하지 않는다.
- Terminal evidence가 추가됐다. Page-change collection은 valid observation 5/5에 도달했지만 `decision=unknown`, `timed_out=true`로 끝났다. 이어지는 collection도 valid 2 또는 3에서 timeout됐다. Sequence 2는 생성되지 않았다.
- 2026-09-08T01:49:14Z에 한 번의 isolated read-only footer ROI 진단을 추가했다. Frame은 4000×3000, acquisition 1.797초였고 candidate retry reason은 없었다. Page pair, edge margin, clipping, illumination, blur 및 obstruction gate는 모두 통과했다.
- 같은 frame의 M1 preview footer 결과는 left/right 모두 `not_observed`, raw text 없음, variant agreement 0이었다. 저장된 source에는 실제 pages 28/29가 보이며 right ROI에는 `29`, left ROI에는 매우 작은/faint footer 영역이 보인다. First failing boundary는 page-change identity collector 이전의 footer recognition으로 좁혀졌다.
- 현재 evidence만으로 crop geometry와 recognizer sensitivity 중 하나를 단독 root cause로 확정할 수 없다. Camera transport, candidate visibility, page-turn detection, guidance audio 및 V4 sequence 1 receipt는 competing cause에서 제외된다.
- 실행 중 process의 warning만 제거하려면 재시작이 필요하므로 현재 run에는 적용하지 않는다. 후속 run에서 `HttpSnapshotCameraSource`의 명시적 insecure camera request 범위에 한정된 warning suppression을 local tooling correction 후보로 둔다.
- 책을 frame에서 더 크게 보이도록 물리 조정한 뒤에도 여러 collection이 valid 4에서 `unknown/timed_out=true`로 끝났다. 이 구간의 recognition processing은 약 570–1,392ms, effective interval은 약 1.843–3.172초였고 footer guidance는 최대 123 stable samples/148.11초까지 지속됐다.
- 따라서 현재 production8초와 실제 live acquisition/recognition cadence는 N=5 admission에 반복적으로 부족하다. 별도로 한 cycle은 valid 5에서도 consensus 실패가 있었으므로 시간 부족만이 유일 원인은 아니다.
- Sequence 2 receipt가 없어 `CONFIRM LONG`과 fresh READY 검증은 prerequisite failure로 생략한다. Sequence 1의 durable receipt와 server artifact, isolated draft state는 삭제하지 않는다.
- 후속 추가 절차는 production 값을 바꾸지 않는 30초 진단 전용 footer collection이다. Pages 26/27 reference와 pages 28/29 query의 raw token/status/ROI hash를 같은 source/model에서 수집해 latency-only와 crop/recognizer instability를 분리한다.
- **Pipeline-fidelity correction 1:** 첫 30초 진단과 isolated/scaled ROI replay는 candidate analyzer의 640px `gray_preview`를 M1에 직접 전달했다. 해당 complete pair 0, empty candidate region 및 scaled misrecognition은 `test_harness_artifact`이며 product root cause 근거에서 제외한다. 파일은 삭제하지 않고 보존한다.
- **Pipeline-fidelity correction 2:** 다음 30초 비교는 `_page_number_preview_inputs()`를 사용했지만 maximum dimension을 1920으로 고정했다. 실제 run의 `input_stage=preview_native`에서 production engine은 `max(frame.payload.shape[:2])`, 즉 4000을 전달한다. 따라서 1920 비교의 26/27 `14/14` 및 28/29 token 분포는 lower-resolution comparison으로만 보존하고 production-input 동일성 주장에서 제외한다.
- 두 번째 진단 시도는 evidence code가 `OpaqueFooterTokenPair.left_raw`라는 존재하지 않는 필드를 읽어 `AttributeError`로 종료했다. 이는 `pair.value`로 수정하고 Laptop interpreter에서 contract smoke PASS 후 재실행했다. Product defect나 JPEG SOS 경고에 의한 종료가 아니다.
- 저장된 두 4000×3000 frame을 production-native 4000 경로로 replay했다. Reference 첫 frame은 `2441|27`, query 첫 frame은 정확한 `28|29`였다. 둘 다 candidate retry reason은 없었다. 한 frame씩만 저장됐으므로 이 결과로 temporal consensus를 주장하지 않는다.
- 실제 production source wrapper와 같은 `ThreadedPreviewCameraSource` + `HttpSnapshotCameraSource`, native 4000 M1을 사용한 query-only 30초 추가 진단은 11 frame, eligible 10, complete pair 7을 얻었다. Pair는 `28|29` 6회, `1|0` 1회였다. 그러나 첫 정확한 `28|29`는 11.406초에 나타났고 최초 8초에는 complete pair 1개, exact pair 0개였다.
- 이 추가 진단은 production camera/source scheduling과 recognizer input을 보존하지만 `SampledFrameEngine` collector/reset 및 원래 process는 실행하지 않았다. Production console의 repeated 8초 timeout과 함께 사용해 liveness mechanism을 진단하며, 단독 full pipeline evidence로 쓰지 않는다.
- Production console에서 얻은 valid count, timeout, decision과 outbox sequence 1/2 상태는 실제 production 경로이므로 유효하다. Fixed 8초 attempt가 실제 acquisition/native OCR 안정화보다 먼저 끝나고 collector를 reset한다는 runtime-profile incompatibility는 확인됐다. N/K/identity/duplicate threshold와 production 8초 값은 이번 run에서 변경하지 않았다.

## 최종 판정

- First failing boundary: `WAITING_FOR_PAGE_CHANGE`의 opaque footer identity admission. `PAGE_CHANGED`, sequence 2 artifact, V4 receipt로 진전하지 못했다.
- 분류: `probable_product_risk_with_confirmed_runtime_profile_incompatibility`, 기존 P1 유지. Camera outage, upload, server receipt, candidate visibility 또는 audio lifecycle가 이 경계의 first cause는 아니다.
- Violated invariant: 고정 Android source와 선정 demo pages에서 선명하고 정지한 새 spread가 N/K/duplicate 계약을 유지한 채 유한 시간 안에 page-change를 통과해야 한다.
- Existing test gap: deterministic/fast observation tests는 실제 snapshot cadence, native M1 변동, page-turn 후 안정화, 8초 timeout/reset 반복을 하나의 engine scenario로 다루지 않는다.
- Root mechanism은 bounded하게 확인했지만 수정 설계는 아직 하나로 확정하지 않는다. 별도 finite acquisition/readiness budget과 identity-consensus budget 분리, 또는 동등한 bounded liveness 규칙을 recorded timing/token replay로 먼저 비교해야 한다.
- 8초 값을 단순 연장하거나 N/K/identity/duplicate threshold를 완화하는 수정은 이 evidence에서 승인하지 않는다. 1920 input 전환도 초기 8초 consensus를 보장하지 않았으므로 단독 fix로 채택하지 않는다.
- H1-F는 prerequisite 부재로 의도적으로 생략됐다. Fresh READY revision은 생성되지 않았으며 H4 진입은 계속 BLOCKED다.
- 이번 camera/fresh H1 실행 중 product source modification count는 **0**이다. 추가·수정 파일은 run-local diagnostic/evidence/report뿐이다.
- 후속 구현 전 packet: [H1 page-change liveness diagnostic/design](work-packets/H1_PAGE_CHANGE_LIVENESS_DESIGN_20260908.md). Recorded sequence replay로 local lifecycle correction과 architecture/config change 필요성을 먼저 분기한다.
- 독립 고비용 검토에서 실제 `SampledFrameEngine`에 N5/K1/K0/8000ms를 유지한 slow exact stream과 recorded timing을 주입해 timeout별 partial observation 폐기와 무진전을 재현했다. 동시에 opaque SAME 뒤 stale visual-change latch가 false `PAGE_CHANGED`를 만들 수 있는 별도 local defect를 확인했다. 상세 범위와 correction 순서는 [H1 및 physical UP 독립 검토](H123_UP_AND_H1_HIGH_COST_REVIEW_20260908.md)에 기록한다.
