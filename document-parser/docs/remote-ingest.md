# 원격 ingest 서버 (GPU 없는 팀원용 임시 도구)

**이건 제품의 일부가 아닙니다.** [`docs/datapack-schema.md`](datapack-schema.md)의 `document_parser.server`(Scenario B, 하드웨어 서빙용)와 완전히 무관합니다. GPU가 없는 팀원이 자기 이미지를 GPU 머신(이 문서 기준 사용자의 로컬 PC)으로 보내서 OCR+TTS 결과(데이터팩)를 대신 받기 위한, 순전히 내부 테스트용 도구입니다. 트랜스포트 프로토콜이 정해지는 것과도 무관하며, 그걸 기다릴 필요 없이 지금 바로 쓸 수 있습니다.

## 뭘 하는가

이미지를 업로드하면, 이미 있는 ingest 파이프라인(`document_parser.datapack.ingest`)을 그대로 돌려서 완성된 데이터팩을 zip으로 돌려줍니다. 팀원은 그 zip을 받아서 **자기 컴퓨터(GPU 없어도 됨)에서 `server/cli.py`로 바로 테스트**할 수 있습니다.

OCR은 한 번에 하나씩만 처리됩니다(GPU 하나를 여러 요청이 동시에 두들기지 않도록) — 여러 명이 동시에 요청해도 순서대로 큐에 쌓여서 처리됩니다.

## 서버 실행 (GPU 머신에서)

```bash
# GPU venv 필요 (docs/gpu-inference-setup.md), 그 위에 flask 추가 설치:
#   <venv>/Scripts/pip install document-parser[remote-ingest]   (또는 그냥 pip install flask)

python -m document_parser.datapack.remote_ingest \
  --api-key <아무 문자열이나 정해서> \
  --piper-model D:/models/piper-korean/ko_KR-kss-medium.onnx \
  --piper-espeak-data D:/espeak-ng-data
```

기본으로 `0.0.0.0:8420`에 바인딩됩니다 — 즉 이 컴퓨터뿐 아니라 같은 네트워크의 다른 기기에서도 접근 가능한 주소로 엽니다. `--api-key`는 유일한 인증 수단입니다(그 외 보안 장치 없음) — 아무 문자열이나 정해서 팀원에게 알려주면 됩니다.

## 팀원 쪽 사용법

```bash
# 1. 작업 제출
curl -X POST http://<이 컴퓨터의 LAN IP>:8420/jobs \
  -H "X-API-Key: <위에서 정한 값>" \
  -F "book_id=my_test_book" \
  -F "images=@p001.png" -F "images=@p002.png"
# -> {"job_id": "...", "status": "queued"}

# 2. 상태 확인 (몇십 초~몇 분 걸림, 페이지당 평균 1분 정도 -- docs/gpu-inference-setup.md 참고)
curl http://<LAN IP>:8420/jobs/<job_id> -H "X-API-Key: ..."
# -> {"status": "queued" | "running" | "done" | "error", ...}

# 3. 완료되면 다운로드
curl -OJ http://<LAN IP>:8420/jobs/<job_id>/download -H "X-API-Key: ..."
# -> my_test_book.zip 을 받음. 압축 풀면 datapacks/{book_id}/ 와 datapacks/_system/ 이 나옴.

# 4. 팀원이 자기 컴퓨터에서 바로 (GPU 불필요):
python -m document_parser.server.cli <압축 푼 datapacks 폴더> my_test_book
```

## 접근 확인 (이 부분은 직접 해봐야 합니다)

**이 컴퓨터에서 자체적으로 확인한 것** (2026-08-22):
- 실제로 서버를 띄우고 `0.0.0.0:8420`으로 바인딩한 뒤, 이 컴퓨터의 LAN IP(`ipconfig`로 확인, 예: `192.168.x.x`)로 curl 요청을 보내 정상 응답 확인함.
- Windows 방화벽이 현재 이 컴퓨터에서 **Domain/Private/Public 프로파일 전부 꺼져 있음**(`Get-NetFirewallProfile`로 확인) — 즉 지금 상태로는 방화벽이 이 포트를 막지 않습니다. (참고로 이건 이 도구만의 문제가 아니라 컴퓨터 전체가 방화벽 없이 열려 있다는 뜻이기도 하니, 원하시면 이 포트만 예외로 열고 방화벽은 다시 켜는 걸 권장합니다.)
- 실제 이미지로 전체 흐름(업로드 → OCR → TTS → zip 다운로드 → 압축 해제 → `server/cli.py`로 재생)을 처음부터 끝까지 실행해서 확인함 — 정상 작동.

**여기서부터는 제가 확인할 수 없는 부분입니다** (팀원이 있는 곳에서 직접 테스트 필요):
- 팀원 컴퓨터가 **실제로 같은 네트워크(같은 사무실 와이파이/유선, 또는 같은 VPN)에 있는지** — 다른 네트워크라면 이 IP로 아예 접속이 안 됩니다.
- 공유기/네트워크 장비가 기기 간 통신을 막아두지 않았는지(예: 게스트 와이파이 격리) — 이건 네트워크 설정에 달려 있어서 로컬에서는 확인이 안 됩니다.

**확인 방법**: 팀원에게 `curl http://<LAN IP>:8420/health` 를 실행해보라고 하면 됩니다. `{"status":"ok"}`가 오면 접근 가능한 것이고, 타임아웃/연결 거부가 나면 같은 네트워크가 아니거나 중간에 뭔가 막고 있는 겁니다 — 그 경우 VPN을 쓰거나, ngrok 같은 터널링 도구로 임시로 외부에 노출하는 걸 고려해야 합니다(이 문서는 그 경우까지는 다루지 않음, 필요하면 알려주세요).

## 알아둘 점

- 개발용 서버(Flask 내장 서버)라서 "프로덕션에 쓰지 말라"는 경고가 뜹니다 — 팀 내부 테스트 용도로는 문제없지만, 외부에 공개하거나 오래 방치할 용도는 아닙니다.
- `--api-key` 외에 다른 인증이 없습니다 — 그 값을 아는 사람은 누구든 이 컴퓨터의 GPU로 작업을 실행시킬 수 있습니다. 신뢰하는 팀 내에서만 공유하세요.
- 업로드는 요청당 최대 200MB로 제한돼 있습니다.
