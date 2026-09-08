# H1/H2/H3 diagnostic evidence — 2026-09-08

[판정/제안 보고서](../../H1_H2_H3_SOFTWARE_DIAGNOSTIC_RESULT_20260908.md)가 주 산출물이다. Product source는 변경하지 않았다. 이 폴더의 scripts는 diagnostic code이며 production에 주입하거나 서비스로 실행하는 파일이 아니다.

| Evidence | 해석 |
|---|---|
| source-identity-before/after.json | Desktop/Laptop production source246개 raw/LF hashes와 실제 import paths. Both sides 작업 전후 변화0 |
| baseline-verification.json | 기존 environment manifest의 transplant14개 raw hashes와 현재 interpreter/package identity |
| laptop-evidence-inventory.json | 기존 Laptop C: logs/manifests/config hashes와 기존 environment manifest 사본. Credential 내용 없음 |
| raw-evidence.json | 기존 Laptop text logs/reports/harness launchers의 사본을 JSON 문자열로 보존. Byte identity는 inventory/other_files의 SHA-256으로 확인; wrapped transcript를 canonical event log로 간주하지 않음 |
| state-evidence.json | 기존 SQLite mode=ro&immutable=1 결과. WAL0 확인. Existing READY cursor는 host DB reset으로 만든 것이 아님 |
| dump-metadata.json | 원본 dump를 Laptop에서 read-only mmap으로 읽은 metadata만. Dump binary copy, symbols, stack unwind 없음 |
| evidence-review.json | 보존 copy 및 보고 hash 대조; H1 wrapped JSON tail 재조립. 전체 H1 events 아님 |
| h2-hash-reconciliation.json | 보고 hash가 현재 H2 event file 첫4,369바이트와 일치하고 뒤에1,478바이트가 append된 사실 |
| reproduction-results.json | Desktop 보조 fake-boundary 진단. Python3.11.8 및 requests version warning; 실제 Laptop native driver 결과 아님 |
| laptop-reproduction-results.json | Authoritative Python3.11.9에서 unchanged product objects + fake camera/recognizer/serial/playback으로 독립 재현. Assertions PASS는 **결함 재현 성공**이지 acceptance PASS가 아님 |
| firmware-model-results.json | Source constant/algorithm 기반 behavioral model. Compiled C/HAL, ORE measurement, real UART/servo 검증 아님 |
| targeted-existing-tests.txt | Laptop 기존 관련 tests142 passed /8.67s; 새 C: diagnostic temp와 interpreter/test 목록 |
| final-integrity.json | 작업 전후 product/evidence hash 대조, report links, 새 output file hashes |

재실행은 Desktop workspace에서 기존 SSH 인증만 사용한다. Camera/server credential을 command line에 넣지 않는다. 아래 명령은 fake-boundary 진단이며 실제 camera/COM/speaker/production server를 사용하지 않는다.

```powershell
python -B docs/evidence/software-diagnostic-20260908/reproduce.py
python -B docs/evidence/software-diagnostic-20260908/collect_identity.py remote docs/evidence/software-diagnostic-20260908/reproduce.py laptop-reproduction-new.json 0
```

기존 결과를 보존하려면 항상 새로운 output 이름을 지정한다. `collect_identity.py`는 Python script를 기존 SSH stdin으로 보내 C: integration interpreter에서 `-B`로 실행한다. Native dump raw bytes는 출력하지 않는다. `run_existing_tests_remote.py`는 매번 새로운 C: temp 경로를 사용한다. Pytest output/script errors와 real product failures를 구분한다.

진단 과정에서 initial SSH quoting/Windows command-line length, Desktop cp949 decode, diagnostic enum assertion을 보정했다. 최종 script와 authoritative results가 이 폴더에 있다. 이러한 진단 tooling 수정은 product patch가 아니다.

기존 evidence/state 삭제0, Laptop D: filesystem 접근0, production upload0, 실제 servo/serial/speaker 동작0, firmware flash0. 새 C: pytest temp는 보존했고 이번 진단 child processes는 종료됐다. 네 work packet은 제안 상태이며 구현 승인을 대신하지 않는다.
