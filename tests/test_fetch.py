from event_parser_llm.fetch import MAX_CHARS, html_to_text, normalize_text

HTML = """<html><head><title>テスト</title><style>body{}</style></head><body>
<nav>ホーム | お知らせ | アクセス</nav>
<article>
<h1>ＡＢＣ夏祭り２０２６</h1>
<p>日時：2026年8月15日（土）17:00〜21:00</p>
<p>会場：中央公園（東京都千代田区1-1）</p>
<p>入場無料。屋台や盆踊りをお楽しみください。雨天の場合は翌日に順延します。</p>
<p>主催：ABC商店街振興組合　お問い合わせ：03-0000-0000</p>
</article>
<script>console.log("x")</script>
<footer>© 2026 ABC商店街</footer></body></html>"""


def test_normalize_text_converts_fullwidth_and_drops_blank_lines():
    assert normalize_text("ＡＢＣ　１２３\n\n\n次の行  ") == "ABC 123\n次の行"


def test_normalize_text_truncates():
    assert len(normalize_text("あ" * (MAX_CHARS + 100))) == MAX_CHARS


def test_html_to_text_extracts_body_and_drops_script():
    text = html_to_text(HTML)
    assert "ABC夏祭り2026" in text
    assert "2026年8月15日" in text
    assert "console.log" not in text
