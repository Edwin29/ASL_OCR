# Pi production capture 2차 재시도 로그 검토

## 결과와 수용 범위

45초 identity 수집 제한을 사용한 Pi production 실행에서 **26/27 → 28/29 → 30/31** 세 spread의 durable 수신, 서버 처리, 새 READY revision 1 게시를 확인했다. 서버 보존 source_frame.jpg의 실제 쪽번호를 육안으로 대조했다. 사용자는 두 번째 전송 후 다음 페이지로 넘겼다고 확인했으므로 세 번째 수신은 중복 incident가 아니다. 원래 두 spread 절차에 세 번째 spread를 추가한 실제 실행으로 기록한다.

로그 검토 시점에는 현재 촬영 조건의 capture→V4→서버 처리→fresh READY 경로 성공을 확인했다. 이후 사용자가 이번 새 데이터팩의 읽기 품질은 이전 데이터팩들과 큰 차이가 없고 모든 기능이 정상작동했다고 보고했다. 이에 새 READY의 실제 읽기 연결도 사용자 관측 PASS로 추가한다. 전체 H4 체크리스트 및 전원 복구까지 완료됐다는 의미는 아니다.

## 실행 및 근거

- Pi runtime: `/home/user/ASL_OCR_PI/runtime/production-demo-20260915-r2-retry1`
- production `python -m asl_device`, STM controls/presenter, 실제 AUX audio, Android snapshot source.
- scan: `scan-87c8b2c5e29d4c99b27808d64addf32d`
- datapack: `datapack-f93b6930cfa9419e84704869e459fe9b`
- 제목: `새 데이터팩 2026-09-15 23:54 #30`
- config SHA256: `16742b412a125541f991a10afce55ca043d66ba9aeb1f0cd51f4590412ea62c3`
- 45초는 승인된 2차 runtime 시험값이며 N5/K_same1/K_different0 등은 유지했다. 기본 8초 조건의 성공으로 해석하지 않는다.
- Laptop 미리보기는 독립 camera client이며 Pi와 같은 프레임이라는 보장은 없다.
- 근거 폴더: [evidence](evidence/pi-production-demo-20260915-r2-retry1/).
- 최신 상태: `capture-audit-1789484857115172091.json`, `stdout-finalization-review.log`.
- 원본/manifest/log 해시: `review-evidence-hashes.json`.
- 최초 audit `capture-audit-1789484668262518594.json`의 candidate timing은 page-change 시작시간을 혼용한 진단 코드 오류가 있어 최신 audit로 대체한다. 원본은 보존했다. 제품 결함이 아니다.

## 실제 전달 결과

| 순서 | 원본 쪽번호 | scan 시작 후 전송 완료 | HTTP / 시도 | 서버 receipt |
|---|---|---|---|---|
| 1 | 26/27 | 4분 48초 | 201 / 1 | spread-receipt-54bb67208c7d51fdf2c59c9e6a67326d |
| 2 | 28/29 | 7분 00초 | 201 / 1 | spread-receipt-5b8e122cc214d98db756aabf1e273e30 |
| 3 | 30/31 | 8분 51초 | 201 / 1 | spread-receipt-54ca5c05447e2c03a9294139537a5af8 |

세 건 모두 Pi durable outbox `acked`. 각 receipt는 별도 식별자이며 `spread_sent`와 대조했다. 서버 read-only DB의 accepted upload 위치는 다음과 같다. 기준 경로는 Desktop `D:\device-config\state\e0b-production\datapacks\_server\received\v4`이다.

1. `upload-91f0400fb80e4f05a9fc9fff8f758c58/source_frame.jpg`
2. `upload-fa8a81e660b343b7861388e764406fb7/source_frame.jpg`
3. `upload-9158b1844fd740299e2dfedc610f63f2/source_frame.jpg`

CONFIRM LONG 이후 `scan_stopping(through_sequence=3)` → `finalizing` → `datapack_saved(revision=1)`을 확인했다. finalizing부터 saved까지 약84.64초. 서버는 sealed/published, ready spreads 3, processing/rejected/error 각각0이며 catalog도 ready revision1이다. 서버 갱신 UTC는 2026-09-15 15:05:20.589319, 한국시간 9월16일 00:05:20이다. 사용자가 직접 확인한 음성은 데이터팩 생성 중 안내이며 저장 완료 음성 청취는 별도 확정하지 않는다.

## 지연 및 환경 관측

후보8회 중4회가 page_not_found 또는 content_occluded로 중단됐다. 후보1회는 유효관측8개를 얻고도 약47.69초 뒤 unknown timeout이었다. 유효관측 수 충족만으로 승인이 충분하지 않다는 실행 증거다. 실제 raw 문자열 쌍은 해당 feedback에 없어 구체적인 오인식 문자열은 확정하지 않는다.

성공한 후보의 identity 수집 시간은 각각38.85초,31.00초,29.18초. 전체 기록된 처리 간격 중앙값은 약5.42초다. 이는 현재 장치·촬영·동시 미리보기 조건을 포함하며 CPU 계산시간 단독 측정이 아니다.

사용자는 첫 인식이 오래 걸렸으나 좌상단에 인공 플래시 조명을 더하고 가운데 라인에 음영을 만든 후 같은 구도에서 연속 전송됐다고 보고했다. 환경 통제가 성공에 기여했을 가능성을 지지한다. 조명 전후의 통제 비교 및 정확한 조정 시각이 없고45초 정책도 함께 사용했으므로 조명만의 인과 효과, 특정 그림자의 필요성,8초에서도 성공한다는 결론은 내리지 않는다.

## 다음 단계

1. 현재 카메라/책/조명 배치를 기록하고 유지한다. 추가 threshold/CLAHE 변경 근거로 이번 성공을 사용하지 않는다.
2. 이번 새 데이터팩 #30 revision1의 읽기 확인은 후속 사용자 관측으로 완료했다. 아래 기록을 참조한다.30/31은 추가 촬영 페이지로 구분한다.
3. 시연 재현성은 같은 조명에서 새 두-spread capture 반복으로 확인한다. 이번 한 번으로 환경 의존성 해소나 기본8초 복귀를 확정하지 않는다.

이번 로그 검토의 product source modification count: **0**. 진단 코드와 evidence/report만 작성했으며 기존 state와 서버 수신 자료는 변경하지 않았다.

## 후속 새 데이터팩 읽기 관측 — 2026-09-16

사용자 보고: “데이터팩 리딩 결과 이전 데이터팩들과 품질에 큰 차이가 없으며, 모든 기능이 정상작동함을 확인함.”

직전 안내한 새 데이터팩 #30 revision1의 실제 읽기 시험에 대한 사용자 관측 PASS로 기록한다. Pi production 환경에서 live capture→durable receipt→fresh READY→실제 읽기 기능 및 음성/점자 출력까지 연결된 한 차례의 실행 증거가 확보됐다. 품질 평가는 이전 데이터팩 대비 사용자의 정성 비교이며 OCR 정답률 측정이나 기존 content waiver 해소를 의미하지 않는다. 이번 보고를 새로운 packet trace 또는 generation별 자동 대조 결과로 표기하지 않는다.

남은 항목은 같은 촬영 조건의 반복 재현성, 시연용 부팅 자동 실행 및 전체 전원 차단·재공급 후 복구 검증이다. 초기 촬영 지연과 조명 의존성은 유지되는 시연 제약으로 기록한다. 이 관측 반영에서는 제품 코드나 실행 상태를 변경하지 않았다.

후속 갱신: [부팅·전원 복구 시험](PI4_BOOT_POWER_VALIDATION_20260916.md)에서 자동 시작과 이전 읽기 위치 및 실제 출력 복구1회를 확인했다. 같은 촬영 조건의 반복 재현성은 남겨 둔다.
