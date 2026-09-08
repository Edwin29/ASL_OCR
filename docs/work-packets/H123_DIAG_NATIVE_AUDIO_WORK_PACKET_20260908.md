# Proposed bounded implementation packet A — Native audio lifecycle

상태: **제안만 작성; 구현 미승인/미실행**. 근거: [독립 진단 보고서](../H1_H2_H3_SOFTWARE_DIAGNOSTIC_RESULT_20260908.md) §3–7. G3-A/content waiver 유지.

## 수정할 확인 결함

- A1: SoundDeviceWavPlayer.stop의 abort가 worker write/stop/close와 같은 native stream에서 겹친다. Laptop fake-native10/10 재현.
- A2: ReadingAudioController가 replacement job을 publish/notify한 뒤 stop을 호출하여 새 generation 자체를 중단할 수 있다. Real controller/barrier fake에서 current generation failure 재현.
- 두 기존 native AV의 exact root는 **insufficient_evidence**이다. 이 packet이 두 crash를 반드시 해결한다는 전제로 승인하지 않는다.

## Inputs / identity

- `device-runtime/src/asl_device/adapters/reading_audio.py`, `reading_audio.py`, `application.py`(read-only caller review).
- [Laptop reproduction](../evidence/software-diagnostic-20260908/laptop-reproduction-results.json), [reproducer](../evidence/software-diagnostic-20260908/reproduce.py).
- 원본 dump는 Laptop C:에서만 read-only 분석. [dump metadata/hash](../evidence/software-diagnostic-20260908/dump-metadata.json). Symbols/stack 미확보를 출발 상태로 명시한다.
- Baseline HEAD+verified working tree 및 현재 import path를 고정한다. Native package version은 현재 상태 유지.

## Change budget

Production 최대2파일: player adapter와 controller. 필요한 targeted tests만 추가. 외부 credential/API, S0 server, scanner, STM protocol, FRAME, content parser, dependency/lockfile 변경0.

Native stream의 owner와 stop ordering을 명시하여 모든 start/write/abort/stop/close가 lifetime 안에서 직렬 수행되도록 한다. Input thread가 native close와 경쟁하지 않아야 하며 replacement를 열기 전에 old cancellation이 어느 epoch에 속하는지 확정한다. 종료 후 worker/native resource 정리를 검증한다.

단순히 blocking write 전체에 mutex를 씌워 input thread를 오래 막거나 audio interruption을 제거하는 방법은 불가하다. Callback/native backend 전면 교체, 새 scheduler layer, 광범위 architecture 변경이 필요하면 예산 초과로 중단·별도 설계 검토한다. Error swallowing으로 PASS 처리하지 않는다.

## Targeted acceptance

1. 현재 재현의 ownership violation을 실패 assertion으로 전환: adversarial start/write/drain/abort/close interleaving에도 native concurrent call0, use-after-close0, close exactly once.
2. Notify-before-stop scenario: cached/instant fetch 새 generation은 old stop으로 실패하지 않음. 최신만 완료, obsolete completion0.
3. DOWN/UP/CONFIRM 및 mode exit interruption; rapid catalog↔document 전환; fetch 중 cancel, playback 중 cancel, close 중 error/timeout.
4. Bounded resource/cache 유지, response close, thread exit 확인. Shutdown timeout 시 성공으로 기록하지 않음.
5. 관련 existing audio/application tests → device-runtime subsystem. 별도 G3-A에서 authenticated refs/session/generation contract 확인.

## 실제 Windows 재검증 계약

새 C: diagnostic root의 interactive user session에서 실행한다. 시작 전에 Windows audio device/host API/session ID, interpreter/package/DLL identity, bounded iteration 수와 duration을 기록한다. 우선 serial/camera/S0 없이 local authorized WAV playback-only로 lifecycle을 분리하고, HTTPS-only·serial-only·결합 단계로 확대한다. 실험마다 어떤 boundary를 생략했는지 표기한다.

Expected serial packet은 playback-only 단계에서 **없음**. 실제 FRAME/servo 결합은 별도 H3 계획에서 packet·대상 pattern·stop condition을 먼저 보고한다. Evidence는 `C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\diagnostics\audio-<fresh-id>`에 저장한다. Native dump 원본 복사/삭제 없음.

Stop condition: 첫 native crash, torn/noisy playback, stale generation completion, 종료 후 worker/stream 잔존, process hang. 실패 시 현재 state/evidence 보존하고 반복량을 늘려 PASS를 만들지 않는다.

## Deliverable / 완료 조건

독립 patch/diff와 정확한 before/after reproducer, targeted/subsystem 결과, native stress 결과 및 stack/symbol 상태. A1/A2가 닫혀도 실제 crash가 재발하면 incident root를 재분리한다. Native stress와 fresh H3 speaker+physical input 확인 전 H3/H4 audio blocker를 해소하지 않는다. B/C/T packet이나 hardware 문제를 대신 승인하지 않는다.
