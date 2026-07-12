from datetime import date

from analysis.predictor import JRAPredictor
from backend.routers.model import _build_training_frame
from data.database import get_session_factory, Race, Horse, Entry, Result


def _make_session(tmp_path):
    factory = get_session_factory(f"sqlite:///{tmp_path / 'train.db'}")
    return factory()


def test_build_training_frame_joins_results_and_entries(tmp_path):
    session = _make_session(tmp_path)
    session.add(Race(id="202605010101", name="テストR", date=date(2026, 1, 1)))
    session.add(Horse(id="H1", name="テスト馬"))
    session.add(Entry(race_id="202605010101", horse_id="H1",
                      jockey="ルメール", jockey_id="J1"))
    session.add(Result(race_id="202605010101", horse_id="H1", rank=1))
    session.commit()

    df = _build_training_frame(session)

    assert len(df) == 1
    row = df.iloc[0]
    assert row["rank"] == 1
    assert row["jockey"] == "J1"          # jockey_id 優先
    assert row["jockey_name"] == "ルメール"
    assert row["horse_id"] == "H1"          # 馬IDをキーにする
    assert row["horse_name"] == "テスト馬"   # 表示名は別列
    session.close()


def test_build_training_frame_keeps_same_named_horses_distinct(tmp_path):
    """同名・別horse_idの馬2頭が_build_training_frameを通っても
    horse_id列で衝突しないことを確認する（Task 5の回帰テスト）。

    Task 5適用前は `"horse_id": horse_name or result_horse_id` のように
    馬名をhorse_id列に入れていたため、同名の馬が同じキーに潰れていた。
    このテストは実際に_build_training_frameを通すため、その退行を検出できる。
    """
    session = _make_session(tmp_path)
    session.add(Race(id="202605010101", name="テストR1", date=date(2026, 1, 1)))
    session.add(Race(id="202605010102", name="テストR2", date=date(2026, 1, 2)))
    # 同じ名前(「テスト馬」)だが異なるhorse_idを持つ2頭
    session.add(Horse(id="H1", name="テスト馬"))
    session.add(Horse(id="H2", name="テスト馬"))
    session.add(Entry(race_id="202605010101", horse_id="H1",
                      jockey="ルメール", jockey_id="J1"))
    session.add(Entry(race_id="202605010102", horse_id="H2",
                      jockey="武豊", jockey_id="J2"))
    session.add(Result(race_id="202605010101", horse_id="H1", rank=1))
    session.add(Result(race_id="202605010102", horse_id="H2", rank=4))
    session.commit()

    df = _build_training_frame(session)

    # horse_id列がhorse_nameの重複によって潰れていないこと
    assert set(df["horse_id"]) == {"H1", "H2"}
    assert len(df) == 2

    # エンドツーエンドで衝突しないことも確認する
    predictor = JRAPredictor()
    predictor.prepare_data(df)
    assert "H1" in predictor.horse_map
    assert "H2" in predictor.horse_map
    assert predictor.horse_map["H1"] != predictor.horse_map["H2"]
    session.close()


def test_build_training_frame_empty_db(tmp_path):
    session = _make_session(tmp_path)
    df = _build_training_frame(session)
    assert df.empty
    session.close()
