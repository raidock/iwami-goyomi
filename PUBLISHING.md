# 石見暦 公開のしかた（GitHub Pages）

手元で動いているものを、誰でも見られるサイトとして公開する手順です。
**1コマンドずつ実行してください。**

---

## 0. 公開前に必ず埋めるもの

`config.yaml` の `site:` を開いて、**連絡先を必ず入れてください。**

```yaml
site:
  title: 石見暦
  reading: いわみごよみ
  tagline: 浜田・江津の催しと締切を、ひとつの暦に。
  url: ""          # 手順3のあとに埋めます
  contact: ""      # ← 必須。メール／フォームURL／SNSアカウントなど
  operator: ""     # 誰が運営しているか
```

`contact` が空だと、**サイト上に赤字で警告が出ます。** うっかり公開できないようにしています。

なぜ必須かというと、公開すると必ずこの3つが来るからです。

1. 「うちのイベントも載せてほしい」
2. 「日程が違います」
3. 「掲載をやめてほしい」

3つ目に応じられない状態で公開するのは、相手に対して不誠実です。

連絡先には**専用のメールアドレスやフォームを推奨**します。個人の常用アドレスを載せると、後から変えるのが大変です。

---

## 1. GitHub にリポジトリを作る

GitHub にログインし、新しいリポジトリを作ります。

- 名前の例: `iwami-goyomi`
- **Public**（Pages を無料で使うため）
- README や .gitignore は**追加しない**（こちらに用意済み）

---

## 2. 手元のものを送る

プロジェクトのフォルダで、1行ずつ実行します。

```bash
git init
```

```bash
git add .
```

```bash
git commit -m "石見暦 初版"
```

```bash
git branch -M main
```

`<ユーザー名>` と `<リポジトリ名>` は自分のものに置き換えてください。

```bash
git remote add origin https://github.com/<ユーザー名>/<リポジトリ名>.git
```

```bash
git push -u origin main
```

### 承認データも一緒に送る

承認済みのデータは手元の `~/iwami-events-data` にあります。
GitHub 上では毎回消えてしまうので、リポジトリの中へ複製します。

```bash
cp -r ~/iwami-events-data ./data
```

```bash
git add data && git commit -m "承認データを追加" && git push
```

---

## 3. GitHub Pages を有効にする

GitHub のリポジトリページで、

1. **Settings** タブ
2. 左メニューの **Pages**
3. **Source** を **GitHub Actions** に変更

これで `https://<ユーザー名>.github.io/<リポジトリ名>/` が公開URLになります。

このURLを `config.yaml` の `site.url` に書き戻してください。SNSで共有したときの
表示（OGP）に使われます。

```bash
git add config.yaml && git commit -m "公開URLを設定" && git push
```

---

## 4. 動かしてみる

1. **Actions** タブを開く
2. 左の「石見暦を収集して公開」を選ぶ
3. **Run workflow** を押す

数分で完了し、Pages にサイトが出ます。

以降は**毎朝6時に自動で収集・公開**されます。

---

## 運用のしかた

自動収集は動きますが、**承認は人の作業**です。手元でこうします。

```bash
git pull                    # GitHubが集めた新着を取り込む
```

```bash
python main.py pending --data-dir ./data
```

```bash
python main.py review --data-dir ./data
```

```bash
git add data && git commit -m "承認" && git push
```

次回の自動実行で、承認したものが公開されます。

**1日5分の作業**を想定しています。承認待ちが増えすぎたら、分類器のルールを
足して減らすのが正しい対処です（`collector/classify.py`）。

---

## 公開したあとに考えること

- **X / Instagram で告知する** — 既にアカウントがあるなら、そこが最初の入口になります
- **問い合わせに応じる** — 「載せてほしい」が来たら、それが投稿フォームを作る合図です
- **市町を増やす** — `config.yaml` に3行足すだけです（益田市・大田市・邑南町ほか）

**掲載を望まない主催者からの申し出には、必ず速やかに応じてください。**
自動収集で成り立っているサイトは、それをやらないと一瞬で信頼を失います。
