"""'What should I measure next?'  For a patient with some vitals recorded, Rounds looks at
similar past patients to guess what each missing vital could plausibly be, and picks the
measurement expected to remove the most uncertainty about the patient's risk level.

We test this policy against (a) a fixed checklist order and (b) random order, by asking:
after the nurse takes only k measurements, what share of truly High-risk patients are flagged?
"""
import os, sys
import numpy as np, pandas as pd
from sklearn.model_selection import StratifiedKFold
sys.path.insert(0, os.path.dirname(__file__))
from rounds_model import (load, fit_rounds, to_X, VITALS, SHORT, CONS_MAP, SEED, OUT)

K_NEIGHBOURS = 30


def entropy(p):
    return -(p * np.log(np.clip(p, 1e-12, 1))).sum(-1)


def numeric(df):
    x = df[VITALS].copy(); x['Consciousness'] = x['Consciousness'].map(CONS_MAP)
    return x.astype(float).to_numpy()


def choose_next(model, train, train_num, scale, patient, observed, rng):
    """Return the missing vital with the lowest expected entropy after measuring it."""
    missing = [v for v in VITALS if v not in observed]
    obs_idx = [VITALS.index(v) for v in observed]
    if obs_idx:
        pnum = numeric(patient.to_frame().T)[0]
        dist = (((train_num[:, obs_idx] - pnum[obs_idx]) / scale[obs_idx]) ** 2).sum(1)
        nb = np.argsort(dist)[:K_NEIGHBOURS]
    else:
        nb = rng.choice(len(train), K_NEIGHBOURS, replace=False)
    rows = []
    for v in missing:
        for i in nb:
            r = patient.copy()
            for u in VITALS:
                if u not in observed and u != v: r[u] = np.nan
            r[v] = train.iloc[i][v]
            rows.append(r)
    P = model.predict_proba(to_X(pd.DataFrame(rows))).reshape(len(missing), len(nb), -1)
    exp_ent = entropy(P).mean(1)
    return missing[int(np.argmin(exp_ent))]


def predict_with(model, patient, observed):
    r = patient.copy()
    for u in VITALS:
        if u not in observed: r[u] = np.nan
    return model.predict(to_X(r.to_frame().T))[0]


def main():
    d = load(); rng = np.random.default_rng(SEED)
    fixed_order = ['Respiratory_Rate', 'Oxygen_Saturation', 'Systolic_BP', 'Heart_Rate', 'Temperature', 'Consciousness']
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEED)
    rec = []; first_pick = []
    for fold, (tr, te) in enumerate(skf.split(d, d['Risk_Level'])):
        dtr, dte = d.iloc[tr].reset_index(drop=True), d.iloc[te].reset_index(drop=True)
        model = fit_rounds(dtr, rng)
        tnum = numeric(dtr); scale = tnum.std(0) + 1e-9
        for _, p in dte.iterrows():
            orders = {'Rounds picks next vital': [], 'Fixed checklist order': fixed_order,
                      'Random order': list(rng.permutation(VITALS))}
            obs = []
            for k in range(len(VITALS)):
                obs.append(choose_next(model, dtr, tnum, scale, p, obs, rng))
            orders['Rounds picks next vital'] = obs
            first_pick.append(dict(Patient_ID=p.Patient_ID, Risk_Level=p.Risk_Level,
                                   first=SHORT[obs[0]], second=SHORT[obs[1]], third=SHORT[obs[2]]))
            for name, order in orders.items():
                for k in range(1, 4):
                    rec.append(dict(policy=name, k=k, truth=p.Risk_Level,
                                    pred=predict_with(model, p, order[:k])))
        print('fold', fold, 'done', flush=True)
    r = pd.DataFrame(rec)
    r['high'] = r.truth == 'High'; r['flag'] = r.pred == 'High'; r['correct'] = r.truth == r.pred
    summ = r.groupby(['policy', 'k']).apply(lambda g: pd.Series({
        'high_recall': g[g.high].flag.mean(),
        'accuracy': g.correct.mean(),
        'high_missed_as_low_or_normal': g[g.high].pred.isin(['Low', 'Normal']).mean()}), include_groups=False).reset_index()
    summ.to_csv(os.path.join(OUT, 'next_vital_policy.csv'), index=False)
    pd.DataFrame(first_pick).to_csv(os.path.join(OUT, 'next_vital_choices.csv'), index=False)
    print(summ.round(3))
    print(pd.DataFrame(first_pick)[['first', 'second']].value_counts().head(10))


if __name__ == '__main__':
    main()
