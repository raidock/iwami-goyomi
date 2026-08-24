# 検索機能の実現可能性（【133】）

**測ったもの**: 検索対象にできるフィールドの充足率（公開204件）と、静的サイトのまま
実現する場合に必要なJSの見積もり。
**データ**: `out/events.json`（公開204件）と `collector/publish.py` の `_card()` が
実際に生成するHTML。
**結論**: JSは必須（CSSだけでは文字列の部分一致ができない）だが、最小限（15〜20行
程度、外部ライブラリ不要）で済みそう。**実装するかどうかは判断していない。**

---

## 1. 何を検索対象にできるか

`out/events.json` 204件のフィールド充足率:

| フィールド | あり | 割合 |
|---|---|---|
| city | 204 | 100.0% |
| category | 162 | 79.4% |
| description | 143 | 70.1% |
| tags | 59 | 28.9% |
| venue | 7 | 3.4% |
| organizer | 3 | 1.5% |

タイトル文字数は 6〜88字（平均26.9字）。

**venue（会場）は予想どおり少ない**（7件のみ）。検索対象に入れる価値は薄い。

より重要な点: `_card()` が生成する `.card` の HTML には、**すでに以下が表示テキスト
として入っている**（`collector/publish.py:142` 以降）。

- タイトル（`<h3><a>`）
- 市町（`data-city` 属性、かつ `.muni` に表示テキストとしても）
- カテゴリ（`.src` に「カテゴリ・掲載 日付」の形で表示）
- タグ（`.tg`。あれば）

つまり **`card.textContent` をそのまま検索対象にすれば、タイトル・市町・カテゴリ・
タグの部分一致検索は、データを新たに取得・埋め込みしなくても実現できる。**

一方 **description（70.1%）はカードに表示されていない**。検索対象に加えるには
`data-desc` 属性を各カードに追加するか、`events.json` を別途fetchする必要があり、
「タダでは済まない」。**まずは textContent だけで始め、description は次の判断に回す
のが軽い。**

## 2. 静的サイトのまま実現できるか

**文字列の部分一致検索そのものは、CSSだけでは実現できない**（`:contains()` は
CSSに存在しない）。**JSは避けられない。**

ただし、規模は小さい:

- 204件の `.card` を毎回全走査しても軽い（体感で問題になる件数ではない）
- 実装イメージ（試作はしていない。行数は概算）:

  ```js
  const q = document.getElementById('q');
  q.addEventListener('input', () => {
    const needle = q.value.trim();
    document.querySelectorAll('.card').forEach(c => {
      c.classList.toggle('search-hide',
        needle && !c.textContent.includes(needle));
    });
  });
  ```
  ```css
  .card.search-hide { display: none; }
  ```

  15〜20行程度（大文字小文字・全角半角の正規化を入れるならもう少し増える）。
  **外部ライブラリは不要**（設計判断6に抵触しない）。

## 3. 市町の絞り込みとの組み合わせ

いまの市町絞り込みは `:target` + CSS（`_filter_nav`、`collector/publish.py:165`）で、
`.card:not([data-city="..."])` を隠す方式。

検索を `.card` に `.search-hide` クラスを足す方式にすれば、**2つの絞り込みは
独立に効き、自然にAND条件になる**（すでに `:target` ルールで隠れているカードに
`.search-hide` が付いても付かなくても、非表示のままなので競合しない）。
**この組み合わせ方は設計として無理がなさそう**（試作はしていない）。

## 4. 0件のときの案内

`_filter_nav` は市町ごとの0件を**ビルド時**に判定して個別メッセージを埋め込んでいる
（`n == 0` のとき `.empty-city` を出す）。検索は**閲覧時**に0件になりうるので、
同じ方式は使えない。

`collector/publish.py` はすでに `:has()` を使っている（`.block:not(:has(.card[...]))`）
ので、**「検索結果0件」の判定もCSSの `:has()` に任せられる可能性がある**
（`.block:not(:has(.card:not(.search-hide)))` のような形。**未検証、アイデアのみ**）。
これができれば、0件メッセージの表示自体にJSを増やさずに済む。

## 5. JSが無効な環境

検索欄を既定で非表示にしておき、`<html>` に `js` クラスを付ける定型パターン
（ページ先頭で `document.documentElement.classList.add('js')` を実行し、
CSS側は `.search{display:none} .js .search{display:block}`）を使えば、
**JSが無効なときは検索欄自体が出ない**（要望どおりの「出ないだけ」を満たせる）。
これも1〜2行の追加で済む。

## まだ測っていないこと

- 全角半角・ひらがなカタカナの正規化をどこまでやるか（`normalize_title` の
  正規表現が `collector/review.py` に既にあるので流用できるかもしれない）
- 実際に動かしたときの見た目・操作感（試作していない）
