# Device Integration E0-B.3 / E0-B.3.2 검증 보고서

작성일: 2026-09-02
원 작업 패킷: `DEVICE_INTEGRATION_E0_B_3_REPLAY_BOUNDARY_VERIFICATION_WORK_PACKET.md`
교정 패킷: `DEVICE_INTEGRATION_E0_B_3_2_IDENTITY_ROLE_REPORT_CONTRACT_CORRECTION_WORK_PACKET.md`
상태: **E0-B.3.2 local diagnostics/report 교정 및 전체 회귀 완료 / E0-B.4 actual evidence closure 대기**

## 결론

E0-B.3이 추가한 observer diagnostics 자체는 Scanner candidate, opaque identity, artifact와 ACK 판정을
변경하지 않았다. 그러나 실제 E0-B.3.1 이후 full Laptop log를 검토한 결과, E0-B.3 report가 동일
`identity_collection_*` event family의 두 역할을 혼동한 사실을 확인했다.

```text
candidate_verification
  stable candidate를 accepted reference와 비교
  SAME -> duplicate suppression
  DIFFERENT 5/5 -> artifact processing

page_change
  ACK된 펼침면 뒤 화면 변화를 감시
  SAME -> 같은 펼침면, 계속 대기
  DIFFERENT 5/5 -> candidate 검색 재개
```

실제 성공 로그에서 spread lineage가 있는 candidate는 두 개뿐이었다.

- `video-00000092` candidate -> valid 5/5 -> `different` -> `spread_sent(1)`
- `video-00000365` candidate -> valid 5/5 -> `different` -> `spread_sent(2)`

그 사이 `video-00000310`~`314`의 5/5 `different`는 page-change 감시였다. `video-00000314`는 책
페이지 314나 MP4 frame 314가 아니라 runtime source counter다. 따라서 E0-B.3의 314/315 `candidate
4/5 + content_occluded`와 318 `candidate 1/5 + source_exhausted` 주장은 실제 runtime 증거로 확정되지
않았고, 이를 필수로 요구하던 report checks는 잘못됐다.

E0-B.3.2는 Scanner 정책을 바꾸지 않고 역할과 report 의미만 교정했다. 고정 영상의 정상 전송 수 2와
Server 2 spreads/4 fragments/duplicate 0 기대값은 유지한다.

## 실제 Laptop 관찰

E0-B.3.1 revision 이후 사용자가 제공한 full log는 다음을 통과했다.

- 새 데이터팩 항목 선택
- 이전 완료 실행과 다른 `datapack-ee8c7c014211465c9fdff0dd7839b6eb`
- 두 candidate가 각각 5/5 `different`
- `spread_sent` sequence 1, 2
- EOF `queued_count=2`, `acked_count=2`
- user confirm 뒤 `scan_stopping(through_sequence=2)`
- `finalizing`, `datapack_saved(revision=1)`, `reading_resumed`
- 고유 page ID 4개: spread 1 L/R, spread 2 L/R
- 마지막 page에서 down 경계 유지와 up navigation 복귀

이 로그는 E0-B remote runtime happy path가 성공했음을 확인한다. 다만 E0-B.3.2 이전 binary의 로그라
explicit `identity_role`이 없고, raw transcript/Server summary 파일이 현재 저장소에 들어 있지 않다.
따라서 schema v2 report의 최종 `passed` 산출물 생성은 E0-B.4 actual evidence closure로 분리한다.

## E0-B.3.2 구현

### Book Scanner

- `OpaqueIdentityRole`에 `candidate_verification`, `page_change` 정의
- candidate selected/collection started/observed/decided/aborted에 bounded role 추가
- ACK 또는 duplicate suppression 뒤 page-change monitoring 시작 event 추가
- 두 collector path가 emit helper에 role을 명시적으로 전달
- collector, threshold, decision, artifact와 state transition 순서 변경 없음

### Device Runtime

- Book Scanner role을 추측하지 않고 bounded feedback whitelist로 전달
- candidate/page-change 모두 frame/spread/count/decision/timing의 기존 제한 유지
- raw token, pair digest, image, API key와 model path 비노출 유지

### Report schema v2

- `candidate_attempts[]`와 `page_change_checks[]` 분리
- explicit role이 없거나 unknown이면 spread ID로 추측하지 않고 failure/limitation
- source hash/status 검사
- 새 데이터팩 선택/scan lineage 검사
- candidate 2개 각각 5/5 `different` 검사
- `spread_sent [1,2]`, EOF 2/2 검사
- revision 1 저장과 같은 datapack의 L/R reading 4페이지 검사
- Server summary가 없으면 `provisional`, 2/4/0이면 `passed`, malformed/mismatch면 `failed`
- 4/5 hard-reject와 1/5 EOF abort 필수 check 제거

## 보수 계약 동결

다음은 변경하지 않았다.

- candidate stable/sample window/interval
- opaque identity N=5, `k_same=1`, `k_different=0`
- hard reject/missing/provider error의 valid observation 의미
- stable-window evidence 재사용 금지
- EOF frame 반복/padding 금지
- ACK 전 `spread_sent` 금지
- user confirm 전 자동 seal/finalize 금지
- V3-B/V4/S1/Server DB와 wire schema

페이지별 capture recall 또는 314/315·318의 제품 정책은 이 교정에서 결정하지 않는다.

## 테스트 결과

| 범위 | 결과 |
|---|---:|
| Book Scanner role/events 집중 | 14 passed |
| Device adapter/report 집중 | 11 passed |
| Book Scanner 전체 | 299 passed |
| Device Runtime 전체 | 107 passed, 3 skipped |
| Document Parser | 제품 코드 비변경; 최신 기준 602 passed, 4 skipped 유지 |

첫 전체 실행은 저장소 공용 `tmp` 아래 pytest basetemp 생성 권한 때문에 fixture setup error가 났다.
제품 assertion failure는 없었다. 각 프로젝트 내부의 전용 ASCII basetemp로 동일 suite를 재실행해 위 전체
결과가 통과했다. 생성한 임시 디렉터리는 확인 후 제거했다.

## 다음 실제 확인 — E0-B.4

1. E0-B.3.2 revision을 Laptop에 반영한다.
2. PowerShell transcript를 파일로 보존하며 동일 hash 영상을 fresh datapack으로 실행한다.
3. 두 candidate가 `identity_role=candidate_verification`, 각각 5/5 `different`인지 확인한다.
4. 중간 SAME/DIFFERENT가 `identity_role=page_change`로 분리되는지 확인한다.
5. sequence `[1,2]`, EOF 2/2, save revision 1과 reading 4페이지를 확인한다.
6. Desktop Server summary `2/4/0`을 JSON으로 보존한다.
7. schema v2 boundary report를 실행해 `status=passed`를 보존한다.

이후 real camera, HC-05/STM, 점자 frame과 speaker는 별도 physical E0-B다. deterministic bench parser는
실제 OCR/TTS 품질 authority가 아니므로 production content acceptance도 별도다.
