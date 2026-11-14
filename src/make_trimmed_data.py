"""Trim the big public CMS/HRSA downloads to only the rows and columns the notebook uses,
so every input fits in the GitHub repo (<100 MB per file). Run once on the raw downloads."""
import sys, pandas as pd
raw, out = sys.argv[1], sys.argv[2]
c = pd.read_csv(f'{raw}/Complications_and_Deaths-Hospital.csv', dtype=str)
c[c['Measure ID'] == 'ISCMR'].to_csv(f'{out}/Complications_and_Deaths-Hospital.csv', index=False)
h = pd.read_csv(f'{raw}/HCAHPS-Hospital.csv', dtype=str, usecols=['Facility ID', 'HCAHPS Measure ID', 'HCAHPS Linear Mean Value'])
h[h['HCAHPS Measure ID'].isin(['H_COMP_3_LINEAR_SCORE', 'H_COMP_1_LINEAR_SCORE', 'H_COMP_9_LINEAR_SCORE'])].to_csv(f'{out}/HCAHPS-Hospital.csv', index=False)
p = pd.read_csv(f'{raw}/BCD_HPSA_FCT_DET_PC.csv', dtype=str, usecols=['HPSA Status', 'Designation Type', 'HPSA Score', 'Rural Status',
                'State and County Federal Information Processing Standard Code'])
p.to_csv(f'{out}/BCD_HPSA_FCT_DET_PC.csv', index=False)
for f in ['Health_Risk_Dataset.csv', 'Hospital_General_Information.csv', 'SVI_2022_US_COUNTY.csv']:
    open(f'{out}/{f}', 'wb').write(open(f'{raw}/{f}', 'rb').read())
