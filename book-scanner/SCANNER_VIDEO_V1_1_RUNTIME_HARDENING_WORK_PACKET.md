# Scanner Video V1.1 — Runtime 계약·후보 판정 하드닝 작업 패킷

상태: **구현·결정론적 검증 완료 — 실제 MP4 replay 차단**
작성일: 2026-08-30
선행 조건: V0 계약 및 V1 PC sampled-frame engine 구현 완료
후속 조건: V2 seam-conservative + UVDoc atomic artifact

## 1. 배경과 목표

V1은 PC camera/replay source, 표본 cadence, 안정 window, best-frame 선택과 비동기
`SpreadProcessor` 호출을 구현했다. 전체 unit test 162개가 통과했고 p30 4000×3000 JPEG에서
좌우 page 후보 검출도 확인했다.

그러나 V2 착수 전 점검에서 다음 계약·판정 공백이 확인됐다.

- cancel 뒤 processor 결과 event를 버릴 수는 있지만 processor가 이미 artifact를 publish하는
  것은 막지 못함
- 기본 session ID가 고정값이라 새 engine/process 실행 간 artifact ID가 충돌할 수 있음
- V1 `seam_proxy_fraction`이 p30 세 장에서 모두 정확히 0.5로, 실제 seam 이동을 측정하지 못함
- “저해상도 preview 분석”이라는 문서와 달리 page mask는 12MP 원본에서 먼저 계산됨
- 기존 offline fallback을 그대로 hard gate로 쓰면 p30 세 장 모두 오른쪽
  `UNEVEN_ILLUMINATION`으로 거부됨

V1.1의 목표는 V2가 안전하게 staging과 atomic commit을 구현할 수 있도록 실행 계약을
고정하고, 실제 의미가 없는 seam 안정성 지표를 교체하는 것이다. V1.1은 실제 seam crop이나
UVDoc artifact를 생성하지 않는다.

## 2. 확정할 설계 결정

### 2.1 Prepare와 publish 분리

`SpreadProcessor`는 최종 ready 디렉터리를 직접 publish하지 않는다.

권장 책임 분리는 다음과 같다.

1. processor가 private staging 영역에서 좌우 결과와 manifest 후보를 준비
2. processor가 `PreparedSpreadArtifact` 또는 명시적 실패를 반환
3. engine이 해당 job이 여전히 active인지 확인
4. active job만 `ArtifactStore.commit()`으로 final 디렉터리에 atomic publish
5. commit 성공 뒤에만 `SpreadArtifactRef`, `READY_FOR_PREFLIGHT`, `ARTIFACT_READY` 생성

취소된 job의 staging 결과는 ready artifact가 아니다. 기본 정책은 정리이며, 보존이 필요하면
ready namespace와 분리된 diagnostics namespace에 명시적으로 저장한다.

processor 내부에서 commit해야만 하는 구현은 채택하지 않는다. 단순 cancellation token 확인은
확인 직후 cancel이 들어오는 race가 남으므로 publish 권한을 engine/store 경계로 이동한다.

### 2.2 Job identity와 cancellation

각 processing 시도에 immutable `ProcessingJobId`를 부여한다.

- job은 session ID, spread ID, source frame ID를 포함하거나 이들에 연결됨
- engine은 active job 하나만 소유
- cancel 또는 retry 전환 시 active job을 폐기 상태로 바꿈
- 늦게 완료된 future는 staging 경로를 정리할 수 있지만 commit 권한을 얻지 못함
- 다른 job의 prepared 결과를 현재 job으로 commit할 수 없음

`Future.cancel()` 성공 여부를 ready publish의 근거로 사용하지 않는다. 이미 실행 중인 GPU 작업은
끝날 수 있다는 전제에서 lineage와 publish 권한을 검사한다.

### 2.3 고유 session ID와 artifact 충돌 정책

production engine 생성 시 caller가 고유 session ID를 제공해야 한다.

- production 기본 고정값 금지
- 권장 형식: UUIDv4 또는 동등한 충돌 내성 ID
- test에서는 결정론적 ID 주입 허용
- spread/job/artifact ID는 session ID 아래에서 결정론적으로 파생 가능
- manifest에는 session, spread, job, source frame ID를 모두 기록

final artifact 경로가 이미 존재할 경우:

- 동일 lineage와 동일 manifest hash면 idempotent existing result로 반환 가능
- 하나라도 다르면 충돌 오류로 중단
- 기존 final 디렉터리를 자동 덮어쓰거나 삭제하지 않음
- staging과 final은 같은 filesystem/volume에 두어 directory rename의 atomicity를 보장

### 2.4 실효성 있는 seam stability proxy

현재 bbox 기반 proxy는 제거하거나 진단 전용으로 강등한다. V1 후보 단계에서는 최종 V2 seam을
대신 계산하지 않되, 축소 preview에서 실제 gutter 위치 변화에 반응하는 proxy를 사용한다.

우선 구현 후보:

1. 원본을 `preview_max_dimension` 이하로 먼저 축소
2. 좌우 ROI에 명시적 spine overlap 적용
3. 중앙 허용 band 안에서 row별 luminance valley 또는 저비용 연속 경로 계산
4. 유효 row의 median seam x와 row dispersion 산출
5. 인접 표본의 normalized median seam shift를 안정성 metric으로 사용

proxy가 다음 조건을 만족하지 못하면 hard seam gate로 사용하지 않는다.

- 책 전체의 수평 이동과 실제 gutter 이동에 반응
- 중앙의 본문 글줄 한두 개에 과도하게 끌리지 않음
- 검은 배경과 페이지 외곽을 gutter로 오인하지 않도록 중앙 band에 제한
- seam을 찾지 못한 표본을 임의의 0.5로 성공 처리하지 않음
- p30 서로 다른 촬영본에서 항상 동일 상수가 나오지 않음

최종 seam-conservative crop은 계속 V2의 full-resolution `LuminanceValleySeamDetector`가
책임진다. V1.1 proxy 결과를 final crop 좌표로 재사용하지 않는다.

### 2.5 Preview-first 후보 분석

candidate scheduling에 필요한 segmentation/motion/seam proxy는 축소 preview에서 먼저
계산한다. 원본 full-resolution frame은 선택된 뒤 processor 입력으로 보존한다.

- preview에서 측정된 좌표와 면적은 full frame 대비 normalized 값으로 기록
- 원본 축소 이전 크기와 preview 크기를 모두 diagnostics에 기록
- preview 생성 때문에 원본 BGR frame을 덮어쓰지 않음
- V2 local readiness가 V1 preview mask를 최종 mask로 신뢰하지 않음

성능 합격 수치는 임의로 정하지 않는다. 현재 p30 12MP 한 장의 V1 분석 약 0.60초를 baseline으로
기록하고 preview-first 전후 latency와 판정 변화만 보고한다.

### 2.6 Offline fallback의 위치

`assess_fixed_layout_fallback()` 결과는 V1.1/V2에서 diagnostics로 보존하되 현재 threshold를
runtime hard gate로 승격하지 않는다.

근거:

- p30 세 장 모두 좌우 crop과 UVDoc 처리가 가능했음
- 동일 세 장이 오른쪽 `UNEVEN_ILLUMINATION` 때문에 spread-level fallback에서는 거부됐음
- 작은 검증 집합에서 만든 offline threshold를 production acceptance로 일반화할 근거가 없음

V2 hard failure는 우선 page/mask/crop 부재, decode 불가, physical frame 잘림, lineage/hash 손상,
UVDoc 명시적 실패처럼 직접 확인 가능한 조건으로 제한한다. 조명·blur·shadow 값은 기록하되
별도 검증 패킷 전에는 자동 거부 사유로 확정하지 않는다.

## 3. 계약 변경 범위

예상 production 경계:

```text
src/book_scanner/video/
  types.py       # ProcessingJobId, PreparedSpreadArtifact/commit 결과 계약
  protocols.py   # SpreadPreparer와 ArtifactStore prepare/commit 책임 분리
  engine.py      # active-job ownership, cancel 뒤 commit 차단
  candidate.py   # preview-first 분석과 유효 seam proxy
  config.py      # preview seam provisional config
```

정확한 타입 이름은 구현 시 저장소 관례에 맞춰 조정할 수 있지만 다음 불변식은 유지한다.

- prepared는 ready가 아님
- commit 전에는 `SpreadArtifactRef`가 없음
- `ARTIFACT_READY`는 commit 성공 뒤에만 발생
- cancel된 job은 final artifact를 만들 수 없음
- final bundle의 두 페이지는 하나의 source frame을 공유

기존 legacy `session/`, `judge/`, `transmit/` public API는 변경하지 않는다.

## 4. 테스트 행렬

### 4.1 Cancel/publish race

- prepare 시작 전 cancel: processor/commit 호출 0
- prepare 실행 중 cancel: future 완료 가능, commit 0, ready event 0
- prepare 완료 직후 commit 직전 cancel: commit 0
- commit 성공 뒤 cancel: 이미 commit된 artifact를 손상·삭제하지 않음
- 이전 job의 늦은 완료가 다음 retry job의 artifact로 publish되지 않음
- staging cleanup 실패가 ready 성공으로 바뀌지 않음

race 테스트는 `threading.Event` 또는 barrier를 사용해 각 경계를 결정론적으로 재현한다.

### 4.2 Identity와 collision

- production engine의 `session_id` 인자를 생략할 수 없고, composition root가 UUID 등을 생성해 주입
- 서로 다른 engine instance의 session/spread/artifact ID 충돌 없음
- 같은 ID와 같은 hash의 재commit은 정의된 idempotent 결과
- 같은 ID와 다른 hash는 충돌 오류
- existing final directory 자동 overwrite 0
- staging과 final이 다른 volume이면 명시적 config 실패

### 4.3 Seam proxy

- 고정 spread의 연속 preview에서 seam shift가 threshold 이하
- gutter가 수평 이동한 합성 frame에서 proxy가 이동량을 반영
- 중앙 본문 dark line만 바뀐 frame에서 gutter로 급격히 점프하지 않음
- 검은 외부 배경을 gutter로 선택하지 않음
- page-turn/hand occlusion 표본은 stable window를 만들지 않음
- seam 미검출은 상수 0.5 성공이 아니라 명시적 retry/metric unavailable
- p30 세 촬영본의 proxy가 모두 기계적으로 0.5에 고정되지 않음

### 4.4 Preview-first 회귀

- 12MP 입력에서도 candidate 분석은 설정된 preview 크기에서 수행
- 선택된 processor 입력은 축소본이 아니라 원본 frame
- 좌우 page pair/motion/stale/best-frame 기존 테스트 유지
- preview 변환 전후 normalized coordinate 범위 검증
- p30 3장 page-pair 검출 회귀 없음

## 5. 완료 기준

- cancel 중 또는 cancel 뒤 final artifact publish 0
- `ARTIFACT_READY`가 atomic commit 성공 뒤에만 발생
- 고유 session/job identity와 collision/idempotency 정책 테스트 통과
- seam proxy가 실제 gutter 변화에 반응하고 상수 0.5 문제가 제거됨
- candidate 분석이 preview-first라는 문서와 구현 일치
- p30 3장 page-pair 검출 유지
- offline fallback을 미검증 runtime hard gate로 사용하지 않음
- V0/V1 및 legacy 전체 unit test 회귀 없음
- 변경 파일을 V2 시작 전 별도 commit으로 고정

## 6. 검증 자료와 미검증 표시

현재 확인된 자료:

- p30 JPEG 3장: 4000×3000, V1 page-pair 검출 성공
- 기존 seam-conservative 좌우 crop non-empty
- CUDA UVDoc 좌우 실행 성공 및 한 adapter에서 `load_count=1`
- 전체 unit test 162개 통과

아직 없는 자료:

- `20260830_133526.mp4` local replay와 human timeline
- 실제 page-turn 구간의 false select/miss
- 물리 PC webcam backend의 장시간 buffer/cancel 동작

따라서 V1.1 완료 뒤에도 실제 영상 안정성 calibration은
`BLOCKED_VIDEO_NOT_AVAILABLE`로 남길 수 있다. 합성·JPEG 검증을 실제 영상 검증 완료로
표현하지 않는다.

## 7. 비범위

- full-resolution seam-conservative crop 생성
- UVDoc inference와 artifact 파일 작성
- manifest 상세 schema와 hash 작성
- Document Parser preflight·전송·outbox
- 실제 음향/TTS와 guidance hysteresis
- page-change/중복 전송 방지
- Pi camera/GPIO
- offline illumination/blur threshold 재보정

## 8. 중단 조건

- cancel된 processor가 final ready artifact를 publish할 수밖에 없음
- final artifact 기존 경로를 덮어써야만 재시도가 가능함
- seam proxy를 다시 고정 centerline 또는 상수 0.5로 가장해야 함
- preview 결과를 V2 final mask/crop으로 재사용해야 함
- 미검증 fallback threshold를 production hard gate로 채택해야 함
- V1.1 변경을 기존 대규모 미커밋 변경과 구분해 보존할 수 없음

## 9. 구현 결과 (2026-08-30)

### 9.1 계약과 engine

- `ProcessingJobId`, `PreparedPageArtifact`, `PreparedSpreadArtifact`,
  `PreparationDecision`을 immutable/직렬화 가능한 계약으로 추가했다.
- production `SampledFrameEngine`은 고정 기본 session ID를 제거하고 caller가 명시적
  `session_id`를 주입하도록 변경했다.
- `SpreadPreparer.prepare()`는 private staging 결과만 반환하고,
  `ArtifactStore.commit()` 성공 뒤에만 `SpreadArtifactRef`와 `ARTIFACT_READY`가 생성된다.
- cancel 시 active job 권한을 먼저 폐기한다. 이미 실행 중인 prepare가 완료되면 staging을
  discard하며 commit하지 않는다.
- prepare가 partial staging 생성 뒤 예외를 내도 job ID 기반 staging을 정리한 뒤 local retry한다.
- commit이 먼저 시작됐다면 engine lock 안의 짧은 publish 경계를 완료한 뒤 cancel을 처리하고,
  이미 commit된 artifact는 삭제하지 않는다.

### 9.2 Filesystem artifact store

- staging/final root의 동일 filesystem을 확인한다.
- staging 경로와 artifact 내부 상대 경로가 지정 root를 탈출하지 못하게 한다.
- manifest/좌/우 파일 hash를 commit 전에 검증한다.
- manifest의 artifact/session/job/spread/source-frame lineage를 prepared 계약과 대조한다.
- artifact별 exclusive commit lock과 directory rename을 사용한다.
- 동일 lineage·동일 hash 재commit은 idempotent result로 처리하고 duplicate staging을 정리한다.
- 동일 artifact ID의 다른 lineage/hash 또는 손상된 final은 collision으로 거부하며 덮어쓰지 않는다.

### 9.3 Preview-first와 seam proxy

- 12MP 원본은 보존하고 candidate segmentation/motion/seam 분석은 최대 640px preview에서
  먼저 실행하도록 변경했다.
- source/preview 크기를 diagnostics에 함께 기록한다.
- bbox 경계 평균 proxy를 제거하고 중앙 제한 band의 luminance profile, center prior와
  row dispersion을 사용한 gutter proxy로 교체했다.
- page/seam 미검출은 상수 0.5 성공이 아니라 `SEAM_FAILED`와 unavailable metric으로 기록한다.
- offline fallback assessment는 runtime hard gate에 연결하지 않았다.

### 9.4 검증 결과

- video 계약/engine/store/candidate 테스트: **58 passed**
- 전체 `book-scanner/tests/unit`: **179 passed**
- cancel 중 prepare 완료: commit 0, ready event 0, staging discard 확인
- prepare 완료 뒤 cancel-before-poll: commit 0 확인
- commit 성공 뒤 cancel: committed artifact 보존 확인
- 동일 artifact idempotency, hash/lineage collision, path escape, commit lock 검증
- 서로 다른 명시적 session의 spread/job ID가 충돌하지 않음 확인

p30 JPEG 세 장의 V1.1 preview 측정:

| 입력 | 원본 → preview | 분석 시간 | seam proxy | page pair | hard reason |
|---|---:|---:|---:|---|---|
| `20260830_111919.jpg` | 4000×3000 → 640×480 | 43.48ms | 0.5421875 | 있음 | `OUT_OF_FRAME` |
| `20260830_112000.jpg` | 4000×3000 → 640×480 | 32.82ms | 0.5515625 | 있음 | 없음 |
| `20260830_112042.jpg` | 4000×3000 → 640×480 | 32.53ms | 0.53125 | 있음 | 없음 |

기존 약 0.60초 full-resolution candidate baseline보다 짧아졌고 세 값이 상수 0.5에 고정되지
않았다. 첫 입력의 오른쪽 preview mask는 full frame 상단에 실제 접촉하므로 `OUT_OF_FRAME`을
임의로 제거하지 않았다. 이 판정의 실제 영상 false positive/negative 여부는 MP4 timeline 없이는
완료로 판단하지 않는다.

### 9.5 남은 상태

- `20260830_133526.mp4`: `BLOCKED_VIDEO_NOT_AVAILABLE`
- 실제 webcam 장시간 buffer/cancel: 미검증
- V1.1 source/tests/packet: V2 착수 전 별도 baseline commit으로 고정
- V2 full-resolution seam/UVDoc artifact 생성: 미구현

코드와 결정론적 검증 및 별도 baseline 고정까지 완료한 뒤 V2 구현을 시작한다.
