# ASL_OCR Hardware Integration H0 Status — 2026-09-07

적용 계획: `HARDWARE_INTEGRATION_EXECUTION_PLAN_20260907.md`의 H0.

현재 판정은 **H0 BLOCKED / MODE-LEVER-SOLDER-P1**이다. 자동 preflight, Android IP Camera의 실제 촬영 구도와 장시간 transport, 실제 스피커 청취, STM flash/verify, PCA address startup 및 v3 handshake는 통과했다. Post-flash actuator의 의도하지 않은 움직임·걸림·발열·냄새가 없고 비상 전원 차단이 가능하다는 human observation도 통과했다. 물리 mode lever의 납땜 단선이 확인되어 전체 입력 준비만 닫히지 않았다. H1은 시작하지 않았다.

## 자동 PASS evidence

| 항목 | 결과 |
|---|---|
| Laptop run root | `C:\ASL_OCR_INTEGRATION_RUNTIME\demo-20260905\hardware-integration\h0-20260907-205411` |
| source baseline | HEAD/diff set 및 stabilization transplant hash 일치 |
| imports/dependencies | integration checkout 격리 유지, `pip check` PASS |
| model identity | 기존 G0 hash 10/10 재확인 |
| runtime/config | production parser full parse PASS, `laptop-device-001`, D: dependency 0, isolated state writable |
| Desktop server | loopback와 Tailscale health HTTP 200, 동일 server instance |
| auth/audio transport | authenticated Piper system cue fetch PASS |
| camera enumeration | `720p HD Camera`, stable identity digest `51ce622de8130013`, 장치 1개 |
| camera transport | DirectShow, selector-guarded index 0, 요청/실효 `1280×720`, 약 30 fps, `YUY2`, 20/20 frame, liveness PASS |
| Android camera adjusted stability | production source와 같은 HTTPS snapshot 경로에서 약 548초 동안 `4000×3000` 418/418 frame, fetch failure 0 |
| Android camera strict probe | production parser/factory와 최소 `3000×2000` 기준으로 3/3 decode, `4000×3000`, unique pixel hash 3/3, fallback 0 |
| Android camera final preview | page 26/27, 네 모서리·중앙 seam·좌우 순서 보존; 사용자 조정 완료 확인, preview SHA-256 `9662af8d94d742eb449474d18e24dc4ca507a7069a04eabe8b613565c17856cd` |
| STM source | Desktop/Laptop normalized hash 3/3 일치 |
| firmware build | CubeIDE 2.2.0 clean build, 0 errors/0 warnings |
| firmware artifact | `kitel2026final.elf`, SHA-256 `62ecee2ccc811cf046466d38e80001f959f27a6f256f803903769289b9556c05` |
| firmware flash | 지정 ST-Link `0670FF485775495067203341`, STM32CubeProgrammer 2.23.0, download/verify/software reset PASS, target voltage 3.24 V |
| COM5 startup | `115200` baud passive capture; `PCA 0x40 FOUND`, `PCA 0x41 FOUND`, `PCA INIT OK`; UART transmit 0 |
| COM9 handshake | `9600` baud; `HELLO,3` observed, 12-byte `ACK,HELLO,3` written, COM5에서 `BT: HOST CONNECTED (V3 EDGES)` 확인; FRAME 0 |

MSMF/MJPG 최초 probe는 실제 FourCC 불일치로 실패했다. 같은 장치가 DirectShow/YUY2에서 요청 해상도·FPS·FourCC와 정확히 일치하여 runtime-only camera 설정을 그 조합으로 고정했다. 제품 source와 scanner acceptance threshold는 변경하지 않았다.

## 아직 닫히지 않은 항목

1. 최초 저장된 Laptop 전면 카메라 preview는 폐기 후보 진단 evidence다. 실제 integration source는 아래 Android IP Camera로 교체됐고 새 preview의 최종 구도는 통과했다.
2. Laptop에서 `HC-05`가 Bluetooth identity `98D302969C8C`, `COM9`으로 계속 매핑된다. 실제 reset 동기화 시험에서 `HELLO,3 -> ACK,HELLO,3`와 STM 측 `BT: HOST CONNECTED (V3 EDGES)`가 모두 확인됐다.
3. USB 재연결 후 ST-Link Virtual COM `COM5`가 계속 열거된다. 지정 probe `0670FF485775495067203341`로 SHA-256 `62ecee2ccc811cf046466d38e80001f959f27a6f256f803903769289b9556c05` ELF를 download/verify/reset했고 모두 PASS다.
4. COM5 부팅 로그로 PCA9685 `0x40/0x41` presence와 init는 확인했다. 하드웨어팀이 동일한 공통 핀/PCA map의 이전 `final main.c`에서 dummy data로 actuator 정상 동작을 확인했다는 human evidence가 제공됐다. 해당 코드의 PB8/PB9 I2C, PA9/PA10 HC-05, PA0/PA1/PA4/PB0/PB1 button 및 `0x40 CH0~9=top`, `0x41 CH0~9=bottom` map은 현재 source와 일치한다. 실제 current FRAME-to-cell/dot 방향은 H2에서 다시 확인한다.
5. SSH 비대화형 재생은 실제 사용자 audio session의 판정 근거가 될 수 없어, preview와 WAV를 로그인된 `user` interactive session에서 실행하는 일회성 scheduled task를 사용했다. 사용자가 실제 Piper 안내 청취를 확인하여 speaker playback은 PASS다.
6. 사용자는 actuator 전원을 별도로 차단할 수 없지만 STM·Raspberry Pi·motor 공통 전원을 즉시 끄는 독립 ON/OFF switch가 있다고 확인했다. 이를 H0 비상 차단 수단으로 기록한다. Flash/reset 후에도 의도하지 않은 움직임, 걸림, 발열, 냄새가 없음을 확인했다.

## 새 hardware issue — MODE-LEVER-SOLDER-P1

- 분류: **P1 / hardware integration incident**
- 재현·evidence: current firmware handshake 직후 `NAV,V,R,1`; current source에서 PC2 pull-up HIGH는 reading/released다. 사용자가 물리 lever 납땜 단선을 확인했다.
- first failing boundary: 물리 lever contact -> PC2 mode GPIO. STM/HC-05/host protocol 이전 경계다.
- 현재 영향: PC2는 pull-up HIGH에 고정된 것으로 관측되어 reading mode는 선택할 수 있지만 물리 lever로 capture LOW와 reading HIGH를 전환할 수 없다.
- H1 containment: production `controls=console`에서 `lever activated`/`lever released`를 사용한다. 제품 source 수정이 없고 H1의 원래 계획과 일치한다.
- H2 containment: 승인된 runtime-only console+STM presenter harness에서 console lever event를 사용한다. 물리 lever 합격을 주장하지 않는다.
- H3 containment: fixed HIGH/reading과 `--initial-mode reading`으로 STM navigation/audio/FRAME/actuator 경로는 시험 가능하다. mode lever input 항목은 BLOCKED로 남긴다.
- H4: 실제 capture -> reading 물리 전환이 필수이므로 수리 전에는 전체 PASS 불가하다.
- bench-only 대안: 정확한 NUCLEO-F446RE PC2 header 위치를 board schematic에서 확인한 뒤 전원을 끈 상태에서 PC2-GND 임시 jumper를 연결하면 capture LOW, 제거하면 internal pull-up에 의해 reading HIGH를 만들 수 있다. 이는 lever의 전기 신호를 대체하지만 기계 lever acceptance를 대체하지 않는다.
- 금지된 우회: firmware에서 lever 입력 무시/상수화, protocol 변경, STM mode event suppression, production composition에 숨은 두 번째 input source 추가.
- 최소 영구 해결 범위: PC2 lever 납땜 복구 후 A/R edge, debounce, 재연결 initial mode event를 재검증한다. 제품 source 수정은 필요하지 않다.

## 새 software diagnostic issue — ANDROID-PREFLIGHT-SOURCE-P1

- 분류: **P1 / preflight diagnostic boundary**, 현재 실제 runtime path에서는 contained
- 재현: H1의 `android_ip_camera` config로 `python -m asl_device --preflight` 실행 시 `e0b_profile`은 `physical E0-B requires pc_camera or android_uvc`로 실패한다. 동시에 별도 `camera` check는 Android HTTPS source가 아닌 Laptop 내장 camera `640×480`을 검사해 PASS를 반환한다.
- first failing boundary: `asl_device.laptop_acceptance`의 profile/source 선택. Production `build_local_device`와 `_default_scanner_factory` 이전의 검증 도구 경계다.
- 위험: 이 preflight의 camera PASS를 Android runtime camera readiness로 오인하면 wrong-camera 또는 저해상도를 숨길 수 있다.
- containment: 해당 preflight camera 결과를 H1 evidence에서 제외한다. Production parser/factory를 사용한 strict Android probe의 source type, no-fallback, `4000×3000`, 418-frame stability와 actual operator preview만 사용한다.
- 현재 integration 영향: production scanner/runtime source 불일치 증거는 없으므로 H1 실행은 가능하다. Repository-defined preflight의 Android profile 지원은 후속 bounded software pass에서 수정·회귀해야 한다.
- 제품 source 수정: 0

사용자가 제공한 이전 `final main.c`는 공유 핀/PCA 배선 evidence로만 사용한다. 이 코드는 현재 authoritative v3 source에 있는 PC0 page-previous, PC1 confirm, PC2 mode lever, `HELLO,3`, ACK/sequence/dedupe 및 DOWN A/R contract를 포함하지 않으므로 firmware replacement 후보가 아니다.

## STM flash/startup/handshake evidence

- flash tool: STM32CubeProgrammer 2.23.0
- target: `STM32F446xx`, device ID `0x421`, NUCLEO-F446RE, target voltage `3.24 V`
- ST-Link: serial `0670FF485775495067203341`, firmware `V2J48M35`
- ELF identity: SHA-256 `62ecee2ccc811cf046466d38e80001f959f27a6f256f803903769289b9556c05`
- flash result: erase/download/verify/software reset PASS
- startup: both PCA addresses found and init PASS
- wireless: COM9 received `HELLO,3`; host sent only `ACK,HELLO,3`; COM5 confirmed `BT: HOST CONNECTED (V3 EDGES)`
- no braille FRAME was transmitted
- after handshake the STM emitted `NAV,V,R,1`, representing the current mode-lever release edge. It was not ACKed or applied to a Device Runtime in this isolated handshake probe. H1 must record the physical lever position and production handling of the initial event.

## Android IP Camera 전환

사용자는 H0/H1의 실제 카메라로 Android IP Camera 앱과 `https://192.168.1.78:4444`를 지정했다. 기존 전면 카메라 probe는 transport 진단 evidence로만 보존하고 실제 integration camera 선택에서는 제외한다.

최초 network boundary 확인 당시 Laptop은 `172.100.4.84`여서 접속이 timeout됐다. 이후 Laptop Wi-Fi가 `192.168.1.53/24`로 전환되어 카메라와 같은 사설망에 들어왔다.

Production `android_ip_camera` source가 `/video/snapshot?camera=back&snapshot_res=max`를 Basic credential-file 참조로 열었다. credential 값과 hash는 evidence에 기록하지 않았다. 앱 인증서는 OS trust store에서 신뢰되지 않아, 이 run은 profile이 명시적으로 지원하는 self-signed/insecure TLS runtime mode를 사용했다.

- profile: `android_ip_camera`
- fallback: 없음
- raw/effective frame: `4000×3000`
- transport: HTTPS snapshot, rear camera, maximum resolution
- frames: 3/3 decoded, unique frame 3
- preview SHA-256: `79608fcf4c854b640a856d41a2335db1c4a9100b1b62271aeb5df977cdb71b66`
- config SHA-256: `d0141e08b62b56ac27b6765c9d873fa1c74a6a3a9908b95ab23c8b870d0aa387`

조정 뒤 자동 영상 검사는 펼침면 전체, 중앙 seam, landscape 방향, 26/27 페이지와 검은 배경을 확인했다. 사용자는 실제 촬영 화면 조정을 완료했다. 최종 strict preview에서도 네 모서리, page 26 left/page 27 right와 수식·본문 판독 가능성을 확인했으므로 H0 camera framing/transport는 PASS다.

휴대폰 앱의 가로 미리보기와 실제 `snapshot_res=max` 4:3 frame의 시야 차이를 해결하기 위해 Laptop interactive session에 actual-source live preview를 추가했다. 버퍼링 중에도 마지막 frame을 유지하고 재접속하며, production 최소 해상도는 변경하지 않은 채 저해상도는 빨간색, `3000×2000` 이상은 초록색으로 표시한다. 조정 세션은 `4000×3000` 418 frame과 failure 0을 기록했다. 이후 production factory strict probe는 3개 frame 모두 `4000×3000`, pixel hash 3개 고유, preview SHA-256 `9662af8d94d742eb449474d18e24dc4ca507a7069a04eabe8b613565c17856cd`로 통과했다. 이 뷰어는 runtime-only 진단 도구이며 product source 변경은 아니다.

조정 전 한 차례 source가 `960×720`으로 내려가 기존 strict viewer가 종료됐다. 이는 production threshold 위반을 정확히 검출한 demo capture-condition event다. threshold를 완화하지 않았고, 조정 뒤 장시간 및 strict probe에서 재현되지 않아 현재 H0 blocker는 아니다.

이번 H0 작업의 product source modification은 **0**이다.
