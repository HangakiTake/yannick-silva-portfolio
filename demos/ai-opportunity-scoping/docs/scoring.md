# Scoring formula

Pebblecart (a fictional home-goods shop) ranks processes by payoff minus a fraction of effort. Every term is rounded to 4 decimal places, half up, before it is used in the next step. The same input therefore always produces the same ranking.

Weights live in `config/scoring.json`. They are not renormalised. If you change one, the rank can change, and the examples below say how.

## Inputs used

From the parsed row only:

- monthly volume (count of items per month)
- minutes per item
- error rate (0 to 1). A blank error rate is treated as 0 and flagged `missing_error_rate`. It is not a silent guess that the work is accurate in real life; the flag stays on the row.
- number of systems in the data-sources cell, split on commas
- the notes, for a coarse effort tag

## Terms

1. `monthly_hours = volume * minutes / 60`
2. `hours_score = min(monthly_hours / hours_cap, 1) * 100` with `hours_cap` 400 (about two and a half full-time months)
3. `error_score = min(error_rate / error_cap, 1) * 100` with `error_cap` 0.10
4. `payoff = w_hours * hours_score + w_error * error_score`
5. `source_score = min(n_sources / source_cap, 1) * 100` with `source_cap` 4
6. Effort tag from the notes, after the scrub list in `docs/architecture_rubric.md` (so "no judgment" is not read as judgment):
   - 85 if a judgment phrase matches and no structured phrase matches
   - 25 if a structured phrase matches and no judgment phrase matches
   - 85 if both match (judgment wins; the work is still language-heavy)
   - 55 if neither matches
7. `effort = w_sources * source_score + w_unstructured * effort_tag`
8. `net = payoff - w_effort * effort`

Default weights: `w_hours` 0.70, `w_error` 0.30, `w_sources` 0.40, `w_unstructured` 0.60, `w_effort` 0.25.

Sort by `net` descending, then `payoff` descending, then process name ascending. The sort is stable.

The build shortlist skips rows whose architecture is "don't automate". They stay in the full ranking and in the "leave with the team" section.

## What happens if you change a weight

Effort is held equal in the first example so the flip is only the payoff weights. Both rows use one source and the note "checklist, always the same, no language", so the effort tag is 25 and `source_score` is 25. Effort is 0.40 * 25 + 0.60 * 25 = 25.00. The effort penalty at `w_effort` 0.25 is 6.25 and does not change which row wins.

**HighHours:** volume 2000, minutes 10, error rate 0.01.

- hours = 333.3333, hours_score = 83.3333
- error_score = 10.0000
- default payoff = 0.70 * 83.3333 + 0.30 * 10 = 61.3333
- default net = 55.0833

**HighError:** volume 400, minutes 6, error rate 0.10.

- hours = 40.0000, hours_score = 10.0000
- error_score = 100.0000
- default payoff = 0.70 * 10 + 0.30 * 100 = 37.0000
- default net = 30.7500

HighHours ranks above HighError on the default weights.

Set `w_hours` to 0.20 and `w_error` to 0.80. Effort is unchanged.

- HighHours payoff = 0.20 * 83.3333 + 0.80 * 10 = 24.6667, net = 18.4167
- HighError payoff = 0.20 * 10 + 0.80 * 100 = 82.0000, net = 75.7500

HighError now ranks above HighHours. Raising the error weight promotes the high-error process.

**Second flip, effort weight.** Same payoff weights as the default. The test sets the payoff and the effort directly so the example does not depend on wording:

- Easy: payoff 70.0000, effort 20.0000. Default net = 70 - 0.25 * 20 = 65.0000.
- Hard: payoff 80.0000, effort 90.0000. Default net = 80 - 0.25 * 90 = 57.5000.

Easy ranks above Hard. Set `w_effort` to 0.05:

- Easy net = 70 - 1 = 69.0000
- Hard net = 80 - 4.5 = 75.5000

Hard now ranks above Easy. Lowering the effort weight lets a harder, higher-payoff process through. Raising it does the opposite.

## Trace

Each scored row keeps the raw cells, the normalised inputs, every term above, the weight set, and the effort-tag reason. Nothing in the rank is a hidden constant.
