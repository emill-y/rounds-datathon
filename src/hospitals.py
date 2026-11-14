"""Part 2: where is failure to rescue worst?  Joins 5 public datasets at the hospital and county level."""
import os, re
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import KFold, cross_val_predict
from sklearn.metrics import r2_score, mean_absolute_error
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.inspection import permutation_importance

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, 'data'); OUT = os.path.join(ROOT, 'outputs')
SEED = 42


def norm_county(s):
    s = str(s).upper().replace('.', '').replace("'", '').strip()
    s = re.sub(r'\b(COUNTY|PARISH|BOROUGH|CITY AND BOROUGH|CENSUS AREA|MUNICIPALITY|MUNICIPIO)\b', '', s)
    s = s.replace('SAINT ', 'ST ').replace('STE ', 'STE ')
    return re.sub(r'\s+', ' ', s).strip()


def load_iscmr():
    c = pd.read_csv(os.path.join(RAW, 'Complications_and_Deaths-Hospital.csv'), dtype=str)
    x = c[c['Measure ID'] == 'ISCMR'].copy()
    for col in ['Score', 'Denominator', 'Lower Estimate', 'Higher Estimate']:
        x[col] = pd.to_numeric(x[col], errors='coerce')
    x = x.dropna(subset=['Score', 'Denominator'])
    return x.rename(columns={'Score': 'FTR_rate', 'Denominator': 'FTR_cases', 'Compared to National': 'FTR_vs_national'})[
        ['Facility ID', 'Facility Name', 'City/Town', 'State', 'ZIP Code', 'County/Parish', 'FTR_rate', 'FTR_cases',
         'Lower Estimate', 'Higher Estimate', 'FTR_vs_national']]


def load_general():
    g = pd.read_csv(os.path.join(RAW, 'Hospital_General_Information.csv'), dtype=str)
    g = g[['Facility ID', 'Hospital Type', 'Hospital Ownership', 'Emergency Services', 'Hospital overall rating']]
    g['Hospital overall rating'] = pd.to_numeric(g['Hospital overall rating'], errors='coerce')
    return g


def load_hcahps():
    want = {'H_COMP_3_LINEAR_SCORE': 'Help_ASAP_score',
            'H_COMP_1_LINEAR_SCORE': 'Nurse_comm_score', 'H_COMP_9_LINEAR_SCORE': 'Staff_coordination_score'}
    h = pd.read_csv(os.path.join(RAW, 'HCAHPS-Hospital.csv'), dtype=str,
                    usecols=['Facility ID', 'HCAHPS Measure ID', 'HCAHPS Linear Mean Value'])
    h = h[h['HCAHPS Measure ID'].isin(want)]
    h['val'] = pd.to_numeric(h['HCAHPS Linear Mean Value'], errors='coerce')
    w = h.pivot_table(index='Facility ID', columns='HCAHPS Measure ID', values='val').rename(columns=want).reset_index()
    return w


def load_svi():
    s = pd.read_csv(os.path.join(RAW, 'SVI_2022_US_COUNTY.csv'), dtype={'FIPS': str, 'STCNTY': str}, encoding='utf-8-sig')
    s = s.replace(-999, np.nan)
    s['FIPS'] = s['FIPS'].str.zfill(5)
    s['county_key'] = s['COUNTY'].map(norm_county) + '|' + s['ST_ABBR']
    s['Pop_density'] = s['E_TOTPOP'] / s['AREA_SQMI']
    keep = {'FIPS': 'FIPS', 'county_key': 'county_key', 'COUNTY': 'County', 'ST_ABBR': 'ST', 'E_TOTPOP': 'County_pop',
            'RPL_THEMES': 'SVI_overall', 'RPL_THEME1': 'SVI_socioeconomic', 'RPL_THEME2': 'SVI_household',
            'RPL_THEME3': 'SVI_minority', 'RPL_THEME4': 'SVI_housing_transport', 'EP_UNINSUR': 'Pct_uninsured',
            'EP_POV150': 'Pct_below_150_poverty', 'EP_MINRTY': 'Pct_minority', 'EP_AGE65': 'Pct_65plus', 'Pop_density': 'Pop_density'}
    return s[list(keep)].rename(columns=keep)


def load_hpsa():
    p = pd.read_csv(os.path.join(RAW, 'BCD_HPSA_FCT_DET_PC.csv'), dtype=str,
                    usecols=['HPSA Status', 'Designation Type', 'HPSA Score', 'Rural Status',
                             'State and County Federal Information Processing Standard Code'])
    p = p[p['HPSA Status'].isin(['Designated', 'Proposed For Withdrawal'])]
    p = p[p['Designation Type'].isin(['Geographic HPSA', 'High Needs Geographic HPSA', 'HPSA Population'])]
    p['FIPS'] = p['State and County Federal Information Processing Standard Code'].str.zfill(5)
    p['HPSA Score'] = pd.to_numeric(p['HPSA Score'], errors='coerce')
    p['rural'] = p['Rural Status'].isin(['Rural', 'Partially Rural'])
    a = p.groupby('FIPS').agg(HPSA_designations=('HPSA Score', 'size'), HPSA_max_score=('HPSA Score', 'max'),
                              HPSA_rural=('rural', 'max')).reset_index()
    return a


def main():
    f = load_iscmr().merge(load_general(), on='Facility ID', how='left').merge(load_hcahps(), on='Facility ID', how='left')
    f['county_key'] = f['County/Parish'].map(norm_county) + '|' + f['State']
    svi = load_svi()
    f = f.merge(svi, on='county_key', how='left')
    print(f"hospitals with FTR rate: {len(f)}; matched to SVI county: {f.FIPS.notna().mean():.1%}")
    f = f.merge(load_hpsa(), on='FIPS', how='left')
    f['HPSA_designations'] = f['HPSA_designations'].fillna(0)
    f['In_shortage_area'] = (f['HPSA_designations'] > 0).astype(int)
    f['Rural'] = f['HPSA_rural'].fillna(False).astype(bool).astype(int)

    # Excess deaths relative to the best-performing quarter of hospitals (deaths per 1,000 x cases)
    bench = f['FTR_rate'].quantile(0.25)
    f['Deaths_est'] = f['FTR_rate'] * f['FTR_cases'] / 1000
    f['Excess_deaths_vs_best_quartile'] = ((f['FTR_rate'] - bench).clip(lower=0) * f['FTR_cases'] / 1000)
    f['SVI_quartile'] = pd.qcut(f['SVI_overall'], 4, labels=['Q1 least vulnerable', 'Q2', 'Q3', 'Q4 most vulnerable'])
    f['Help_ASAP_quartile'] = pd.qcut(f['Help_ASAP_score'].rank(method='first'), 4,
                                      labels=['Q1 slowest help', 'Q2', 'Q3', 'Q4 fastest help'])
    f.to_csv(os.path.join(OUT, 'hospitals_joined.csv'), index=False)

    headline = dict(
        hospitals=len(f), period='Jul 2023 - Jun 2025 (2 years)', benchmark_rate_best_quartile=round(bench, 2),
        national_cases=int(f.FTR_cases.sum()), est_deaths=round(f.Deaths_est.sum()),
        excess_deaths_2yr=round(f.Excess_deaths_vs_best_quartile.sum()),
        excess_deaths_per_year=round(f.Excess_deaths_vs_best_quartile.sum() / 2),
        hospitals_worse_than_national=int((f.FTR_vs_national == 'Worse Than the National Rate').sum()))
    print(headline)

    def wmean(g):  # case-weighted failure-to-rescue rate
        return pd.Series({'hospitals': len(g), 'cases': g.FTR_cases.sum(),
                          'FTR_rate_weighted': np.average(g.FTR_rate, weights=g.FTR_cases),
                          'excess_deaths_2yr': g.Excess_deaths_vs_best_quartile.sum(),
                          'pct_worse_than_national': (g.FTR_vs_national == 'Worse Than the National Rate').mean()})
    by_svi = f.dropna(subset=['SVI_quartile']).groupby('SVI_quartile', observed=True).apply(wmean, include_groups=False)
    by_help = f.dropna(subset=['Help_ASAP_score']).groupby('Help_ASAP_quartile', observed=True).apply(wmean, include_groups=False)
    by_short = f.groupby('In_shortage_area').apply(wmean, include_groups=False)
    by_rural = f.groupby('Rural').apply(wmean, include_groups=False)
    by_type = f.groupby('Hospital Ownership').apply(wmean, include_groups=False).sort_values('FTR_rate_weighted')
    for name, t in [('svi', by_svi), ('help', by_help), ('shortage', by_short), ('rural', by_rural), ('ownership', by_type)]:
        t.to_csv(os.path.join(OUT, f'ftr_by_{name}.csv')); print('\n', name); print(t.round(3))
    tot = f.Excess_deaths_vs_best_quartile.sum()
    headline['pct_excess_in_most_vulnerable_svi_quartile'] = round(100 * by_svi.loc['Q4 most vulnerable', 'excess_deaths_2yr'] / tot, 1)
    headline['ftr_rate_slowest_help_q'] = round(by_help.loc['Q1 slowest help', 'FTR_rate_weighted'], 2)
    headline['ftr_rate_fastest_help_q'] = round(by_help.loc['Q4 fastest help', 'FTR_rate_weighted'], 2)

    # Hospital-level predictive model: which hospitals have high failure-to-rescue rates?
    feats = ['SVI_overall', 'SVI_socioeconomic', 'SVI_household', 'SVI_minority', 'SVI_housing_transport', 'Pct_uninsured',
             'Pct_65plus', 'Pop_density', 'HPSA_designations', 'HPSA_max_score', 'Rural', 'Help_ASAP_score', 'Nurse_comm_score',
             'Staff_coordination_score', 'FTR_cases', 'Emergency', 'Gov', 'Nonprofit', 'Proprietary']
    f['Emergency'] = (f['Emergency Services'] == 'Yes').astype(int)
    f['Gov'] = f['Hospital Ownership'].str.startswith('Government', na=False).astype(int)
    f['Nonprofit'] = f['Hospital Ownership'].str.startswith('Voluntary', na=False).astype(int)
    f['Proprietary'] = (f['Hospital Ownership'] == 'Proprietary').astype(int)
    X, y, w = f[feats].astype(float), f['FTR_rate'], f['FTR_cases']
    kf = KFold(5, shuffle=True, random_state=SEED)
    preds = {
        'Mean baseline': np.full(len(y), np.nan),
        'Linear regression': cross_val_predict(make_pipeline(SimpleImputer(strategy='median'), StandardScaler(), LinearRegression()), X, y, cv=kf),
        'Gradient boosting': cross_val_predict(HistGradientBoostingRegressor(max_iter=300, learning_rate=0.03, max_depth=3, min_samples_leaf=40, random_state=SEED), X, y, cv=kf),
    }
    for tr, te in kf.split(X): preds['Mean baseline'][te] = y.iloc[tr].mean()
    mres = []
    for k, p in preds.items():
        top = y >= y.quantile(0.75)
        flagged = p >= np.quantile(p, 0.75)
        mres.append(dict(model=k, R2=r2_score(y, p), MAE=mean_absolute_error(y, p),
                         top_quartile_precision=(top[flagged]).mean() if flagged.any() else np.nan))
    mres = pd.DataFrame(mres); mres.to_csv(os.path.join(OUT, 'hospital_model_metrics.csv'), index=False); print(mres.round(3))
    gb = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.03, max_depth=3, min_samples_leaf=40, random_state=SEED).fit(X, y)
    pi = permutation_importance(gb, X, y, n_repeats=10, random_state=SEED)
    imp = pd.DataFrame({'feature': feats, 'importance': pi.importances_mean}).sort_values('importance', ascending=False)
    imp.to_csv(os.path.join(OUT, 'hospital_model_importance.csv'), index=False); print(imp.head(10).round(4))
    corr = f[feats + ['FTR_rate']].corr(method='spearman')['FTR_rate'].drop('FTR_rate').sort_values()
    corr.to_csv(os.path.join(OUT, 'hospital_spearman.csv')); print(corr.round(3))
    headline.update({f'model_{r.model}_R2': round(r.R2, 3) for r in mres.itertuples()})
    import json; json.dump(headline, open(os.path.join(OUT, 'headline_numbers.json'), 'w'), indent=2, default=str)
    print(headline)

    # county roll-up for the Tableau map
    cty = f.dropna(subset=['FIPS']).groupby(['FIPS', 'County', 'ST']).agg(
        hospitals=('Facility ID', 'size'), cases=('FTR_cases', 'sum'), excess_deaths_2yr=('Excess_deaths_vs_best_quartile', 'sum'),
        SVI_overall=('SVI_overall', 'first'), In_shortage_area=('In_shortage_area', 'max'), Help_ASAP_score=('Help_ASAP_score', 'mean')).reset_index()
    cty['FTR_rate_weighted'] = f.dropna(subset=['FIPS']).groupby('FIPS').apply(lambda g: np.average(g.FTR_rate, weights=g.FTR_cases), include_groups=False).reindex(cty.FIPS).values
    cty.to_csv(os.path.join(OUT, 'tableau_counties.csv'), index=False)


if __name__ == '__main__':
    main()
