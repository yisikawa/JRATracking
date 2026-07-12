import jax
import jax.numpy as jnp
import numpyro
import numpyro.distributions as dist
from numpyro.infer import SVI, Trace_ELBO, NUTS, MCMC
from numpyro.infer.autoguide import AutoNormal
from numpyro.optim import Adam
import pandas as pd
import numpy as np


def _model(jockey, horse, won, top3, J, H):
    sigma_j    = numpyro.sample('sigma_j',    dist.HalfCauchy(2.5))
    sigma_h    = numpyro.sample('sigma_h',    dist.HalfCauchy(2.5))
    alpha      = numpyro.sample('alpha',      dist.Normal(0., 5.))
    alpha_top3 = numpyro.sample('alpha_top3', dist.Normal(0., 5.))
    beta_j     = numpyro.sample('beta_j',     dist.Normal(jnp.zeros(J), sigma_j))
    beta_h     = numpyro.sample('beta_h',     dist.Normal(jnp.zeros(H), sigma_h))
    numpyro.sample('won',  dist.Bernoulli(logits=alpha      + beta_j[jockey] + beta_h[horse]), obs=won)
    numpyro.sample('top3', dist.Bernoulli(logits=alpha_top3 + beta_j[jockey] + beta_h[horse]), obs=top3)


class JRAPredictor:
    UNKNOWN = '__UNKNOWN__'

    def __init__(self, model_path=None):  # model_path は互換性のため残す
        self.fit_result  = None
        self.fit_mode    = None   # 'advi' | 'fast' | 'standard'
        self.jockey_map  = {}     # name/id → 0-indexed int
        self.horse_map   = {}     # horse_id → 0-indexed int
        self.jockey_display_map = {}
        self.horse_display_map  = {}   # horse_id → 馬名
        self.horse_name_map     = {}   # 馬名 → horse_id
        self.summary = None

    def prepare_data(self, df: pd.DataFrame) -> dict:
        unique_jockeys = list(df['jockey'].unique()) + [self.UNKNOWN]
        self.jockey_map = {name: i for i, name in enumerate(unique_jockeys)}
        if 'jockey_name' in df.columns:
            self.jockey_display_map = dict(zip(df['jockey'], df['jockey_name']))

        unique_horses = list(df['horse_id'].unique()) + [self.UNKNOWN]
        self.horse_map = {name: i for i, name in enumerate(unique_horses)}
        if 'horse_name' in df.columns:
            self.horse_display_map = dict(zip(df['horse_id'], df['horse_name']))
            # 同名の馬が複数存在する場合、name→horse_idの逆引きは最後に処理された馬のhorse_idで上書きされる（後勝ち）。
            # horse_id指定なら常に正確に解決できるため、この経路は名前だけで馬を指定した場合にのみ影響する。
            self.horse_name_map = {name: hid for hid, name in self.horse_display_map.items()}

        unk_j = self.jockey_map[self.UNKNOWN]
        unk_h = self.horse_map[self.UNKNOWN]

        return {
            'jockey': jnp.array(df['jockey'].map(self.jockey_map).fillna(unk_j).astype(int).values),
            'horse':  jnp.array(df['horse_id'].map(self.horse_map).fillna(unk_h).astype(int).values),
            'won':    jnp.array((df['rank'] == 1).astype(int).values),
            'top3':   jnp.array((df['rank'] <= 3).astype(int).values),
            'J':      len(self.jockey_map),
            'H':      len(self.horse_map),
        }

    def train(self, df: pd.DataFrame, mode: str = 'standard') -> pd.DataFrame:
        """モデルを学習する。mode: 'advi'(高速) / 'fast'(標準) / 'standard'(精密)"""
        data = self.prepare_data(df)
        self.fit_mode = mode
        rng_key = jax.random.PRNGKey(42)

        if mode == 'advi':
            guide  = AutoNormal(_model)
            svi    = SVI(_model, guide, Adam(0.01), loss=Trace_ELBO())
            result = svi.run(rng_key, 20000, **data, progress_bar=False)
            self.fit_result = {'type': 'advi', 'svi': svi, 'params': result.params}
        elif mode == 'fast':
            mcmc = MCMC(NUTS(_model), num_warmup=200, num_samples=300,
                        num_chains=2, progress_bar=True)
            mcmc.run(rng_key, **data)
            self.fit_result = {'type': 'mcmc', 'samples': mcmc.get_samples()}
        else:
            mcmc = MCMC(NUTS(_model), num_warmup=500, num_samples=1000,
                        num_chains=4, progress_bar=True)
            mcmc.run(rng_key, **data)
            self.fit_result = {'type': 'mcmc', 'samples': mcmc.get_samples()}

        self.summary = self._build_summary()
        return self.summary

    def _build_summary(self) -> pd.DataFrame:
        rows = {}
        is_advi = self.fit_result['type'] == 'advi'

        if is_advi:
            params = self.fit_result['params']
            for pname in ['alpha', 'alpha_top3']:
                v = float(params.get(f'{pname}_auto_loc', 0.))
                rows[pname] = {'Mean': v, 'StdDev': float('nan'),
                               '5%': float('nan'), '95%': float('nan'), 'R_hat': float('nan')}
            bj = np.array(params.get('beta_j_auto_loc', np.zeros(len(self.jockey_map))))
            bh = np.array(params.get('beta_h_auto_loc', np.zeros(len(self.horse_map))))
            for i, v in enumerate(bj):
                rows[f'beta_j[{i}]'] = {'Mean': float(v), 'StdDev': float('nan'),
                                         '5%': float('nan'), '95%': float('nan'), 'R_hat': float('nan')}
            for i, v in enumerate(bh):
                rows[f'beta_h[{i}]'] = {'Mean': float(v), 'StdDev': float('nan'),
                                         '5%': float('nan'), '95%': float('nan'), 'R_hat': float('nan')}
        else:
            samples = self.fit_result['samples']
            for pname in ['alpha', 'alpha_top3']:
                s = np.array(samples[pname])
                rows[pname] = {'Mean': float(s.mean()), 'StdDev': float(s.std()),
                               '5%': float(np.percentile(s, 5)), '95%': float(np.percentile(s, 95)),
                               'R_hat': float('nan')}
            bj = np.array(samples['beta_j'])  # (samples, J)
            for i in range(bj.shape[1]):
                s = bj[:, i]
                rows[f'beta_j[{i}]'] = {'Mean': float(s.mean()), 'StdDev': float(s.std()),
                                         '5%': float(np.percentile(s, 5)), '95%': float(np.percentile(s, 95)),
                                         'R_hat': float('nan')}
            bh = np.array(samples['beta_h'])  # (samples, H)
            for i in range(bh.shape[1]):
                s = bh[:, i]
                rows[f'beta_h[{i}]'] = {'Mean': float(s.mean()), 'StdDev': float(s.std()),
                                         '5%': float(np.percentile(s, 5)), '95%': float(np.percentile(s, 95)),
                                         'R_hat': float('nan')}

        return pd.DataFrame(rows).T

    def get_summary(self) -> pd.DataFrame:
        """学習時に計算した summary を返す（旧pickle向けに遅延構築も可能）"""
        if getattr(self, 'summary', None) is None:
            self.summary = self._build_summary()
        return self.summary

    def predict(self, race_entries: list) -> tuple:
        if self.fit_result is None:
            raise RuntimeError("モデルが学習されていません。train() を先に呼んでください。")

        unk_j = self.jockey_map[self.UNKNOWN]
        unk_h = self.horse_map[self.UNKNOWN]
        j_idx = np.array([self.jockey_map.get(e['jockey'], unk_j) for e in race_entries])
        resolved = [self.resolve_horse_key(e['horse']) for e in race_entries]
        h_idx = np.array([self.horse_map[k] if k is not None else unk_h for k in resolved])

        if self.fit_result['type'] == 'advi':
            params     = self.fit_result['params']
            alpha      = float(params.get('alpha_auto_loc',      0.))
            alpha_top3 = float(params.get('alpha_top3_auto_loc', 0.))
            beta_j     = np.array(params.get('beta_j_auto_loc', np.zeros(len(self.jockey_map))))
            beta_h     = np.array(params.get('beta_h_auto_loc', np.zeros(len(self.horse_map))))
            lw = alpha      + beta_j[j_idx] + beta_h[h_idx]
            lt = alpha_top3 + beta_j[j_idx] + beta_h[h_idx]
            return 1 / (1 + np.exp(-lw)), 1 / (1 + np.exp(-lt))
        else:
            samples    = self.fit_result['samples']
            alpha      = jnp.array(samples['alpha'])       # (S,)
            alpha_top3 = jnp.array(samples['alpha_top3'])  # (S,)
            beta_j     = jnp.array(samples['beta_j'])      # (S, J)
            beta_h     = jnp.array(samples['beta_h'])      # (S, H)
            lw = alpha[:, None] + beta_j[:, j_idx] + beta_h[:, h_idx]
            lt = alpha_top3[:, None] + beta_j[:, j_idx] + beta_h[:, h_idx]
            return (np.array(jax.nn.sigmoid(lw).mean(axis=0)),
                    np.array(jax.nn.sigmoid(lt).mean(axis=0)))

    def known_jockeys(self) -> list:
        return [k for k in self.jockey_map if k != self.UNKNOWN]

    def known_horses(self) -> list:
        return [k for k in self.horse_map if k != self.UNKNOWN]

    def resolve_horse_key(self, value: str):
        """horse_id または馬名を horse_map のキーに解決する。未知なら None"""
        if value in self.horse_map and value != self.UNKNOWN:
            return value
        hid = self.horse_name_map.get(value)
        if hid in self.horse_map:
            return hid
        return None
