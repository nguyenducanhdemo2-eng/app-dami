from app.main import lead_score, render_reply


def test_lead_score_prioritizes_booking_intent():
    high = lead_score("Mình cần tìm photographer chụp kỷ yếu, xin báo giá", "kỷ yếu")
    low = lead_score("Mình đã tìm được ekip, không cần nữa", "kỷ yếu")
    assert high > low
    assert high >= 80


def test_reply_template_substitution_and_length():
    text = render_reply(
        "Chào @{username}, mình gửi thông tin {keyword} nhé.",
        username="@duc_anh",
        keyword="chụp kỷ yếu",
    )
    assert text == "Chào @duc_anh, mình gửi thông tin chụp kỷ yếu nhé."
    assert len(text) <= 500

