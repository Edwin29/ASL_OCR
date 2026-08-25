# book-scanner v2

문제집 페이지를 개조 휴대폰/PC 카메라로 스캔해 `document-parser`에 input으로 넘기는
파이프라인. **v1(단일 프레임 사전 촬영-가능 판정)은 폐기하고 처음부터 다시 설계했다** —
v1은 배경(책상/천)과 페이지가 하나의 컨투어로 뭉개지는 문제, 페이지 내부 인쇄물이
실제 페이지 경계보다 강한 엣지로 경쟁하는 문제 때문에 실사진 신뢰도가 낮았다.

## 핵심 전환: "촬영가능여부" → "전송가능여부"

v1은 촬영 *전에* "찍어도 되는가"를 저해상도 프리뷰 한 장으로 실시간 판단하려 했다.
v2는 다르다: 카메라가 고정된 환경에서 프레임을 **반복적으로 캡쳐**하고, 각 캡쳐+
후보정 결과에 대해 "**전송 가능한가**"를 사후 판단한다. 카메라 고정이라는 제약을
실제로 활용해서, 세션 시작 시 찍어둔 "책 없는 빈 프레임"과 각 캡쳐 프레임을
배경 차감(background subtraction)으로 비교한다 — 배경 텍스처가 무엇이든, 인쇄물이
페이지 위에 뭐가 있든 상관없이 "달라진 영역 = 책"으로 분리되므로 v1의 두 실패 원인이
구조적으로 사라진다.

## 전송가능여부의 세 축

1. **기하** (`judge/geometry_judge.py`) — 회전/크기/프레임경계. v1 `judge.py` 계승.
2. **안정성** (`judge/stability_judge.py`) — 최근 N프레임의 코너/면적이 일관되는지
   (책이 정지했는지). 반복 캡쳐 구조라서 처음으로 구현 가능해진 축(로드맵 Stage 4의
   원래 취지).
3. **화질** (`judge/quality_judge.py`) — document-parser 자신의
   `document_parser.preprocess.quality.ImageQualityGate`를 그대로 재실행. 새 화질
   기준을 만들지 않는다 — document-parser가 실제로 무엇을 안정적으로 받는지의
   권위있는 기준이 이미 거기 있다.

세 축 모두 실패해야 최종적으로 전송 거부(`TransmitBlockReason`), 어느 하나만
실패해도 그 프레임은 재시도 대상이 된다.

## 두 페이지 스프레드

책받침을 완만한 V자로 만들어 펼친 책을 올리는 설계를 사용자가 제안했다(곡률 완화 +
카메라를 책등 중심에 고정). 실제 예시 사진으로 확인한 것: 단순한 "사다리꼴 두 장
접붙인 리본" 모양이 아니라 책등 근처가 진짜 곡면으로 휘어 있다(로드맵이 이미 위험
요소로 짚어둔 문제). 물리적 V자 받침이 아직 없어 정확한 형상을 모델링할 수 없으므로,
**곡면을 직접 푸는 대신 중심선으로 프레임을 좌/우로 나누고 각각에 단일 페이지
파이프라인을 독립적으로 적용**한다(`detect/spread.py`). 왼쪽 페이지 전송 완료 →
오른쪽 페이지 → 둘 다 끝나면 다음 스프레드 감시로 자동 복귀.

중심선 위치는 이번 라운드에서 자동 검출하지 않고 세션 설정값(기본 50%)으로 취급한다
— 실제 받침이 없어 검증할 수 없는 상태에서 새 검출 알고리즘을 또 만들지 않기 위해서.

## 구조

```
src/book_scanner/
  detect/
    background.py   # 배경 등록 + 차감 -> foreground mask (순수 함수)
    corners.py        # foreground mask -> PageGeometry (v1의 해상도 독립 처리 계승)
    spread.py           # 프레임을 좌/우 서브프레임으로 분할
  correct/              # v1에서 거의 그대로 복구: 원근 보정 + 해시/원자적 저장 +
                         # 메타데이터. 검출 전략이 바뀌어도 유효했음 — v1 때 실사진으로
                         # document-parser 통합까지 검증됨
  judge/
    geometry_judge.py / stability_judge.py / quality_judge.py  # 세 축
    transmit_judge.py    # 세 축 합성 (기하->안정성->화질 순, 화질만 파일 I/O 있어
                          # 앞의 두 축을 통과해야 실행)
    guidance.py            # TransmitBlockReason -> 안내 문구 (비프음/TTS 연동은 보류)
  session/
    capture_source.py  # CaptureSource 프로토콜 + 웹캠/이미지시퀀스 구현체
    loop.py               # 상태 머신 제너레이터: 배경등록 -> (좌/우 반복) 판정 ->
                           # 가이드 또는 보정+전송 -> 완료 시 자동으로 다음 스프레드 대기
  transmit/
    client.py           # document-parser의 기존 remote_ingest 업로드 API 얇은 래퍼
                         # (책임 모듈 위치는 미정 -- 양쪽 다 옮기기 쉽게 분리해 둠)
```

## 실행

```bash
pip install -e .
python -m pytest tests/unit -q
```

수동 테스트(웹캠 또는 이미지 시퀀스로 실제 루프 돌려보기):

```bash
# 이미지 시퀀스 (첫 장이 배경 프레임)
python tools/run_session_cli.py --images bg.jpg f1.jpg f2.jpg ... --out-dir session_out

# 웹캠
python tools/run_session_cli.py --webcam --out-dir session_out

# 실제 document-parser 서버로 전송하려면
python tools/run_session_cli.py --images ... --out-dir session_out \
  --server http://localhost:8420 --api-key KEY --book-id my_book
```

## 이번에 하지 않은 것

실제 Pi 카메라 제어, 실제 버튼 GPIO 입력, 실제 비프음 회로/TTS 오디오 출력(문구
매핑까지만), document-parser 전달 책임 모듈의 최종 위치 확정, 동일 페이지 중복 스캔
방지(로드맵 Stage 7), 중심선(책등) 자동 검출(설정값으로만 처리), 책등 곡면의 실제
복원/평탄화(원근 보정은 여전히 평면 가정 — 좌/우 분할이 곡률 문제 자체를 없애주지는
않고, 물리적 완화에 기댄다).

물리적 V자 받침이 만들어지면: 실제 스프레드 사진으로 중심선 설정값이 맞는지, 좌/우
분할 후 각 파이프라인이 신뢰할 만하게 동작하는지, 안정성/화질 임곗값이 실측과 맞는지
재검증이 필요하다 — 지금은 전부 하드웨어 부재로 미검증 상태다.
