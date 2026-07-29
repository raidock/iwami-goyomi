"""石見暦（いわみごよみ）。"""
__version__ = "2.5.0"

# 情報源に名乗る名前（設計判断12「User-Agent は正直に名乗る」）。
#
# **定義はここ1か所だけ。** かつて2か所に別々の名前が書かれていて、
# どちらも実体と違っていた —
#   collector/sources/base.py … sanin-nomi-collector/1.0 (+personal flea-market tracker)
#   main.py の詳細ページ取得   … iwami-events-collector/1.5 (+local tool)
# 相手のサーバの管理者が見て「誰が来ているか」を辿れないと、名乗った意味がない。
# 連絡先は公開サイト（掲載方針と問い合わせ先はそこから辿れる）。
USER_AGENT = f"iwami-goyomi/{__version__} (+https://raidock.github.io/iwami-goyomi/)"
