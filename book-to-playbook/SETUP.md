# 설치 · 스케줄 등록 (macOS / Windows 공용)

파이프라인은 **어느 OS·어느 폴더**에 두든 그대로 돈다. macOS 전용 가정
(`~/.claude/skills/book-to-playbook` 하드코딩, `/opt/homebrew/bin/python3`, bash 스크립트,
launchd)은 모두 걷어냈다.

## 0. 요구사항

- Python **3.7 이상** (이 리포 자체는 표준 라이브러리만 사용)
- `jhts` 패키지(시세수집팀) — 시세 자동판정용. 없으면 판정이 "데이터 없음"으로 정직하게 나올 뿐 크래시하지 않는다
- git (자동 발행을 쓸 때만)

확인:

```
python --version        # Windows
python3 --version       # macOS
```

## 1. 경로 규칙

`shared/paths.py` 가 단일 기준점이다. 하드코딩된 경로는 더 이상 없다.

| 값 | 결정 방식 |
|---|---|
| `BASE` | `$BOOK_TO_PLAYBOOK_HOME` → 없으면 **이 폴더**(book-to-playbook 루트 — `shared/`의 부모) |
| `LOGS` | `BASE/logs` |

어느 폴더에 두든 그대로 돈다 — 화면은 로컬 실시간 서버(`entry.serve`)가 매 요청 그린다(정적 발행·GitHub Pages 폐지).

현재 값 확인:

```
python -m shared.paths
```

## 2. 크레덴셜

`BASE` 에 아래 파일을 두면 실행 시 자동으로 환경변수에 주입된다(없으면 건너뜀).
`.gitignore` 처리되어 있다. 시세 크레덴셜은 이 리포에 없다 — 수집은 jhts 시세수집팀 몫이다.

`telegram.env` — (선택) 알림. 없으면 데스크톱 알림으로 대체된다.

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

jhts 시세 패키지가 pip 설치가 아니면 `local.env` 에 경로를 적는다(커밋 안 함 — `local.env.example` 참고):

```
PYTHONPATH=C:\Users\<사용자>\jhts
```

## 3. 수동 실행

```
python -m entry.run daily        # 판정 → 백테스트 탭 데이터 → 검사 (장 마감 후)
python -m entry.run watch [--every N]  # asof=지금 기준 N분(기본 5)마다 재판정(장중 포함)
python -m entry.run check        # 검사만 전부(CHECKS 한 목록) — 요약 + 종료코드
```

옵션: `--quiet`(콘솔 최소화) · `--no-verify-tree`(tree 태그 검사 생략 — 트리 안정 후) · `--parity`(check 만 — 신호 패리티 추가)

래퍼도 있다 — macOS/Linux는 `./run.sh`, Windows는 `run.cmd`.
파이썬 경로를 고정하고 싶으면 `BOOK_TO_PLAYBOOK_PYTHON` 환경변수를 쓴다.

첫 실행은 콘솔 출력을 눈으로 확인한 뒤 자동화에 걸 것(자동 git 푸시는 없다 — 커밋은 직접 한다).

## 4. 스케줄 등록

운용 주기: **화~토 08:00 (KST)** — 미국 장 마감 후 종가 기준 판정. 필요에 맞게 바꾼다.
(이건 발행 스케줄일 뿐 판정 시점의 제한이 아니다 — 판정은 보는 그 순간(asof) 기준이고, 장중에도
`python -m entry.run watch [--every N]` 이 asof=지금으로 N분마다 재판정한다.)

### macOS (launchd)

`~/Library/LaunchAgents/com.book-to-playbook.daily.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.book-to-playbook.daily</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>/Users/<사용자>/.claude/skills/book-to-playbook/run.sh</string>
    <string>daily</string>
  </array>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>8</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>8</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>8</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>8</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Weekday</key><integer>6</integer><key>Hour</key><integer>8</integer><key>Minute</key><integer>0</integer></dict>
  </array>
  <key>StandardErrorPath</key><string>/Users/<사용자>/.claude/skills/book-to-playbook/logs/launchd.err</string>
</dict>
</plist>
```

```bash
launchctl load  ~/Library/LaunchAgents/com.book-to-playbook.daily.plist
launchctl list | grep book-to-playbook          # 등록 확인
launchctl start com.book-to-playbook.daily      # 즉시 1회 실행(테스트)
launchctl unload ~/Library/LaunchAgents/com.book-to-playbook.daily.plist   # 해제
```

### Windows (작업 스케줄러)

관리자 권한 없이 등록된다. 경로는 실제 설치 위치로 바꿀 것.

```cmd
schtasks /Create /TN "book-to-playbook daily" /SC WEEKLY /D TUE,WED,THU,FRI,SAT /ST 08:00 ^
  /TR "\"D:\book-to-playbook\run.cmd\" daily"

:: 장중 재판정(asof=지금 기준) — 21:30 에 띄우면 그때부터 --every N 분마다 재판정·발행한다(종료 전까지)
schtasks /Create /TN "book-to-playbook watch" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 21:30 ^
  /TR "\"D:\book-to-playbook\run.cmd\" watch"
```

```cmd
schtasks /Query  /TN "book-to-playbook daily" /V /FO LIST   :: 등록·마지막 결과 확인
schtasks /Run    /TN "book-to-playbook daily"               :: 즉시 1회 실행(테스트)
schtasks /Delete /TN "book-to-playbook daily" /F            :: 해제
```

노트북이 그 시각에 꺼져 있을 수 있으면 작업 스케줄러 GUI에서 해당 작업의
**"예약된 시작 시간을 놓친 경우 가능한 한 빨리 작업 시작"** 을 켠다.
(`schtasks` 명령줄로는 이 옵션이 지정되지 않는다.)

## 4-1. 내 포지션 (`books/<slug>/positions.json` — 커밋하지 않음)

```json
{"positions": [{"prod": "TQQQ", "entry_date": "20260915", "entry_px": 81.2}]}
```

화면의 청산·분할 판정은 이 파일의 보유분에 대해 낸다. 없으면 규칙 목록만 보인다. 개인 정보라 `.gitignore` 대상이고
로컬 서버 화면에서만 보인다.

## 5. 줄바꿈(git)

`.gitattributes` 로 `eol=lf` 를 고정해 두었다 — 이게 없으면 맥과 윈도우가
같은 결과물을 서로 다른 줄바꿈으로 써서 매 실행마다 파일 전체가 diff로 뜬다.
(정적 발행·자동 push 는 폐지됐다 — 커밋은 직접 한다. 화면은 `entry.serve` 가 맡는다.)

## 6. 문제가 생기면

| 증상 | 원인 · 조치 |
|---|---|
| 콘솔에 한글이 `???` 로 | 옛 스크립트를 직접 실행한 경우. `run.py` 를 거치면 UTF-8이 강제된다 |
| 판정이 전부 ❔ 판정 불가 | jhts 시세 조회 실패. `logs/cron.log` 의 stderr, 페이지 상단 '시세 없음 → 수집 요청' 확인 |
| 🟡 확인 대기만 나온다 | 수동(✋) 조건(개장 전·장중·저자 미명시)이 있어서다 — 체크리스트에서 직접 체크하면 등급이 다시 계산된다 |
| `판정 파일 없음 — 발행 중단` | `run.py daily` 가 먼저 돌아야 한다(jhts 가 PYTHONPATH 에 있는지 확인) |
| 값이 안 바뀐다 | 캐시 TTL(기본 8초) 대기 또는 `/api/verdict?force=1` · 서버 재시작(`entry.serve`) |
| `python` 을 못 찾음(Windows) | `BOOK_TO_PLAYBOOK_PYTHON` 에 python.exe 전체 경로 지정 |

## 7. 로컬 실시간 서버로 보기 (폰 포함)

판정 페이지는 **로컬 실시간 서버**로 본다(정적 발행·GitHub Pages 는 폐지 — §5). 매 요청마다 엔진을 새로
돌려 그리고, SSE/폴링으로 값이 살아 움직인다(`🟢 실시간 · jhts(marketdata) · 갱신 HH:MM:SS`).

```bash
python3 -m entry.serve                 # http://127.0.0.1:8799/ · 판정 JSON /api/verdict
PLAYBOOK_PORT=9000 python3 -m entry.serve   # 포트 변경
```

| 환경변수 | 기본 | 뜻 |
|------|------|----|
| `PLAYBOOK_PORT` | `8799` | 포트 |
| `PLAYBOOK_HOST` | `0.0.0.0` | 바인딩 주소(LAN/테일스케일 접속 허용) |
| `PLAYBOOK_TTL`  | `8`    | 판정 캐시 TTL(초) — 잦은 폴링이 시세 창구를 두드리지 않게 |
| `PLAYBOOK_TICK` | `15`   | SSE tick 주기(초) |

| 경로 | 내용 |
|------|------|
| `GET /` | 최신 판정을 구워 넣은 플레이북 페이지(이후 스스로 갱신) |
| `GET /api/verdict` | 판정 JSON(라이브) — `consumers.display.verdict_view` 로 계산, 8초 TTL 캐시, CORS 허용. `?force=1` 이면 캐시 무시 |
| `GET /events` | SSE — tick 마다 브라우저가 `/api/verdict` 를 다시 당겨 그림 |

**폰에서 보기**: 서버는 `0.0.0.0` 바인딩이라 같은 와이파이면 데스크톱 LAN IP 로 바로 붙는다
(`ipconfig getifaddr en0` → `http://192.168.x.y:8799/`). 집 밖에서도 보려면 [Tailscale](https://tailscale.com)
을 데스크톱·폰 양쪽에 깔고 같은 계정으로 로그인한 뒤 `tailscale ip -4`(예 `100.x.y.z`) 주소로 붙는다
(MagicDNS 를 켜면 호스트 이름으로도 됨). 종료는 서버 콘솔에서 `Ctrl+C`.
