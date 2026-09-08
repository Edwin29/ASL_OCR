# T-close / Host read bound 후속 구현 결과

2026-09-08. [이전 구현 보고서](H123_IMPLEMENTATION_RESULT_20260908.md) §9의 두 후보에 대한 사용자 승인으로 수행했다. **이번 product 변경2파일, test 변경·추가3파일. Desktop/Laptop source 반영 후507 tests PASS, 새 G3-A automated PASS.** H4 BLOCKED는 유지한다.

## 1. T-close: 관측 후보를 confirmed_product_defect로 확인하고 수정

**First failing boundary:** `DeviceFlowCoordinator.stop()`의 `scanner.cancel()` 및 `connectivity.stop()` 예외 처리. 기존 catch-pass가 정상 shutdown에서 실패를 숨겨 Application/CLI가0으로 끝났다. 이전 fatal이 있었으면 종료코드는2여도 cleanup 실패가 별도로 관측되지 않았다.

독립 regression은 scanner cancel과 connectivity stop을 모두 실패시키고 나머지 resource close, 최초 원인, 종료 상태를 확인한다. 수정 전 정상 stop의 exit0, direct stop의 예외 누락이 재현됐다. [Before 결과](evidence/h123-followup-20260908/before.txt).

수정은 [coordinator.py](../device-runtime/src/asl_device/coordinator.py) 한 파일이다.

- Cleanup 실패를 발생 순서대로 `cleanup_failures`에 `resource.operation:ExceptionClass`로 보존한다. 예외 메시지를 새 log에 출력하지 않는다.
- Scanner cancel이 실패해도 connectivity stop을 시도한다. STOPPED로 전환한 뒤 최초 exception 객체를 그대로 전파한다.
- 기존 Application containment가 coordinator 실패를 기록하고 scanner/controls/audio 등 후속 resource close를 계속 수행하며 exit2를 반환한다. Application/CLI 파일의 추가 변경은 필요하지 않았다.
- 기존 `fatal_reason`은 덮어쓰지 않는다. Fatal incident와 cleanup failure는 별도 정보다.
- Stop을 다시 호출하면 이미 시도한 cleanup을 반복하지 않는다. 상태는 STOPPED, resource cleanup attempt는 exactly once다. 실패 작업을 자동 재시도하는 새 lifecycle은 도입하지 않았다.

**Classification:** confirmed_product_defect. 기존 severity를 승격하지 않았다. 기존 coordinator/Application ownership을 복원하는 bounded local correction이며 architecture layer 변경이 아니다. 기존3파일 상한 중1파일을 사용했다.

## 2. Host read bound: 실제 설치 pyserial에서 원인을 확인하고 수정

**First failing boundary:** serial worker의 `connection.readline()`. Complete-line framer의255byte 제한은 `readline()`이 반환한 뒤에 적용되므로 그 호출의 수명이나 메모리 사용을 제한하지 못했다.

Laptop에 설치된 pyserial3.5의 실제 `loop://` transport에서 timeout50ms, newline 없는80byte를5ms 간격으로 공급했다. Credential/COM/servo 접근은 없다.

| 관측 | 기존 readline | read_until(size=256) |
|---|---:|---:|
| 한 read 반환 시간 | 0.500초 | 0.062초 |
| 해당 read 반환 bytes | 80 | 11 |

[실제 pyserial source와 측정](evidence/h123-followup-20260908/serial-probe.json). `read_until`은 호출 시작 때 timeout을 만들고 byte read 사이에 만료를 검사한다. `readline`의 per-byte read timeout 갱신과 다르다. 버스트1024byte 시험에서도 반환량은256byte였다.

같은 실제 pyserial loopback을 production worker에 주입한 baseline/candidate 비교도 수행했다. 지속 입력 중 두 worker가 실제 살아 있고 worker exception이 없는 상태에서 close를 호출했다.

| Worker 관측 | Baseline | Candidate |
|---|---|---|
| close 반환 시점 | 약1.000초 | 측정 clock 해상도에서0.000초 |
| close 반환 뒤 worker 생존 | true | false |
| probe cleanup 후 생존 | false | false |

[Worker before/after](evidence/h123-followup-20260908/worker-probe-final.json). Candidate의0.000초는 즉시성 보장 수치가 아니다. 설정된 timeout과 OS scheduling에 따른 한계 안에서 해당 시험의 종료를 관찰한 값이다.

수정은 [stm_serial.py](../device-runtime/src/asl_device/adapters/stm_serial.py) 한 파일이다.

- SerialConnection/worker가 `read_until(size=256)`을 사용한다. 기존 pyserial>=3.5,<4 dependency 범위 안이며 dependency 변경0.
- Partial record는 기존 framer가 이어 붙이고 LF가 완성돼야 parser/ACK/dedupe로 전달한다. Oversize record는 기존처럼 newline까지 폐기한다.
- Timeout으로 read가 나뉘어도 seq78을 seq7로 ACK하지 않는다. 기존 release priority/hold watermark/reconnect framer reset/FRAME ordering을 유지한다.
- `SerialConnection` test double은 `read_until`을 제공하도록 갱신했다. Production pyserial은 이미 해당 API를 제공한다. Wire protocol migration이나 device state migration은 없다.

**Classification:** confirmed_product_defect. Host I/O worker의 국소 수정이며 기존2파일 상한 중1파일을 사용했다. 전체 read timeout 검사와 byte cap을 갖지만 Windows native driver hang이나 엄밀한 hard realtime을 보장하지 않는다. `read_until`은 각 `read(1)` 뒤 deadline을 확인하므로 timeout 반환은 설정값을 약간 넘을 수 있다. Timeout production 값, baudrate, FRAME grammar, V3 semantics, firmware IRQ/DMA를 변경하지 않았다.

## 3. 회귀와 source 반영

- [새 targeted regression](../device-runtime/tests/unit/test_h123_followup.py): 정상/fatal cleanup 실패 분리, 첫 exception identity, 모든 cleanup 시도와 exactly once, bounded worker read와 partial sequence 보존. 수정 전4 fail을 보존했다.
- 기존 STM unit/integration fake 두 파일에 새 serial read API를 반영했다. 기존 assertion/acceptance를 완화하지 않았다.
- [Laptop staged 검증](evidence/h123-followup-20260908/staged-tests.json): Device unit/integration301 PASS.
- [Laptop source 반영 후 검증](evidence/h123-followup-20260908/final-validation.json): **Device301 + Scanner206 =507 PASS**. Product246개 파일의 Desktop/Laptop normalized hash mismatch0, 실제3 package import는 `C:\ASL_OCR_INTEGRATION`, 기존 환경 manifest hash 보존.
- [반영 manifest](evidence/h123-followup-20260908/laptop-alignment-apply.json): 적용 직전 baseline 일치/기타 Python process 부재 확인. Backup은 `C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\diagnostics\h123-followup-alignment-1788827092096610000`. 기존 `C:\ASL_OCR`/state/DB/credentials/evidence 보존, Laptop D: 접근0.
- [이번 파일별 delta](evidence/h123-followup-20260908/implementation-delta.json). 이 보고서의 baseline은 이전12파일 correction이 반영된 상태다. 과거 보고서의 test 수와 hash는 당시 결과로 유지한다.

### 시험 중 별도로 남긴 V4 storage 실패

Desktop 회귀에서114 PASS/1 FAIL이 나왔다. 실패는 `test_e0_response_loss_ack_flush_seal_and_reading_are_ordered[connection_loss]`의 첫 spread durable row 부재였다. Server log는503, 새 isolated DB는 `UPLOAD_STORAGE_TEMPORARY`를 기록했다. 해당 V4 경로는 underlying OSError를 이 오류로 매핑한다. [실패 output](evidence/h123-followup-20260908/after.txt), [read-only DB 관측](evidence/h123-followup-20260908/storage-observation.json).

동일 test를 짧은 별도 temporary path에서 실행하자1 PASS였고, Laptop의 staged/실제 source 전체 테스트도 통과했다. [Desktop 재검증](evidence/h123-followup-20260908/desktop-v4-recheck.txt). 이것만으로 Windows path limit, 일시 filesystem 오류 또는 권한 중 원인을 확정하지 않는다. **First boundary는 isolated upload storage, exact cause는 insufficient_evidence**로 남긴다. 승인된 두 packet의 source 변경은 실패한 upload/SCANNING 경로를 바꾸지 않았다.

기존 `LoseFirstResponse` harness는 첫 응답의 성공 여부와 무관하게 “after durable server commit” exception을 주입한다. 이번503에서 그 문구는 실제 durable commit 증거가 아니다. Assertion은 수정하지 않았고 V4/Parser product 변경도 하지 않았다. 필요 시 별도 storage exception 계측으로 다룬다.

## 4. G3-A 및 physical acceptance

**새 G3-A automated PASS**, 전체 status는 `manual_pending`. 고정 MP4 두 spread를 새 Desktop loopback production OCR/Piper 서버·DB로 처리했다. 두 durable receipt, 네 fragment, 네 page의 nonempty braille, audio resource136개 검증, fresh READY revision1을 확인했다. Datapack은 `datapack-a9ba6a70b86f4ec1be5438da030739d4`다. [G3-A report](evidence/h123-followup-20260908/g3a-evidence/e0b-production-full-model-report.json), [receipt/READY event](evidence/h123-followup-20260908/g3a-evidence/e0b-replay-console.log).

기존 인증을 재사용하고 `--no-playback`을 유지했다. COM/servo packet0. 최대900초/무진전300초의 bounded run이 exit0으로 정상 종료했다. 고정 replay·scripted controls와 audio transport evidence이며 live Android/physical controls/실제 청취 검증이 아니다. Source hash는 이번 최종 validation과 연결하고 과거 G3-A evidence는 보존한다.

이번 두 패킷의 코드 결함 확인에는 사용자 관측이 필요하지 않았다. 실제 COM/HC-05, physical V3 A/R, 정상 FRAME 속도 및 physical cell acceptance는 수행하지 않았다. Loopback을 physical acceptance로 대체하지 않는다. Fresh H3에서는 DOWN hold/release 중 navigation과 disconnect/reconnect를 실제 packet·worker 종료에 대응해 관측해야 한다. H4 blocker인 native crash root, live camera 가용성/liveness, MCU 수신 손상과 hardware 배선/셀은 이번 범위로 종결하지 않는다.

## 5. 호환성·rollback

Public user workflow와 accepted/durable/applied/physically observed completion은 유지한다. 변화는 cleanup 실패가 더 이상 정상 종료로 보이지 않고, serial 입력 read가 worker를 무기한 점유하지 않게 된 것이다. T-close의 직접 coordinator caller는 실패 exception을 받을 수 있으며 production Application은 기존 containment로 이를 처리한다.

Rollback은 새 device process를 정상 종료한 뒤 위 C: backup의 두 product 파일을 복구하고 이번 test 변경을 별도 되돌리는 단위다. DB/state migration, stable device ID 변경, firmware flash가 필요하지 않다. 예전 read lifetime/cleanup 관측 결함을 되살리는 rollback이므로 장애 분석용으로만 검토한다.
