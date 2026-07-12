import pandas as pd

from analysis.predictor import JRAPredictor


def _df():
    return pd.DataFrame([
        {"rank": 1, "jockey": "J1", "jockey_name": "ルメール",
         "horse_id": "H1", "horse_name": "テスト馬"},
        {"rank": 4, "jockey": "J2", "jockey_name": "武豊",
         "horse_id": "H2", "horse_name": "サンプル馬"},
    ])


def test_prepare_data_builds_horse_maps():
    p = JRAPredictor()
    p.prepare_data(_df())
    assert p.horse_display_map == {"H1": "テスト馬", "H2": "サンプル馬"}
    assert p.horse_name_map == {"テスト馬": "H1", "サンプル馬": "H2"}


def test_resolve_horse_key_accepts_id_and_name():
    p = JRAPredictor()
    p.prepare_data(_df())
    assert p.resolve_horse_key("H1") == "H1"
    assert p.resolve_horse_key("テスト馬") == "H1"
    assert p.resolve_horse_key("存在しない馬") is None


def test_horse_map_keeps_duplicate_names_distinct():
    """同名・異なるhorse_idの馬が学習時に衝突しないことを確認する"""
    df = pd.DataFrame([
        {"rank": 1, "jockey": "J1", "jockey_name": "ルメール",
         "horse_id": "H1", "horse_name": "テスト馬"},
        {"rank": 2, "jockey": "J2", "jockey_name": "武豊",
         "horse_id": "H2", "horse_name": "テスト馬"},  # 同名・別ID
    ])
    p = JRAPredictor()
    p.prepare_data(df)
    # horse_mapには2つの別々のインデックスが存在すること（衝突していない）
    assert p.horse_map["H1"] != p.horse_map["H2"]
    assert len({p.horse_map["H1"], p.horse_map["H2"]}) == 2


def test_get_summary_is_cached():
    p = JRAPredictor()
    p.prepare_data(_df())
    p.fit_result = {"type": "advi", "svi": None, "params": {}}
    s1 = p.get_summary()
    s2 = p.get_summary()
    assert s1 is s2  # 2回目はキャッシュが返る
