# Critical-path architecture assurance evidence

이 폴더는 2026-09-08 architecture assurance의 새로운 Desktop 진단 산출물이다. 이전 `software-diagnostic-20260908` evidence는 수정하지 않았다.

- `assure.py`: 기존 read-only SSH helper를 이용한 identity/probe driver. Laptop에서 Python stdin 실행, `-B`, 실제 source import; 새 Laptop 파일 생성0.
- `source-identity-before.json`, `source-identity-after.json`: Desktop/Laptop246개 product source와 interpreter/import 위치. 이전 진단 종료본과 비교.
- `probes.py`, `laptop-probes.json`: 실제 Python object + fake boundary. CP-I1 camera read 동안 input/cancel 대기, CP-H1 timeout partial-line의 잘못된 seq ACK, CP-T1 fatal STOPPED 뒤 connectivity stop 생략.
- `finish.py`, `integrity.json`: source 무변경, local evidence hash index, report link 확인. Remote state/DB의 최신 내용 재수집을 주장하지 않는다.

각 probe의 assertion PASS는 **현재 결함/구조 의존성 재현 성공**이다. H1/H2/H3/H4 acceptance, native driver 안정성, compiled firmware, UART, PCA, servo 물리 적용을 검증하지 않는다. Physical I/O0, credential/config 변경0, Laptop D: 접근0. 모든 fake thread/connection은 정리했다.

재실행 명령(Desktop):

```powershell
python -B docs/evidence/critical-path-architecture-assurance-20260908/assure.py identity source-identity-before.json
python -B docs/evidence/critical-path-architecture-assurance-20260908/assure.py probe
python -B docs/evidence/critical-path-architecture-assurance-20260908/assure.py identity source-identity-after.json
python -B docs/evidence/critical-path-architecture-assurance-20260908/finish.py
```

보존된 evidence를 덮어쓰지 않으려면 재시험은 새 날짜/id의 복제된 diagnostic directory에서 수행한다. 현재 사용된 파일 hash는 integrity.json을 참조한다.
