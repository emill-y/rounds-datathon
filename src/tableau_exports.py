"""Build the data behind the three Tableau dashboards.

  python src/tableau_exports.py        (from the repo root, ~2 min)

Dashboard 1  Patient Priority      -> tableau/d1_patient_priority.csv, tableau/d1_patient_vitals_long.csv
Dashboard 2  NEWS2 vs Rounds       -> tableau/d2_missingness_curves.csv, tableau/d2_missingness_runs.csv
Dashboard 3  Failure-to-rescue map -> tableau/d3_hospitals.csv, tableau/d3_states.csv

Every patient-level prediction is OUT-OF-FOLD: a patient is always scored by a model that
was trained without them.
"""
import os, sys
import numpy as np, pandas as pd
from sklearn.model_selection import StratifiedKFold
sys.path.insert(0, os.path.dirname(__file__))
import news2
from rounds_model import load, fit_rounds, to_X, VITALS, SHORT, SEED, ROOT
import hospitals as H

TAB = os.path.join(ROOT, 'tableau'); os.makedirs(TAB, exist_ok=True)
PRIORITY = ['Respiratory_Rate', 'Oxygen_Saturation', 'Systolic_BP', 'Heart_Rate', 'Consciousness', 'Temperature']
MISSING_RATES = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]
ALERT_RATES = [0.20, 0.28, 0.35]          # 0.28 ~= share of patients who are truly High risk
REPEATS = 5


def drop_random(df, rate, rng):
    m = df.copy()
    if rate == 0: return m
    drop = rng.random((len(m), len(VITALS))) < rate
    for j, v in enumerate(VITALS): m.loc[drop[:, j], v] = np.nan
    return m


def at_alert_rate(score, truth_high, rate, rng):
    """Alert on the top `rate` share of patients by score (random tie-break), so both methods
    raise exactly the same number of alerts and can be compared fairly."""
    n_alert = int(round(rate * len(score)))
    order = np.lexsort((rng.random(len(score)), -np.asarray(score, float)))
    alert = np.zeros(len(score), bool); alert[order[:n_alert]] = True
    tp = (alert & truth_high).sum(); fp = (alert & ~truth_high).sum()
    return dict(recall=tp / truth_high.sum(), precision=tp / max(alert.sum(), 1),
                false_alerts_per_100=100 * fp / len(score), missed_high_per_100=100 * (truth_high & ~alert).sum() / len(score))


def main():
    d = load(); rng = np.random.default_rng(SEED)
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
    folds = list(skf.split(d, d['Risk_Level']))
    models = [fit_rounds(d.iloc[tr], rng) for tr, _ in folds]
    p_high_col = list(models[0].classes_).index('High')

    # ---------------- Dashboard 2: performance as vitals go missing ----------------
    runs = []
    for rep in range(REPEATS):
        for rate in MISSING_RATES:
            rrng = np.random.default_rng(1000 * rep + int(rate * 100))
            for (tr, te), model in zip(folds, models):
                test = d.iloc[te].reset_index(drop=True)
                masked = drop_random(test, rate, rrng)
                truth = (test.Risk_Level == 'High').to_numpy()
                scores = {'NEWS2 (missing = normal)': news2.news2_total(masked).to_numpy(),
                          'Rounds': model.predict_proba(to_X(masked))[:, p_high_col]}
                default_flags = {'NEWS2 (missing = normal)': (news2.news2_risk(masked) == 'High').to_numpy(),
                                 'Rounds': model.predict(to_X(masked)) == 'High'}
                for meth, s in scores.items():
                    for ar in ALERT_RATES:
                        runs.append(dict(method=meth, missing_pct=int(rate * 100), alert_rule=f'Top {int(ar*100)}% alerted',
                                         alert_rate_pct=int(ar * 100), repeat=rep, **at_alert_rate(s, truth, ar, rrng)))
                    f = default_flags[meth]
                    tp = (f & truth).sum(); fp = (f & ~truth).sum()
                    runs.append(dict(method=meth, missing_pct=int(rate * 100), alert_rule='Default threshold (High)',
                                     alert_rate_pct=round(100 * f.mean(), 1), repeat=rep, recall=tp / truth.sum(),
                                     precision=tp / max(f.sum(), 1), false_alerts_per_100=100 * fp / len(f),
                                     missed_high_per_100=100 * (truth & ~f).sum() / len(f)))
    runs = pd.DataFrame(runs)
    runs.to_csv(os.path.join(TAB, 'd2_missingness_runs.csv'), index=False)
    curves = runs.groupby(['method', 'missing_pct', 'alert_rule']).agg(
        recall=('recall', 'mean'), recall_sd=('recall', 'std'), precision=('precision', 'mean'),
        false_alerts_per_100=('false_alerts_per_100', 'mean'), missed_high_per_100=('missed_high_per_100', 'mean'),
        alert_rate_pct=('alert_rate_pct', 'mean')).reset_index()
    curves.to_csv(os.path.join(TAB, 'd2_missingness_curves.csv'), index=False)
    print(curves[curves.alert_rule == 'Top 28% alerted'].round(3).to_string())
    print(curves[curves.alert_rule == 'Default threshold (High)'].round(3).to_string())

    # ---------------- Dashboard 1: a de-identified "night ward" priority list ----------------
    wrng = np.random.default_rng(2025)
    ward = d.groupby('Risk_Level').sample(10, random_state=11).reset_index(drop=True)
    ward = ward.sample(frac=1, random_state=5).reset_index(drop=True)
    shown = drop_random(ward, 0.40, wrng)       # ~40% of vitals not yet charted (night round)
    fold_of = {pid: k for k, (_, te) in enumerate(folds) for pid in d.iloc[te].Patient_ID}
    P = np.vstack([models[fold_of[pid]].predict_proba(to_X(shown.iloc[[i]]))[0] for i, pid in enumerate(shown.Patient_ID)])
    cls = list(models[0].classes_)
    out = pd.DataFrame({'Bed': [f'Bed {i+1:02d}' for i in range(len(shown))],
                        'Patient': [f'PT-{1000 + i*7 % 997:04d}' for i in range(len(shown))]})   # fictional display IDs
    out['Dataset_ID'] = shown.Patient_ID
    for v in VITALS: out[SHORT[v]] = shown[v]
    out['On_Oxygen'] = shown.On_Oxygen
    for c in ['High', 'Medium', 'Low', 'Normal']: out[f'P_{c}'] = P[:, cls.index(c)].round(3)
    out['Rounds_risk'] = np.array(cls)[P.argmax(1)]
    out['NEWS2_score_today'] = news2.news2_total(shown).to_numpy()
    out['NEWS2_risk_today'] = news2.news2_risk(shown).to_numpy()
    out['Missing_count'] = shown[VITALS].isna().sum(1).to_numpy()
    out['Missing_vitals'] = shown[VITALS].apply(lambda r: ', '.join(SHORT[v] for v in VITALS if pd.isna(r[v])) or 'none', axis=1).to_numpy()
    out['Next_measurement'] = shown.apply(lambda r: next((SHORT[v] for v in PRIORITY if pd.isna(r[v])), 'none, all charted'), axis=1).to_numpy()
    # priority score: probability of High, plus half the probability of Medium
    out['Priority_score'] = (out.P_High + 0.5 * out.P_Medium).round(3)
    out['Priority_rank'] = out.Priority_score.rank(ascending=False, method='first').astype(int)
    out['NEWS2_would_miss'] = ((ward.Risk_Level == 'High').to_numpy() & (out.NEWS2_risk_today != 'High').to_numpy())
    out['NEWS2_would_miss'] = out['NEWS2_would_miss'].map({True: 'Yes', False: 'No'})
    out['True_risk_validation_only'] = ward.Risk_Level.to_numpy()
    out = out.sort_values('Priority_rank')
    out.to_csv(os.path.join(TAB, 'd1_patient_priority.csv'), index=False)
    long = out.melt(id_vars=['Bed', 'Patient', 'Priority_rank', 'Rounds_risk'], value_vars=[SHORT[v] for v in VITALS],
                    var_name='Vital', value_name='Value')
    long['Status'] = np.where(long.Value.isna(), 'Missing', 'Charted')
    long['Is_next'] = long.apply(lambda r: 'Measure next' if out.set_index('Bed').loc[r.Bed, 'Next_measurement'] == r.Vital else '', axis=1)
    long['Vital_order'] = long.Vital.map({SHORT[v]: i + 1 for i, v in enumerate(PRIORITY)})
    long.to_csv(os.path.join(TAB, 'd1_patient_vitals_long.csv'), index=False)
    print(out[['Bed', 'Priority_rank', 'Rounds_risk', 'P_High', 'NEWS2_risk_today', 'Missing_vitals', 'Next_measurement', 'True_risk_validation_only']].head(12).to_string())
    print('High-risk patients in ward:', (ward.Risk_Level == 'High').sum(), '| NEWS2 misses:', (out.NEWS2_would_miss == 'Yes').sum(),
          '| High in Rounds top 10:', (out.head(10).True_risk_validation_only == 'High').sum())

    # ---------------- Dashboard 3: failure-to-rescue map ----------------
    f = H.load_iscmr().merge(H.load_general(), on='Facility ID', how='left').merge(H.load_hcahps(), on='Facility ID', how='left')
    f['county_key'] = f['County/Parish'].map(H.norm_county) + '|' + f['State']
    f = f.merge(H.load_svi(), on='county_key', how='left').merge(H.load_hpsa(), on='FIPS', how='left')
    f['Rural'] = f['HPSA_rural'].fillna(False).astype(bool).map({True: 'Rural', False: 'Urban'})
    bench = f.FTR_rate.quantile(0.25)
    f['Benchmark_rate'] = round(bench, 2)
    f['Deaths_est'] = f.FTR_rate * f.FTR_cases / 1000
    f['Excess_deaths_2yr'] = (f.FTR_rate - bench).clip(lower=0) * f.FTR_cases / 1000
    f['SVI_quartile'] = pd.qcut(f.SVI_overall, 4, labels=['Q1 least vulnerable', 'Q2', 'Q3', 'Q4 most vulnerable']).astype(str)
    f['Help_quartile'] = pd.qcut(f.Help_ASAP_score.rank(method='first'), 4, labels=['Q1 slowest help', 'Q2', 'Q3', 'Q4 fastest help']).astype(str)
    f['ZIP'] = f['ZIP Code'].str.zfill(5)
    f = f.rename(columns={'Facility Name': 'Hospital', 'City/Town': 'City', 'Hospital overall rating': 'CMS_star_rating'})
    cols = ['Facility ID', 'Hospital', 'City', 'State', 'ZIP', 'FIPS', 'County', 'FTR_rate', 'Lower Estimate', 'Higher Estimate',
            'FTR_vs_national', 'FTR_cases', 'Deaths_est', 'Excess_deaths_2yr', 'Benchmark_rate', 'Hospital Ownership', 'CMS_star_rating',
            'Help_ASAP_score', 'Nurse_comm_score', 'SVI_overall', 'SVI_quartile', 'Help_quartile', 'Rural', 'Pct_uninsured']
    f[cols].to_csv(os.path.join(TAB, 'd3_hospitals.csv'), index=False)
    st = f.groupby('State').apply(lambda g: pd.Series({
        'hospitals': len(g), 'cases': g.FTR_cases.sum(), 'FTR_rate_weighted': np.average(g.FTR_rate, weights=g.FTR_cases),
        'excess_deaths_2yr': g.Excess_deaths_2yr.sum(), 'excess_deaths_per_year': g.Excess_deaths_2yr.sum() / 2,
        'hospitals_worse_than_national': (g.FTR_vs_national == 'Worse Than the National Rate').sum()}), include_groups=False).reset_index()
    st.to_csv(os.path.join(TAB, 'd3_states.csv'), index=False)
    print(st.sort_values('excess_deaths_per_year', ascending=False).head(8).round(1).to_string())


if __name__ == '__main__':
    main()
