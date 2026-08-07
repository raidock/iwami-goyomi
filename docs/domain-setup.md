# 独自ドメインへの切り替え手順

**ドメインを取得した日に、上から順にこのとおりやれば戻れます。**
このファイルは、まだドメインが無い段階で書きました（2026-08-07）。
取得のタイミングは Takao さんが決めます。ここにあるのは手順だけです。

**なぜ先に書くか。** 切り替えの直前は告知の準備で忙しくなります。DNSの反映に
最大24時間、HTTPS強制はさらにその後すぐ使えないことがあります。**待ち時間がある
作業**なので、手が空いているいまのうちに迷わない形にしておきます。

候補・価格の調査は `REPORT.md`（2026-08-06付）にあります。**このファイルは
「どのドメインにするか」ではなく「取ったあとどうするか」だけを扱います。**

---

## 0. 前提

- 対象のドメインを `iwami-goyomi.jp` として書きます。**別のドメインにした場合は、
  以下のコマンドの `iwami-goyomi.jp` を実際のドメインに読み替えてください**
- 石見暦は GitHub Pages を**カスタム GitHub Actions ワークフロー**
  （`.github/workflows/collect.yml` の `actions/deploy-pages@v4`）で公開しています。
  **ブランチ公開方式とは設定のしかたが違います。** `CNAME` というファイルは
  リポジトリに作りません（作ると無視されるだけです）。カスタムドメインは
  **GitHubの画面（Settings → Pages）だけで設定します**

---

## 1. レジストラ側でDNSを設定する

ドメインを取得したレジストラの管理画面で、以下のどちらかを設定します。

### 案A: Aレコード（IPv4）を4つ

apex（`iwami-goyomi.jp` そのもの。`www` なし）に、次の4つのIPアドレスを
**すべて**登録します。

```
185.199.108.153
185.199.109.153
185.199.110.153
185.199.111.153
```

### 案B: ALIAS または ANAME レコード

レジストラが対応していれば、Aレコード4つの代わりに1本で済みます。

```
raidock.github.io
```

**`www` を使うなら**、`www.iwami-goyomi.jp` にCNAMEレコードを1本足します。

```
raidock.github.io
```

**どちらの案にするかは、レジストラの管理画面にAAAA/ALIAS/ANAMEの項目が
あるかで決めてください。** 無ければ案A（Aレコード4つ）一択です。

---

## 2. GitHub側でカスタムドメインを設定する

1. https://github.com/raidock/iwami-goyomi/settings/pages を開く
2. 「Custom domain」に `iwami-goyomi.jp` を入力して Save
3. 「Enforce HTTPS」のチェックボックスが**すぐには押せないことがあります。**
   DNSの検証が終わるまでグレーアウトしたままです。焦らず後で戻ってきてください

**この時点でリポジトリに変更は要りません。** `CNAME` ファイルをコミットする
必要はありません（上の「0. 前提」のとおり）。

---

## 3. 待つ

- **DNSの反映に最大24時間**かかることがあります
- 反映を確認するコマンド:

```bash
dig iwami-goyomi.jp +short
```

上の4つのIPアドレス（またはALIAS先）が出れば反映ずみです。**すぐ出なくても
壊れていません。** 数時間おきに確かめてください

- 反映が終わると、GitHubのPages設定画面で「Enforce HTTPS」のチェックが
  押せるようになります。**押してください。** 証明書の発行にも少し時間が
  かかることがあります

---

## 4. コードの4箇所を書き換える

**ドメインが実際に生きて、HTTPSも通ってから実行してください。** 先に書き換えると、
DNSがまだ反映していない間、壊れたURLが公開されます。

対象は4箇所だけです（2026-08-07 時点で `grep -rn raidock.github.io` で確認ずみ）。

```bash
cd ~/App/iwami-goyomi
git pull

NEW_URL="https://iwami-goyomi.jp/"
OLD_URL="https://raidock.github.io/iwami-goyomi/"

# config.yaml の site.url（ここを直せば index.html の canonical・OGP は自動で追随）
sed -i '' "s#${OLD_URL}#${NEW_URL}#" config.yaml

# README.md の公開先リンク
sed -i '' "s#${OLD_URL}#${NEW_URL}#" README.md

# CLAUDE.md 冒頭の「公開先」
sed -i '' "s#${OLD_URL}#${NEW_URL}#" CLAUDE.md

# collector/__init__.py の USER_AGENT（情報源に名乗っている自己申告URL）
sed -i '' "s#${OLD_URL}#${NEW_URL}#" collector/__init__.py

git diff --stat
```

**`events.ics` の `PRODID`/`UID`（`sanin-nomi`）は対象外です。** CLAUDE.md の
設計判断2で固定と決まっているので、ドメインが変わっても触りません。上の
コマンドも `sanin-nomi` には触れません。

差分を見て問題なければコミット・pushします。

```bash
git add config.yaml README.md CLAUDE.md collector/__init__.py
git commit -m "chore: 独自ドメイン iwami-goyomi.jp に切り替える"
git push
```

push すると、`collect.yml` のワークフローがサイトを生成し直します
（コード修正なので収集はしません。サイト生成だけです）。

---

## 5. 切り替え後に確認すること

Actions が緑になったら、**新しいドメインを実際に開いて確認してください。**

- [ ] `https://iwami-goyomi.jp/` でサイトが開くか
- [ ] 鍵マーク（HTTPS）が付いているか
- [ ] `https://raidock.github.io/iwami-goyomi/` を開いたとき、新しいドメインへ
      **リダイレクトされるか。** これは公式ドキュメントで明言されていなかった点です
      （2026-08-06 の調査）。一般的な挙動としては転送されるはずですが、
      **実際にブラウザで確かめてください。** されていなければ、旧URLを
      共有した先（もしあれば）に一言添える必要があります
- [ ] `view-source:` で `<link rel="canonical">` と `<meta property="og:url">` が
      新しいドメインになっているか（`config.yaml` の書き換えが効いているかの確認）
- [ ] `#gotsu` のような市町別の絞り込みリンクが、新しいドメインでもそのまま
      使えるか（`:target` はURLフラグメントだけの仕組みなので、ドメインが
      変わっても壊れないはずですが、念のため）
- [ ] 収集がちゃんと動くか（`USER_AGENT` の書き換えが反映されているか）は、
      次の朝6時の定時収集を待つか、手元で `python main.py collect --no-fetch`
      を軽く流して確認してください

---

## 6. うまくいかなかったとき

- **サイトが真っ白 / 404** → DNSがまだ反映していません。手順3に戻って
  `dig` で確認してください
- **「Your site is having problems building」のような警告がGitHubから来る** →
  Pages設定画面のCustom domainの欄を見てください。DNS検証に失敗していると
  警告が出ます。Aレコード4つが全部正しいか見直してください
- **HTTPSにならない** → 反映直後は数十分〜数時間かかることがあります。
  Settings → Pages を開き直して「Enforce HTTPS」を再度確認してください
- **どうしても直らない** → Custom domainの欄を一度空にして保存し、
  数分待ってから同じドメインを入れ直すと直ることがあります
  （検証プロセスがやり直されます）

---

## 参考: 調べた元ネタ

- GitHub公式: DNS設定・カスタムActionsワークフローでのCNAME扱い
  （2026-08-06に `developers.google.com` ではなく `docs.github.com` を直接調査）
- ドメイン候補の空き状況・価格比較は `REPORT.md`（2026-08-06付、上書きされるので
  残したい数字はこのファイルに書き足すこと）
