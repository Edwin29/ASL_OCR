# Laptop C: 용량 정리 및 산출물 게시 결과

## 게시 완료

최종 코드·펌웨어·보고서·선별 증거 91개 파일을 ASL_OCR GitHub `main`에 게시했다.

- 커밋: [`bafdb4ebb3247370aeceb5e50936e02c023f4d8f`](https://github.com/Edwin29/ASL_OCR/commit/bafdb4ebb3247370aeceb5e50936e02c023f4d8f)
- 게시 범위와 보존 정책: [제출·재현용 산출물](PROTOTYPE_RELEASE_20260916.md)
- 파일별 기록: [publication-files.json](evidence/release-20260916/publication-files.json)
- SSH Git 원격의 기존 host-key 검증 실패로 HTTPS 전송을 사용했다. 기존 remote 설정·SSH 인증·credential은 변경하지 않았고, 전송 후 원격 `main`의 커밋 일치를 확인했다.

게시 전 카메라·ARM 설정 19개 및 STM host·MODE 44개 테스트가 통과했다. 기존 진단 스크립트 `verify_mapping.py` 끝의 빈 줄이 전체 staged whitespace 검사에서 지적되었으며, 원시 진단 자료의 바이트를 유지하기 위해 수정하지 않았다. 제품 변경 diff의 whitespace 검사는 통과했다.

## 용량 조사와 실제 삭제

대상 호스트는 SSH `user@100.106.45.8`의 `LAPTOP-HUM24QK4`다. 읽기 조사는 C: integration source/runtime와 pip 캐시에 한정했다. Laptop D:는 접근하지 않았다.

| 항목 | 확인 결과 |
|---|---:|
| C: 전체 용량 | 237,090,369,536 bytes |
| 정리 전 여유 공간 — inventory 시점 | 82,845,696 bytes, 약 79MiB |
| pip 캐시 조사 점유 | 2,984,679,195 bytes |
| pip purge 보고 | 파일 1,868개, 디렉터리 4,225개, 2,984.7MB 삭제 |
| 정리 후 pip 캐시 | 1,938 bytes, 16개 파일 |
| 정리 후 C: 여유 공간 | 3,050,713,088 bytes, 약 3.05GB / 2.84GiB |
| 전후 C: 여유 공간 증가 | 2,967,867,392 bytes, 약 2.97GB |

삭제한 것은 `C:\Users\user\AppData\Local\pip\Cache`의 패키지 다운로드·빌드 캐시다. integration Python의 `python -m pip cache dir`로 실제 경로가 해당 C: 디렉터리임을 먼저 확인한 후, `python -m pip cache purge`를 실행했다. 기존 설치 패키지를 제거하는 명령은 실행하지 않았다. 캐시 삭제량과 C: 순증가량의 차이는 별도 시스템 쓰기를 포함하는 전체 볼륨 전후 측정의 차이이며, 그 세부 원인은 조사하지 않았다.

## 보존·확인 사항

- `C:\ASL_OCR` 원본과 `C:\ASL_OCR_INTEGRATION` source/venv를 보존했다.
- SQLite·전송 상태·촬영 산출물·실험 로그·crash dump·모델·펌웨어 백업·인증 파일을 삭제하지 않았다.
- 정리 후 실제 interpreter는 `C:\ASL_OCR_INTEGRATION\.venv-e0b\Scripts\python.exe`이고, device runtime·book scanner·document parser의 `__file__`이 모두 C: integration source를 가리킴을 확인했다.
- host `stm_serial.py` SHA-256이 기존 V3 배포 값 `d2ff49463dcdb103150ff8312f0a5ef6128cb513acde98cfb3bf6da753fcdf34`와 일치했다.
- 기존 원본·state·hardware-integration·models 디렉터리의 존재를 재확인했다. DB 전체 무결성 검사나 새 production 실행을 했다는 뜻은 아니다.
- 조사·확인용 소형 Python 스크립트 두 개는 `C:\ASL_OCR_INTEGRATION_RUNTIME\laptop_c_inventory_20260916.py`, `laptop_cleanup_verify_20260916.py`에 남겼다. 제품 코드는 이번 용량 정리에서 수정하지 않았다.

후속 원시 확인: [laptop-cleanup-after.json](evidence/release-20260916/laptop-cleanup-after.json).

약 3GB의 여유를 확보했지만 C:의 남은 공간은 여전히 작다. 이번에 조사한 integration runtime의 실험 증거와 모델은 보존 가치가 있으므로 자동 삭제 대상으로 승격하지 않았다. 더 큰 공간이 필요하면 다른 앱·개인 데이터 등의 점유를 별도로 조사해야 하며, 미게시 원시 증거를 ‘GitHub 백업 완료’로 간주하여 삭제해서는 안 된다.

## 보고서 설명문

[정정 반영 설명문](SW_REPORT_REVISED_EXPLANATIONS_20260916.md)에 10개 정정·보완 항목을 작성했다. Page IR·AST는 동일 방정식의 서로 다른 정리 수준으로 설명하고, 문제 코드·동그라미 번호의 휴리스틱 두 가지와 전송 승인 조건별 이유를 추가했다. `0.2ⁿ` 예시는 독립 시행 가정 아래 같은 페이지임을 모두 놓칠 확률이며 측정된 중복 전송률이 아님을 명시했다.

첨부 DOCX의 SHA-256은 정리 후에도 `c9fa7bbe3965fb4bec7293e903cf44f52f73900d4a31e916db4a2f4c6e15d944`로 동일했다. 첨부 본문은 변경하지 않았다.
