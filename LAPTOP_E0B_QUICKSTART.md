# E0-B.1 Laptop 빠른 시작 — Tailscale + 준비된 영상

이 절차는 Laptop과 Desktop이 같은 LAN에 없지만 각각 인터넷에 연결된 환경을 기준으로 한다.
E0-B.1에서는 camera와 STM/HC-05 대신 준비된 MP4와 console controls를 사용해 Server 송수신과
reading data 수신까지 확인한다. 실제 camera/STM/speaker 검증은 후속 physical E0-B다.

## 1. 양쪽 컴퓨터에 Tailscale 설치

Desktop과 Laptop 모두 아래 명령을 실행한 뒤 **같은 Tailscale 계정**으로 로그인한다. 개인 prototype은
별도 도메인을 구매하지 않고 Tailscale Personal tailnet을 사용할 수 있다.

```bat
winget install --id Tailscale.Tailscale -e
```

Laptop에는 Git과 Python 3.11도 설치한다.

```bat
winget install --id Git.Git -e
winget install --id Python.Python.3.11 -e
```

설치 후 terminal을 다시 열고 `git --version`, `py -3.11 --version`, `tailscale status`를 확인한다.
Laptop이 Desktop과 같은 tailnet의 device 목록에 보여야 한다.

## 2. Laptop에 저장소 받기

```bat
set GIT_LFS_SKIP_SMUDGE=1
git clone --branch codex/asl-ocr-integration-c0-handoff --single-branch https://github.com/Edwin29/ASL_OCR.git D:\ASL_OCR
cd /d D:\ASL_OCR
```

이미 clone했다면 해당 폴더에서 다음을 실행한다.

```bat
git switch codex/asl-ocr-integration-c0-handoff
git pull --ff-only
```

## 3. Model bundle 다운로드

다음 ZIP을 Laptop에 직접 다운로드하고 압축을 푼다. Desktop에서 복사할 필요가 없다.

- [E0-B model bundle ZIP](https://github.com/Edwin29/ASL_OCR/releases/download/e0b-model-bundle-2026-09-01/ASL_OCR_E0B_MODEL_BUNDLE_2026-09-01.zip)
- ZIP SHA-256: `44fa79a338d397e31519474c87db60eaed73025198a7c5673ecc1424ced0f817`

압축을 푼 뒤 Setup에 전달할 폴더는 바로 아래에 `uvdoc`과 `paddle`이 있는
`E0B_MODEL_BUNDLE` 폴더다. Setup이 Paddle manifest의 모든 asset hash도 다시 검사한다.

## 4. Desktop Server와 고정 HTTPS 주소 시작

Desktop 저장소 root에서 두 batch를 각각 별도 terminal로 실행한다.

```bat
tools\windows\e0b-start-server.bat D:\device-config\secrets\device-api-key.txt D:\device-config\state\e0b-bench
tools\windows\e0b-start-tailscale-serve.bat
```

두 번째 batch는 local health를 먼저 검사하고 Tailscale Serve를 `127.0.0.1:8421`에 연결한 뒤 다음과
같은 고정 주소를 출력한다.

이 tailnet에서 Serve를 처음 사용하는 경우 batch가 다음 형태의 1회 활성화 링크를 먼저 출력할 수
있다.

```text
Serve is not enabled on your tailnet.
To enable, visit: https://login.tailscale.com/f/serve?node=...
```

링크를 browser에서 열고 **Desktop Tailscale과 같은 tailnet 소유 계정**으로 로그인한 뒤 Serve를
활성화한다. API key나 Tailscale auth key를 입력하는 단계가 아니다. 활성화가 끝나면 최초 batch를
종료하고 `e0b-start-tailscale-serve.bat`를 다시 실행한다. 이 관리 화면 활성화는 tailnet당 최초 한
번만 필요하다.

```text
ORIGIN=https://<desktop-machine>.<tailnet>.ts.net
```

이 주소는 Quick Tunnel처럼 매 실행마다 바뀌지 않는다. Tailscale 로그아웃이나 machine 이름 변경을
하지 않는 한 Laptop config에서 계속 재사용한다. Laptop browser 또는 terminal에서 다음 health가
성공하는지 확인한다.

```powershell
Invoke-RestMethod https://<desktop-machine>.<tailnet>.ts.net/api/v1/health
```

주소는 public Internet에 공개되지 않으며 같은 tailnet의 device만 도달할 수 있다. API 요청에는 기존
별도 API key도 계속 필요하다. Tailscale Serve 자체 credential은 복사하지 않는다.

`tailscale serve`가 활성화 링크에서 계속 대기하거나 권한 오류를 내면 Desktop에서 batch를 관리자
권한으로 다시 실행한다. Laptop health가 실패하면 양쪽 Tailscale이 Connected인지, 같은 tailnet device
목록에 보이는지, Desktop Server terminal이 계속 실행 중인지 순서대로 확인한다.

2026-09-01 Desktop 검증에서는 Serve reset/start 뒤 hostname 동일, private HTTPS health `ok`와 동일
Server instance가 확인됐다. 실제 hostname은 private tailnet 식별자이므로 Git 문서에 기록하지 않고
Desktop wrapper 출력값을 Laptop setup에 전달한다.

## 5. Laptop replay 자동 Setup

준비된 책 영상 MP4가 `D:\Downloads\scanner-replay.mp4`, 압축을 푼 model 폴더가
`D:\Downloads\E0B_MODEL_BUNDLE`이라고 가정하면 다음을 실행한다.

```bat
cd /d D:\ASL_OCR
tools\windows\e0b-replay-setup.bat D:\Downloads\scanner-replay.mp4
```

화면에서 입력하는 값은 네 가지뿐이다.

- 위 단계의 `https://...ts.net` Server origin
- Device ID: 예를 들어 `laptop-device-001`
- model bundle의 `E0B_MODEL_BUNDLE` 폴더 경로
- Desktop Server와 동일한 API key

COM port와 camera index/width/height/FPS는 replay mode에서 묻지 않고 사용하지 않는다. Setup은 다음을
자동 수행한다.

1. `.venv-e0b` Python 3.11 환경과 pinned dependency 설치
2. remote connectivity와 replay/console config 생성
3. API key를 TOML 밖의 local secret file에 저장
4. model bundle 구조와 hash 검증·복사
5. MP4를 `D:\ASL_OCR_E0B\inputs\scanner-replay.mp4`로 복사
6. 첫 frame decode, file SHA-256과 크기를 `reports\e0b-replay-input.json`에 기록
7. Tailscale HTTPS Server health 확인

실제 camera/COM/audio hardware preflight는 실행하지 않는다.
생성된 replay config에는 Laptop CPU에서 기존 N=5 footer identity 관측을 끝낼 수 있도록
`opaque_identity_max_collection_ms = 30000`이 명시된다. 이 값은 replay profile에만 적용되며
physical camera profile의 기본 `1500ms`, N=5와 candidate threshold는 바꾸지 않는다.
고정 `test1.mp4`의 검증된 source cadence는 `sample_interval_ms = 100`이다. 500ms로 바꾸면 성공
candidate frame 92/365를 건너뛰므로 같은 acceptance가 아니다.

E0-B.2 이전에 setup한 `D:\ASL_OCR_E0B\device-app.e0b.toml`은 저장소를 pull하는 것만으로 자동
갱신되지 않는다. 최신 저장소를 받은 뒤 위 setup을 같은 영상/model bundle로 다시 실행하거나,
해당 config의 `[scanner]`에 다음 한 줄이 있는지 확인한다.

```toml
sample_interval_ms = 100
opaque_identity_max_collection_ms = 30000
```

## 6. Replay 실행과 확인

```bat
tools\windows\e0b-replay-run.bat
```

console에서는 `up`, `down`, `left`, `right`, `next`, `prev`, `confirm`, `lever`를 입력할 수 있다.
기본 흐름은 새 데이터팩 항목을 `up/down`으로 선택하고 `confirm`, artifact/V4 ACK의 `spread_sent`와
영상 종료의 `scan_input_exhausted`를 확인한 뒤 다시 `confirm`하여 scan을 닫고 READY/reading 진입을
기다리는 것이다. Reading 중 `right`, `next` 등의 명령을 입력하면 바뀐 Server 응답이 다음 형태의
JSON line으로 표시돼야 한다.

E0-B.3.1부터 console event ID에는 process boot namespace가 포함된다. `새 데이터팩 추가`를 confirm한
직후 `confirm_selection`의 `datapack_id`가 이전 완료 실행의 ID와 다른지 확인한다. 이전 ID가 다시
표시되면 fresh acceptance가 아니므로 `Ctrl+C`로 중단하고 repository revision을 확인한다. 명령 수를
임의로 바꿔 idempotency key를 회피하는 방법은 acceptance 절차로 사용하지 않는다.

```json
{"type":"reading_snapshot","reading_session_id":"...","datapack_id":"...","cursor":{},"braille_cells":[],"audio_ref":"..."}
```

같은 snapshot을 polling한 결과는 중복 출력하지 않는다. 종료는 `Ctrl+C`다. 이 성공은
`MP4 -> Scanner -> V3-B -> Tailscale HTTPS -> V4/S1 -> READY -> reading snapshot`을 입증하지만 실제
camera, HC-05/STM, 점자 셀이나 speaker를 입증하지 않는다.

영상이 끝나면 다음 feedback이 정확히 한 번 표시된다. 아래 값은 E0-B에 고정한 `test1.mp4`
SHA-256 `16c57970bc493abcef4a1db0f1917b22956bf5ca1a2ee8b4565fde1f6574e6f8`의 기대값이다.

```json
{"type":"feedback","code":"scan_input_exhausted","details":{"queued_count":2,"acked_count":2}}
```

이 영상의 runtime acceptance 기대값은 전송 가능한 candidate 2개와 `spread_sent` sequence 1, 2다.
실제 E0-B.3.1 이후 로그에서 두 candidate는 각각 `candidate_verification` 5/5 `different`를 통과했다.
그 사이의 `page_change` identity는 이미 전송한 펼침면이 바뀌었는지 감시하며, `same`이면 대기를
계속하고 5/5 `different`이면 새 candidate 검색을 재개한다. runtime `source_frame_id`의 숫자를 책
페이지 번호나 원본 MP4 frame 번호로 해석하지 않는다. 310/311 등의 영상별 품질 평가는 offline audit
층에 남기며 runtime identity event의 직접 인과 증거로 승격하지 않는다. `candidate_selected`는 곧
`spread_sent`를 뜻하지 않는다.

E0-B.3.2부터 다음 bounded JSONL에 `identity_role`이 함께 표시된다. raw OCR token이나 image는 출력하지
않는다.

```json
{"type":"feedback","code":"candidate_selected","details":{"identity_role":"candidate_verification","source_frame_id":"...","spread_id":"..."}}
{"type":"feedback","code":"identity_collection_progress","details":{"identity_role":"candidate_verification","valid_observations":5,"query_sample_count":5}}
{"type":"feedback","code":"identity_collection_decided","details":{"identity_role":"candidate_verification","decision":"different","valid_observations":5,"query_sample_count":5}}
{"type":"feedback","code":"identity_collection_decided","details":{"identity_role":"page_change","decision":"same","valid_observations":1,"query_sample_count":5}}
```

E0-B.3.3부터 ACK callback에서 생성된 page-change 시작 event도 Device feedback으로 전달된다. 각 ACK의
최소 기대 순서는 다음과 같다.

```json
{"type":"feedback","code":"spread_sent","details":{"sequence":1}}
{"type":"feedback","code":"identity_collection_started","details":{"source_frame_id":"...","spread_id":"...-spread-000001","identity_role":"page_change","query_sample_count":5}}
{"type":"feedback","code":"identity_collection_progress","details":{"identity_role":"page_change","valid_observations":1,"query_sample_count":5}}
```

`identity_collection_started`는 새 candidate 또는 추가 spread가 아니다. 방금 ACK된 spread를 기준으로
page-change 감시가 시작됐다는 observer event다. 동일 ACK에서 한 번만 나타나야 한다.

- `queued_count >= 1`, `acked_count >= 1`이고 `spread_sent`를 확인했다면 `confirm`을 입력한다.
- `queued_count >= 1`, `acked_count = 0`이면 아직 전송 settlement 중일 수 있으므로
  `spread_sent` 또는 명시적 retry/reject feedback을 먼저 기다린다.
- `queued_count = 0`이면 artifact가 생성되지 않은 실패다. `confirm`으로 빈 datapack을 성공 처리하지
  말고 `Ctrl+C`로 종료한 뒤 마지막 `scanner_guidance` 또는 `footer_identity_unavailable`을 보존한다.

`scan_input_exhausted`는 EOF를 알릴 뿐 자동 ACK·seal·READY authority가 아니다. Paddle의
`No ccache found`, oneDNN 정보와 Windows의 “제공된 패턴에 해당되는 파일을 찾지 못했습니다” 메시지는
단독으로는 replay 실패 원인이 아니다.

진단 report가 필요하면 UTF-8 no-BOM writer로 한 실행의 출력을 보존한다. Windows PowerShell 5.1의
`Start-Transcript`는 native/Python child output을 빠뜨릴 수 있고 `Tee-Object`는 UTF-16 LE 파일을 만들 수
있으므로 E0-B JSONL 증거 수집에 사용하지 않는다.

```powershell
$log = "D:\ASL_OCR_E0B\reports\e0b-replay-console.log"
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText($log, "", $utf8NoBom)

& .\tools\windows\e0b-replay-run.bat D:\ASL_OCR_E0B 2>&1 |
  ForEach-Object {
    $line = [string]$_
    $line
    [System.IO.File]::AppendAllText(
      $log,
      $line + [Environment]::NewLine,
      $utf8NoBom
    )
  }

.\.venv-e0b\Scripts\python.exe `
  .\tools\windows\e0b_replay_boundary_report.py `
  D:\ASL_OCR_E0B\reports\e0b-replay-console.log `
  D:\ASL_OCR_E0B\reports\e0b-replay-input.json `
  D:\ASL_OCR_E0B\reports\e0b-replay-boundary.json
```

report schema v2는 candidate attempt와 page-change check를 별도로 집계한다. E0-B.3.3 start가 있으면
page-change check에 accepted `spread_id`와 시작 frame lineage도 보존한다. 두 candidate의 5/5
`different`, sequence `[1,2]`, EOF 2/2, revision 1 저장과 L/R 4페이지 reading이 runtime 성공 조건이다.
4/5 hard-reject나 1/5 EOF abort는 필수 조건이 아니다. Laptop log와 source hash만 통과하면 report
상태는 `provisional`이다. Server 확인 결과를 다음 형태의 JSON으로 저장하고 `--server-summary <path>`를
추가했을 때만 `passed`가 된다.

```json
{"spread_receipts":2,"fragments":4,"duplicates":0}
```

## 7. Desktop 단일 호스트 rehearsal

Laptop과 Desktop을 반복 이동하기 어려울 때는 준비된 E0-B root를 Desktop에 한 번 마련한 뒤 다음
명령으로 Scanner→V4/S1→save→reading 전체 소프트웨어 경계를 자동 검증할 수 있다.

```bat
tools\windows\e0b-desktop-loopback-acceptance.bat D:\ASL_OCR_E0B
```

E0-B.4-D harness는 실행별 loopback port, Server SQLite, Device outbox/artifact와 secret work directory를
격리한다. JSON event를 기준으로 두 번의 `confirm`, 4페이지 `down`, 마지막 `up`을 자동 입력하고 UTF-8
console log, Server 2/4/0 evidence와 schema v2 boundary report를 저장한다. 기본 산출물은 저장소
`tmp\e0b-loopback-runs\<run-id>\evidence`에 생성된다.

이 결과는 `environment=desktop_loopback`인 rehearsal 증거다. 실제 Laptop↔Tailscale host/network 경계,
camera, STM/HC-05와 speaker를 통과했다는 증거는 아니며, E0-B.4-L과 Physical E0-B는 별도로 남는다.

## 8. Desktop audio transport와 직접 청취

`reading_snapshot.audio_ref`가 실제 WAV로 해석되고 Desktop 기본 출력장치로 재생되는지는 별도 도구로
검증한다. 먼저 소리를 내지 않는 자동 검사만 실행할 수 있다.

```bat
tools\windows\e0b-desktop-audio-transport-acceptance.bat D:\ASL_OCR_E0B --no-playback
```

정상 결과는 `automated_transport_status=passed`, `status=manual_pending`이다. 실제 청취까지 수행하려면
Windows 설정에서 시연할 스피커·이어폰을 기본 출력장치로 선택하고 음량을 20~30%로 낮춘 뒤 다음을
실행한다.

```bat
tools\windows\e0b-desktop-audio-transport-acceptance.bat D:\ASL_OCR_E0B
```

기대 순서는 다음과 같다.

1. 짧은 beep
2. 낮은 짧은 tone
3. 약 0.4초 뒤 높은 짧은 tone

도구가 묻는 beep·저음·고음·음높이 구분에 모두 `yes`로 답한 뒤에만 `heard`를 입력한다. 장치나 음량을 바꾸고 다시 재생하려면
`retry`, 하나라도 들리지 않으면 `not-heard`를 입력한다. 재생은 WAV bytes를 메모리에서 수행하며
Device 쪽 영구 WAV 파일을 만들지 않는다. 기본 evidence는
`tmp\e0b-audio-runs\<run-id>\evidence`에 저장된다.

SAPI는 이 acceptance에서 제외됐다. 실제 Piper 한국어 합성·전송·청취는 다음 명령으로 별도 검증한다.

```bat
tools\windows\e0b-desktop-piper-transport-acceptance.bat D:\ASL_OCR_E0B
```

`--no-playback`을 붙이면 실제 Piper 합성과 인증 transport만 자동 확인하고 `manual_pending`으로 남긴다.
수동 모드는 두 고정 한국어 문장이 들리고 문구와 순서가 이해됐는지 구성요소별로 묻는다. 이 고정 문장
검증은 production Piper 경로 증거지만 전체 수학·표 발화 품질 평가는 아니다. reading navigation과
재생 generation 결합·이전 재생 중단, Raspberry Pi ALSA/PipeWire backend는 후속 패킷이다.

## 9. Device Runtime 통합 reading audio

Device Runtime의 실제 reading audio 다운로드·RAM cache·navigation 중단을 포함한 Desktop 통합 검증은
저장소 루트에서 다음 명령으로 실행한다.

```bat
tools\windows\e0b-device-audio-playback-acceptance.bat D:\ASL_OCR_E0B --no-playback
```

`--no-playback`은 실제 Piper 합성, S0 인증 다운로드, generation `[0,1,2,3,4]`, 중단 2회, cache hit와
client WAV 파일 0을 자동 검증하고 `manual_pending`으로 남긴다. 실제 기본 출력장치를 검증할 때는 옵션을
제거한다. 첫 페이지 음성을 끝까지 들은 뒤 두 번째 페이지 음성이 재생 중 중단되고, 첫 페이지 cache
재방문과 빠른 연속 이동 후 최신 음성만 남는지 확인해 각 질문에 `yes`, 마지막에 `heard`를 입력한다.

```bat
tools\windows\e0b-device-audio-playback-acceptance.bat D:\ASL_OCR_E0B
```

이 도구는 `D:\venvs\gpu_ocr_test` 또는 `E0B_PIPER_PYTHON`이 가리키는 환경에 `piper-tts`와 실제 재생용
`sounddevice`가 필요하다. SAPI fallback이나 client WAV 영구 저장은 사용하지 않는다.

## 10. 종료와 fallback

Desktop에서 Server terminal을 `Ctrl+C`로 종료한다. Serve 설정도 지우려면 다음을 실행한다.

```bat
tools\windows\e0b-stop-tailscale-serve.bat
```

Tailscale을 사용할 수 없는 1회 시험에는 기존 `e0b-start-quick-tunnel.bat`를 fallback으로 쓸 수 있다.
그 주소는 public이고 재시작 때 바뀌므로 E0-B.1 고정 endpoint acceptance 증거로는 사용하지 않는다.
