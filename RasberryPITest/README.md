# Raspberry Pi 4 bounded load controller

전력 측정을 위해 모니터나 키보드 없이 부팅 직후 CPU와 메모리 점유율을 80%대로 유지하는 프로그램입니다. 기본 목표는 CPU 84%, 메모리 84%이며, 실제 측정값이 89%에 도달하면 즉시 부하를 줄입니다.

> 점유율 측정과 제어에는 지연이 있으므로 모든 순간에 90% 미만임을 수학적으로 보장할 수는 없습니다. 이 프로그램은 상한을 89%로 설정하고 1초마다 피드백 제어합니다. 중요한 데이터가 없는 시험용 OS 이미지에서만 사용하세요.

## 안전장치

- CPU 또는 메모리 측정값 89% 이상에서 즉시 부하 감소
- CPU 온도 80°C 이상에서 CPU 부하 감소
- 운영체제용 가용 메모리 최소 256 MiB 보존
- 서비스 중지 시 할당 메모리 해제
- 낮은 프로세스 우선순위(`Nice=10`)와 높은 OOM 종료 우선순위 적용
- 프로그램 인자로 89%보다 높은 상한 설정 차단

## GitHub를 통한 설치

라즈베리파이에서 저장소를 복제한 뒤 실행합니다. 아래 URL은 자신의 저장소 URL로 바꾸세요.

```sh
git clone https://github.com/USERNAME/REPOSITORY.git
cd REPOSITORY/RasberryPITest
chmod +x install.sh uninstall.sh
sudo ./install.sh
```

설치 스크립트는 프로그램을 `/opt/raspberry-pi-load`에 복사하고 systemd 서비스를 등록해 현재 즉시 실행하며, 이후 부팅 때마다 자동 실행합니다.

## 확인 및 제어

```sh
systemctl status raspberry-pi-load.service
journalctl -u raspberry-pi-load.service -f
sudo systemctl stop raspberry-pi-load.service
sudo systemctl start raspberry-pi-load.service
```

서비스를 완전히 제거하려면 다음을 실행합니다.

```sh
sudo ./uninstall.sh
```

## 목표값 변경

`raspberry-pi-load.service`의 `ExecStart` 인자를 수정한 후 다시 설치하세요. 권장 범위는 목표값 82~86%, 상한 88~89%입니다.

```sh
sudo ./install.sh
```

지원 인자:

```text
--cpu-target 84
--memory-target 84
--upper-limit 89
--temperature-limit 80
--interval 1.0
--memory-chunk-mb 8
--minimum-available-mb 256
```

메모리 1GB 모델에서는 OS 상태에 따라 84% 목표와 256MiB 보존 조건을 동시에 만족하지 못할 수 있습니다. 이때 프로그램은 점유율 목표보다 가용 메모리 보존을 우선합니다.

## 로컬 테스트

```sh
python3 -m unittest -v
```
