# 프로토타입 제출·재현용 소프트웨어 산출물

2026-09-16 정리 기준. Git 기준점 `8f5bb4393ac0730068b3e767666e862a1a51125f` 이후 승인되어 구현·검증된 소프트웨어와 펌웨어, 최종 보고서 및 선별 증거를 게시한다. 이번 정리는 새 기능 개발이나 하드웨어 재시험이 아니다.

## 우선 읽을 문서

- [최신 기능 점검과 보고서 수록 후보](PROTOTYPE_REVIEW_AND_SW_REPORT_ITEMS_20260916.md)
- [정정 반영 설명문: Page IR·AST·판별 규칙·전송 조건](SW_REPORT_REVISED_EXPLANATIONS_20260916.md)
- [수록 우선순위](SW_REPORT_CORRECTIONS_AND_PRIORITY_20260916.md)
- [Technical Overview](ASL_OCR_TECHNICAL_OVERVIEW.md): 9월 10일 기준 알고리즘 설명. 현재 Pi 배포·카메라 재시도·검증 상태는 아래 최신 문서가 우선한다.
- [Pi 촬영 결과](PI4_PRODUCTION_CAPTURE_RESULT_20260916.md), [부팅·전원 검증](PI4_BOOT_POWER_VALIDATION_20260916.md), [카메라 재연결 수정](PI4_CAMERA_RECONNECT_CORRECTION_20260916.md)
- [운용 주의사항](PROTOTYPE_DEMO_OPERATION_NOTES_20260915.md)

## 포함 범위

1. ARM CPU에서 OCR 추론 스레드를 한 개로 지정한 수정과 재연결 가능한 카메라 오류의 반복 재시도.
2. STM host의 V3 기본 경로, 연결 협상 제한 시간과 재접속, 초기 MODE 이후 최신 FRAME 1회 재송신.
3. 하드웨어팀의 모터별 실측 펄스표, 검증한 GPIO/PCA 배선 반영, 논리적인 셀 순서 보정을 포함한 production 펌웨어 `main.c`, `main.h`, `.ioc`.
4. 관련 회귀 테스트, H1 이후 통합 기록, Pi 실행·부팅 구성의 실제 스크립트와 선별된 검증 증거.

파일별 길이와 SHA-256은 [게시 파일 목록](evidence/release-20260916/publication-files.json)에 기록한다. 해시는 게시 준비 시 로컬 파일 바이트 기준이다. Git의 줄바꿈 정규화에 따라 다른 운영체제 checkout의 바이트 해시는 달라질 수 있다. 이전 실행 증거에 적힌 해시는 해당 실행 당시 배포 파일의 해시이며 현재 파일로 덮어쓰지 않는다.

## 현재 배포와 호환성

현재 시연은 Android IP Camera → Pi 4 → Desktop OCR/parser/Piper 서버 → Pi AUX·HC-05 → STM/PCA/점자 셀 경로다. Pi의 기존 config, 모델, 페어링, 인증 파일과 장치 ID를 사용한다. 단순 clone만으로 이 외부 환경까지 생성되지는 않는다.

- Pi 시연 config의 페이지 식별 수집 제한 시간은 45초다. N=5, SAME 1회 일치 차단 등 기존 식별 조건은 유지한다.
- 부팅 스크립트는 [pi-boot 증거 폴더](evidence/pi-boot-20260916/)에 포함한다. 실제 설치 경로를 사용하는 배포 기록이며 범용 설치 프로그램은 아니다. `install_root.sh`는 기존 서비스가 없을 때만 설치하도록 되어 있다.
- 최신 카메라 재연결 코드는 Desktop과 Pi에 배포되었고 Laptop에는 이 정리 작업에서 새로 배포하지 않는다.
- Laptop의 기존 source·runtime·상태와 펌웨어 백업은 보존한다. 펌웨어를 이번 게시 작업에서 다시 flash하지 않는다.

## 게시 전 검증

- 카메라 복구·ARM 설정: **19 PASS** ([scanner.xml](evidence/release-20260916/scanner.xml)).
- STM host·MODE 계약: **44 PASS** ([host.xml](evidence/release-20260916/host.xml)). Windows pytest 캐시 기록 권한 경고 1건이 있었으며 테스트는 통과했다.
- Desktop의 production `main.c`와 host source 해시가 기존 V3 배포 기록에 일치함을 확인했다. 이번에는 재빌드·재플래시하지 않았다.
- 신규 게시 대상의 크기와 credential 패턴을 검사했다. 인증 키·비밀번호·개인 키·실행 SQLite는 포함하지 않는다.
- 첨부 DOCX는 수정하지 않는다. 정정 반영 설명은 별도 Markdown 산출물이다.

전체 회귀검사나 새로운 H4 수용 시험을 이번 63개 검사로 대체하지 않는다. 실제 사용자 관측, 서버 저장 응답, READY 게시와 모의 어댑터 검사는 각 보고서의 구분을 유지한다.

## 저장소와 로컬 보존 범위

저장소에는 재현에 필요한 코드·설정 예시·보고서·선별 증거를 넣는다. 대용량 원시 촬영 이미지, crash dump, 모델, 가상환경, DB·사용자 상태, 개인 실행 config와 나머지 원시 실험 자료는 로컬에 보존한다. 보고서의 과거 경로와 해시 목록에는 이 비공개·미게시 원시 자료를 가리키는 항목도 있다. GitHub에 보고서가 있다는 사실만으로 원시 자료 전체가 백업됐다고 간주하지 않는다.

Laptop C: 정리는 실제 점유 조사 후 재생성 가능한 pip 다운로드 캐시를 대상으로 한다. 모델과 설치된 패키지는 실행 자산이므로 pip 다운로드 캐시와 구분한다. 정리 결과와 확보 용량은 별도 후속 기록에 남긴다.
