import os
from cmdstanpy import CmdStanModel
import pandas as pd
import numpy as np


class JRAPredictor:
    UNKNOWN = '__UNKNOWN__'

    def __init__(self, model_path=None):
        if model_path is None:
            model_path = os.path.join(os.path.dirname(__file__), 'jra_model.stan')
        self.model_path = model_path
        self.model = None
        self.fit_result = None
        self.jockey_map = {}
        self.horse_map = {}
        self.jockey_display_map = {}  # jockey key (ID or name) → 表示用名前

    def compile_model(self):
        self.model = CmdStanModel(stan_file=self.model_path)

    def prepare_data(self, df: pd.DataFrame) -> dict:
        """DataFrameをStan入力形式に変換する。
        末尾に UNKNOWN センチネルを追加し、学習未知の騎手・馬に対応する。
        """
        unique_jockeys = list(df['jockey'].unique()) + [self.UNKNOWN]
        self.jockey_map = {name: i + 1 for i, name in enumerate(unique_jockeys)}
        if 'jockey_name' in df.columns:
            self.jockey_display_map = dict(zip(df['jockey'], df['jockey_name']))

        unique_horses = list(df['horse_id'].unique()) + [self.UNKNOWN]
        self.horse_map = {name: i + 1 for i, name in enumerate(unique_horses)}

        unk_j = self.jockey_map[self.UNKNOWN]
        unk_h = self.horse_map[self.UNKNOWN]

        jockey_idx = df['jockey'].map(self.jockey_map).fillna(unk_j).astype(int).tolist()
        horse_idx  = df['horse_id'].map(self.horse_map).fillna(unk_h).astype(int).tolist()

        won_flags  = (df['rank'] == 1).astype(int).tolist()
        top3_flags = (df['rank'] <= 3).astype(int).tolist()

        return {
            'N':          len(df),
            'J':          len(self.jockey_map),
            'H':          len(self.horse_map),
            'jockey':     jockey_idx,
            'horse':      horse_idx,
            'won':        won_flags,
            'top3':       top3_flags,
            'N_new':      1,
            'jockey_new': [1],
            'horse_new':  [1],
        }

    def train(self, df: pd.DataFrame) -> pd.DataFrame:
        """モデルをMCMCサンプリングで学習し、サマリーを返す"""
        if self.model is None:
            self.compile_model()
        data = self.prepare_data(df)
        self.fit_result = self.model.sample(
            data=data, chains=4, iter_warmup=500, iter_sampling=1000
        )
        return self.fit_result.summary()

    def predict(self, race_entries: list) -> tuple:
        """
        新しいレースの出走リストに対して勝率・3着内率を予測する。

        Args:
            race_entries: [{'jockey': '騎手名', 'horse': '馬名'}, ...] のリスト

        Returns:
            (prob_win, prob_top3): 各エントリーの確率を表すnumpy配列のタプル
        """
        if self.fit_result is None:
            raise RuntimeError("モデルが学習されていません。train() を先に呼んでください。")

        unk_j = self.jockey_map[self.UNKNOWN]
        unk_h = self.horse_map[self.UNKNOWN]

        jockey_idx = [self.jockey_map.get(e['jockey'], unk_j) for e in race_entries]
        horse_idx  = [self.horse_map.get(e['horse'],   unk_h) for e in race_entries]

        data = {
            'N':          1,
            'J':          len(self.jockey_map),
            'H':          len(self.horse_map),
            'jockey':     [1],
            'horse':      [1],
            'won':        [0],
            'top3':       [0],
            'N_new':      len(race_entries),
            'jockey_new': jockey_idx,
            'horse_new':  horse_idx,
        }

        gq = self.model.generate_quantities(data=data, mcmc_sample=self.fit_result)
        prob_win  = gq.stan_variable('prob_win').mean(axis=0)
        prob_top3 = gq.stan_variable('prob_top3').mean(axis=0)
        return prob_win, prob_top3

    def known_jockeys(self) -> list:
        return [k for k in self.jockey_map if k != self.UNKNOWN]

    def known_horses(self) -> list:
        return [k for k in self.horse_map if k != self.UNKNOWN]
