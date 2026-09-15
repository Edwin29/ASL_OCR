# Raspberry Pi4 전원 운용 기준 H4 이전 검증 재평가

## 판정

사용자가 최종 시연 환경을 Pi4, 전원 투입 후 자동 앱 시작, 종료는 전원 차단으로 확정했다. 기존 Laptop H1/H2/H3는 핵심 소프트웨어·물리 통합 회귀 증거로 유효하지만 최종 플랫폼 및 전원 lifecycle acceptance를 대신하지 못한다. Laptop Ctrl+C/앱 재시작에 집중한 최근 점검은 개발·장애 진단 가치가 있으며, 최종 시연 준비의 우선순위는 Pi cold boot와 전원 차단 후 복구로 바꾼다.

근거: `HW_SW_INTEGRATION_PLAN.md` 단계7은 Pi가 실제 최종 대상이면 target validation을 전체 완료 범위에 포함하도록 명시한다. 이번 계획에서는 이를 H4 이후 선택 작업이 아니라 **최종 H4 이전 target 준비 gate**로 취급한다. 추가 Laptop H4는 필요 시 진단용이며 최종 수용은 Pi에서 수행한다.

## 기존 증거의 적용 범위

| 검증 | 계속 유효한 부분 | 최종 Pi에서 다시 확인할 부분 |
|---|---|---|
| H1 두 spread/receipt/READY | 서버·parser 및 선택 교재 성공 경로 | Pi camera decode/orientation, M1/UVDoc 실행·처리 간격, capture 중 입력 지연 |
| H3 물리 reading | firmware mapping/LUT, FRAME, 버튼 의미, 같은 cursor 출력 | Linux Bluetooth transport·권한, 실제 AUX 출력과 동시 실행 |
| V3-only와 bounded retry | fallback 차단과 늦은 연결 재시도 코드 | Bluetooth 준비가 늦는 cold boot에서 양방향 V3 확인 |
| Laptop Ctrl+C 정리 | application/COM/audio cleanup 코드 동작 | 전원 차단에서는 cleanup이 실행된다고 기대하지 않음 |
| 앱 재시작 cursor 복구 | 서버 cursor와 재진입 의미 | 실제 Pi 저장 매체·자동 서비스 계정·전원 차단 후 복구 |
| 첫 UP로 재접속 | STM만 계속 켜진 상황의 관측된 운용 우회 | 전체 동시 cold boot와 다름; 전원 topology에 따라 우선순위 결정 |

## 전원 구성에 따른 조건부 판정

Pi/STM/PCA·서보가 함께 꺼지면 STM의 이전 connected 상태도 사라지므로 정상 cold boot에서 Laptop 앱 단독 재시작과 같은 잔존 연결 조건은 그대로 적용되지 않는다. 다만 전원 투입·PCA 초기화·Pi 부팅·Bluetooth 준비의 시간차는 실제로 검증해야 한다. STM이 계속 켜져 있고 Pi만 꺼진다면 입력1회로 깨우는 제약은 정상 운용 경로에 직접 해당한다. 사용자가 **Pi4·STM·PCA/서보 모두 함께 꺼짐**을 확인했다. 따라서 정상 종료·재시작 검증은 전체 cold boot를 기준으로 하고 앱만 재시작하는 무조작 reconnect는 정상 시연 필수 gate에서 제외한다. 기존 UP1회 우회는 앱 crash/서비스 재시작 같은 보조 경로에만 유지한다.

## 우선순위와 완료 조건

1. **P0: Pi 실제 런타임 이식 및 자동 시작 준비.** OS/architecture/Python과 native 의존성·model asset·import identity를 확인한다. 앱 계정에서 기존 인증·TLS profile, writable persistent outbox/artifact 경로, Linux HC-05 장치 경로/권한, AUX 유선 이어폰 출력을 준비한다. stable device identity는 보존하되 Laptop과 Pi를 같은 identity로 동시에 실행하지 않는다. SSH 수동 실행 성공과 로그인 없는 자동 시작 성공을 분리한다. `RasberryPITest/raspberry-pi-load.service`는 합성 부하용이며 production launcher가 아니다.
2. **P0: 실제 전원 투입→무로그인 사용 가능.** 선택한 전원 구성 그대로 제한된 cold boot 시험을 수행한다. 서비스1개, network/server/camera 접근, V3 HELLO/ACK와 MODE, 부팅 CLEAR 실제 수납, READY 선택·AUX 음성·물리 점자까지 확인한다. Catalog 음성만으로 연결 준비를 판정하지 않는다. 정상1회와 준비 순서가 늦는 조건1회 등 최소 표본으로 시작하고 시간·실패 원인·수동 개입을 기록한다. 엄격한 임의 부팅 SLA는 새로 만들지 않는다.
3. **P0: 전원 차단 후 복구.** 실제 시연용 원본 evidence를 보존한 별도 진단 state에서 수행한다. 먼저 안정된 READY reading 위치에서 전원 차단/재투입 후 filesystem/DB 접근·같은 cursor·출력 복구를 확인한다. 이어 수집/전송 중 전원 차단이 시연상 가능한 만큼 pending outbox 및 서버 receipt 경계의 replay/idempotency를 대상으로 한 bounded 시험을 설계한다. 이미 receipt가 완료된 spread가 중복 생성되지 않는지와 미완료 spread가 조용히 사라지지 않는지 구분한다. SQLite BEGIN/COMMIT(`delivery_store.py:87`)과 sending→retrying 복구 로직, 파일 fsync/rename 일부 구현은 확인되지만 실제 저장 매체의 전원 차단 내구성 증거는 아니다. Pi에서 실제 설정·저장소 특성을 확인하기 전 defect나 무손실 보장을 단정하지 않는다.
4. **P0: Pi에서 H4.** 전원 자동 시작 후 physical controls→두 spread→durable receipt→CONFIRM LONG fresh READY→page/item/math-window→AUX 음성+같은 generation 물리 점자를 확인한다. 처리량은 선택 교재/한정 경로로 평가하며 Scanner threshold나 timeout을 완화하지 않는다.

## 후순위/비필수 항목

- Windows PowerShell native exit code null 해결: Pi 최종 시연의 gate에서 제외, 개발 실행기 관측 한계로 유지.
- Ctrl+C 자동 CLEAR: 전원 차단은 코드 정리 기회를 보장하지 않으므로 최종 전원 종료 해결책이 아니다. 물리 점 잔류 여부와 다음 부팅 CLEAR를 관측한다. 전원 차단 순간 자동 수납을 요구한다면 전원/기구 조건까지 별도 계약이 필요하지만 현재 그런 요구는 추가하지 않는다.
- 무조작 앱 단독 재접속 완전 자동화: 동시 전원 차단이면 장애/운영 보조 경로로 내리고 기존 UP1회 우회를 유지할 수 있다. Pi만 재시작하는 구성이라면 cold boot 절차에 포함해 검증한다.

## 변경 범위와 미확인 사항

이번 재평가는 문서 변경만 수행한다. Pi에 접속하거나 전원 차단·서비스 설치·새 firmware 적용은 하지 않았다. Pi가 현재 켜져 있는지, OS/실제 storage/audio/Bluetooth 서비스 구성은 아직 확인하지 않았다. 과거 Windows 환경과 RaspberryPi 부하 fixture만으로 Linux 설치 가능성이나 latency를 단정하지 않는다. 현재 플랫폼 의존성/권한/자동 서비스 배치 작업이 필요하다는 근거는 있으나 핵심 architecture 재설계가 필요하다는 근거는 없다. 최종 H4 ready 판정은 위 gate 증거 뒤에 한다.
