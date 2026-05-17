data {
  int<lower=0> N;                          // number of training entries
  int<lower=0> J;                          // number of jockeys (includes UNKNOWN sentinel)
  int<lower=0> H;                          // number of horses  (includes UNKNOWN sentinel)
  array[N] int<lower=1, upper=J> jockey;   // jockey index per entry
  array[N] int<lower=1, upper=H> horse;    // horse index per entry
  array[N] int<lower=0, upper=1> won;      // 1st place flag
  array[N] int<lower=0, upper=1> top3;     // top-3 finish flag (provides more signal than won alone)

  int<lower=0> N_new;
  array[N_new] int<lower=1, upper=J> jockey_new;
  array[N_new] int<lower=1, upper=H> horse_new;
}

parameters {
  real alpha;                   // intercept for win
  real alpha_top3;              // intercept for top-3 (typically > alpha)
  vector[J] beta_j;             // jockey ability
  real<lower=0> sigma_j;        // jockey ability spread
  vector[H] beta_h;             // horse ability
  real<lower=0> sigma_h;        // horse ability spread
}

model {
  sigma_j ~ cauchy(0, 2.5);
  beta_j  ~ normal(0, sigma_j);

  sigma_h ~ cauchy(0, 2.5);
  beta_h  ~ normal(0, sigma_h);

  alpha      ~ normal(0, 5);
  alpha_top3 ~ normal(0, 5);

  // joint likelihood: win and top-3 trained simultaneously
  won  ~ bernoulli_logit(alpha      + beta_j[jockey] + beta_h[horse]);
  top3 ~ bernoulli_logit(alpha_top3 + beta_j[jockey] + beta_h[horse]);
}

generated quantities {
  vector[N_new] prob_win;
  vector[N_new] prob_top3;
  for (n in 1:N_new) {
    prob_win[n]  = inv_logit(alpha      + beta_j[jockey_new[n]] + beta_h[horse_new[n]]);
    prob_top3[n] = inv_logit(alpha_top3 + beta_j[jockey_new[n]] + beta_h[horse_new[n]]);
  }
}
