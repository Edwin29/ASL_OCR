# Pi4 Scanner 지연 분리 진단 — 2026-09-15

## 결론

후속 [동일 ROI·스레드 비교](PI4_LAPTOP_IDENTICAL_ROI_COMPARISON_20260915.md)에서 같은 lossless 입력/모델/추론 crop을 검증했다. 좌우7회 합계 중앙값은 Laptop 기존0.422초, Laptop1thread0.586초, Pi1thread2.227초였다. Pi는 같은1thread Laptop보다도3.80배 느려 스레드 제한만으로 설명되지 않는 실행 환경 성능 차이를 확인했다. 우측 conflict는 세 조건에서 같았으며 성능 문제와 분리한다.

현재 배치와 ARM 단일 스레드 실행에서 **미리보기의 중복 snapshot 요청을 없애는 것만으로 연속 판정 문제가 해결된다는 근거는 없다.** Pi만 카메라를 읽는 구간에서도 표본 처리 중앙값은 약4.97초였다. 기존 실제 Scanner 검사에서는 N5/8000ms를 유지한 채 90초 동안 identity timeout4회, 첫 local artifact0개였다. 충돌 회피와 촬영 liveness는 별도 결과다.

이번 단계는 제품 수정 없이 진단 코드만 추가했다. V4 업로드/receipt 주입/음성/STM/서보 출력 없음. H4는 미통과다.

## 실행 경로와 계측

Pi의 기존 config, `create_snapshot_source`, default Scanner factory의 모델/provider, production candidate analyzer 및 native preview 전처리를 사용했다. HTTP fetch/decode, analyzer, 전처리, 번호 provider를 시간 wrapper로 감쌌고 원래 결과/예외는 변경하지 않았다. network residual은 fetch+decode에서 decode를 뺀 값으로 인증·body 수신·검증 overhead를 포함한다. 순수 네트워크 시간이라고 부르지 않는다.

미리보기 동시 요청 A → Pi 단독 요청 B → 동시 요청 A2, 각5개 표본으로 순서 효과를 일부 확인했다. 각 구간 별 프로세스/모델 초기화가 있으며 표본은 동일 픽셀이 아니다. 작은 표본으로 통계적 동등성을 주장하지 않는다. JPEG 첫 원본은 각 run에 보존했다.

| 중앙값 | A: 동시 요청 | B: Pi 단독 요청 | A2: 동시 요청 복귀 |
|---|---:|---:|---:|
| 수신 전체(해독 포함) | 1.768초 | 1.724초 | 1.931초 |
| JPEG 해독 | 0.228초 | 0.231초 | 0.226초 |
| 수신 residual | 1.495초 | 1.453초 | 1.660초 |
| candidate 분석 | 0.205초 | 0.206초 | 0.206초 |
| preview 전처리 | 0.022초 | 0.022초 | 0.022초 |
| 양쪽 번호 provider | 2.792초 | 2.831초 | 2.850초 |
| 표본 단계 합계 | 4.802초 | 4.965초 | 5.147초 |
| 26/27 complete | 0/5 | 1/5 | 2/5 |

각 열의 중앙값끼리 더한 값과 합계 중앙값은 다를 수 있다. 모든15개 표본은 가로4000×3000, source fetch attempt1이었다. 경고 존재와 별개로 각 프로세스 exit0, native crash 없음. preview JPEG export 약20ms는 단계 합계에서 제외했고 relay의 CPU/network 부하는 남아 있으므로 B를 완전히 무부하인 실행으로 부르지 않는다.

## 미리보기 가시성과 격리 근거

- Laptop 진단 `pi-focus-20260915-05/show_relay_capable_preview.py`, 수동 task `ASL_Pi_FocusPreview_20260915_05`. 자동 종료 시간 제한 없음; 사용자 Q/Esc/창닫기 또는 해당 진단 stop marker로 종료.
- A/A2: Laptop 자체 snapshot 수신. B: 수신 worker stop 및 실제 thread 종료를 확인한 후 `external-ready.json` 기록(12:38:08 UTC). Pi가 받은 프레임의 비례 축소 JPEG를 Desktop의 SSH relay로 Laptop 창에 전달했다. 카메라 입력/인식 이미지는 native 크기 그대로다.
- B의 화면은 Pi 표본 시각과 수신 후 경과 시간을 표시한다. 원래 camera stream과 동일한 갱신률을 주장하지 않는다. 12회 relay 전송 완료 후 독립 미리보기로 복귀했으며 heartbeat 갱신을 확인했다.
- 쪽 표시 빨간 박스는 계속 제거한 상태다. production 가림 감지 annotation은 유지한다. 별도 LEFT/RIGHT footer 창은 독립 수신 모드에서 표시한다.

## 실제 인식 호출 분해 및 replay 한계

1. 저장 JPEG2개를 다시 분석한 profile에서는 live 때와 다른 후보가 선택되어 `not_observed`였다. 재인코딩·candidate/ROI 재구성의 영향이 분리되지 않았으므로 이 replay의 결과나1.5초대 시간을 live 인식과 등치하지 않는다. `saved-footer-call-profile-1789476101856624205.json`을 그대로 보존한다.
2. 추가 실제 프레임1개에서 production `_predict`를 직접 계측했다. provider 약3.000초 중 모델 호출6회, 합계 약2.321초였다. 첫 호출 약497ms, 후속 호출 약364~366ms. left26 observed, right conflict. 원본은 재검증용 PNG로 보존했다. 모델 호출이 지연의 큰 부분임을 이 표본에서 확인했다.
3. `page_number_recognizer.py:335`의 `recognize()`는 위치 순위가 정해진 최대4개 영역에 대해 original/enhanced 각1회씩 계산하고, 마지막에 첫 후보를 반환한다. 뒤 후보의 계산이 정상 반환값에 사용되지 않는 경우가 있어 국소 최적화 후보지만, 이번 계측만으로 불필요한 호출 수 또는 모든 입력의 동등성을 확정하지 않는다. 예외 발생 경로도 비교해야 한다.

## 실제 collector와의 관계

- `engine.py:506`의 `_poll_opaque_identity`는 현재 clock으로 timeout을 확인한 뒤 수신→analyzer→provider를 직렬 수행한다. 750ms sampling 설정이 연산 시간이 긴 상황에서750ms 완료 주기를 보장하지 않는다.
- `opaque_identity.py:151`의 `decision()`은 새 reference가 없는 경우 유효 관측N5와 다수 일치 조건이 필요하고, `:213`에서8000ms 경과를 판정한다. 같은 영상/관측 재사용을5회 증거로 세지 않는다.
- 실제90초 검사의 유효 관측 수는 각 timeout 시1,2,1,0이었다. 이번 A/B에서는 중복 요청이 없어도4.23~6.13초/표본이었다. 따라서 현재 관측 속도가5개 수집에 불충분하다는 판단을 뒷받침한다. 단, A/B는 실제 collector를 다시 실행한 것이 아니며 root cause를 단일 함수/카메라로 확정하지 않는다.
- 별도 환경 spot check: Pi51.1°C, `get_throttled=0x0`, ondemand, 현재1800000kHz. 전체 run 동안 thermal 상태를 연속 관측한 것은 아니다.

## 우선순위와 다음 bounded packet

1. **인식 결과를 보존하는 연산량 감소 후보 조사**: 실제 lossless frame/ROI를 고정해 후보 순위와 두 variant 판단을 보존하면서 후순위 계산의 정상 결과/예외 차이를 비교한다. 승인 전 production 조기 반환이나 batching을 적용하지 않는다. N/K/confidence/variant/duplicate 기준 완화 금지.
2. **수신과 분석의 중첩 가능성 평가**: 최신 프레임1개만 유지하는 기존 preview acquisition 구조를 Pi에서 재사용할 수 있는지 lifecycle/clock/frame identity 기준으로 확인한다. 새 architecture layer나 worker를 먼저 구현하지 않는다. 단독으로 수신을 중첩해도 남는 인식 비용을 함께 계산해야 한다.
3. **우측 번호 안정성**: lossless 동일 ROI에서 후보 위치/variant 불일치를 재현한다. 더 많은 앵글 조정이나 낮은 confidence 통과를 기본 해결책으로 삼지 않는다. 측정용 저장 JPEG 결과 차이는 harness fidelity 한계로 보존한다.
4. 최소 수정 후보가 승인·검증된 후 실제 Scanner first artifact → production 두 spread durable receipt → fresh READY → Pi 물리 입력/AUX/점자 → 공동 전원/부팅 검증 순으로 진행한다.

성공 기준은 timeout 연장이나 N축소가 아니라 기존 criteria 아래 실제 서로 다른 프레임에서 유효 관측이 모여 artifact가 만들어지는 것이다. 수정이 새로운 스케줄링 구조를 요구하면 변경 범위·기존 contract·rollback을 먼저 보고한다.

## Evidence

[계측 요약](evidence/pi-ocr-thread-correction-20260915/stage-timing-summary.json), 각 `stage-timing-*` run의 manifest/samples/first image 및 원시 log, `laptop-preview05-external-ready.json`, `laptop-preview05-heartbeat.json`, `probe_stage_timing.py`, `probe_live_predict_timing.py`, `profile_saved_footer_calls.py`를 보존했다. 이전 [OCR correction 기록](PI4_OCR_THREAD_CORRECTION_RESULT_20260915.md)의 native crash 완화 결과는 유지한다. 이번 진단의 추가 product source modification count는 **0**.
