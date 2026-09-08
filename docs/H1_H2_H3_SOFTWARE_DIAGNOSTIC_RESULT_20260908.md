# H1/H2/H3 독립 Software Diagnostic & Pipeline-Fidelity Audit

작성일: 2026-09-08. **Read-only product diagnosis 완료. H4 BLOCKED; integration ready 아님. Product source 수정 0.**

이 문서는 기존 status/proposal의 결론을 재사용하지 않고, Laptop 원시 파일·SQLite·dump metadata와 현재 source의 독립 재현을 구분하여 판정한다. 실제 카메라 촬영, speaker 재생, serial 송신, servo 구동, firmware build/flash, production API upload는 이번 진단에서 실행하지 않았다. 기존 G3-A PASS와 content P1 waiver/Deferred는 유지한다. 신규 테스트 통과는 H1–H4 수용을 대체하지 않는다.

진단 evidence root: [software-diagnostic-20260908](evidence/software-diagnostic-20260908/). 주요 재현은 [reproduce.py](evidence/software-diagnostic-20260908/reproduce.py), authoritative Laptop 결과는 [laptop-reproduction-results.json](evidence/software-diagnostic-20260908/laptop-reproduction-results.json)이다. 재현 assertion은 **수정 전 잘못된 동작을 확인**하기 위한 것이며 수정 후 acceptance assertion으로 복사하면 안 된다.

## 1. Pipeline-fidelity matrix

### 1.1 Source / config identity

- Desktop/Laptop HEAD: `ea7e6f24b38bc74bd2405ca1f35ed1acd2bab42e`. HEAD 단독이 baseline이라는 뜻이 아니다.
- Laptop interpreter: `C:\ASL_OCR_INTEGRATION\.venv-e0b\Scripts\python.exe`, Python 3.11.9. SHA-256 `21bb438c0d4a6f1f164b9a646f6ee000340185e5871180aec06db8d3f07c0082`.
- `asl_device`, `book_scanner`, `document_parser`의 현재 `__file__` 모두 해당 integration checkout의 각 `src` 아래이다. 기존 `C:\ASL_OCR` import contamination 없음.
- 세 Python source tree와 authoritative STM Core의 246개 파일은 Desktop/Laptop **LF-normalized hash 모두 일치**. raw hash 차이는 줄바꿈 차이이므로 raw 동일성으로 과장하지 않는다.
- 기존 integration environment manifest의 transplant 14파일은 **현재 Laptop raw hash 14/14 일치**. manifest는 S-01/S-02뿐 아니라 9월 7일 승인된 parser 3파일 및 test 2파일 후속 변경을 기록한다. 이를 임의 신규 drift로 취급하지 않는다. [baseline-verification.json](evidence/software-diagnostic-20260908/baseline-verification.json), [source-identity-before.json](evidence/software-diagnostic-20260908/source-identity-before.json).
- 설치 상태 확인: sounddevice 0.5.6, cffi 2.1.1, pyserial 3.5, requests 2.34.2, numpy 2.3.5, opencv-python 5.0.0.93. dependency 변경/재정렬 없음.
- 각 H1/H2/H3/H3-R config는 현재 Laptop `DeviceAppConfig.from_toml`로 parse 성공. 보존 config/harness/launcher 15파일과 physical-down 원시 3파일의 현재 Laptop counterpart hash가 일치한다. `result.json`은 다른 파일명이라 basename 대조 대상에서 제외했다.
- 당시 모든 process의 import dump가 남아 있는 것은 아니다. 따라서 현재 identity와 당시 launcher/run manifest가 일치한다는 결론이며, 과거 process memory 전체 동일성을 증명한 것은 아니다.

공통 config는 viewport=10, poll=20 ms, strict Android snapshot profile, sample interval=750 ms, identity collection=8,000 ms, snapshot timeout=12 s이다. H1만 operator preview=true. STM은 COM9/9600, read timeout=20 ms, reconnect=500–5,000 ms, debounce=30 ms, hold=650/180 ms. Audio는 sounddevice, resource=4 MiB/cache=8 MiB·4 entries, request timeout=10 s. 각 config의 C: outbox/artifact root는 run별 격리된다. Secret 값 없이 parsed config를 [raw-evidence.json](evidence/software-diagnostic-20260908/raw-evidence.json)의 `configs`에 기록했다.

### 1.2 실행 composition

| Run | Launcher / Python entrypoint | Runtime override · controls / presenter / audio | 실제 초기 mode · 시작 state/cursor |
|---|---|---|---|
| H1-223731 | SSH가 interactive scheduled task를 구성; `h1-interactive-runtime.ps1` → `python -m asl_device --config … --initial-mode capture` | `build_local_device`; ConsoleControlSource / JsonLineReadingPresenter / ReadingAudioController + SoundDeviceWavPlayer. Physical STM만 대체 | capture catalog → synthetic new datapack → 새 scan. 첫 spread seq1. reading cursor 시작 없음 |
| H1-231944 | 동일 production entrypoint, 새 run/state | 동일, strict HttpSnapshotCameraSource + operator preview | capture catalog index25 선택 → 별도 새 datapack/scan. seq1 이후 page change 대기 |
| H2 | interactive task → `h2-runtime.ps1` → `h2-console-stm-harness.py` | config controls는 stm_serial이나 실제 ConsoleControlSource 주입. MultiPresenter(JSON stdout/log + production StmSerialControlSource). Production audio enabled | `initial_mode=READING`; 기존 READY revision1 선택. 복구 page3/node16/gen87 → prev page2/node0/gen88 |
| H2 paced/burst | runtime diagnostic script → pyserial 직접 write | DeviceApplication, Coordinator, S0, host presenter 우회. COM9 packet/COM5 trace | 고정 generation88/89/90; persisted reading cursor를 이동한 시험 아님 |
| H3 production | `h3-runtime.ps1`, 후속 visible/tee launcher 모두 `python -m asl_device --config …` | Production StmSerialControlSource가 controls/presenter; production sounddevice. 콘솔 명령 주입 없음 | **CLI default는 capture**. PC2의 V,R 이후 reading catalog로 전환. 문서 이름 `stm-reading`/manifest `initial_target=reading`이 initial mode override는 아님. CONFIRM 불가로 document cursor 미검증 |
| H3-R combined | `h3r-runtime.ps1` → `h3r-console-stm-harness.py` | console 주입 + JSON/STM MultiPresenter + production audio enabled | 기존 READY; page2/gen88 복구, prev×2 → page0/gen90, item navigation → gen110 |
| H3-R braille only | `h3r-braille-runtime.ps1` → 별도 harness | 동일 console/presenter, audio disabled | 기존 READY gen88; 이후 console down stall. 정식 production acceptance 아님 |
| H3-R paced110/111 | `generation-110-paced-frame.py`, `generation-111-paced-clear.py` | direct serial, 20 ms/byte. S0/host presenter/audio 우회 | 고정 FRAME gen110 수식 / gen111 all-zero |
| Physical DOWN follow-up | runtime task → `h3r-physical-down-harness.py` | BootstrapThenStmControls가 synthetic CONFIRM/PREV×2/DOWN×15 후 physical STM으로 전환. BootstrapGatedPresenter가 중간 FRAME 억제. audio disabled | 가정 page0/node15와 달리 readiness marker는 page1/node8. 측정 DOWN 후 page1/node9/gen129. **NAV,D,S,2: V2 async SHORT** |

### 1.3 통과/대체한 boundary와 claim 상한

B-ID는 [PROTOTYPE_STABILIZATION_GATE](PROTOTYPE_STABILIZATION_GATE.md)의 B00–B11을 따른다.

| Run | 실제 evidence로 지지하는 boundary | 대체/미완료 | 주장 가능 / 불가능 |
|---|---|---|---|
| H1×2 | B00, B02 new scan, B03 live source/candidate, B04 artifact 생성 lineage, B05 durable receipt1; B06 spread ready1은 보존 서버 응답으로 확인. B09 system cue 청취는 당시 human observation | B01 전부 console 대체. B03 두 번째 page-change 실패. B07 미실행/미게시, B08 문서 reading 없음, B10 physical 없음 | 첫 spread durable receipt는 재확인 가능. Two-spread finalize/READY, physical input, complete L/R 파일 재hash 및 OCR 의미 정확성은 이 evidence만으로 불가 |
| H2 | B02 READY 선택, B08 restored cursor/prev, B09 production WAV playback, B10 host presentation 및 손상된 STM line | B01 console, B03–B07 생략. Paced script는 B10 하류만 | Transport failure 및 paced parser/운동 확인 가능. 새 capture/publish, V3 GPIO 수용, production-speed 물리 안정성 PASS 불가 |
| H3 production | B01 V3 handshake·DOWN A/R·ACK·일부 GPIO, B02 reading catalog, B09 isolated title playback, B10 malformed line, B11 reconnect 일부 | 새 capture/READY 없음. Physical CONFIRM/PAGE NEXT/MODE 필수 동작 미완료; B08 document cursor 없음 | V3 DOWN cadence/reconnect 일부 가능. Stable document cursor recovery, full physical controls, TTS+점자 end-to-end PASS 불가 |
| H3-R combined | B08 실제 READY snapshots, B09 다수 실제 재생, B10 production serial 실패; native crash evidence | console B01, B03–B07 생략 | 실제 content output 진단에 유효. Production full pipeline 및 안정성 PASS 불가 |
| H3-R paced | B10 정확한 line parse와 당시 physical observation | upstream 모두 우회, pacing으로 arrival cadence 변경 | 수식 pattern 운동 및 clear residual 국소화. Host transport reliability, TTS coexistence, 최신 generation 소유권 수용 불가 |
| Physical DOWN | readiness marker 후 B01 **V2 SHORT** → B08 한 item 이동 → B10 exact FRAME gen129/10 cells/visible movement | scripted bootstrap, intermediate FRAME 억제, audio off, 기존 READY | 측정 action의 lineage 가능. V3 edge/hold, TTS 동시성, rapid FRAME stress 및 live capture-to-reading 불가 |

ConsoleControlSource는 production DeviceInputEvent를 생성한다. Application/Coordinator 이후 command semantics는 유지하지만 GPIO, firmware debounce, press/release 판정, HC-05 생성, ACK/dedupe, lever 배선을 우회한다. H2/H3-R connectivity capabilities는 **parsed config 기준 STM**이므로 실제 console override와 차이가 있다. 이것은 harness fidelity caveat이며 S0 command가 별도 구현으로 바뀌었다는 증거는 아니다.

SSH는 주로 orchestration이었다. H1/H2 launcher는 `LogonType Interactive`, user/Limited를 명시한다. H3는 production module을 쓰되 초기 redirection·후속 transcript·tee 실행이 섞여 있다. stdin/stdout buffering, NativeCommandError 포장, 보존 범위는 달라진다. 따라서 “SSH만 달랐으므로 process/audio 환경이 완전히 같다”는 주장은 불가하다. 실제 speaker 수용은 당시 interactive playback + human observation에 의존한다. 이번 SSH fake tests를 speaker/audio-device-context 검증으로 쓰지 않았다.

## 2. H1/H2/H3 evidence validity

### H1

- 두 isolated DB는 WAL 크기 0 확인 후 `mode=ro&immutable=1`로 읽었다. 각각 outbox row **1개, seq1, acked, attempt1, HTTP201**, stable device ID 동일. seq2 없음. [state-evidence.json](evidence/software-diagnostic-20260908/state-evidence.json).
- 223731: scan `scan-2b05e8b5cb234da48c265b07d94b84a7`, artifact `spread-47577804af842a4b8490f3aea35262f5`, frame191, receipt `spread-receipt-e1bf0646b544e633f7670772ac105d1e`. DB SHA `4b368b7aabe65e71b52f15dd63eb1a6e569ac720dd8a4a3c9d52afd8aa6bc3fa`.
- 231944: scan `scan-9725fbc4b3d04095a1810a3d16ef6b35`, artifact `spread-cd479bf7b7c9a62b8e2c967750e052d2`, frame69, receipt `spread-receipt-678834b6e1bd5b4a69f548ab666b37cb`. DB SHA `2692efd88e1b57e55e173e7ba124c80c8ab371fa7dc19909d1dea5eb22521f07`.
- 두 보존 `h1-server-scan-status.json` 모두 raw `status=open`, ready1, through_sequence=null, finalization=null, published_revision=null. 별도 `h1-live-diagnostic.json`의 `finalizing` 표시는 raw status와 다르므로 finalize 실행 증거에서 제외한다.
- ACK cleanup 뒤 로컬 artifact payload는 남아 있지 않아 저장된 manifest/inventory hash를 현재 L/R 원본 파일 재hash로 재확인하지 못했다. DB에 기록된 same-frame lineage와 당시 보고서의 범위를 구분한다.
- H1 transcript는 약 3 KB의 **tail/조각**이다. 줄바꿈을 재조립하면 H1-1 4개/H1-2 5개 feedback JSON이 유효하다. 후자는 page-change unknown timeout valid1/1/0, 2,500 ms interval, 612 ms recognition, fatal frame_decode_failed, wrapper exit0을 보존한다. 전체 유효/무효/quality reject 시계열은 없다.
- `h1-post-first-spread-diagnostic.json`의 `event_count=0`, `spread_sent_count=0`은 로그 수집/파싱 공백이며 durable ACK 부재를 뜻하지 않는다. [evidence-review.json](evidence/software-diagnostic-20260908/evidence-review.json).
- 보존 post-fatal burst는 10/10 성공, 4000×3000, 1,187–1,438 ms. 이는 **그 후 측정 구간의 회복**을 증명한다. 직전 fatal이 단 한 번의 timeout인지, HTTP status인지, decode 3회 소진인지, analyzer 오류인지는 증명하지 않는다. Phone 방전 원인은 당시 human report이며 이번에 전기적으로 재현하지 않았다.

### H2 / H3 / H3-R

- 보고서에 적힌 hash9개 중 8개가 현재 파일 전체와 일치한다. 다른 하나 H2 events의 보고 hash `cee1fbfc…`는 현재 파일 **첫 4,369바이트의 SHA-256과 정확히 일치**한다. 현재 전체 hash는 `bc3f7fd3dba4def645dba97bb0b8c37ccedbff70bdc3296269eb0627f1a9941b`; 뒤에 재실행 catalog/audio 이벤트 1,478바이트가 append됐다. 원래 시험 prefix 무결성은 보존됐으나 전체를 단일 실행으로 분석하면 안 된다. [h2-hash-reconciliation.json](evidence/software-diagnostic-20260908/h2-hash-reconciliation.json).
- H2 burst raw trace의 `AK,1`, `FRA,…`, 3 ms의 `FRAME,2,00,0,8,…`, 20 ms의 정확한 cursor5+cells10을 재확인했다. Production formatter 외 direct script에서도 손상되어 **S0/host formatter 단독 원인 가설은 반증**된다. Wire capture가 없으므로 host driver/HC-05/STM RX 중 exact loss 지점은 미확정이다.
- H3 COM5 trace의 `NAV,D,A,44` @103796.531, `NAV,D,R,45` @103797.765와 V3 reconnect를 확인했다. 후속 event file은 append된 여러 process 실행을 포함한다. 보고서의 hold timing을 모든 run의 단일 타임라인으로 확장하지 않는다.
- Physical-down 3개 raw file의 hash는 보고서·Desktop copy·현재 Laptop 모두 일치한다. NAV,D,S,2 → ACK2 → page1/node9/gen129 → `[38,45,34,60,1,52,11,38,45,52]`의 lineage는 유효하다. V3로 바꾸어 인용하지 않는다.
- H3-R combined log는 gen110 playback_started(21,653 ms), 이후 interrupted까지만 보존한다. 이후 DOWN command의 정확한 native call 순서는 이 로그에 없다. Audio-disabled stall은 process crash의 반복으로 세지 않는다.
- Paced clear111의 정확한 zero parse는 raw JSON에서 확인한다. **두 번 반복한 동일 residual**은 status/human observation이며 보존 current JSON 하나를 독립 raw trace 두 개로 세지 않는다. STM `ShowCurrentState`는 요청 cells를 출력하고 `ApplyBrailleFrame`은 I2C 오류를 반환하지 않는다. 따라서 “zero parse = 모든 PCA PWM 적용 성공”은 성립하지 않는다.
- H0의 build/flash ELF hash는 역사적 보고 evidence다. 이번에 예상 integration `Debug/kitel2026final.elf`는 없었으며 설치 flash를 새로 읽지 않았다. Firmware mechanism 분석은 현재 source + 당시 COM5 protocol에 근거하며 fresh flash identity acceptance는 아니다.

### Crash dumps

원본을 복사하지 않고 Laptop에서 read-only mmap으로 MINIDUMP header/module/exception stream을 읽었다. Python stdlib parser v1 사용. cdb/windbg/dumpchk는 PATH에서 없고 Windows Kits의 표준 x64 debugger 경로에도 없다. Symbol 로드/stack unwind는 **미실행**이다. 주소를 호출 stack으로 추정하지 않았다. [dump-metadata.json](evidence/software-diagnostic-20260908/dump-metadata.json).

| 원본 | 크기 / SHA-256 | 독립 확인 |
|---|---|---|
| python.exe.27012.dmp | 43,851,515 / `d7ad18d2b268740b796ea1423983f537e7803ac3d6a31c64e69da443244a76d5` | thread28816, 0xc0000005 read AV, `ucrtbase.dll+0xee451` |
| python.exe.31856.dmp | 44,441,578 / `c0cb1fcb7ab89c5dc7f103ef40c15f1c85c35aa29036f60481f1512e7a5f6a11` | thread29564, 0xc0000005 read address0x1, `libcrypto-3.dll+0x290dde` |

두 dump의 integration cffi/PortAudio 로드는 확인했다. venv launcher 아래 base Python DLL 경로가 존재하는 것은 venv의 정상 구조이며 그 자체로 import contamination을 뜻하지 않는다. **Loaded module과 fault module은 root-cause stack이 아니다.**

## 3. Issue별 independent reproduction 결과

Production source를 import해 fake camera/recognizer/native stream/serial boundary만 주입했다. 실제 UI input/HTTP/servo/native driver 재현으로 과장하지 않는다. Laptop Python 3.11.9에서 모든 diagnostic assertions 통과. Desktop 3.11.8에서도 보조 실행했으며 Desktop requests dependency warning은 별도 environment caveat다.

| ID / 기존 severity | 실패 invariant · first failing boundary | 독립 결과 | 분류 / 기존 가설과의 관계 |
|---|---|---|---|
| LIVE-PAGE-CHANGE-LIVENESS-P1 | B03: healthy eligible changed spread에서 N=5를 모아 다음 capture로 진행할 수 있어야 함 | Engine/collector unchanged; 모든 pair valid. 1.9 s/관측 +20 ms poll: 5개 후 SEARCHING, **9.58 s**. 2.5 s: 20개 관측 동안 4개마다 timeout/reset, WAITING 유지. 동일 2.5 s·finite30 s: 5개/12.58 s에 SEARCHING. Missing pair는 진전 없음 | **environment_failure**: 8초 runtime profile과 특정 실제 cadence의 호환 실패를 확인. Engine clock의 product 여부/실제 H1의 유일 원인은 **insufficient_evidence**. 기존 “무조건 engine budget 변경” 결론은 지지하지 않음. 기존 P1 blocker 유지 |
| HTTP-SNAPSHOT-TRANSIENT-FATAL-P1 | B03 source exception → engine ERROR; recoverable acquisition과 auth/permanent failure 분리 | requests Timeout, HTTP401, HTTP503 각각 **fetch1회 → ERROR/frame_decode_failed**. Bad JPEG→good는 **2회 후 성공**; bad JPEG 지속은3회 후 실패 | Transport recovery/taxonomy는 **confirmed_product_defect / P1**. 모든 decode failure 즉시 fatal 가설 반증. H1 마지막 exception subtype는 insufficient_evidence |
| POST-FIRST-SPREAD-GUIDANCE-SILENCE-P1 | B03 unknown timeout을 operator guidance에 전달해야 함 | Slow/missing page-change timeout 반복 시 `opaque_identity_decided`만 발생; guidance 종류0. Source와 audio mapper를 함께 확인 | **confirmed_product_defect / P1**. 이 branch의 silence는 cue 미생성이다. 과거 모든 silence가 이 원인이거나 audio transport 전체 정상이라는 결론은 불가 |
| ANDROID-PREFLIGHT-SOURCE-P1 | B00 readiness probe가 configured strict source를 확인해야 함 | Android config를 `_probe_e0b_profile`이 거부하고 `_probe_camera`는 fake OpenCV index0을 열어640×480 PASS 반환 | **confirmed_product_defect / P1, tooling**. Actual runtime factory fallback 결함으로 확대하지 않음 |
| FATAL-EXIT-STATUS-D01 | B11: fatal stop이 supervisor에 정상 exit로 보이지 않아야 함 | Fake external catalog가 FatalPortError → **real Coordinator fatal_error/STOPPED → real Application.run → CLI main0** | **confirmed_product_defect / Deferred 유지**. 실제 supervisor가 exit만으로 restart/health 결정한다는 evidence 없음; P1 자동 승격 안 함 |
| STM-FRAME-TRANSPORT-INTEGRITY-P1 | B10 production-rate bytes가 STM에서 동일한 완전한 line이 되어야 함 | Real host worker + fake serial: ACK/FRAME write는 완전하고 단일 worker 소유. Firmware source-derived timing model은 blocking 때 유실 가능. 실제 UART/HC-05 재실행은 not_run | Symptom P1 유지, exact incident root **insufficient_evidence**; firmware polling RX는 **probable_product_risk**. Interrupt/DMA를 확정 fix로 선결정하지 않음 |
| RAPID-READING-SUPERSESSION-NATIVE-CRASH-P1 | B09/B11 supersession이 native lifetime을 파괴하지 않아야 함 | Actual SoundDeviceWavPlayer + fake native stream으로 write↔abort, abort↔stop/close overlap을 **10/10** 재현. Dump metadata2개 AV 확인. Actual native crash 재현/stack은 not_run | Native incident root **insufficient_evidence / P1**. 별도 A1 lifecycle ownership 결함은 **confirmed_product_defect / P1**. PortAudio 단독 원인 단정 불가 |
| ACTUATOR-CLEAR-RESIDUAL-P1 | B10 accepted zero → 모든 dot retraction | 보존 exact zero parse 확인. New physical reproduction/전압·PWM 측정 없음 | **hardware_or_wiring / P1**을 작업 분류로 유지하되 exact calibration/driver 원인은 **insufficient_evidence**. Incoming grammar 변경 대상 아님 |
| STM-REQUIRED-CONTROL-INPUT-P1 | B01 intended button → configured GPIO/NAV | GPIO map/code와 COM5의 PAGE PREVIOUS 및 부재 증거 확인. New continuity/physical input 시험 not_run | **hardware_or_wiring / P1**. PC1 failure vs 실제 배선/라벨/연속성 확정 불가. Pin swap 금지 |
| MODE-LEVER-SOLDER-P1 | B01 lever contact → PC2 LOW/HIGH 전환 | source pull-up 및 V,R trace 일치; broken solder는 기존 human evidence | **hardware_or_wiring / P1**, 신규 전기적 재현 없음. software mode semantics 수정 안 함 |

## 4. Confirmed root causes

### A1. Native stream 소유권이 lock으로 보호되지 않는다

[adapters/reading_audio.py](../device-runtime/src/asl_device/adapters/reading_audio.py)의 `play`는 `_stream` 참조 게시만 lock으로 보호하고 native start/write/stop/close는 lock 밖에서 수행한다. `stop`도 lock에서 참조만 얻고 밖에서 abort한다. Input thread가 stop을 실행하는 동안 worker가 finally로 진입하면 같은 stream의 abort와 close가 동시에 실행될 수 있다. 재현은 두 thread의 barrier로 정확히 이 실행 순서를 고정한다. **실제 native AV를 fake가 재현했다는 뜻은 아니다.** 독립 수정할 수 있는 lifetime 결함과 사건의 crash attribution을 분리한다.

### C2. Transport retry 없음 + error taxonomy 소실

[sources.py](../book-scanner/src/book_scanner/video/sources.py)의 read loop는 `FrameDecodeError`만3회 retry한다. `_fetch_decoded_frame`은 그 밖의 예외를 `SnapshotTransportError`로 감싼다. Engine `_read_frame_for_opaque`는 이를 별도 처리하지 않고 broad Exception→FRAME_DECODE_FAILED→ERROR로 만든다. 401/403, timeout,5xx, TLS, credential-read 원인이 operator boundary에서 구분되지 않는다. Strict source 유지와 bounded recovery는 양립 가능하며 webcam 대체가 필요하지 않다.

### C3. Page-change timeout branch에 guidance emission이 없다

[engine.py](../book-scanner/src/book_scanner/video/engine.py) `_poll_opaque_page_change`의 timeout branch는 decision emit 후 collector를 새로 만들 뿐이다. [reading_audio.py](../device-runtime/src/asl_device/reading_audio.py)의 system cue mapping에는 identity_collection_decided→guidance 대응이 없다. 따라서 이 조건에서 silence의 first missing boundary는 WAV transport가 아니라 Scanner feedback 생성이다. **Silence는 seq2 부재의 원인이 아니다.**

### T1/T2. Preflight source routing / fatal result 유실

[laptop_acceptance.py](../device-runtime/src/asl_device/laptop_acceptance.py)의 profile whitelist 및 `_probe_camera` 분기는 Android HTTP profile을 다루지 않는다. [coordinator.py](../device-runtime/src/asl_device/coordinator.py)의 `_fatal`은 STOPPED로 전환하지만 [__main__.py](../device-runtime/src/asl_device/__main__.py)는 정상 return한 application에 대해 항상0을 반환한다. PowerShell wrapper의 `Write-Host $LASTEXITCODE`가 원인이 아니라 이미 Python CLI가0을 반환한다. 일부 wrapper 자체도 `-NoExit`/exit 전달 부재가 있어 child outcome과 task completion을 별도로 검증해야 한다.

새로 확인한 A2/B-host root cause는 §7에 분리했다. Liveness 8초 설정의 호환 문제는 재현됐지만 production engine patch를 요구하는 root cause로 확정하지 않았다.

## 5. 반증하거나 좁힌 기존 가설

1. **“N=5이면 5×관측시간이8초를 넘으면 항상 실패”는 거짓.** Engine은 다음 poll의 acquisition **전** timeout을 검사하며 `observe()`는 `now` 없이 결정한다. 다섯 번째 observation을 deadline 전에 시작하면9.58초에 완성해도 DIFFERENT가 된다. 2.5초 case는 다섯 번째를 시작하기 전에 reset된다.
2. **“한 번의 decode error가 바로 fatal”은 거짓.** Decode는3회 retry. Transport 예외가 첫 번에 종료되는 것은 재현됐다.
3. **“post-fatal10/10이면 직전 단발 HTTP timeout이 원인임이 확정”은 불가.** 이후 가용성만 확인된다. 마지막 exception/cause chain이 기록되지 않았다.
4. **“정상 host formatter만 고치면 FRAME 유실 해결”은 지지되지 않는다.** Direct serial burst도 손상됐다. 반대로 **“STM UART ORE가 이미 측정됐다”도 거짓**이다. ORE/FE/NE·wire trace가 없다.
5. **“PortAudio가 두 crash의 확정 원인”은 불가.** Lifetime overlap과 두 fault module은 확인했지만 stack이 없다. libcrypto fault가 HTTPS·hashing 자체 버그를 입증하는 것도 아니다.
6. **“H3 initial mode는 reading”은 launcher와 불일치.** Module default capture 이후 physical V,R로 reading에 들어간다.
7. **“physical DOWN follow-up은 V3 acceptance”는 반증.** 측정 packet은 V2 NAV,D,S,2다.
8. **“정확한 zero parse면 PCA/servo application도 성공”은 불가.** Print는 요청 상태이며 I2C return/실제 pulse/기계적 위치 증거가 아니다. Repeated clear는 host generation/encoding 문제의 증거가 아니다.
9. **“H1 event_count0 또는 H2 whole-file hash 차이는 해당 product path 실패/증거 손상”은 반증.** H1 수집 공백, H2 verified prefix 뒤 append로 설명된다.

## 6. Competing hypotheses와 부족한 evidence

| Incident | 경쟁 가설 | 닫는 데 필요한 최소 evidence |
|---|---|---|
| H1 actual liveness | 느린 snapshot/analyze/OCR; missing footer pair; quality hard reject reset; synchronous debug/preview/I/O 지연;8초 profile | 각 frame acquisition 시작/종료, analyzer 결과/reject reason, recognizer 결과·시간, collector start/reset reason, valid/missing count를 한 시계로 기록. 동일 source/구도8초 vs bounded30초 비교. 현재 tail의 valid1/0은 all-valid slow-only 재현과 다르므로 단독 원인 금지 |
| H1 terminal fatal | transport timeout/5xx; 연속 decode3회 소진; analyzer 예외; source stop/session 문제 | secret-safe exception class + HTTP status + attempt + stage + cause, 이후 recovery. Lost historical exception은 새 live snapshot으로 복원할 수 없음 |
| FRAME 손상 | STM polling starvation/overrun; HC-05 buffering/radio/전원; host COM virtual driver; debug 수집 손상 | TX bytes/MCU RX 동시 logic trace, ORE/FE/NE counters, actuator 변경0/일부/20개, direct UART와 HC-05 비교. COM5 logger만으로 wire-byte loss 위치 확정 금지 |
| Native AV | audio abort/close race; new-generation late stop; OpenSSL/urllib/cffi/driver lifecycle; 다른 native heap corruption | dump exception-thread 및 모든 관련 thread stack+symbol 상태; bounded isolated native playback-only, HTTPS-only, presenter-only, paired supersession tests. 같은 Windows interactive audio-device context 기록 |
| Clear residual | horn/cam/state0 angle, channel mapping, PCA I2C error/전원, physical retraction | 셀별 top/bottom residual map, 실제 PWM pulse·전압, I2C status, power-cycle clear. 측정 없이 LUT/global offset 수정 금지 |
| Required controls | continuity/label mismatch, installed pin map, switch contact, firmware image 차이 | actual PC0/PC1/PB1/PC2 voltage+continuity와 intended button labels, flashed artifact identity. 현재 absence trace는 broken pin을 확정하지 못함 |

## 7. 자체 source audit에서 발견한 새 defect/risk

실제 경로와 한 단계 인접 lifecycle/error path만 포함한다. 코드 스타일·일반 refactor는 포함하지 않았다.

| 새 ID · 분류 | Reachable trigger → wrong behavior / violated invariant | 독립 evidence와 기존 test gap | H1–H4 영향 · 최소 범위 |
|---|---|---|---|
| **A2 AUDIO-NEW-GENERATION-LATE-STOP / confirmed_product_defect / P1** | `ReadingAudioController._submit`이 pending job을 publish/notify한 뒤 lock 밖에서 stop. Worker가 먼저 replacement playback에 들어가면 그 stop이 새 generation을 중단 | Real controller + barrier fake playback에서 gen1 playback_started→reading_audio_failed, superseding gen 없음. 기존 fake Player는 즉시 완료/stop counter만 세며 이 interleaving을 막지 않음 | B09 latest-generation 음성이 시작 직후 잘릴 수 있음. A1과 같은 packet에서 stop 대상/epoch를 게시 순서와 일치시킴. Native lifetime lock만 추가하면 자동 해결된다고 가정하지 않음 |
| **B-host RELEASE-OVERTAKES-ACTIVATION / confirmed_product_defect / P1** | App가 synchronous 작업 중17+ input backlog. `_release_events`를 우선 가져와 poll16 한도를 채운 뒤 normal queue 일부만 가져옴. Batch 내 sort만 하므로 뒤 activation보다 release가 먼저 전달됨 | **Real StmSerialControlSource worker**, fake HELLO3→UP1…16→DOWN A17/R18. ACK18까지 확인. Poll1 release 포함, poll2 activation. Real HoldRepeatController는 물리 release 후 다시 active/late repeat1. 기존 tests는 작은 batch, full queue1의 BUSY, rehandshake release를 시험하나 cross-batch temporal order 미시험 | B01/B11 release stop invariant 위반. Host queue merge/order 또는 이미 release된 activation fencing만 좁게 수정. ACK/dedupe/hold650·180 유지. Firmware ring-buffer patch와 독립 subcommit |
| **C-clock COLLECTION-DEADLINE-NOT-HARD / probable_product_risk / P1 candidate** | Fifth observation이8초 전 시작·후 완료. `observe()`가 now 없이 DIFFERENT를 돌려 configured8초 이후 acceptance | 실제 engine fake-clock 결과9.58초. Completion-time bound가 계약인지 sample-start budget인지 문서에서 구분 부족. 기존 tests는 fake instant recognition/cadence | B03 cancellation/operator wait budget. 먼저 hard ceiling 의미를 확정하고 측정. N/identity gate 완화로 해결하지 않음. 현재 새 P1 확정/기존 severity 승격 없음 |
| **B-rx OVERFLOW-SUFFIX-ACCEPTANCE / probable_product_risk / P1 candidate** | `PumpBluetoothInput`에서 길이255 이후 한 byte를 버리고 length0으로 reset. Oversize line의 나머지 suffix가 FRAME로 시작하면 같은 line 끝에서 정상 parse 경로로 전달 | source-derived model: `X×256 + FRAME,… + LF`에서 FRAME suffix 전달. **Compiled C/HAL test 아님**. Firmware receive recovery native unit seam 없음 | B10 malformed line 뒤 동기화 오류. Compiled stub test로 승격 후 discard-until-newline 적용 후보. Grammar 변경 없음 |
| **B-pca APPLICATION-ERROR-NOT-OBSERVABLE / probable_product_risk / P1 candidate** | Motor_SetState/PCA I2C write가 HAL_ERROR/TIMEOUT인데 ApplyBrailleFrame은 void로 계속하고 ParseAndApplyFrame은1/ShowCurrentState 출력 | Code audit: 실패한 motor cache는 갱신하지 않지만 aggregate 실패와 실제 적용은 출력하지 않음. HAL-error injection과 PWM 측정 미실행 | B10 clear/physical application evidence 오독 위험. 먼저 stub HAL 실패·retry와 hardware I2C 측정. 최소 진단 status 후보; calibration patch 근거로 사용 금지 |

RX timing 모델은 MCU 측정을 대체하지 않는다. 9600 8N1은 약1.042 ms/byte인데 source에는 31문자 handshake debug 송신 약2.691 ms, main-loop control TX, 변경4모터마다100 ms delay가 있다. 최대20모터 변경에는5×100 ms delay가 들어간다. 이 동안 UART RX가 polling 밖에 있으면 loss가 가능하다는 가설을 모델로 확인했다. 모델 loss count를 실제 STM ORE count로 보고하지 않는다. 정확한 계산/문자열은 [firmware-model-results.json](evidence/software-diagnostic-20260908/firmware-model-results.json)에 있다.

Audit coverage: camera start/read/retry/stop와 response close, collector reset/ACK reference bank, page-change guidance, Application input drain/hold/release/presentation containment, authenticated WAV fetch/cache/cancel/close, stream worker/epoch, STM handshake/ACK/dedupe/reconnect/write ownership, firmware polling/line/parser/PCA, Coordinator fatal/CLI를 읽었다. S-01 namespace/S-02 pending lineage는 유지된다. Native exception은 Python presentation `except Exception`이 contain하지 못한다. Broad dependency upgrade, protocol redesign, unused legacy bridge, generic OCR 개선으로 확장하지 않았다.

## 8. Harness / environment / hardware 분류

- **test_harness_artifact:** H1 transcript 조각/summary event_count0; H2 config-vs-console capability mismatch; H3-R audio-disabled console stall; scripted bootstrap의 persisted-cursor 가정 차이; intermediate FRAME 억제; paced input. 각 사실의 fidelity 한계를 명시하며 product defect로 승격하지 않는다.
- **environment_failure:** 당시 phone battery/endpoint outage(기존 human/network report); H3 BOM config parse 실패; H2 process COM9 경합;8초 live-profile cadence 호환 문제; Desktop 보조 Python requests warning. BOM/COM9은 prepared/clean run evidence와 분리한다. Source/credential을 고쳐 해결했다고 주장하지 않는다.
- **hardware_or_wiring:** MODE solder, required controls 부재/오배선, clear residual 작업 분류. 실제 root measurement는 미완료다.
- **expected_behavior:** N=5 전에 UNKNOWN, hard-rejected/missing pair를 valid로 세지 않음, duplicate reference 보호, normal TEXT/choices empty braille→zero FRAME, latest-wins intermediate FRAME coalescing, input ACK≠physical applied. H2 첫 두 빈 snapshot에서 nonzero pattern이 없는 사실은 content defect가 아니다.
- **out_of_scope_observation:** 기존 math-limit/aligned-minus/choice-TTS와 focus-granularity Deferred. 이번 incident의 새 root cause와 직접 연결되지 않아 수정 후보에서 제외한다.

## 9. 수정 대상과 비수정 대상

즉시 **제안 가능한 confirmed source correction**: A1 native lifetime, A2 replacement late-stop, B-host cross-batch release ordering, C2 transport recovery/taxonomy, C3 timeout guidance, T1 strict preflight, T2 fatal exit result. 이 목록은 구현 승인이 아니다.

조건부 진단 우선: B-rx receive mechanism/overflow, B-pca error observability, C-clock deadline semantics. UART timing 모델이나 fault module만으로 interrupt/DMA·dependency upgrade를 미리 선택하지 않는다.8초→30초 runtime profile은 deterministic discrimination에서는 유효했으나 실제 source/구도에서 승인 가능한 bounded evidence를 추가해야 한다. 코드 threshold를 낮추지 않는다.

비수정: scanner N/K/candidate/identity/duplicate thresholds; FRAME grammar/cell encoding; V3 ACK/dedupe/press-release; stable device ID; auth/TLS scope; 기존 databases/artifacts; hardware pin/LUT/servo angles; 기존 content P1/Deferred. 새 architecture layer가 필요하면 work packet change budget 초과로 별도 보고한다.

## 10. Defect별 최소 patch 범위

| 항목 | 예상 product 변경 상한 | 변경 후 invariant / 유지 contract |
|---|---|---|
| A1/A2 | `adapters/reading_audio.py`, `reading_audio.py` 최대2 production파일 + targeted tests | Native stream lifecycle 한 owner/직렬 순서, old stop이 current epoch를 중단하지 않음, shutdown 후 native resource 종료. Auth refs/cache bounds/interruption/latest generation/completion guard 유지. Blocking write lock으로 input thread 무한 대기 금지 |
| B-host | `adapters/stm_serial.py` 최대1파일, 필요성이 재현된 경우에만 `hold_repeat.py`까지2파일 | activation/release의 세션·시간 순서를 poll batch 전체에서 보존, release 이후 stale activation 반복 없음. ACK/dedupe/queue BUSY/protocol/hold cadence 유지 |
| B-rx 조건부 | authoritative `Core/Src/main.c`, UART IRQ/MSP 관련 필요한 최소 파일 ≤3 + tests/build evidence | 완전 line consumer와 bounded RX buffering, overflow line 전체 discard+다음 newline 복구. ISR에서 PCA/debug 실행 금지. Baud/grammar/servo LUT 유지. DMA/IRQ 선택은 측정 후 |
| C2/C3 | `video/sources.py`, `video/engine.py`; mapping이 반드시 필요하면 existing scanner adapter까지3파일 | Retryable transport의 finite retry/recovery, auth/permanent 명시 실패, UNKNOWN guidance rate limit. Strict source와 scan/artifact/receipt lineage 유지. 무제한 retry/시간 제외 금지 |
| C-profile/clock | 새 isolated runtime profile과 문서 우선; engine 추가 변경은 clock test로 필요 입증 후 | N=5와 유한 wall-clock ceiling 동시 만족. 30초를 무조건 production default로 만들지 않음 |
| T1 | `laptop_acceptance.py` 및 existing factory의 작은 재사용만 | Configured Android source probe, webcam open0. Secret-safe diagnostic/TLS profile scope 유지 |
| T2 | `coordinator.py`/`application.py`/`__main__.py` 중 필요 최소 경로 + 사용 launcher≤1 | Fatal result 보존→nonzero, normal stop0; child code와 task lifecycle 분리. Feedback·durable lineage 변경 없음. 기존 D01 severity 유지 |

모든 packet은 source baseline/hash를 고정한 독립 변경으로 검토한다. 광범위 formatter/refactor·lockfile/dependency 재생성은 change budget 밖이다. B-host는 원래 제안에 없던 새 확인 결함이므로 firmware patch에 몰래 포함하지 않고 별도 subcommit/승인 범위로 표시한다.

## 11. Defect별 targeted regression

| 대상 | 수정 후 필수 regression |
|---|---|
| A1 | controllable native stub: start/write/abort/drain-stop/close 각각 중 supersession; same stream concurrent native call0; close exactly once; shutdown worker 종료; stop failure/cleanup error에서도 자원 유실 없이 explicit result |
| A2 | notify-before-stop adversarial scheduling; cached/fast fetch 새 generation이 늦은 old stop에 영향을 받지 않음; old generation completion0; latest generation 정확히 완료; interrupt 기능 유지 |
| B-host | backlog15/16/17/128, multiple A/R cycles, saturated queue release, disconnect/rehandshake release, dedupe retry, input namespace. Physical release 뒤 늦은 repeat0; ordered accepted action semantics 유지 |
| B-rx | compiled unchanged-C failing test부터: max valid line, ACK+FRAME back-to-back, split reads, CR/LF, oversize/suffix/malformed 후 다음 정상 line, actuator20 change blocking, overflow/error counters. 수정 후 firmware build/hash와 production-rate electrical RX exactness |
| C2 | Timeout→success,5xx→success, truncated JPEG→success(기존3 decode 보호), 지속 failure finite ceiling,401/403 no retry storm, TLS/auth file failure taxonomy, source stop/cancel 중 retry; release response/session; fallback0, duplicate artifact/receipt0 |
| C3 | page-change unknown timeout + missing/hard reject 구분, bounded rate-limit, recovery 후 guidance reset, same-page/unknown에서 false PAGE_CHANGED0, guidance→existing authenticated system cue |
| C-profile/clock | all-valid1.9/2.5 s, variable acquisition/OCR delay, invalid/reset series, deadline 직전 시작/직후 completion, finite30초 discrimination. N=5/K/duplicates unchanged, timeout 무한 확대 없음 |
| T1/T2 | strict factory-selected source identity/resolution, webcam constructor 호출0; 실제 Coordinator fatal→CLI child nonzero, normal/KeyboardInterrupt 정상 정책, launcher task-visible outcome 보존 |

현재 실행한 기존 targeted suite는 Laptop에서 **142 passed / 8.67 s**. Test files, interpreter, 새 C: temp root와 exit0은 [targeted-existing-tests.txt](evidence/software-diagnostic-20260908/targeted-existing-tests.txt)에 있다. Audio·STM·Application·hold·preflight·Scanner adapter/source/collector/engine tests를 포함한다. 이는 **수정 전 baseline/test-gap 확인**이며 위 신규 수정 후 tests를 이미 통과했다는 뜻이 아니다.

## 12. Subsystem / G3-A / fresh H1–H3 검증 순서

1. 독립 packet 승인 후 해당 failing reproducer를 acceptance regression으로 전환하고 최소 patch. A native lifecycle/epoch 우선, B-host queue ordering 및 B-rx 측정/확정 correction은 독립 유지.
2. Packet별 targeted tests → 관련 device-runtime/book-scanner/firmware subsystem tests. Camera profile만으로 해결되는 부분을 engine 변경과 분리한다.
3. 기존 hash-fixed G3-A regression replay: N5, spread2/fragment4/duplicate0, through2, fresh READY, S0 cursor/audio/frame semantics. 기존 PASS evidence는 덮어쓰지 않는다. 이번 진단에서 replay/upload는 하지 않았다.
4. Fresh H1: 새 isolated C: runtime + 새 datapack, same Android source pages26/27→28/29. seq1/2 durable ACK 이후 안내, CONFIRM LONG→fresh READY. Frame/identity/quality/reset/transport 단계별 시간을 보존한다. Console 허용 구간은 B01 substitute로 계속 표시한다.
5. Fresh H2: READY S0 + production sounddevice + production-rate STM presenter. nonzero→zero→nonzero, normal math/LEFT-RIGHT window/page/item, rapid supersession. Paced serial로 PASS 대체 금지.
6. Fresh H3: wiring/lever/clear 측정 및 필요한 hardware correction 후 production module, physical mode·CONFIRM S/L·PAGE NEXT/PREV·V3 DOWN A/R, speaker/physical braille/reconnect/reading exit-reentry/restart cursor. Event boot namespace와 generation lineage 기록.
7. A/B/C/T 각각 통과했어도 physical clear/필수 controls/actual native stability가 남으면 H4 진입 안 함. All green 후 H4 fresh full pipeline + H5가 요구된 경우 별도 수용.

향후 servo/native/live 시험은 실행 전에 목적·expected packet·stop condition·새 evidence root를 명시한다. 이번에는 이러한 물리 시험을 실행하지 않았다. 독립 correction은 다른 subsystem의 threshold/protocol/acceptance를 바꾸지 않는다.

## 13. H4 진입 가능 여부

**BLOCKED.** H1 two-spread/finalize/fresh READY 경로 미완료, production FRAME loss exact mechanism 미확정, native crash attribution 및 real speaker stress 미검증, required controls/lever/clear residual 미해결이다. 한 번의 physical DOWN V2 성공이나 paced nonzero PASS, 기존142 tests/G3-A PASS로 대체할 수 없다. 이 진단은 implementation scope 결정용이며 integration readiness 승인이 아니다.

## 14. Product source modification count

**0 files / 0 patches.** 새 파일은 진단 문서·reproducer·증거 사본/요약·제안 work packet뿐이다. Laptop에는 read-only SSH 조사 및 fake tests의 새 C: diagnostic temp만 사용했다. 기존 `C:\ASL_OCR`, integration product source, 기존 state/SQLite/artifacts/evidence, SSH/camera/server credentials를 변경하지 않았다. Laptop D: filesystem 접근0, firmware flash0, 실제 serial 송신0, servo 구동0, production upload0이다.

수정은 아직 승인·실행하지 않았다. 후속 검토용 독립 packet:

- [Native audio lifecycle](work-packets/H123_DIAG_NATIVE_AUDIO_WORK_PACKET_20260908.md)
- [STM receive integrity 및 독립 host release-order correction](work-packets/H123_DIAG_STM_INTEGRITY_WORK_PACKET_20260908.md)
- [Live camera liveness/recovery](work-packets/H123_DIAG_LIVE_CAMERA_WORK_PACKET_20260908.md)
- [Tooling / exit semantics](work-packets/H123_DIAG_TOOLING_EXIT_WORK_PACKET_20260908.md)
