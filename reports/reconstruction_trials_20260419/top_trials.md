# Phase B.5 — hyperparameter search summary

Pilot: 20 buildings; trials: 50; seed: 42.
Total wall time: 530s.

## Top 3 trials

### #1 — score -0.013

- mean IoU: 0.352
- median IoU: 0.000
- frac IoU ≥ 0.9: 0.20
- review rate: 0.85
- mean coverage_ref: 0.392
- mean over_coverage: 0.065

Config:
```json
{
  "w_fit": 1.0991,
  "w_prior": 0.2193,
  "w_complexity": 0.4988,
  "theta_cov": 0.8764,
  "theta_overlap": 0.0727,
  "theta_az_deg": 23.2981,
  "k_azimuth_bins": 3,
  "azimuth_bin_width_deg": 45.0,
  "time_limit_s": 5.0,
  "lp_gap_epsilon": 0.02,
  "runner_up_margin": 0.05
}
```

### #2 — score -0.013

- mean IoU: 0.352
- median IoU: 0.000
- frac IoU ≥ 0.9: 0.20
- review rate: 0.85
- mean coverage_ref: 0.392
- mean over_coverage: 0.065

Config:
```json
{
  "w_fit": 0.7787,
  "w_prior": 0.595,
  "w_complexity": 0.3409,
  "theta_cov": 0.8353,
  "theta_overlap": 0.08,
  "theta_az_deg": 82.3201,
  "k_azimuth_bins": 3,
  "azimuth_bin_width_deg": 45.0,
  "time_limit_s": 5.0,
  "lp_gap_epsilon": 0.02,
  "runner_up_margin": 0.05
}
```

### #3 — score -0.017

- mean IoU: 0.373
- median IoU: 0.000
- frac IoU ≥ 0.9: 0.20
- review rate: 0.90
- mean coverage_ref: 0.418
- mean over_coverage: 0.065

Config:
```json
{
  "w_fit": 1.8999,
  "w_prior": 0.8809,
  "w_complexity": 0.4408,
  "theta_cov": 0.8554,
  "theta_overlap": 0.0894,
  "theta_az_deg": 78.3621,
  "k_azimuth_bins": 6,
  "azimuth_bin_width_deg": 45.0,
  "time_limit_s": 5.0,
  "lp_gap_epsilon": 0.02,
  "runner_up_margin": 0.05
}
```
