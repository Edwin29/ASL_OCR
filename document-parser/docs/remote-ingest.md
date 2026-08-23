# 원격 ingest 서버 (GPU 없는 팀원용 임시 도구)

**하드웨어(점자 디스플레이)까지 한 번에 테스트하려면 이 문서 대신 [hardware/stm_pi_bridge/README.md](../hardware/stm_pi_bridge/README.md)의 `combined_server.py` + `test_client.py`를 쓰세요** — 이미지 업로드부터 디스플레이 테스트 모드 진입까지 한 번에 이어집니다. 아래는 GPU 없는 팀원이 하드웨어 없이 데이터팩 파일만 받아가고 싶을 때를 위한, 순수 이미지→데이터팩 변환 전용 흐름입니다(계속 유효합니다).

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

**추천: 자동 클라이언트 스크립트.** [`tools/remote_ingest_client.py`](../tools/remote_ingest_client.py)를 팀원에게 파일 하나로 전달하면 됩니다 — 파이썬 표준 라이브러리만 쓰기 때문에 이 프로젝트를 따로 설치할 필요가 없습니다. 제출 → 완료 대기(자동 재확인) → 다운로드 → 압축 해제까지 한 번에 처리합니다.

```bash
python remote_ingest_client.py \
  --server <서버 주소 (LAN IP 또는 터널 주소)> \
  --api-key <서버 운영자가 알려준 값> \
  --book-id my_test_book \
  p001.png p002.png
```

완료되면 결과 폴더 경로와, 그걸 확인하는 다음 명령어(`python -m document_parser.server.cli <결과폴더> my_test_book`)까지 화면에 그대로 출력해줍니다.

**수동으로 하고 싶다면** (위 스크립트가 하는 일을 그대로 풀어놓은 것):
```bash
# 1. 작업 제출
curl -X POST http://<서버 주소>:8420/jobs \
  -H "X-API-Key: <위에서 정한 값>" \
  -F "book_id=my_test_book" \
  -F "images=@p001.png" -F "images=@p002.png"
# -> {"job_id": "...", "status": "queued"}

# 2. 상태 확인 (몇십 초~몇 분 걸림, 페이지당 평균 1분 정도 -- docs/gpu-inference-setup.md 참고).
#    "done"이 나올 때까지 몇 초 간격으로 반복 실행.
curl http://<서버 주소>:8420/jobs/<job_id> -H "X-API-Key: ..."
# -> {"status": "queued" | "running" | "done" | "error", ...}

# 3. 완료되면 다운로드
curl -OJ http://<서버 주소>:8420/jobs/<job_id>/download -H "X-API-Key: ..."
# -> my_test_book.zip 을 받음. 압축 풀면 {book_id}/ 와 _system/ 이 바로(추가 폴더 없이) 나옴.

# 4. 팀원이 자기 컴퓨터에서 바로 (GPU 불필요):
python -m document_parser.server.cli <압축 푼 폴더> my_test_book
```

## 접근 확인 (이 부분은 직접 해봐야 합니다)

**이 컴퓨터에서 자체적으로 확인한 것** (2026-08-22):
- 실제로 서버를 띄우고 `0.0.0.0:8420`으로 바인딩한 뒤, 이 컴퓨터의 LAN IP(`ipconfig`로 확인, 예: `192.168.x.x`)로 curl 요청을 보내 정상 응답 확인함.
- Windows 방화벽이 현재 이 컴퓨터에서 **Domain/Private/Public 프로파일 전부 꺼져 있음**(`Get-NetFirewallProfile`로 확인) — 즉 지금 상태로는 방화벽이 이 포트를 막지 않습니다. (참고로 이건 이 도구만의 문제가 아니라 컴퓨터 전체가 방화벽 없이 열려 있다는 뜻이기도 하니, 원하시면 이 포트만 예외로 열고 방화벽은 다시 켜는 걸 권장합니다.)
- 실제 이미지로 전체 흐름(업로드 → OCR → TTS → zip 다운로드 → 압축 해제 → `server/cli.py`로 재생)을 처음부터 끝까지 실행해서 확인함 — 정상 작동.

**여기서부터는 제가 확인할 수 없는 부분입니다** (팀원이 있는 곳에서 직접 테스트 필요):
- 팀원 컴퓨터가 **실제로 같은 네트워크(같은 사무실 와이파이/유선, 또는 같은 VPN)에 있는지** — 다른 네트워크라면 이 IP로 아예 접속이 안 됩니다.
- 공유기/네트워크 장비가 기기 간 통신을 막아두지 않았는지(예: 게스트 와이파이 격리) — 이건 네트워크 설정에 달려 있어서 로컬에서는 확인이 안 됩니다.

**확인 방법**: 팀원에게 `curl http://<LAN IP>:8420/health` 를 실행해보라고 하면 됩니다. `{"status":"ok"}`가 오면 접근 가능한 것이고, 타임아웃/연결 거부가 나면 같은 네트워크가 아닌 것입니다 — 아래 "다른 네트워크에 있는 팀원" 참고.

## 다른 네트워크에 있는 팀원 (Cloudflare Tunnel)

팀원이 같은 사무실/VPN이 아니라 완전히 다른 네트워크(집, 카페 등)에 있으면 LAN IP로는 접속이 안 됩니다. 이 경우 [Cloudflare Tunnel](https://github.com/cloudflare/cloudflared)의 "quick tunnel"을 씁니다 — 계정 가입 없이, 실행 파일 하나로 임시 공개 HTTPS 주소를 만들어서 로컬 포트로 그대로 전달합니다. 공유기 설정을 전혀 건드리지 않습니다(아웃바운드 연결만 만드는 방식).

```bash
# 1. cloudflared 다운로드 (Windows 64bit 기준, 한 번만)
curl -L -o cloudflared.exe https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe

# 2. remote_ingest 서버가 이미 떠 있는 상태에서, 터널 실행
cloudflared.exe tunnel --url http://localhost:8420
```

몇 초 뒤 다음과 비슷한 출력이 나옵니다:
```
Your quick Tunnel has been created! Visit it at (it may take some time to be reachable):
https://무작위-단어-4개.trycloudflare.com
```

이 `https://...trycloudflare.com` 주소를 팀원에게 LAN IP 대신 전달하면 됩니다 — 사용법(`/jobs`, `/jobs/<id>`, `/jobs/<id>/download`)은 완전히 동일하고, 주소만 바뀝니다. 실제로 이 주소로 업로드→상태확인→다운로드 전체 흐름이 정상 작동함을 확인했습니다(2026-08-22).

**알아둘 점**:
- 계정 없이 만든 임시 터널이라 **cloudflared 프로세스가 살아있는 동안만** 유효합니다. 껐다 다시 켜면 주소가 바뀝니다(고정 주소가 필요하면 Cloudflare 계정으로 "named tunnel"을 만들어야 하는데, 이 문서는 그 경우까진 다루지 않습니다).
- 이 순간부터 **서버가 진짜로 인터넷에 공개됩니다.** 보호 수단은 여전히 `X-API-Key` 하나뿐입니다 — 주소와 키를 아는 사람은 누구든 이 컴퓨터의 GPU로 작업을 실행시킬 수 있습니다. URL과 키 둘 다 신뢰하는 팀 안에서만 공유하세요.
- 터널도, 서버도 그걸 띄운 프로세스/세션이 끝나면 같이 내려갑니다.

## 알아둘 점

- 개발용 서버(Flask 내장 서버)라서 "프로덕션에 쓰지 말라"는 경고가 뜹니다 — 팀 내부 테스트 용도로는 문제없지만, 외부에 공개하거나 오래 방치할 용도는 아닙니다.
- `--api-key` 외에 다른 인증이 없습니다 — 그 값을 아는 사람은 누구든 이 컴퓨터의 GPU로 작업을 실행시킬 수 있습니다. 신뢰하는 팀 내에서만 공유하세요.
- 업로드는 요청당 최대 200MB로 제한돼 있습니다.
