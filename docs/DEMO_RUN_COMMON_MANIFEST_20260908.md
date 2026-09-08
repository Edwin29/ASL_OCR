# ASL_OCR 한정 실제 시연 Run 공통 manifest

기계 판독 가능한 기준은 [run-common-manifest.json](evidence/demo-run-common-manifest-20260908/run-common-manifest.json)이다. 이 문서는 run 시작 전에 무엇을 고정하고 무엇을 새로 채워야 하는지 설명한다.

## 판정

공통 manifest 상태는 **prepared_with_blockers**다. Desktop production server와 Tailscale HTTPS health는 동일한 server instance에서 PASS이고, Laptop source/import/config·audio device·COM presence를 credential 없이 확인했다. 다음 실제 run을 시작할 source/config 기준은 마련됐다.

다음 항목은 아직 시작 조건을 충족하지 않는다.

- Android source의 현재 frame 획득 가능성.
- 실제 authenticated Piper와 빠른 control supersession을 결합한 사람의 청취.
- STM target build, flashed binary identity와 rollback image.
- Normal-rate FRAME의 wire→MCU RX→parser→PCA→physical cells 연속성.
- PAGE NEXT, CONFIRM SHORT/LONG, mode lever와 cell clear의 물리 수용.

따라서 이 manifest는 H1/H2/H3/H4 PASS 선언이 아니다.

## 공통으로 고정된 identity

- Source는 commit `ea7e6f24b38bc74bd2405ca1f35ed1acd2bab42e`만이 아니라 S-01/S-02 stabilization과 승인된 H1/H2/H3 correction을 포함한다. Product246개 파일의 digest는 `300d69673168801900dae581f453d773bd3121caf938fb4d06928ccec3da20c9`다.
- Laptop Python3.11.9 및 세 package import는 모두 `C:\ASL_OCR_INTEGRATION`을 가리킨다. Manifest 수집 시 실행 중인 production `-m asl_device` process는 없었다.
- Desktop production server는 PID26900이 `127.0.0.1:8421`을 listen하며, Tailscale HTTPS와 local health가 `server-d3b9d880827248f9a952faa14d0485bd`로 일치했다.
- Server launcher가 `D:\Projects\OCR\document-parser\src`를 `PYTHONPATH`로 지정하는 계약과 현재 server module hash를 기록했다. 실행 process 내부 `module.__file__`을 직접 읽은 증거는 아니므로 manifest에도 그 한계를 표시했다.
- Camera는 strict Android IP profile이다. 해당 profile에만 self-signed TLS 허용이 유지되고, webcam fallback은 없다. Credential 값과 credential 파일 경로는 기록하지 않았다.
- COM9/9600은 HC-05 host link, COM5는 STLink debug로 열거됐다. Manifest 수집 중 포트를 열거나 packet을 보내지 않았다.
- Firmware source hash는 기록했지만 target build/flashed identity/rollback은 `unverified`다. MSVC/HAL fixture PASS를 board identity로 승격하지 않았다.

## 시작 state

Production DB에는 READY7개와 `laptop-device-001`의 stable progress4개가 보존돼 있다. 최신 cursor candidate는 datapack `datapack-63c0ac30cc8a482f8fa9d0795e044a03`, revision1, page index1/node9, braille offset10, generation134다.

과거 open reading session4개와 최신5개 presence row가 `active`로 남아 있다. 현재 Laptop process가 없으므로 이 row는 live process 증거가 아니다. 삭제하거나 reset하지 않고, 새 run의 boot/session ID와 분리한다. 실제 run 시작 시 DB hash와 cursor를 다시 snapshot한다.

## Production 경로와 harness 구분

| Profile | Entry / controls / initial mode | 보존·우회 경계 |
|---|---|---|
| Camera probe | Isolated strict source probe, Device state 없음 | HTTP/TLS/auth/decode/stop만 통과. App/outbox/server/audio/STM 우회 |
| Audio console | Custom production-class composition, console, READING | Device/S0/authenticated audio/native speaker 보존. Capture/STM 우회 |
| Fresh H1 | `python -m asl_device`, console, CAPTURE | Live capture부터 READY/TTS까지. Physical STM만 우회 |
| H2 console+STM | Custom composition, console override, READING | S0/audio/production STM presenter 보존. Physical input/capture 우회 |
| Fresh H3 | `python -m asl_device`, STM controls/presenter, CAPTURE | Physical V3부터 reading/audio/braille/restart. Live capture는 요구하지 않음 |
| H4 | `python -m asl_device`, override0, CAPTURE | 한 run에서 전체 production 경로 |

H2 TOML 자체는 `stm_serial` controls를 선언한다. 과거 H2는 runtime에서 console controls를 주입하고 STM presenter를 유지했다. Manifest는 parsed config와 override를 별도 필드로 기록한다. H3의 historical target은 reading이지만 production constructor initial mode는 CAPTURE다. Physical lever event가 reading mode를 만들어야 한다.

## Run 시작 전 필수 갱신

각 run은 새 C: evidence root와 config copy/hash를 만들고, launcher·entrypoint·override·initial state·session ID를 기록한다. Actual playback process의 Windows session/audio device, COM ownership/negotiated protocol, firmware build/flash/rollback identity도 해당 run에서 채운다.

Hardware/servo run은 예상 packet/frame 수, 최대 동작, stop condition과 observer field를 먼저 붙인다. `ACK`, outbox, `spread_sent`, READY revision, native audio completion, 사람의 청취, PCA 적용과 실제 cells를 각각 기록한다. 이 신호는 서로 대체하지 않는다.

수집 원시 evidence는 [Laptop runtime](evidence/demo-run-common-manifest-20260908/laptop-runtime.json), [Desktop runtime](evidence/demo-run-common-manifest-20260908/desktop-runtime.json), [preserved run identities](evidence/demo-run-common-manifest-20260908/preserved-run-identities.json)에 있다. Password/API key 값은 어느 파일에도 포함하지 않았다.
