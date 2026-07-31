# EBS 수능특강 수학 Document Parser 1차 구현 플랜

- 작성일: 2026-08-01
- 검토 대상: `document_parser_phase1_plan.md`
- 기준 자료:
  - `2027 수능특강 수학 I.pdf`
  - `2027 수능특강 수학 I-png-Images.zip`
- 결론: 원 기획의 핵심 방향은 타당하다. 다만 현재 PNG 압축본은 해상도가 낮아 OCR 기준선용 주 입력으로 쓰기 어렵고, PDF 텍스트 계층도 자동 정답 데이터로 신뢰하기 어렵다. 따라서 1차 구현은 PDF에서 고해상도 페이지 이미지를 재생성하고, 이미지 단독 입력 파이프라인을 기준으로 검증하는 방식으로 시작해야 한다.

---

## 1. 검토 요약

### 1.1 설계 타당성 판단

기획서의 핵심 설계는 프로젝트 배경과 목적에 잘 맞는다.

시각장애인 수학 학습 지원이라는 배경에서는 "무엇이 중요한가"보다 "페이지에 있는 인식 가능한 정보를 누락하지 않고, 수식과 표를 후속 모듈이 다룰 수 있는 구조로 넘기는가"가 1차 Parser의 본질에 가깝다. 따라서 다음 결정은 타당하다.

| 설계 결정 | 판단 | 근거 |
|---|---|---|
| 이미지 단독 입력 우선 | 타당 | 실제 서비스 입력이 페이지 이미지일 가능성이 높고, PDF 텍스트 계층은 교재 제작 방식에 따라 깨질 수 있다. 이번 PDF도 텍스트 추출 결과가 한글과 수식에서 안정적이지 않다. |
| 의미 중립성 | 타당 | Parser가 문제, 풀이, 정답, 중요도 등을 판단하면 답 비노출, 스킵, 교육 의미 분류가 Parser에 섞인다. 1차 목표인 TTS 전체 낭독과 수식·표 점자 소비에는 의미 분류가 필수 아니다. |
| 콘텐츠 타입을 `TEXT`, `MATH`, `TABLE`, `UNSUPPORTED_VISUAL`로 제한 | 타당 | 후속 TTS와 점자 모듈의 소비 계약을 단순하게 유지한다. |
| 원본 좌표, 크롭, 엔진 버전, 신뢰도 보존 | 매우 타당 | OCR 오류 검수, 중복 제거, 수식 재처리, 표 셀 검증에 필수다. |
| 실패 가시성 | 매우 타당 | 시각장애인용 학습 도구에서는 무음 삭제가 가장 위험하다. 저신뢰와 미지원 영역을 명시해야 한다. |
| 기성 OCR 활용과 규칙 우선 | 타당 | 현재 범위는 자체 학습 모델보다 데이터 정리, 엔진 비교, 좌표 병합, AST 검증이 먼저다. |
| Parser와 TTS·점자 출력기 분리 | 타당 | Page IR을 안정화하면 TTS, 점자, 표 탐색기를 독립적으로 개선할 수 있다. |

### 1.2 반드시 보완할 점

1. 현재 ZIP PNG 해상도는 OCR 기준선으로 부족하다.
   - PDF는 160쪽이다.
   - ZIP에는 정규 1-160쪽과 52-54쪽 복사본 3개가 있어 총 163개 파일이 있다.
   - 정규 PNG는 모두 584x737이다.
   - PDF의 페이지 크기와 거의 같은 픽셀 수이므로 72dpi 렌더에 가깝다.
   - PDF를 300dpi로 렌더링하면 2434x3071 이미지가 생성된다.
   - 작은 첨자, 분수선, 로그 밑, 표 내부 숫자, 도형 라벨 OCR에는 584x737 입력이 낮다.

2. PDF 텍스트 계층은 자동 골든 정답으로 쓰지 않는다.
   - `pypdf` 텍스트 추출 결과가 한글·수식에서 깨진 글리프와 잘못된 기호를 포함한다.
   - PDF는 사람이 확대 확인하거나 고해상도 이미지를 생성하는 참고자료로 사용한다.

3. 표의 정의를 더 엄격히 해야 한다.
   - 수학 교재에는 "정답 목록", "보기 나열", "가로 선택지", "설명 박스"가 많다.
   - 모든 줄 정렬 구조를 TABLE로 만들면 TTS 낭독과 점자 탐색이 과도해진다.
   - 1차 P0 TABLE은 선이 있는 표, 명확한 행·열 격자, 셀 경계가 있는 구조로 제한한다.
   - 정렬된 목록과 정답 모음은 기본적으로 TEXT 블록으로 처리하고, 후속 버전에서 별도 `LIST`나 확장 계층을 검토한다.

4. 그래프·도형의 "미지원" 처리는 텍스트 보존과 분리해야 한다.
   - 예: 20쪽의 지수함수 그래프, 54쪽의 삼각형 도형은 의미 해석은 비범위지만 축 이름, 점 이름, 식 라벨은 OCR 가능하다.
   - `UNSUPPORTED_VISUAL` 노드는 시각자료 영역을 알리고, 내부 OCR 텍스트는 하위 노드로 보존해야 한다.

5. P0 범위가 넓으므로 수직 슬라이스로 쪼개야 한다.
   - 일반 OCR, 읽기 순서, 수식 AST, 표 IR, 통합 Reconciler를 한 번에 완성하려 하면 기준선이 늦어진다.
   - 먼저 "페이지 이미지 -> OCR 토큰 -> 읽기 순서 TEXT Page IR"을 끝내고, 그 위에 수식과 표를 붙이는 순서가 현실적이다.

---

## 2. 로컬 자료 점검 결과

### 2.1 파일 인벤토리

| 파일 | 확인 결과 | 구현상 의미 |
|---|---|---|
| `2027 수능특강 수학 I.pdf` | 160쪽, 단일 페이지 크기 583.9371 x 737.0081 pt | 고해상도 페이지 이미지 생성과 골든 검수 참고용으로 사용 |
| `2027 수능특강 수학 I-png-Images.zip` | 정규 1-160쪽 + 52-54쪽 복사본 3개 | 입력 매니페스트 생성 시 복사본 제외와 자연 정렬 필요 |
| ZIP 내부 PNG | 모든 정규 이미지가 584x737, RGBA | 품질 게이트에서 `LOW_QUALITY` 또는 별도 `zip72` 세트로 관리 |
| PDF 300dpi 렌더 | 2434x3071, RGB | OCR 기준선과 골든 작성의 기본 페이지 이미지 후보 |

### 2.2 자산 사용 원칙

1. 원본 PDF와 ZIP은 수정하지 않는다.
2. ZIP PNG는 저해상도 회귀/열화 시험 세트로 보존한다.
3. OCR 기준선과 골든 페이지 주석은 PDF에서 300dpi 또는 필요 시 400dpi로 렌더링한 이미지로 작성한다.
4. 최종 합격 조건은 "PDF가 없어도 페이지 이미지 입력만으로 처리"이므로, 렌더링 결과도 일반 이미지 입력으로 취급한다.
5. PDF 텍스트 추출 결과는 자동 정답으로 쓰지 않고, 사람이 검수할 때만 참고한다.

### 2.3 대표 샘플 페이지 후보

| 페이지 | 관찰 내용 | 추천 용도 |
|---|---|---|
| 3쪽 | 교재 구조 안내, 여러 시각 요소와 삽입된 페이지 이미지 | `UNSUPPORTED_VISUAL`, 장식/미지원 영역, 내부 텍스트 보존 |
| 4쪽 | 선 있는 표, 그래프, 한글+수식, 다수 독립 수식 | 초기 통합 골든, 표 P0, 그래프 미지원, 수식 AST |
| 8쪽 | 로그 정의와 성질, 인라인 수식과 독립 수식 다수 | 수식 후보 검출, LaTeX/AST 파서 핵심 골든 |
| 12쪽 | 상용로그표 일부, 작은 표와 화살표 | 작은 표 셀 구조, 표 내부 텍스트 보존 |
| 19쪽 | 대표 기출 문제, 출제 의도, 풀이 라벨 | 의미 중립성, 박스형 레이아웃, 읽기 순서 |
| 20쪽 | 그래프가 많은 개념 페이지 | `UNSUPPORTED_VISUAL` + 그래프 내부 텍스트 보존 |
| 54쪽 | 삼각형 도형 여러 개와 증명 수식 | 도형 미지원 영역, 수식·도형 중복 방지 |
| 102쪽 | 한눈에 보는 정답, 2단 정답 목록 | 2단 읽기 순서, 답 비노출 비범위 확인 |
| 120쪽, 140쪽, 150쪽 | 정답과 풀이 영역, 긴 수식 전개 | 현재 페이지 전체 반환 원칙, 수식 행 순서 |

---

## 3. 구현 방향

### 3.1 기술 스택 제안

현재 프로젝트 폴더에는 코드가 없으므로 Python 기반으로 시작한다.

| 영역 | 선택 |
|---|---|
| 언어 | Python |
| 패키지 구조 | `src/document_parser/` |
| 이미지 처리 | Pillow, NumPy, OpenCV 계열 라이브러리 |
| PDF 렌더 | `pypdfium2` 우선, Poppler는 보조 |
| 스키마 | JSON Schema + Python dataclass/Pydantic 계층 |
| 테스트 | pytest |
| 디버그 산출물 | PNG 오버레이, JSONL 리포트 |
| OCR | 공급자별 Adapter 인터페이스로 분리 |

OCR 엔진은 구현 초기에 고정하지 않는다. 먼저 Adapter 계약과 평가 harness를 만들고, 프로젝트가 사용할 수 있는 한국어 OCR, 수식 OCR, 표 구조 인식기를 동일 인터페이스로 비교한다.

### 3.2 저장소 구조

```text
document-parser/
├─ pyproject.toml
├─ src/
│  └─ document_parser/
│     ├─ assets/
│     ├─ ingest/
│     ├─ preprocess/
│     ├─ ocr/
│     ├─ layout/
│     ├─ math/
│     ├─ table/
│     ├─ visual/
│     ├─ reconcile/
│     ├─ serialization/
│     └─ cli/
├─ schemas/
├─ profiles/
├─ tests/
├─ fixtures/
├─ tools/
├─ docs/
└─ data/
   ├─ manifests/
   ├─ pages_zip72/
   ├─ pages_pdf300/
   ├─ golden/
   └─ debug/
```

대용량 렌더 이미지와 OCR 결과 캐시는 Git 관리 대상에서 제외하는 것을 권장한다. 단, 작은 골든 fixture와 스키마 예제는 저장소에 포함한다.

---

## 4. 단계별 구현 플랜

### 단계 0. 자산 정리와 기준 입력 생성

목표: 전권 페이지 목록과 품질 기준을 확정한다.

작업:

1. ZIP 내부 파일을 자연 정렬로 읽고 정규 페이지 1-160만 매니페스트에 포함한다.
2. `52 - 복사본`, `53 - 복사본`, `54 - 복사본`은 중복 자산으로 기록하고 기본 처리에서 제외한다.
3. PDF를 `source.pdf` 같은 ASCII 내부 작업명으로 복사하거나 경로 처리 계층을 만든다.
4. PDF에서 300dpi 페이지 이미지를 생성하는 렌더러를 구현한다.
5. 필요 시 수식 OCR 비교용으로 선택 페이지를 400dpi로 추가 렌더링한다.
6. ZIP 72dpi 이미지와 PDF 300dpi 이미지의 크기, 해시, 페이지 번호 대응표를 만든다.
7. 초기 골든 후보 10-15쪽을 선정한다.

산출물:

- `data/manifests/ebs_2027_math1_pages.json`
- `data/manifests/asset_audit.json`
- `tools/render_pages.py`
- `docs/asset-audit.md`

완료 기준:

- 정규 160쪽 매니페스트 생성
- 중복 복사본 3개 제외 규칙 검증
- 300dpi 렌더 이미지의 페이지 번호와 원본 PDF 페이지 번호 일치
- ZIP 이미지가 저해상도 세트로 분리됨

### 단계 1. Page IR 스키마와 공통 모델 고정

목표: OCR 엔진과 후속 모듈이 공유할 데이터 계약을 먼저 고정한다.

작업:

1. `ParsedDocument`, `Page`, `Node`, `Span`, `Issue`, `QualityReport`, `EngineManifest` 스키마 작성
2. 공통 좌표계 정의
   - 픽셀 좌표 원점은 좌상단
   - `bbox`는 원본 입력 이미지 기준
   - `normalized_bbox`는 0-1 범위
   - 회전 보정 후 좌표와 원본 좌표의 변환 이력 보존
3. 콘텐츠 타입 확정
   - P0: `TEXT`, `MATH`, `TABLE`, `UNSUPPORTED_VISUAL`
   - 내부 검토용: `UNKNOWN`
4. Issue 코드 사전 작성
   - `LOW_RESOLUTION`
   - `SKEW_CORRECTED`
   - `OCR_LOW_CONFIDENCE`
   - `MATH_PARSE_FAILED`
   - `TABLE_STRUCTURE_AMBIGUOUS`
   - `UNSUPPORTED_VISUAL_REGION`
   - `DUPLICATE_CONTENT_SUPPRESSED`
   - `ORPHAN_OCR_TOKEN`
5. 금지 필드 검사 추가
   - `importance`, `educational_role`, `problem_role`, `answer_of`, `tts_priority` 등은 기본 Page IR에 들어가지 않도록 검증

산출물:

- `schemas/page-ir.schema.json`
- `schemas/math-ast.schema.json`
- `schemas/table-ir.schema.json`
- `schemas/parse-issue.schema.json`
- `src/document_parser/models/`
- `tests/unit/test_schema_contract.py`

완료 기준:

- 예제 Page IR JSON이 스키마 검증을 통과
- 금지 필드가 들어오면 테스트 실패
- 모든 노드에 좌표와 provenance 필드가 존재

### 단계 2. 이미지 입력, 품질 게이트, 전처리

목표: OCR 전 단계에서 입력 품질과 파생 이미지를 안정적으로 관리한다.

작업:

1. `ImageIngestor` 구현
   - PNG/JPEG 로딩
   - 페이지 ID 생성
   - 이미지 크기와 색상 모드 기록
2. `ImageQualityGate` 구현
   - 픽셀 크기 검사
   - DPI 추정 또는 렌더 세트 기반 품질 태그
   - 회전/기울기 후보
   - 본문 영역 잘림 후보
   - 흐림 점수
3. `ImagePreprocessor` 구현
   - 원본 보존
   - 회색조 파생물
   - 이진화 파생물
   - 명암 보정 파생물
   - 기울기 보정 파생물
4. 전처리 이력 기록
   - 적용 파라미터
   - 파생 이미지 경로
   - 좌표 변환 행렬
5. ZIP 72dpi와 PDF 300dpi의 품질 리포트 비교

산출물:

- `src/document_parser/ingest/`
- `src/document_parser/preprocess/`
- `tests/unit/test_image_quality.py`
- `data/debug/quality_reports/`

완료 기준:

- 584x737 ZIP 이미지는 저해상도 이슈가 기록됨
- 2434x3071 PDF 렌더 이미지는 기본 OCR 입력 조건 통과
- 원본 이미지가 덮어써지지 않음
- 전처리 후에도 원본 좌표로 역변환 가능

### 단계 3. 일반 OCR Adapter와 기준선 평가

목표: 한국어 본문과 기본 좌표를 얻는 최소 파이프라인을 완성한다.

작업:

1. `GeneralOcrAdapter` 인터페이스 정의
   - 입력: 이미지 경로와 옵션
   - 출력: token text, bbox/polygon, confidence, line hint, engine metadata
2. 최소 1개 실제 OCR 엔진 Adapter 구현
3. OCR 결과를 공통 좌표계로 정규화
4. OCR 원시 결과를 캐시
5. 300dpi 샘플 페이지에서 텍스트 기준선 수집
6. ZIP 72dpi와 PDF 300dpi 결과 비교
7. 사람이 일부 페이지를 검수해 오류 유형 정리

산출물:

- `src/document_parser/ocr/general.py`
- `src/document_parser/ocr/adapters/`
- `docs/engine-baseline.md`
- `tests/golden/ocr_text/`

완료 기준:

- 대표 페이지에서 OCR 토큰과 좌표가 생성됨
- 엔진 버전과 설정이 `engine_manifest`에 기록됨
- 저신뢰 OCR 토큰이 삭제되지 않고 issue로 전파됨
- ZIP 72dpi 입력의 정확도 한계가 수치 또는 사례로 기록됨

### 단계 4. 레이아웃 복원과 읽기 순서

목표: OCR 토큰을 줄, 블록, 컨테이너, 페이지 순서로 묶는다.

작업:

1. 토큰 정규화
   - 회전 박스 처리
   - 글자 높이 추정
   - 공백 후보 추정
2. 줄 구성
   - 기준선 유사성
   - y 좌표 겹침
   - 토큰 간 거리
3. 블록 구성
   - 줄 간격
   - 좌우 정렬
   - 박스 경계
   - 라벨 영역
4. 컨테이너/열 판정
   - 1단 본문
   - 2단 페이지
   - 박스형 문제
   - 정답 목록 페이지
5. 읽기 순서 산출
   - 배열 순서
   - 선택적 선후관계 그래프
   - 그래프 순환 검사
6. 디버그 오버레이 생성
   - OCR 토큰
   - 줄/블록
   - reading order index
   - 고아 토큰

산출물:

- `src/document_parser/layout/`
- `src/document_parser/serialization/debug_overlay.py`
- `tests/unit/test_reading_order.py`
- `tests/golden/layout/`

완료 기준:

- 4쪽, 8쪽, 19쪽, 102쪽의 읽기 순서를 사람이 비교 가능
- 최종 TEXT 후보가 모두 좌표를 가짐
- 읽기 순서 그래프 순환 0건
- 고아 OCR 토큰 통계가 리포트됨

### 단계 5. 수식 후보 검출, 수식 OCR, Presentation AST

목표: 인라인 수식과 독립 수식을 보존 가능한 AST로 변환한다.

작업:

1. `MathCandidateDetector` 구현
   - 문자 구성 신호
   - 일반 OCR 저신뢰 신호
   - 2차원 배치 신호
   - 독립 중앙 정렬 신호
   - 표 셀 내부 수식 신호
2. 혼합 줄 분할
   - TEXT-MATH-TEXT 경계 후보
   - 좌우 여백을 포함한 수식 crop 생성
   - 일반 OCR 토큰과 수식 노드 중복 제거 후보 기록
3. `FormulaOcrAdapter` 인터페이스 정의
   - 입력 crop
   - 출력 LaTeX/MathML 후보, confidence, raw result
4. 제한 LaTeX 파서 구현
   - identifier, number, operator
   - fraction
   - radical
   - subscript/superscript
   - relation
   - function application
   - parenthesized row
   - aligned equation rows
5. AST 검증
   - 괄호 짝
   - 미소비 토큰
   - 빈 노드
   - 신뢰도와 실패 issue
6. 실패 정책
   - OCR 실패 crop도 `MATH` 후보 또는 `UNKNOWN`으로 보존
   - raw crop과 좌표를 반드시 남김

산출물:

- `src/document_parser/math/candidates.py`
- `src/document_parser/math/formula_ocr.py`
- `src/document_parser/math/latex_parser.py`
- `src/document_parser/math/ast_validator.py`
- `tests/unit/test_math_ast.py`
- `tests/golden/math/`

완료 기준:

- 4쪽과 8쪽의 대표 수식이 AST로 변환됨
- 인라인 수식이 TEXT 문자열에 중복 저장되지 않고 `MATH_REF`로 연결됨
- AST 실패가 무음 삭제되지 않음
- 원시 수식, crop, 원본 좌표가 역추적 가능

### 단계 6. 표 구조 복원

목표: P0에서 선이 있는 표를 안정적으로 TABLE IR로 만든다.

작업:

1. `TableCandidateDetector` 구현
   - 수평/수직 선분 검출
   - 교차점 검출
   - 셀 경계 후보
   - 표 주변 OCR 토큰 포함
2. `TableStructureParser` 구현
   - 행/열 인덱스
   - 셀 bbox
   - 병합 셀 후보
   - 셀 내부 reading order
3. 표 내부 OCR 재사용
   - 기존 일반 OCR 토큰을 셀에 할당
   - 필요 시 셀 crop OCR
   - 셀 내부 수식은 `MATH_REF` 또는 하위 `MATH` 노드로 연결
4. 정답 목록과 표 구분 규칙
   - 격자/셀 경계가 명확하면 TABLE
   - 단순 가로 나열, 정답 목록, 보기 줄은 기본 TEXT
   - 애매하면 `TABLE_STRUCTURE_AMBIGUOUS` issue
5. P1 선 없는 표 기준선 기록

산출물:

- `src/document_parser/table/`
- `tests/unit/test_table_grid.py`
- `tests/golden/table/`

완료 기준:

- 4쪽의 표, 12쪽의 상용로그표가 TABLE IR로 표현됨
- 표 셀 내용이 본문 TEXT로 중복 낭독되지 않음
- 행·열·셀 조회 fixture 생성
- 선 없는 표는 P1 또는 ambiguity로 분리됨

### 단계 7. 미지원 시각자료 검출

목표: 그래프·도형·복잡한 이미지가 삭제되지 않도록 영역과 내부 텍스트를 남긴다.

작업:

1. connected component와 선분/곡선 밀도를 이용해 시각자료 후보 탐지
2. 그래프/도형/장식 후보를 보수적으로 분리
3. 내부 OCR 텍스트 노드를 `embedded_text_nodes`로 연결
4. 설명 불가능한 영역은 `UNSUPPORTED_VISUAL`로 보존
5. 장식 배경은 기본 소비 노드에서 제외하되, 오검출을 issue로 리포트

산출물:

- `src/document_parser/visual/`
- `tests/golden/unsupported_visual/`

완료 기준:

- 20쪽 그래프 영역이 미지원 시각자료로 표시됨
- 54쪽 도형 영역이 미지원 시각자료로 표시됨
- 축 이름, 점 이름, 라벨 텍스트가 삭제되지 않음
- 그래프나 도형의 의미를 해석한 필드는 생성하지 않음

### 단계 8. 결과 병합, 중복 제거, Page IR 직렬화

목표: 일반 OCR, 수식 OCR, 표 인식, 미지원 시각자료를 하나의 Page IR로 합친다.

작업:

1. `ResultReconciler` 구현
   - 좌표 중첩 기반 중복 후보
   - TEXT와 MATH의 소유 관계
   - TABLE 내부 토큰 소유 관계
   - 시각자료 내부 텍스트 참조
2. 중복 제거 정책
   - 수식으로 확정된 영역의 일반 OCR 토큰은 `MATH_REF`로 대체
   - 표 셀 내부 토큰은 TABLE 소유로 이동
   - 삭제가 아니라 provenance와 suppression issue를 기록
3. 고아 콘텐츠 검사
   - 어떤 노드에도 속하지 않는 OCR 토큰
   - 미지원으로도 표시되지 않은 비텍스트 영역
4. Page IR 직렬화
   - JSON Schema 검증
   - engine manifest 기록
   - validation summary 기록
5. 후속 모듈 fixture
   - TTS 소비 fixture
   - 수식 점자 소비 fixture
   - 표 탐색 fixture

산출물:

- `src/document_parser/reconcile/`
- `src/document_parser/serialization/`
- `fixtures/tts-consumer/`
- `fixtures/braille-consumer/`
- `tools/compare_page_ir.py`

완료 기준:

- 스키마 오류 0건
- 좌표 없는 최종 노드 0건
- 읽기 순서 순환 0건
- 치명적 중복 낭독 0건
- 실패/저신뢰/미지원 콘텐츠가 issue로 전파됨

### 단계 9. 골든 데이터와 평가 자동화

목표: 사람이 검수한 기준 페이지와 전권 구조 회귀를 결합한다.

작업:

1. 골든 세트 40-60쪽 선정
   - 초기 10-15쪽으로 시작하고 점진 확장
2. 수동 주석 포맷 정의
   - 텍스트
   - 좌표
   - reading order
   - 수식 span
   - raw formula
   - AST
   - 표 셀 구조
   - 미지원 영역
3. 평가 지표 구현
   - OCR CER/WER
   - 줄/블록 정확도
   - reading order pair accuracy
   - 수식 영역 정밀도/재현율
   - AST node/edge match
   - 표 셀 match
   - 통합 무결성
4. 변형 시험 생성
   - 축소
   - 압축
   - 회전
   - 흐림
   - 잘림
5. 전권 회귀
   - 160쪽 전체 처리
   - 페이지 누락/중복 검사
   - 처리 시간과 메모리
   - 수식/표/미지원 영역 분포
   - engine error 수집

산출물:

- `tests/golden/`
- `tests/transforms/`
- `tests/full_book/`
- `docs/golden-annotation-guide.md`
- `docs/evaluation-report.md`

완료 기준:

- 초기 골든 세트의 사람이 보는 비교 리포트 생성
- 전권 160쪽이 실패 없이 Page IR 또는 명시적 실패 리포트를 생성
- 필수 무결성 기준 통과
- 남은 치명/주요/경미 오류가 유형별로 정리됨

---

## 5. 우선순위 백로그

### P0-0: 구현 준비

1. 프로젝트 패키지 구조 생성
2. 자산 매니페스트 생성
3. PDF 300dpi 렌더러 작성
4. ZIP 중복 제외 규칙 작성
5. Page IR 스키마 초안 작성

### P0-1: TEXT 기준선

1. 일반 OCR Adapter 계약 작성
2. 1개 OCR 엔진 연결
3. OCR 토큰 표준화
4. 줄/블록 구성
5. reading order 생성
6. TEXT-only Page IR 출력
7. 디버그 오버레이 출력

### P0-2: 수식 기준선

1. 수식 후보 검출 규칙
2. 수식 crop 생성
3. 수식 OCR Adapter 계약
4. 제한 LaTeX 파서
5. Presentation AST 검증
6. `MATH_REF` 병합

### P0-3: 표 기준선

1. 선 있는 표 후보 검출
2. 행·열·셀 구조 생성
3. 셀 내부 OCR 토큰 할당
4. 셀 내부 수식 연결
5. TABLE IR 검증

### P0-4: 통합과 회귀

1. Reconciler
2. 중복 제거
3. 고아 토큰 검사
4. 미지원 시각자료 노드
5. JSON Schema 검증
6. 초기 골든 평가
7. 전권 구조 회귀

### P1

1. 선 없는 표 구조화
2. 복수 OCR 엔진 후보 비교
3. 검수용 JSONL/간단 UI
4. 상세 변형 시험
5. 타 과목 소규모 표본

---

## 6. 구현 중 유지할 불변조건

1. 원본 이미지를 덮어쓰지 않는다.
2. PDF 텍스트 계층에 의존하지 않는다.
3. 모든 최종 노드는 원본 좌표를 가진다.
4. OCR 실패와 AST 실패를 빈 문자열로 만들지 않는다.
5. 저신뢰 노드와 미지원 영역은 issue로 남긴다.
6. 수식으로 확정된 콘텐츠는 일반 TEXT로 중복 소비하지 않는다.
7. 표 셀 내부 콘텐츠는 TABLE 소유 관계를 가진다.
8. 그래프·도형 의미를 자동 해석하지 않는다.
9. 문제·풀이·정답 역할 필드를 기본 Page IR에 넣지 않는다.
10. 엔진 버전, 규칙 버전, 전처리 파라미터를 기록한다.

---

## 7. 첫 2주 실행안

### 1-2일차

- 저장소 패키지 구조 생성
- `asset_audit` 스크립트 작성
- PDF 300dpi 렌더러 작성
- 160쪽 매니페스트 생성
- ZIP 복사본 제외 테스트 작성

### 3-4일차

- Page IR 스키마 초안 작성
- 공통 bbox/normalized bbox 유틸 작성
- 품질 게이트 기본 구현
- 4쪽, 8쪽, 12쪽, 19쪽, 20쪽, 54쪽, 102쪽 렌더 세트 고정

### 5-7일차

- General OCR Adapter 계약 작성
- 실제 OCR 엔진 1개 연결
- OCR raw cache 저장
- TEXT-only Page IR 출력
- OCR 디버그 오버레이 생성

### 8-10일차

- 줄/블록 그룹화 구현
- 1단/2단/박스형 reading order 규칙 구현
- 4쪽, 8쪽, 19쪽, 102쪽 수동 비교
- 고아 토큰 리포트 작성

### 11-14일차

- 수식 후보 검출 1차 규칙 구현
- 인라인 수식 crop 생성
- Formula OCR Adapter stub 또는 실제 엔진 연결
- 제한 LaTeX 파서 골격 작성
- 8쪽 수식 중심 골든 리포트 생성

---

## 8. 최종 1차 종료 조건

1차 구현은 다음 조건을 만족하면 종료 판정할 수 있다.

1. 수학 I 정규 160쪽 이미지 매니페스트를 처리한다.
2. PDF 없이 이미지 입력만으로 Page IR을 생성한다.
3. 골든 세트에서 TEXT, MATH, TABLE, UNSUPPORTED_VISUAL 비교 리포트가 생성된다.
4. 모든 최종 노드가 좌표와 provenance를 가진다.
5. 스키마 오류가 없다.
6. 읽기 순서 그래프 순환이 없다.
7. 수식 AST 실패가 issue로 보고된다.
8. 표 셀 내부 콘텐츠가 중복 낭독되지 않는다.
9. 그래프·도형이 무음 삭제되지 않는다.
10. 정답/풀이/중요도 의미 필드가 기본 Page IR에 없다.

---

## 9. 기획서에 반영하면 좋은 수정 사항

1. "현재 제공된 PNG 압축본은 72dpi급 저해상도이므로 OCR 기준선은 PDF 300dpi 재렌더 이미지를 사용한다"는 문장을 데이터 계획에 추가한다.
2. "ZIP에는 정규 1-160쪽 외 52-54쪽 복사본이 있으므로 입력 매니페스트에서 제외한다"는 자산 정리 규칙을 추가한다.
3. PDF 텍스트 계층은 골든 작성 참고용으로만 사용하고 자동 정답으로 사용하지 않는다고 명시한다.
4. TABLE P0 범위를 "선이 있는 표와 셀 경계가 명확한 표"로 더 좁힌다.
5. 정렬 목록, 선택지 나열, 정답 목록은 기본적으로 TEXT로 처리한다는 규칙을 추가한다.
6. Poppler/PDF 렌더링 도구의 한글 경로 및 CMap 문제를 피하기 위해 렌더러는 ASCII 작업 경로 또는 `pypdfium2`를 우선 사용한다고 명시한다.
7. 초기 구현 단계에 "TEXT-only Page IR" 수직 슬라이스를 추가한다.
8. 디버그 오버레이와 검수 데이터 생성을 P1이 아니라 P0 품질 활동으로 앞당긴다.

