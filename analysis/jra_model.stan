data {
  int<lower=0> N;                 // Number of data points (entries)
  int<lower=0> J;                 // Number of Jockeys
  int<lower=0> H;                 // Number of Horses
  array[N] int<lower=1, upper=J> jockey; // Jockey ID
  array[N] int<lower=1, upper=H> horse;  // Horse ID
  array[N] int<lower=0, upper=1> won;   // 1:Won (or Top 3), 0:Others
  
  // Prediction data
  int<lower=0> N_new;
  array[N_new] int<lower=1, upper=J> jockey_new;
  array[N_new] int<lower=1, upper=H> horse_new;
}

parameters {
  real alpha;                    // Global intercept
  vector[J] beta_j;              // Jockey effect (ability)
  real<lower=0> sigma_j;         // Jockey ability variation
  vector[H] beta_h;              // Horse effect (ability)
  real<lower=0> sigma_h;         // Horse ability variation
}

model {
  // Priors
  sigma_j ~ cauchy(0, 2.5);
  beta_j ~ normal(0, sigma_j);
  
  sigma_h ~ cauchy(0, 2.5);
  beta_h ~ normal(0, sigma_h);
  
  alpha ~ normal(0, 5);

  // Likelihood
  won ~ bernoulli_logit(alpha + beta_j[jockey] + beta_h[horse]);
}

generated quantities {
  // Prediction (Sampling from posterior)
  vector[N_new] prob_new;
  for (n in 1:N_new) {
    prob_new[n] = inv_logit(alpha + beta_j[jockey_new[n]] + beta_h[horse_new[n]]);
  }
}
