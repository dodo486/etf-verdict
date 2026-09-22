# 설치 · 스케줄 등록 (macOS / Windows 공용)

파이프라인은 **어느 OS·어느 폴더**에 두든 그대로 돈다. macOS 전용 가정
(`~/.claude/skills/book-to-playbook` 하드코딩, `/opt/homebrew/bin/python3`, bash 스크립트,
launchd)은 모두 걷어냈다.

## 0. 요구사항

- Python **3.7 이상** (표준 라이브러리만 사용 — pip 설치 불필요)
- git (자동 발행을 쓸 때만)

확인:

```
python --version        # Windows
python3 --version       # macOS
```

## 1. 경로 규칙

`paths.py` 가 단일 기준점이다. 하드코딩된 경로는 더 이상 없다.

| 값 | 결정 방식 |
|---|---|
| `BASE` | `$BOOK_TO_PLAYBOOK_HOME` → 없으면 **이 폴더**(`paths.py`가 있는 곳) |
| `PUBLIC` | `$BOOK_TO_PLAYBOOK_PUBLIC` → 없으면 **부모 폴더에 `.nojekyll`이 있으면 그 부모**, 아니면 `BASE/public` |
| `LOGS` | `BASE/logs` |

즉 두 가지 배치가 모두 된다.

```
# (A) 리포 안에서 바로 — PUBLIC = 리포 루트
<repo>/.nojekyll
<repo>/etf/index.html          ← 발행 대상
<repo>/book-to-playbook/       ← BASE

# (B) 스킬 폴더에 두고 public/ 으로 — 기존 macOS 배치
~/.claude/skills/book-to-playbook/          ← BASE
~/.claude/skills/book-to-playbook/public/   ← PUBLIC (별도 배포 리포)
```

현재 값 확인:

```
python paths.py
```

## 2. 크레덴셜

`BASE` 에 아래 파일을 두면 실행 시 자동으로 환경변수에 주입된다(없으면 건너뜀).
둘 다 `.gitignore` 처리되어 있다.

`kis.env` — 장중 자동판정용 (없으면 장중 항목이 "직접 확인"으로 표시될 뿐, 나머지는 정상)

```
KIS_APP_KEY=...
KIS_APP_SECRET=...
```

`telegram.env` — (선택) 알림. 없으면 데스크톱 알림으로 대체된다.

```
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

## 3. 수동 실행

```
python run.py daily        # EOD 판정 → 발행 (장 마감 후)
python run.py intraday     # 장중 판정 → 발행 (개장+31분)
python run.py publish      # 재판정 없이 현재 JSON으로 발행만
```

옵션: `--no-git`(커밋/푸시 생략) · `--no-push`(커밋만) · `--quiet`

래퍼도 있다 — macOS/Linux는 `./run.sh` / `./run_intraday.sh`, Windows는 `run.cmd` / `run.cmd intraday`.
파이썬 경로를 고정하고 싶으면 `BOOK_TO_PLAYBOOK_PYTHON` 환경변수를 쓴다.

첫 실행은 `--no-git` 으로 결과를 눈으로 확인한 뒤 자동화에 걸 것.

## 4. 스케줄 등록

기존 운용 주기: **EOD = 화~토 08:00 (KST)**, **장중 = 미국 개장 +31분**
(서머타임 23:01 / 표준시 00:01 KST). 아래 시각은 이 기준이며 필요에 맞게 바꾼다.

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

장중용은 같은 형식에 `Label`/인자를 `intraday` 로, 시각을 개장+31분으로 바꾼 별도 plist.

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
  /TR "\"D:\etf-verdict\book-to-playbook\run.cmd\" daily"

schtasks /Create /TN "book-to-playbook intraday" /SC DAILY /ST 23:01 ^
  /TR "\"D:\etf-verdict\book-to-playbook\run.cmd\" intraday"
```

```cmd
schtasks /Query  /TN "book-to-playbook daily" /V /FO LIST   :: 등록·마지막 결과 확인
schtasks /Run    /TN "book-to-playbook daily"               :: 즉시 1회 실행(테스트)
schtasks /Delete /TN "book-to-playbook daily" /F            :: 해제
```

노트북이 그 시각에 꺼져 있을 수 있으면 작업 스케줄러 GUI에서 해당 작업의
**"예약된 시작 시간을 놓친 경우 가능한 한 빨리 작업 시작"** 을 켠다.
(`schtasks` 명령줄로는 이 옵션이 지정되지 않는다.)

## 5. 자동 발행(git)

`PUBLIC` 이 git 리포이고 `origin` 이 있으면 실행 끝에 자동으로 커밋·푸시한다.
푸시를 원치 않으면 `--no-push`, 아예 건드리지 않으려면 `--no-git`.

`.gitattributes` 로 `eol=lf` 를 고정해 두었다 — 이게 없으면 맥과 윈도우가
같은 결과물을 서로 다른 줄바꿈으로 써서 매 실행마다 파일 전체가 diff로 뜬다.

## 6. 문제가 생기면

| 증상 | 원인 · 조치 |
|---|---|
| 콘솔에 한글이 `???` 로 | 옛 스크립트를 직접 실행한 경우. `run.py` 를 거치면 UTF-8이 강제된다 |
| `latest-verdict.json 없음 — 발행 중단` | 야후 조회 실패. `logs/cron.log` 의 stderr 확인(사내망 차단 여부) |
| 장중 항목이 계속 `⚫ 대기` | `kis.env` 없음 또는 개장+31분 작업이 안 돌았음 |
| 발행은 됐는데 사이트가 그대로 | 푸시 안 됨(`--no-push`/origin 없음) 또는 GitHub Pages 반영 지연 |
| `python` 을 못 찾음(Windows) | `BOOK_TO_PLAYBOOK_PYTHON` 에 python.exe 전체 경로 지정 |
