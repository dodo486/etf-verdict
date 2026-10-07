# 로컬 실시간 서버 (M3) + 폰에서 보기

book-to-playbook 판정 페이지는 **로컬 실시간 서버**로 본다(정적 발행·GitHub Pages 는 폐지됐다).

| 여는 법 | 동작 |
|---------|------|
| `python3 -m publish.serve` 로 띄운 서버 | 매 요청 엔진을 새로 돌려 그리고, 15초마다 `/api/verdict` 폴링(또는 `/events` SSE)으로 값이 살아 움직인다 (`🟢 실시간 · jhts(marketdata) · 갱신 HH:MM:SS`). |

## 1. 서버 켜기

```bash
cd ~/claude-projects/etf-verdict/book-to-playbook
python3 -m publish.serve
```

콘솔에 뜨는 주소:

- 로컬:      `http://127.0.0.1:8799/`
- 판정 JSON: `http://127.0.0.1:8799/api/verdict`

포트를 바꾸려면:

```bash
PLAYBOOK_PORT=9000 python3 -m publish.serve
```

환경변수(선택):

| 변수 | 기본 | 뜻 |
|------|------|----|
| `PLAYBOOK_PORT` | `8799` | 포트 |
| `PLAYBOOK_HOST` | `0.0.0.0` | 바인딩 주소(LAN/테일스케일 접속 허용) |
| `PLAYBOOK_TTL`  | `8`    | 판정 캐시 TTL(초) — 잦은 폴링이 시세 창구를 두드리지 않게 |
| `PLAYBOOK_TICK` | `15`   | SSE tick 주기(초) |

## 2. 엔드포인트

| 경로 | 내용 |
|------|------|
| `GET /` `GET /index.html` | 최신 판정을 구워 넣은 플레이북 페이지(루트로 바로 열림, 이후 스스로 갱신) |
| `GET /api/verdict` | 판정 JSON(라이브). `verdict.verdict_engine` 으로 계산, 8초 TTL 캐시, CORS 허용 |
| `GET /events` | SSE — 15초마다 tick. 브라우저가 받으면 `/api/verdict` 를 한 번 더 당겨 다시 그림 |
| 기타 | `BASE` 디렉터리 정적 파일 서빙 |

`GET /api/verdict?force=1` 이면 캐시를 무시하고 새로 계산한다.

## 3. 폰에서 보기 (Tailscale)

집 밖에서도 폰으로 이 서버에 붙으려면 [Tailscale](https://tailscale.com) 이 가장 간단하다(방화벽/포트포워딩 없이 개인 VPN 메시).

1. **데스크톱(서버 켜는 컴퓨터)** 에 Tailscale 설치 후 로그인:
   ```bash
   # macOS: 앱 설치 후 로그인, 또는 CLI
   tailscale up
   ```
2. **폰** 에 Tailscale 앱 설치 → 같은 계정으로 로그인.
3. 데스크톱에서 서버를 켠다: `python3 -m publish.serve` (0.0.0.0 바인딩이라 이미 LAN/테일스케일에서 접속 가능).
4. 데스크톱의 Tailscale 주소를 확인:
   ```bash
   tailscale ip -4          # 예: 100.x.y.z
   tailscale status         # MagicDNS 이름도 확인 가능 (예: my-mac.tailXXXX.ts.net)
   ```
5. 폰 브라우저에서 열기:
   ```
   http://100.x.y.z:8799/
   또는  http://my-mac.tailXXXX.ts.net:8799/   (MagicDNS 켰을 때)
   ```

MagicDNS 를 켜 두면(관리 콘솔 → DNS) IP 대신 호스트 이름으로 접속할 수 있어 편하다. Tailscale 이 켜져 있는 한 카페·회사 등 **어디서든** 같은 주소로 붙는다.

### LAN(같은 와이파이)만 쓸 때

Tailscale 없이 같은 와이파이면 데스크톱의 LAN IP 로 바로 붙는다:

```bash
ipconfig getifaddr en0     # macOS 와이파이 IP (예: 192.168.0.42)
```
폰에서 `http://192.168.0.42:8799/`.

## 4. 종료

서버 콘솔에서 `Ctrl+C`.
