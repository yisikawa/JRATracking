import os
from cmdstanpy import CmdStanModel
import pandas as pd
import numpy as np

class JRAPredictor:
    def __init__(self, model_path=None):
        if model_path is None:
            model_path = os.path.join(os.path.dirname(__file__), 'jra_model.stan')
        self.model_path = model_path
        self.model = None
        self.fit_result = None
        
        # マッピング用辞書 (ID -> Index)
        self.jockey_map = {}
        self.horse_map = {}
        
    def compile_model(self):
        """Stanモデルをコンパイルする"""
        self.model = CmdStanModel(stan_file=self.model_path)
        
    def prepare_data(self, df):
        """データベースのDataFrameをStan入力形式に変換"""
        # 騎手IDを1から始まる連番にマッピング
        unique_jockeys = df['jockey'].unique()
        self.jockey_map = {name: i+1 for i, name in enumerate(unique_jockeys)}
        jockey_indices = df['jockey'].map(self.jockey_map).fillna(1).astype(int).tolist()

        # 馬ID(名前)を1から始まる連番にマッピング
        # df['horse_id'] がある前提 (DBモデル参照)
        # horse_idはユニークな文字列想定だが、念のためuniqueをとる
        unique_horses = df['horse_id'].unique()
        self.horse_map = {name: i+1 for i, name in enumerate(unique_horses)}
        horse_indices = df['horse_id'].map(self.horse_map).fillna(1).astype(int).tolist()
        
        # 勝利フラグ (例: 1着なら1)
        won_flags = (df['rank'] == 1).astype(int).tolist()
        
        return {
            'N': len(df),
            'J': len(self.jockey_map),
            'H': len(self.horse_map),
            'jockey': jockey_indices,
            'horse': horse_indices,
            'won': won_flags,
            'N_new': 0,
            'jockey_new': [],
            'horse_new': []
        }

    def train(self, df):
        """モデルを学習(サンプリング)する"""
        if self.model is None:
            self.compile_model()
            
        data = self.prepare_data(df)
        # N_newが0だとエラーになる場合があるのでダミーを入れる
        data['N_new'] = 1
        data['jockey_new'] = [1]
        data['horse_new'] = [1]
        
        self.fit_result = self.model.sample(data=data, chains=4, iter_warmup=500, iter_sampling=1000)
        return self.fit_result.summary()

    def predict(self, race_entries):
        """
        新しいレースの出走リストに対して確率を予測
        race_entries: List of dict {'jockey': '名前', ...}
        """
        if self.fit_result is None:
            raise Exception("Model not trained yet")
            
        # 予測用データの作成
        jockey_indices = []
        for entry in race_entries:
            # 未知の騎手は平均的な騎手(または特定のID)に割り当てる対応が必要
            # ここでは既存マップにない場合は仮に1とする
            idx = self.jockey_map.get(entry['jockey'], 1)
            jockey_indices.append(idx)
            
        # 生成量 (generated quantities) ブロックのみを実行して高速化したいが、
        # cmdstanpyではsampleのやり直しが必要、またはgenerated_quantitiesメソッドを使用
        # ここでは簡易的に、事後平均パラメータを使って計算するか、再度generateするか。
        # 正しくは generated_quantities を呼ぶ。
        
        # 既存のfit結果を使って予測値を生成
        data = {
            'N': 0, # 学習データは不要だが整合性のため必要ならダミー
            'J': len(self.jockey_map),
            'jockey': [],
            'won': [],
            'N_new': len(jockey_indices),
            'jockey_new': jockey_indices
        }
        
        # Note: Stanのdataブロック制約によりN=0が許容されない場合はダミーを入れる
        # 上記Stanファイルでは N>=0 なので0でもOKだが、jockey[N]の宣言でエラーになるかも
        # 安全策でダミーデータを入れる
        data['N'] = 1
        data['jockey'] = [1]
        data['won'] = [0]
        
        # generated_quantities実行
        pred_result = self.model.generate_quantities(data=data, mcmc_sample=self.fit_result)
        
        # prob_new の平均を取得
        probs = pred_result.stan_variable('prob_new')
        mean_probs = probs.mean(axis=0) # サンプル方向の平均
        
        return mean_probs
