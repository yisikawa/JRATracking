from data.scraper import JRAScraper, _normalize_jockey

_RACE_PAGE_HTML = """
<html><body>
<h1><a href="https://www.netkeiba.com/?rf=logo"><img alt="netkeiba" src="logo.png"/></a></h1>
<dl class="racedata fc">
<h1>3歳新馬</h1>
</dl>
<table class="race_table_01">
<tr><th>着順</th><th>枠</th><th>馬番</th><th>馬名</th><th>性齢</th><th>斤量</th>
    <th>騎手</th><th>タイム</th><th>着差</th><th>上がり</th><th>人気</th><th>単勝</th></tr>
<tr>
  <td>1</td><td>1</td><td>1</td>
  <td><a href="/horse/2020123456/">テストホース</a></td>
  <td>牡3</td><td>54.0</td>
  <td><a href="/jockey/result/recent/05339/">テスト騎手</a></td>
  <td>1:34.5</td><td></td><td>35.0</td><td>1</td><td>1.5</td>
</tr>
</table>
</body></html>
"""


def _scraper() -> JRAScraper:
    return JRAScraper(None)  # db_session はパース系メソッドでは未使用


def test_parse_time_with_minutes():
    assert _scraper()._parse_time("1:34.5") == 94.5


def test_parse_time_under_one_minute():
    # 1000m 戦など 1 分未満のタイムは "58.3" 形式で表示される
    assert _scraper()._parse_time("58.3") == 58.3


def test_parse_time_invalid():
    assert _scraper()._parse_time("") is None
    assert _scraper()._parse_time("中止") is None


def test_normalize_jockey_strips_symbols():
    assert _normalize_jockey("☆西塚") == "西塚"
    assert _normalize_jockey("ルメール") == "ルメール"


def test_extract_race_id_from_url():
    s = _scraper()
    assert s._extract_race_id("202601060112") == "202601060112"
    assert s._extract_race_id("https://db.netkeiba.com/race/202601060112/") == "202601060112"
    assert s._extract_race_id("https://race.netkeiba.com/race/shutuba.html?race_id=202601060112") == "202601060112"


def test_scrape_race_results_skips_header_logo_h1(monkeypatch):
    # netkeibaのレース結果ページは文書冒頭にサイト共通ロゴ用の<h1>(テキストなし)を持つため、
    # dl.racedata内の<h1>(レース名)を正しく拾えることを確認する回帰テスト
    from bs4 import BeautifulSoup

    s = _scraper()
    monkeypatch.setattr(
        s, "fetch_page",
        lambda *a, **k: BeautifulSoup(_RACE_PAGE_HTML, "html.parser"),
    )

    data = s.scrape_race_results("202601060112")

    assert data is not None
    assert data["race"].name == "3歳新馬"


def test_scrape_shutuba_uses_utf8_encoding(monkeypatch):
    # race.netkeiba.com は現在UTF-8で配信されている(以前はEUC-JPだった)ため、
    # fetch_pageにEUC-JPを渡すと文字化けする。utf-8指定になっていることを確認する回帰テスト。
    s = _scraper()
    seen_encodings = []

    def fake_fetch_page(url, encoding='EUC-JP', referer=None):
        seen_encodings.append(encoding)
        return None  # テーブル未検出として早期returnさせ、エンコーディング指定のみ検証する

    monkeypatch.setattr(s, "fetch_page", fake_fetch_page)

    s.scrape_shutuba("202601060112")

    assert seen_encodings, "fetch_page が一度も呼ばれていない"
    assert all(enc == "utf-8" for enc in seen_encodings), seen_encodings
