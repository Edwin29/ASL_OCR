# Pi 시연 자동 시작 및 전체 전원 복구 시험

## 승인 범위와 기준

사용자가 반복 촬영보다 부팅 자동 실행 및 전체 전원 차단·재공급 복구 시험을 우선 승인했다. Pi·STM·PCA/서보가 함께 꺼지는 시연 구성이다. 직전 검증된45초 camera config, 실제 V3 controls/presenter, AUX audio, stable device ID 및 기존 durable state를 유지한다. 제품 소스는 변경하지 않는다.

## 준비 상태

2026-09-16 read-only 확인: 기존 production PID14672가 실행 중이며 부팅 ASL 서비스는 없었다. HC-05 `98:D3:02:96:9C:8C` paired/bonded/trusted, RFCOMM0 connected. 사용자 linger=yes, audio/dialout 권한 보유, ALSA 출력 bcm2835 Headphones. 비밀번호 없는 sudo는 불가하다.

준비 파일: [boot evidence](evidence/pi-boot-20260916/). Pi 복사 위치 `/home/user/ASL_OCR_PI/runtime/boot-setup-20260916`.

- root oneshot `asl-rfcomm`: Bluetooth 서비스 뒤 기존 주소/channel1에 RFCOMM bind. 기존 노드는 주소 일치 확인만 수행한다. 연결 인증이나 firmware 의미를 바꾸지 않는다.
- user `asl-production`: linger 사용자 세션에서 production module 실행. 90초 이내 RFCOMM 노드와 서버 TCP를 확인하며 실제 API/V3/audio 성공은 별도 로그/관측으로 판정한다.
- 실행마다 새 boot-id/PID/config hash manifest와 stdout 보존. 기존 로그 덮어쓰기 없음.
- 실패 종료 시15초 후 재시작,600초 내 최대5회 시작. 한도 초과 시 failed로 남기고 조사한다.
- 서비스 정지는 SIGINT,45초 종료 예산. 실제 전원 차단은 graceful 종료와 다른 시험이다.
- shell syntax, Python compile, systemd system/user unit verify 통과. user unit 배치 및 daemon-reload 완료. 아직 enable/start하지 않았으며 기존 앱은 유지 중이다.
- root 설치 명령 사용자 실행 요청 상태. root helper는 root-owned 경로에 설치한다.

## 실행 순서 및 완료 조건

1. root 설치 결과를 확인한다. 기존 앱의 읽기 cursor와 로그를 보존한 후 SIGINT로 종료하여 단일 앱/단일 serial owner를 확보한다.
2. user 서비스를 enable/start한다. production PID, config identity, V3 handshake, 서버 catalog 연결을 확인한다. 사용자가 AUX 및 물리 읽기/점자 정상 여부를 확인하면 서비스 실행 조건 PASS.
3. 새 데이터팩 #30에서 식별 가능한 지문/수식 위치를 정한다. 로그의 device cursor를 read-only 보존하고 pending upload/finalization이 없는지 확인한다. 그 뒤 사용자에게 전체 전원 차단→재공급을 요청한다. 데이터 쓰기 중 강제 차단 내구성 시험으로 확대하지 않는다.
4. 새로운 Linux boot-id, SSH 로그인에 의존하지 않는 앱 시작시각, 새 run log, 단일 PID, V3 연결 및 catalog를 확인한다. 사용자가 MODE/CONFIRM으로 같은 데이터팩을 선택하고 이전 위치의 실제 음성·점자를 확인한다.
5. 부팅 시작과 통신·출력·cursor 복구는 별도 판정한다. 새 boot-id 없이 서비스 restart만 한 결과는 전원 복구 PASS가 아니다. 전원 OFF 중 점 수납을 보장한다는 주장도 하지 않는다.

초기 앱 mode는 기존capture default를 유지한다. 실제 레버와 시작 화면 일치 여부를 관측하며 레버 왕복이 필요하면 제약으로 남긴다. Desktop production 서버와 Android 앱은 켜 두며 Pi 자동 시작이 외부 서버/카메라 부팅까지 관리한다는 의미는 아니다.

## 되돌리기

앱 자동 실행 중지: `systemctl --user disable --now asl-production.service`.
root binding 자동 실행 중지: `sudo systemctl disable asl-rfcomm.service`.
기존 수동 production 명령으로 복귀 가능하다. 상태/로그/페어링을 삭제하지 않는다. 현재 연결 중 RFCOMM release는 수행하지 않는다. 서비스 파일은 비활성 상태로 보존할 수 있다.

준비 시점 판정: 준비 및 정적 검사 완료, 서비스 시작/부팅/전원 복구 미실행. 최종 결과는 아래 후속 기록 참조. 제품 수정0.

## 서비스 실행 확인

사용자 root 설치 완료 후 `asl-rfcomm` enabled/active 확인. 기존 production PID14672는 SIGINT 후 exit0(UTC2026-09-15T15:53:42)로 종료했다. 기존 로그를 `pre-service-production.log`로 보존했다.

`asl-production` user service enable/start 완료. PID15776, restart0, active. run `runtime/boot-20260916/20260915T155345Z-15776`에서 production entrypoint, server_connecting, capture catalog의 #30 안내, 실제 audio adapter playback_completed를 확인했다. 이 단계는 동일 부팅 안의 서비스 실행이며 실제 cold boot 성공은 아직 아니다. MODE/읽기/점자 사용자 관측과 기억할 복구 위치를 요청했다. 전원 차단은 아직 안내하지 않았다.

사용자가 준비 완료를 보고했다. 전원 차단 전 `pre-power-off.log`, `pre-power-cursor.json` 보존. 기존 boot-id `4f41073e-238f-4c80-a0f4-e0980141278f`, PID15776/restart0. 서버 durable reading_progress는 #30 revision1, page_index0/node_index6, focus `pg-6eb58202c4d6-00000001-L-vl006`, braille_offset0, generation60이다. 같은 generation의 음성 완료 로그도 확인했다. 해당 capture 세션은3건 acked 및 sealed/published 상태를 재조회했다. 전체 전원 차단·재공급을 안내하며 아직 결과는 pending이다.

## 전체 전원 복구 결과 — PASS (이번 시험 범위)

사용자 보고: “부팅 후 약 1분에서 2분 뒤 리딩모드 선택화면입니다 음성 나옴. 나머지는 모두 정상작동.” 전체 전원 차단·재공급 후 안내, 이전 읽기 위치, 버튼/음성/점자 정상 여부에 대한 직전 묶음 절차의 사용자 관측 PASS로 기록한다.

- 새 boot-id `212dd0f2-1ac9-4227-aa47-b34ebf6024ec`로 실제 재부팅 확인.
- `asl-production` active, PID997 한 개, NRestarts0. `asl-rfcomm` active, HC-05 RFCOMM connected. 수동 실행 명령 없이 부팅 서비스가 실행한 manifest 확보.
- config SHA256은 직전45초 검증 설정과 동일. 제품 코드 변경 없음.
- `reading_resumed`의 모든 cursor 필드가 차단 전 서버 reading_progress와 정확히 일치한다. 동일 데이터팩/page/focus/node/offset/generation60 복구를 진단 코드 assertion으로 대조했다. 이후 조작으로 generation65까지 이동하고 음성 완료가 기록됐다.
- 실제 음성/점자/버튼 정상은 사용자 관측 근거다. 이번 run에는 별도 V3 wire trace가 없어 재부팅 직후 handshake packet 자체를 새로 채증했다고 주장하지 않는다. V3-only production 구성의 물리 기능 복구와 raw handshake 수용 시험은 구분한다.

시간·초기 MODE 구분: 사용자 체감 안내 시간은1~2분. 앱 monotonic 로그는 약45.34초에 capture catalog, 약45.41초에 첫 audio 시작, 약464초에 reading 전환을 기록했다. 따라서 reading 모드로 즉시 부팅했다고 확정하지 않는다. 레버 자동 초기 동기화 여부는 이번 보고만으로 분리할 수 없다. 벽시계의 service 시작시각과 `uptime -s`가 역전되어 초기 시각 동기화 영향 가능성을 남기며 wall-clock 차감으로 부팅 소요시간을 계산하지 않았다. user journal은 이 환경에서 조회되지 않아 파일 로그를 근거로 사용했다.

근거: `post-power-on.log`, `post-power-manifest.json`, `power-recovery-result.json`, `evidence-sha256.json`.

완료: 시연용 부팅 자동 실행 및 읽기 대기 상태의 전체 전원 차단·재공급 후 복구1회. 잔여 범위: 동일 촬영 조건의 반복 재현성. 업로드/DB 쓰기 도중 강제 전원 차단, 무제한 반복 전원 시험, 모든 H4 체크리스트 완료를 의미하지 않는다. 시연 시 외부 서버/카메라를 준비하고 안내 후 모드를 확인해 데이터팩을 선택한다. 자동 실행 서비스는 활성 상태로 유지한다.
