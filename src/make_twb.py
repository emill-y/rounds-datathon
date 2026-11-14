"""Write tableau/Rounds_dashboards_v3.twb, a Tableau workbook wired to the CSVs in tableau/.
Open it in Tableau Desktop/Public; if it asks where the CSVs are, point it at the tableau/ folder."""
import os, uuid, csv
from xml.sax.saxutils import quoteattr as qa, escape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAB = os.path.join(ROOT, 'tableau')

GEO = {'State': '[State].[Name]', 'ZIP': '[ZipCode].[Name]'}
STRING_COLS = {'ZIP', 'FIPS', 'Facility ID', 'Bed', 'Patient', 'Dataset_ID'}


def infer(path):
    rows = list(csv.reader(open(path, encoding='utf-8')))
    head, body = rows[0], rows[1:]
    types = {}
    for i, h in enumerate(head):
        vals = [r[i] for r in body if i < len(r) and r[i] != '']
        t = 'integer'
        for v in vals:
            try:
                float(v)
                if t == 'integer' and not v.lstrip('-').isdigit(): t = 'real'
            except ValueError:
                t = 'string'; break
        if h in STRING_COLS: t = 'string'
        types[h] = t
    return head, types


class DS:
    def __init__(self, key, file, calcs=None):
        self.key, self.file = key, file
        self.name = f'federated.{key}'
        self.caption = file.replace('.csv', '')
        self.head, self.types = infer(os.path.join(TAB, file))
        self.calcs = calcs or {}          # caption -> (internal name, datatype, role, formula)

    def col_xml(self, h):
        t = self.types[h]
        role = 'measure' if t in ('integer', 'real') and h not in ('Priority_rank', 'missing_pct', 'Missing_count', 'Vital_order') else 'dimension'
        typ = 'quantitative' if role == 'measure' else ('ordinal' if t != 'string' else 'nominal')
        geo = f' semantic-role={qa(GEO[h])}' if h in GEO else ''
        return f'<column datatype={qa(t)} name={qa("[" + h + "]")} role={qa(role)} type={qa(typ)}{geo} />'

    def xml(self):
        cols = ''.join(f'<column datatype={qa(self.types[h])} name={qa(h)} ordinal={qa(str(i))} />' for i, h in enumerate(self.head))
        table = f'[{self.caption}#csv]'
        calcs = ''.join(
            f'<column caption={qa(cap)} datatype={qa(dt)} name={qa(nm)} role={qa(role)} type={qa("quantitative" if role == "measure" else "nominal")}>'
            f'<calculation class="tableau" formula={qa(f)} /></column>' for cap, (nm, dt, role, f) in self.calcs.items())
        return (f'<datasource caption={qa(self.caption)} inline="true" name={qa(self.name)} version="18.1">'
                f'<connection class="federated"><named-connections>'
                f'<named-connection caption={qa(self.caption)} name={qa("textscan." + self.key)}>'
                f'<connection class="textscan" directory="." filename={qa(self.file)} password="" server="" />'
                f'</named-connection></named-connections>'
                f'<relation connection={qa("textscan." + self.key)} name={qa(self.file)} table={qa(table)} type="table">'
                f'<columns character-set="UTF-8" header="yes" locale="en_US" separator=",">{cols}</columns></relation>'
                f'</connection>'
                + ''.join(self.col_xml(h) for h in self.head) + calcs +
                '</datasource>')


def inst(ds, col, deriv='None', kind=None):
    """column-instance name, e.g. [none:Bed:nk] / [sum:recall:qk]"""
    t = ds.types.get(col)
    if kind is None:
        kind = 'nk' if (t == 'string' or deriv == 'None' and col in ('Priority_rank',)) else 'qk'
    pre = {'None': 'none', 'Sum': 'sum', 'Avg': 'avg', 'CountD': 'ctd'}[deriv]
    return f'[{pre}:{col}:{kind}]'


class Sheet:
    def __init__(self, name, ds, mark, rows=(), cols=(), color=None, text=None, size=None, detail=(), tooltip=(),
                 filt=None, rows_raw=None, cols_raw=None):
        self.__dict__.update(locals())

    def xml(self):
        ds = self.ds
        used = {}  # instance name -> (column, derivation, type)
        def use(spec):
            col, deriv, kind = spec if len(spec) == 3 else (*spec, None)
            name = inst(ds, col, deriv, kind)
            typ = {'nk': 'nominal', 'ok': 'ordinal', 'qk': 'quantitative'}[name.split(':')[-1][:-1]]
            used[name] = (col, deriv, typ)
            return f'[{ds.name}].{name}'
        rows = ' / '.join(use(r) for r in self.rows) if self.rows else (self.rows_raw or '')
        cols = ' / '.join(use(c) for c in self.cols) if self.cols else (self.cols_raw or '')
        enc = ''
        if self.color: enc += f'<color column={qa(use(self.color))} />'
        if self.size: enc += f'<size column={qa(use(self.size))} />'
        if self.text: enc += f'<text column={qa(use(self.text))} />'
        for d in self.detail: enc += f'<lod column={qa(use(d))} />'
        for t in self.tooltip: enc += f'<tooltip column={qa(use(t))} />'
        filt = ''
        if self.filt:
            col, member = self.filt
            fq = use((col, 'None'))
            lvl = fq[len('[' + ds.name + '].'):]
            filt = (f'<filter class="categorical" column={qa(fq)}><groupfilter function="member" level={qa(lvl)} '
                    f'member={qa(chr(34) + member + chr(34))} user:ui-domain="database" user:ui-enumeration="inclusive" '
                    f'user:ui-marker="enumerate" /></filter><slices><column>{escape(fq)}</column></slices>')
        deps = set(c for c, _, _ in used.values())
        geo_extra = ''
        if self.rows_raw:
            geo_extra = ('<column aggregation="Avg" caption="Latitude (generated)" datatype="real" default-type="quantitative" '
                         'name="[Latitude (generated)]" pivot="key" role="measure" type="quantitative" user-datatype="real" visual-totals="Default" />'
                         '<column aggregation="Avg" caption="Longitude (generated)" datatype="real" default-type="quantitative" '
                         'name="[Longitude (generated)]" pivot="key" role="measure" type="quantitative" user-datatype="real" visual-totals="Default" />')
        dep_cols = ''
        for c in sorted(deps):
            if c in ds.head: dep_cols += ds.col_xml(c)
            else:
                cap = next(k for k, v in ds.calcs.items() if v[0] == c)
                nm, dt, role, f = ds.calcs[cap]
                dep_cols += (f'<column caption={qa(cap)} datatype={qa(dt)} name={qa(nm)} role={qa(role)} type="quantitative">'
                             f'<calculation class="tableau" formula={qa(f)} /></column>')
        dep_inst = ''.join(f'<column-instance column={qa(c if c.startswith("[") else "[" + c + "]")} derivation={qa(d)} '
                           f'name={qa(n)} pivot="key" type={qa(t)} />' for n, (c, d, t) in used.items())
        return (f'<worksheet name={qa(self.name)}><table><view>'
                f'<datasources><datasource caption={qa(ds.caption)} name={qa(ds.name)} /></datasources>'
                f'<datasource-dependencies datasource={qa(ds.name)}>{geo_extra}{dep_cols}{dep_inst}</datasource-dependencies>'
                f'{filt}<aggregation value="true" /></view><style />'
                f'<panes><pane selection-relaxation-option="selection-relaxation-allow"><view><breakdown value="auto" /></view>'
                f'<mark class={qa(self.mark)} /><encodings>{enc}</encodings></pane></panes>'
                f'<rows>{escape(rows)}</rows><cols>{escape(cols)}</cols></table></worksheet>')


def dashboard(name, title, layout):
    """layout: list of rows; each row = list of sheet names, laid out side by side."""
    zid = [3]
    def nid(): zid[0] += 1; return str(zid[0])
    h_row = 92000 // len(layout)
    inner = ''
    for r, row in enumerate(layout):
        w = 100000 // len(row)
        for c, sheet in enumerate(row):
            inner += (f'<zone h={qa(str(h_row))} id={qa(nid())} name={qa(sheet)} w={qa(str(w))} '
                      f'x={qa(str(c * w))} y={qa(str(8000 + r * h_row))} />')
    return (f'<dashboard name={qa(name)}><style /><size maxheight="900" maxwidth="1400" minheight="900" minwidth="1400" />'
            f'<zones><zone h="100000" id="1" type-v2="layout-basic" w="100000" x="0" y="0">'
            f'<zone h="8000" id="2" type-v2="title" w="100000" x="0" y="0" />'
            f'{inner}</zone></zones></dashboard>')


def main():
    d1 = DS('d1prio', 'd1_patient_priority.csv')
    d2 = DS('d2curves', 'd2_missingness_curves.csv')
    d3s = DS('d3states', 'd3_states.csv')
    d3h = DS('d3hosp', 'd3_hospitals.csv', calcs={
        'Worse than national (share)': ('[Calc_Worse]', 'real', 'measure',
                                        'AVG(IIF([FTR_vs_national] = "Worse Than the National Rate", 1, 0))')})
    sheets = [
        Sheet('Priority list', d1, 'Square',
              rows=[('Priority_rank', 'None', 'ok'), ('Bed', 'None'), ('Patient', 'None'), ('Rounds_risk', 'None'),
                    ('NEWS2_risk_today', 'None'), ('Missing_vitals', 'None'), ('Next_measurement', 'None')],
              color=('Rounds_risk', 'None'), text=('P_High', 'Sum')),
        Sheet('Recall vs missing', d2, 'Line', rows=[('recall', 'Avg')], cols=[('missing_pct', 'None', 'qk')],
              color=('method', 'None'), filt=('alert_rule', 'Top 28% alerted')),
        Sheet('Precision vs missing', d2, 'Line', rows=[('precision', 'Avg')], cols=[('missing_pct', 'None', 'qk')],
              color=('method', 'None'), filt=('alert_rule', 'Top 28% alerted')),
        Sheet('False alerts vs missing', d2, 'Line', rows=[('false_alerts_per_100', 'Avg')], cols=[('missing_pct', 'None', 'qk')],
              color=('method', 'None'), filt=('alert_rule', 'Top 28% alerted')),
        Sheet('Excess deaths by state', d3s, 'Multipolygon', rows_raw=f'[{d3s.name}].[Latitude (generated)]',
              cols_raw=f'[{d3s.name}].[Longitude (generated)]', detail=[('State', 'None')],
              color=('excess_deaths_per_year', 'Sum'), tooltip=[('FTR_rate_weighted', 'Sum'), ('hospitals', 'Sum')]),
        Sheet('Hospitals', d3h, 'Circle', rows_raw=f'[{d3h.name}].[Latitude (generated)]',
              cols_raw=f'[{d3h.name}].[Longitude (generated)]', detail=[('ZIP', 'None'), ('Hospital', 'None')],
              color=('FTR_rate', 'Avg'), size=('FTR_cases', 'Sum'), tooltip=[('FTR_vs_national', 'None')]),
        Sheet('By community vulnerability', d3h, 'Bar', cols=[('SVI_quartile', 'None')],
              rows_raw=f'[{d3h.name}].[usr:Calc_Worse:qk]'),
        Sheet('By response time', d3h, 'Bar', cols=[('Help_quartile', 'None')],
              rows_raw=f'[{d3h.name}].[usr:Calc_Worse:qk]'),
    ]
    # the two bar sheets use a user calc on rows; register it as a dependency
    xml_sheets = []
    for s in sheets:
        x = s.xml()
        if 'usr:Calc_Worse' in (s.rows_raw or ''):
            x = x.replace('<datasource-dependencies datasource="federated.d3hosp">',
                          '<datasource-dependencies datasource="federated.d3hosp">'
                          '<column caption="Worse than national (share)" datatype="real" name="[Calc_Worse]" role="measure" type="quantitative">'
                          '<calculation class="tableau" formula="AVG(IIF([FTR_vs_national] = &quot;Worse Than the National Rate&quot;, 1, 0))" /></column>'
                          '<column-instance column="[Calc_Worse]" derivation="User" name="[usr:Calc_Worse:qk]" pivot="key" type="quantitative" />', 1)
            x = x.replace('<geo', '<geo')  # no-op
            # bar sheets are not maps: drop the generated lat/long columns
            x = x.replace(x[x.find('<column aggregation="Avg" caption="Latitude'):x.find('<column datatype=', x.find('<column aggregation="Avg" caption="Longitude'))], '', 1) \
                if 'Latitude (generated)' in x else x
        xml_sheets.append(x)
    dashes = [
        dashboard('1 Patient Priority', 'Rounds: who to check first', [['Priority list']]),
        dashboard('2 NEWS2 vs Rounds', 'NEWS2 vs Rounds as vitals go missing',
                  [['Recall vs missing', 'Precision vs missing', 'False alerts vs missing']]),
        dashboard('3 Failure-to-Rescue Map', 'National failure-to-rescue (CMS ISCMR)',
                  [['Excess deaths by state', 'Hospitals'], ['By community vulnerability', 'By response time']]),
    ]
    CARDS = '<cards><edge name="left"><strip size="160"><card type="pages" /><card type="filters" /><card type="marks" /></strip></edge><edge name="top"><strip size="2147483647"><card type="columns" /></strip><strip size="2147483647"><card type="rows" /></strip><strip size="31"><card type="title" /></strip></edge></cards>'
    windows = ''.join(f'<window class="worksheet" name={qa(s.name)}>{CARDS}</window>' for s in sheets) + \
              ''.join(f'<window class="dashboard" name={qa(n)}><cards /></window>' for n in ['1 Patient Priority', '2 NEWS2 vs Rounds', '3 Failure-to-Rescue Map'])
    twb = ("<?xml version='1.0' encoding='utf-8' ?>\n"
           "<workbook original-version='18.1' source-build='2023.3.0 (20233.23.1017.0948)' source-platform='win' version='18.1' "
           "xmlns:user='http://www.tableausoftware.com/xml/user'>"
           "<preferences><preference name='ui.encoding.shelf.height' value='24' /></preferences>"
           '<datasources>' + ''.join(d.xml() for d in [d1, d2, d3s, d3h]) + '</datasources>'
           '<worksheets>' + ''.join(xml_sheets) + '</worksheets>'
           '<dashboards>' + ''.join(dashes) + '</dashboards>'
           '<windows>' + windows + '</windows></workbook>')
    out = os.path.join(TAB, 'Rounds_dashboards_v3.twb')
    open(out, 'w', encoding='utf-8').write(twb)
    print('wrote', out)


if __name__ == '__main__':
    main()
