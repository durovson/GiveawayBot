from services.september_wl_service import WL_APES_PER_PLACE
from locales.en.september_wl import TEXTS as EN_TEXTS
from locales.ru.september_wl import TEXTS as RU_TEXTS


def test_notapes_wl_ratio_is_three():
    assert WL_APES_PER_PLACE == 3


def test_notapes_wl_ratio_is_visible_in_both_languages():
    assert "Every <b>3 NOTAPES</b> = <b>+1 WL</b>" in EN_TEXTS["september_wl_title"]
    assert "Каждые <b>3 NOTAPES</b> = <b>+1 WL</b>" in RU_TEXTS["september_wl_title"]


def test_notapes_wl_floor_calculation():
    assert 2 // WL_APES_PER_PLACE == 0
    assert 3 // WL_APES_PER_PLACE == 1
    assert 8 // WL_APES_PER_PLACE == 2
