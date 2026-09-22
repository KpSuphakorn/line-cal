"""Unit tests for the food estimate cache and the fail-soft guarantee around it."""
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, FoodEstimateCache
from app.services import food_cache
from app.services.ai_chat import strip_food_command


def get_test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


ITEMS = [{"food_name": "ข้าวมันไก่", "calories": 600.0, "protein": 25.0}]


def test_an_estimate_comes_back_for_the_same_description():
    db = get_test_db()
    food_cache.store(db, "ข้าวมันไก่", ITEMS)

    assert food_cache.lookup(db, "ข้าวมันไก่") == ITEMS


def test_spacing_and_casing_do_not_split_one_dish_into_two_entries():
    db = get_test_db()
    food_cache.store(db, "Pad Thai", ITEMS)

    assert food_cache.lookup(db, "  pad   thai ") == ITEMS
    assert db.query(FoodEstimateCache).count() == 1


def test_a_different_description_is_a_miss():
    db = get_test_db()
    food_cache.store(db, "ข้าวมันไก่", ITEMS)

    assert food_cache.lookup(db, "ข้าวผัดกระเพรา") is None


def test_storing_the_same_description_twice_updates_rather_than_duplicates():
    db = get_test_db()
    food_cache.store(db, "ข้าวมันไก่", ITEMS)
    food_cache.store(db, "ข้าวมันไก่", [{"food_name": "ข้าวมันไก่", "calories": 700.0}])

    assert db.query(FoodEstimateCache).count() == 1
    assert food_cache.lookup(db, "ข้าวมันไก่")[0]["calories"] == 700.0


def test_a_hit_is_counted_so_the_cache_can_be_judged_later():
    db = get_test_db()
    food_cache.store(db, "ข้าวมันไก่", ITEMS)
    food_cache.lookup(db, "ข้าวมันไก่")
    food_cache.lookup(db, "ข้าวมันไก่")

    assert db.query(FoodEstimateCache).one().hit_count == 2


def test_a_missing_table_reads_as_a_miss_rather_than_an_error():
    """Deploying this code before running its migration must not break food
    logging — the cache is an optimisation, so an unusable cache is a miss."""
    engine = create_engine("sqlite:///:memory:")  # no create_all: no tables at all
    db = sessionmaker(bind=engine)()

    assert food_cache.lookup(db, "ข้าวมันไก่") is None
    food_cache.store(db, "ข้าวมันไก่", ITEMS)  # must not raise


def test_empty_input_is_never_cached():
    db = get_test_db()
    food_cache.store(db, "   ", ITEMS)
    food_cache.store(db, "ข้าวมันไก่", [])

    assert db.query(FoodEstimateCache).count() == 0


def test_the_cache_key_drops_the_command_word():
    """"กิน ข้าวมันไก่" and "ข้าวมันไก่" describe the same food."""
    assert strip_food_command("กิน ข้าวมันไก่") == "ข้าวมันไก่"
    assert strip_food_command("เพิ่ม ข้าวมันไก่") == "ข้าวมันไก่"
    assert strip_food_command("ข้าวมันไก่") == "ข้าวมันไก่"


@patch("app.services.line_handler.reply_flex")
@patch("app.services.line_handler.ai_quota_remaining", return_value=10)
def test_a_cached_dish_never_calls_the_model_again(_quota, _reply):
    """The whole point: a repeat lunch must cost no request from the shared
    per-model daily Gemini allowance."""
    from app.services.line_handler import _capture_food

    db = get_test_db()
    analyzer = MagicMock(return_value={"items": ITEMS})

    _capture_food(db, "u1", "text", None, analyzer, MagicMock(), "tok", cache_text="ข้าวมันไก่")
    _capture_food(db, "u1", "text", None, analyzer, MagicMock(), "tok", cache_text="ข้าวมันไก่")

    assert analyzer.call_count == 1, "the second identical dish must come from cache"


@patch("app.services.line_handler.reply_flex")
@patch("app.services.line_handler.ai_quota_remaining", return_value=10)
def test_a_photo_is_never_served_from_cache(_quota, _reply):
    """Two photos are never the same meal, so the image path passes no key."""
    from app.services.line_handler import _capture_food

    db = get_test_db()
    analyzer = MagicMock(return_value={"items": ITEMS})

    _capture_food(db, "u1", "image", None, analyzer, MagicMock(), "tok")
    _capture_food(db, "u1", "image", None, analyzer, MagicMock(), "tok")

    assert analyzer.call_count == 2
    assert db.query(FoodEstimateCache).count() == 0
