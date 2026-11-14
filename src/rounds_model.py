"""Rounds: predict NEWS2-style risk from INCOMPLETE vitals and pick the next vital to measure.

Run:  python src/rounds_model.py        (from the repo root)
Outputs go to outputs/ (metrics tables, Tableau CSVs, figures).
"""
import itertools, json, os, sys
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import f1_score, recall_score, accuracy_score
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.dirname(__file__))
import news2

SEED = 42
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'outputs'); os.makedirs(OUT, exist_ok=True)
CLASSES = ['Normal', 'Low', 'Medium', 'High']
VITALS = ['Respiratory_Rate', 'Oxygen_Saturation', 'Systolic_BP', 'Heart_Rate', 'Temperature', 'Consciousness']
SHORT = {'Respiratory_Rate': 'RR', 'Oxygen_Saturation': 'SpO2', 'Systolic_BP': 'BP',
         'Heart_Rate': 'HR', 'Temperature': 'Temp', 'Consciousness': 'ACVPU'}
CONTEXT = ['O2_Scale', 'On_Oxygen']           # known from the chart without measuring anything
CONS_MAP = {'A': 0, 'C': 1, 'V': 2, 'P': 3, 'U': 4}


def load():
    d = pd.read_csv(os.path.join(ROOT, 'data/Health_Risk_Dataset.csv'))
    return d


def to_X(df):
    X = df[CONTEXT + VITALS].copy()
    X['Consciousness'] = X['Consciousness'].map(CONS_MAP)
    # clinically meaningful derived feature; NaN propagates when either input is missing
    X['Shock_Index'] = X['Heart_Rate'] / X['Systolic_BP']
    return X.astype(float)


def mask(df, keep):
    m = df.copy()
    for v in VITALS:
        if v not in keep:
            m[v] = np.nan
    return m


def augment(df, rng, copies=12, p_drop=0.45):
    """Train-time masking: every training patient is shown with random vitals missing,
    so one model learns to cope with any combination of missing measurements."""
    parts = [df]
    for _ in range(copies):
        m = df.copy()
        drop = rng.random((len(m), len(VITALS))) < p_drop
        for j, v in enumerate(VITALS):
            m.loc[drop[:, j], v] = np.nan
        parts.append(m)
    return pd.concat(parts, ignore_index=True)


def fit_rounds(train_df, rng):
    a = augment(train_df, rng)
    clf = HistGradientBoostingClassifier(max_iter=400, learning_rate=0.05, max_leaf_nodes=31,
                                         l2_regularization=1.0, random_state=SEED)
    clf.fit(to_X(a), a['Risk_Level'])
    return clf


def fit_logreg(train_df, rng):
    a = augment(train_df, rng)
    clf = make_pipeline(SimpleImputer(strategy='median', add_indicator=True), StandardScaler(),
                        LogisticRegression(max_iter=2000, C=1.0))
    clf.fit(to_X(a), a['Risk_Level'])
    return clf


def metrics(y, p):
    y = pd.Series(y).reset_index(drop=True); p = pd.Series(p).reset_index(drop=True)
    hi = y == 'High'
    return dict(
        accuracy=accuracy_score(y, p),
        macro_f1=f1_score(y, p, labels=CLASSES, average='macro', zero_division=0),
        high_recall=recall_score(y == 'High', p == 'High', zero_division=0),
        # the dangerous error: a truly High-risk patient labelled Low or Normal
        high_missed_as_low_or_normal=float(p[hi].isin(['Low', 'Normal']).mean()) if hi.any() else np.nan,
    )


def subsets():
    for k in range(1, len(VITALS) + 1):
        for s in itertools.combinations(VITALS, k):
            yield s


def main():
    d = load()
    rng = np.random.default_rng(SEED)
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
    rows, oof_full, rr18_rows = [], [], []
    majority = d['Risk_Level'].mode()[0]
    models = {}
    for fold, (tr, te) in enumerate(skf.split(d, d['Risk_Level'])):
        dtr, dte = d.iloc[tr], d.iloc[te]
        rounds = fit_rounds(dtr, rng); lr = fit_logreg(dtr, rng)
        models[fold] = rounds
        for s in subsets():
            m = mask(dte, s)
            preds = {
                'Majority class': [majority] * len(m),
                'NEWS2 (missing = normal)': news2.news2_risk(m),
                'Logistic regression': lr.predict(to_X(m)),
                'Rounds (gradient boosting)': rounds.predict(to_X(m)),
            }
            for name, p in preds.items():
                r = metrics(dte['Risk_Level'], p)
                r.update(model=name, fold=fold, n_vitals=len(s), vitals='+'.join(SHORT[v] for v in s))
                rows.append(r)
        # "guessed" respiratory rate: charted as 18 without counting (a documented real-world habit)
        g = dte.copy(); g['Respiratory_Rate'] = 18
        for name, p in {'NEWS2 with RR charted as 18': news2.news2_risk(g),
                        'Rounds with RR charted as 18': rounds.predict(to_X(g)),
                        'Rounds with RR left blank': rounds.predict(to_X(mask(dte, [v for v in VITALS if v != 'Respiratory_Rate']))),
                        'NEWS2 all vitals measured': news2.news2_risk(dte)}.items():
            r = metrics(dte['Risk_Level'], p); r.update(scenario=name, fold=fold); rr18_rows.append(r)
        pf = dte[['Patient_ID', 'Risk_Level']].copy()
        proba = rounds.predict_proba(to_X(dte))
        for i, c in enumerate(rounds.classes_): pf[f'P_{c}'] = proba[:, i]
        pf['Rounds_pred'] = rounds.classes_[proba.argmax(1)]; pf['fold'] = fold
        oof_full.append(pf)

    res = pd.DataFrame(rows)
    res.to_csv(os.path.join(OUT, 'metrics_by_vital_subset_fold.csv'), index=False)
    by_subset = res.groupby(['model', 'n_vitals', 'vitals'])[['accuracy', 'macro_f1', 'high_recall', 'high_missed_as_low_or_normal']].mean().reset_index()
    by_subset.to_csv(os.path.join(OUT, 'metrics_by_vital_subset.csv'), index=False)
    by_k = by_subset.groupby(['model', 'n_vitals'])[['accuracy', 'macro_f1', 'high_recall', 'high_missed_as_low_or_normal']].mean().reset_index()
    by_k.to_csv(os.path.join(OUT, 'metrics_by_number_of_vitals.csv'), index=False)
    rr18 = pd.DataFrame(rr18_rows).groupby('scenario')[['accuracy', 'macro_f1', 'high_recall', 'high_missed_as_low_or_normal']].mean().reset_index()
    rr18.to_csv(os.path.join(OUT, 'guessed_rr_experiment.csv'), index=False)
    oof = pd.concat(oof_full); oof.to_csv(os.path.join(OUT, 'oof_predictions_full_vitals.csv'), index=False)
    print(by_k.pivot(index='n_vitals', columns='model', values='high_recall').round(3))
    print(by_k.pivot(index='n_vitals', columns='model', values='macro_f1').round(3))
    print(rr18.round(3))
    best = by_subset[by_subset.model == 'Rounds (gradient boosting)'].sort_values('high_recall', ascending=False).groupby('n_vitals').head(1)
    print(best.round(3))


if __name__ == '__main__':
    main()
