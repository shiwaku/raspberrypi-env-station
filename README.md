# raspberrypi-env-station

室内に置いた Raspberry Pi 4 Model B（8GB）で、CO2・温度・湿度を定期的に計測して SQLite に記録する。
同じ Pi で、気象庁の防災情報 XML と、みちびき（QZSS）の L1S 信号で配信される災危通報を受け取る。
結果は、帰宅に使う在来線と出張で使う新幹線の運行状況、よく使う便の遅延・欠航とあわせて、室内の大型モニターに地図とグラフで常時表示する（ダッシュボード・XML 取得・交通情報は未実装）。

**設計図**: https://shiwaku.github.io/raspberrypi-env-station/design.html （元ファイルは [docs/design.html](docs/design.html)。`main` にマージすると GitHub Pages に反映される）

| 役割 | 機材 | 接続 | 状態 |
|---|---|---|---|
| CO2・温度・湿度 | 秋月 AE-SCD40-BO（Sensirion SCD40） | I2C 0x62 | 購入済み |
| 災危通報の受信 | u-blox MAX-M10S 搭載ボード + SMA アクティブアンテナ | UART | 未購入 |
| 気象情報（警報・注意報・地震） | 気象庁 防災情報XML の Atom フィード | 共用 Wi-Fi → インターネット | 未実装 |
| 鉄道の運行状況（帰宅に使う在来線、出張で使う新幹線） | ODPT など（入手先を調査中、#12） | 共用 Wi-Fi → インターネット | 未実装 |
| 飛行機の遅延・欠航（よく使う行き先の出発便） | ODPT など（入手先を調査中、#13） | 共用 Wi-Fi → インターネット | 未実装 |
| 設置場所 | `config.toml` の `[station]` に緯度経度を書く | — | — |

設置場所は動かないので GPS では測らない。

## 配線

基板のシルク表示でピン名を確認し、電源を切ってから配線する。

| 機材のピン | Raspberry Pi（物理ピン） |
|---|---|
| SCD40 VIN(+)（赤） | 3.3V（1 番） |
| SCD40 GND(G)（黒） | GND（6 番） |
| SCD40 SDA(D)（青） | GPIO2 / SDA（3 番） |
| SCD40 SCL(C)（黄） | GPIO3 / SCL（5 番） |
| MAX-M10S 電源 | 3.3V（17 番）※ 電源電圧はボードの仕様で要確認 |
| MAX-M10S GND | GND（9 番） |
| MAX-M10S TX | GPIO15 / RXD（10 番） |
| MAX-M10S RX | GPIO14 / TXD（8 番） |

TX と RX は交差させる（受信機の TX → Pi の RXD）。

- GPIO の 40 本のピンは、基板の長い辺の端に 2 列で並ぶ。1 番は USB・LAN 端子から遠い端で、基板の内側の列にある（裏から見るとハンダが四角）。内側の列が奇数、端の列が偶数
- 端の列の 1 番側の 2 本（2 番・4 番）は 5V。センサーの電源をここに差すと壊れる
- AE-SCD40-BO は付属ケーブルを基板の CN1 に差し、反対側のメスのソケットを Pi のピンに差す。色は黒 GND・赤 VIN・青 SDA・黄 SCL（基板の G・+・D・C の印字と見比べて確かめる）
- 向きのわかる図は[設計図の配線](https://shiwaku.github.io/raspberrypi-env-station/design.html)にある

## Raspberry Pi の準備

### Tera Term の鍵を作る（PC で作業）

Pi には PC の Tera Term から SSH で入る。パスワードでは入れないようにし、鍵の認証だけを許す。

1. Tera Term を起動し、「設定」→「SSH 鍵生成」を開く。
2. 鍵の種類に **ED25519** を選んで「生成」を押す。
3. 鍵のパスフレーズを入れ、「公開鍵の保存」で `id_ed25519.pub` を、「秘密鍵の保存」で `id_ed25519` を保存する。秘密鍵は PC から外に出さない。

### OS を microSD に書き込む（PC で作業）

1. [Raspberry Pi Imager](https://www.raspberrypi.com/software/) で「Raspberry Pi 4」「Raspberry Pi OS (64-bit)」（デスクトップ付き）を選ぶ。モニターにダッシュボードを映すので Lite ではなくデスクトップ版にする。
2. 設定の編集で、ホスト名・ユーザー名とパスワード・Wi-Fi を入れる。
3. 同じ画面のサービス（リモートアクセス）の欄で SSH を有効にし、**公開鍵認証のみを許可**を選んで、`id_ed25519.pub` の中身（1 行）を貼る。パスワード認証は有効にしない。
4. 書き込んだ microSD を Pi に挿し、モニター・USB キーボード・マウスをつないで電源を入れる。最初の起動とアドレスの確認は Pi の画面で行う。

### Tera Term で Pi に入る

1. Pi の画面でターミナルを開き、`hostname -I` で Pi の IP アドレスを調べる。
2. PC の Tera Term で「ファイル」→「新しい接続」を開き、ホストにその IP アドレス、サービスに SSH（ポート 22）を入れて接続する。
3. 認証の画面でユーザー名を入れ、「RSA/DSA/ECDSA/ED25519 鍵を使う」を選んで `id_ed25519` を指定し、鍵のパスフレーズを入れる。
4. 入れたら、パスワードでは入れない設定になっているか確かめる（`passwordauthentication no` と出れば OK）。

```sh
sudo sshd -T | grep -i passwordauthentication
```

- 共用 Wi-Fi が端末どうしの通信を遮断している（クライアント分離）と、PC から Pi に届かない。そのときは運営者に相談するか、PC と Pi を LAN ケーブルで直接つなぐ
- IP アドレスは再起動などで変わることがある。つながらなくなったら Pi の画面で `hostname -I` を見直す

### 先に会社や自宅で動かしてみる

コワーキングに置く前に、会社や自宅の Wi-Fi で計測と SSH を確かめてよい。Imager の Wi-Fi 欄には、最初に使う場所の Wi-Fi を入れる。

場所を移すときは、移す前に次の場所の Wi-Fi を Pi に登録しておく。Pi の画面右上の Wi-Fi アイコンから選んでもよい。登録した Wi-Fi は、見つかれば自動でつながる。

```sh
sudo nmcli dev wifi connect "<SSID>" --ask     # パスワードを聞かれる
nmcli connection show                          # 登録済みの Wi-Fi の一覧
```

IP アドレスは場所ごとに変わるので、移したら Pi の画面で `hostname -I` を見て、Tera Term の接続先を変える。

### コワーキングの共用 Wi-Fi で使う

設置場所はコワーキングスペースの一室で、Wi-Fi は施設の共用回線を使う。つなぐ前に運営者に次を確かめておく。

- 端末の登録（MAC アドレスの申請）が必要か。ブラウザでログインする方式（キャプティブポータル）だと、つなぐときに Pi の画面でログインし直す必要がある
- 認証方式。WPA2/WPA3-Personal なら Imager の設定欄で足りる。WPA2-Enterprise（ID とパスワードで入る方式）なら、別に設定が要る
- 常時接続する機器を置いてよいか
- 端末どうしの通信が遮断されていないか（クライアント分離）。遮断されていると PC の Tera Term から Pi に入れない

共用回線にはほかの入居者の機器も載るので、Pi が受け付ける接続は SSH だけにし、それも鍵がないと入れないようにする。

- SSH は鍵の認証だけを許す（パスワード認証は無効）。秘密鍵のある PC の Tera Term からだけ入れる
- ダッシュボードの Web サーバーは `127.0.0.1` だけで待ち受け、Pi 自身の画面からだけ開く
- Wi-Fi は外向きの通信（気象庁 XML・ナウキャスト・背景地図・交通情報の取得、OS の更新）だけに使う

### 大型モニターにつなぐ

Pi 4 の映像出力は micro-HDMI。**micro-HDMI to HDMI ケーブル**でモニターの HDMI 入力につなぐ。電源（USB-C）の隣の端子（HDMI0）を使う。

- 画面は 60 インチ以上を想定。4K の画面でも、Pi からは 1920×1080 で出してテレビ側で拡大させる。4K で出すと地図の描画が重くなり、文字も小さくなる
- 長さは 5m 程度までなら普通のケーブルで足りる。それ以上はアクティブケーブルを使う
- 画面が自動で消えないよう、`sudo raspi-config` の Display Options → Screen Blanking を無効にする
- テレビを使う場合は次も確認する
  - 無操作や無信号で電源が切れる設定（無操作電源オフ・オートパワーオフ）を切る
  - 画面の端が欠けるときは、テレビの画面サイズ設定を「全画素表示」「ジャストスキャン」などにする
  - 有機 EL は同じ画面を出し続けると焼き付くことがある。液晶ならまず問題ない。有機 EL なら夜間は画面を消す
- ダッシュボードは 3〜5m 離れて読める文字の大きさで作る（CO2 の現在値は大きく、細かい表は載せない）
- ダッシュボードは起動時に Chromium の全画面表示（キオスク表示）で開くよう設定する（ダッシュボード実装時に手順を追加）

### I2C と UART を有効にする（Pi で作業）

```sh
# Interface Options で次を設定する
#   I2C → Yes
#   Serial Port → ログインシェル: No / シリアルポート: Yes
sudo raspi-config

# Pi 4 の GPIO14/15 を安定した UART（PL011）にするため Bluetooth を止める（Wi-Fi は影響を受けない）
echo "dtoverlay=disable-bt" | sudo tee -a /boot/firmware/config.txt
sudo usermod -aG dialout $USER   # シリアルを sudo なしで読む
sudo reboot

# SCD40 が見えるか確認（62 が表示されれば OK）
sudo apt install -y i2c-tools
i2cdetect -y 1

# uv を入れる
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## 使い方（CO2・温度・湿度）

```sh
uv sync --extra pi
cp config.example.toml config.toml   # [station] の緯度経度を設置場所に合わせる

uv run env-station --once            # 1 回だけ計測して表示
uv run env-station                   # interval_s ごとに計測し続ける（Ctrl+C で終了）
```

実機がない PC では `uv sync` してから `uv run env-station --fake` でダミー値を記録できる。

## 災危通報の受信

デコードと表示は [qzss_dcr](https://github.com/fractional-n/qzss_dcr)（MIT）に任せる。このリポジトリには含めず、別に clone して動かす。

```sh
git clone https://github.com/fractional-n/qzss_dcr.git
cd qzss_dcr
python3 qzss_dcr.py /dev/serial0 -b 38400 --configure-m10   # 初回は L1S を有効にする設定を送る
```

アンテナは窓際など空の見える場所に置く。みちびきが見えていれば、L1S のメッセージは 4 秒ごとに届く。

## データ

`data/readings.sqlite` に保存する。時刻は UTC。

`readings` テーブル（1 行 = 1 時刻 × 1 センサー × 1 指標）:

| ts | sensor | metric | value |
|---|---|---|---|
| 2026-11-07T10:00:00+00:00 | scd4x | co2_ppm | 612 |
| 2026-11-07T10:00:00+00:00 | scd4x | temperature_c | 22.4 |

`station` テーブル（1 行だけ）: 起動時に `config.toml` の `[station]` の内容を書き込む。

```sh
sqlite3 data/readings.sqlite \
  "SELECT ts, value FROM readings WHERE metric = 'co2_ppm' ORDER BY ts DESC LIMIT 10"
```

## 注意

- SCD40 の CO2 保証範囲は 400〜2000 ppm。電源投入直後の数分は値が安定しない。
- SCD40 は自動補正（ASC）が既定で有効。週に 1 回は外気程度（約 400 ppm）まで下がる前提で補正される。夜間や週末に無人になる部屋なら条件を満たしやすい。
- SCD40 の温度は自己発熱や Pi の熱で高めに出る。センサーは Pi から離して置く。
- 災危通報の表示は参考情報。避難などの判断は公的機関の発表に従う。

## 開発

```sh
uv run pytest
uv run ruff check
uv run ruff format
```

## ライセンス

MIT License（[LICENSE](LICENSE)）。災危通報のデコードに使う qzss_dcr は別リポジトリで、それぞれのライセンスに従う。
