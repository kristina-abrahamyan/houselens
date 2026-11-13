"""Offline source-contract tests: no live BoE access and no fake CPI fallback."""
import datetime as dt
import unittest
from urllib.error import HTTPError
from update import cpi_projections

SAMPLE = '''<!doctype html><html><head><meta property="article:published_time" content="2026-11-05T12:00:00+00:00"></head><body>
<h1>Monetary Policy Report - November 2026</h1><h2>Table 3.B: Summary of outputs of the central projection and scenarios</h2>
<table><tbody>
<tr><th> </th><th>2026 Q4</th><th>2027 Q4</th><th>2028 Q4</th><th>2029 Q4</th></tr>
<tr><td colspan="5">Central projection</td></tr>
<tr><td>CPI inflation <sup>(b)</sup></td><td>3.8 (3.2)</td><td>4.0 (2.1)</td><td>2.0 (1.9)</td><td>1.8</td></tr>
<tr><td>GDP</td><td>2.2</td><td>1.0</td><td>1.4</td><td>1.6</td></tr>
<tr><td colspan="5">Adverse inflation scenario</td></tr>
<tr><td>CPI inflation</td><td>4.0</td><td>5.5</td><td>3.0</td><td>2.2</td></tr>
</tbody></table></body></html>'''

class CPIProjectionTests(unittest.TestCase):
    def test_extracts_only_central_projection_without_old_values_in_parentheses(self):
        result=cpi_projections.parse_cpi_report(SAMPLE, 'https://example.org/boe-report')
        self.assertEqual(result['asOf'],'2026-11-05')
        self.assertEqual([p['rate'] for p in result['series']],[3.8,4.0,2.0,1.8])
        self.assertEqual(result['series'][1]['quarter'],'2027 Q4')
        self.assertIn('four-quarter CPI',result['measure'])

    def test_rejects_unlabelled_or_unverifiable_projections(self):
        with self.assertRaises(ValueError):
            cpi_projections.parse_cpi_report('<html>Inflation will be about 5%</html>','https://example.org')
        with self.assertRaises(ValueError):
            cpi_projections.parse_cpi_report(SAMPLE.replace('Central projection','Unspecified'), 'https://example.org')
        with self.assertRaises(ValueError):
            cpi_projections.parse_cpi_report(SAMPLE.replace('2026-11-05T12:00:00+00:00','missing'), 'https://example.org')

    def test_discovers_newest_available_report_without_hardcoded_2026(self):
        urls=[]
        def fake(url, **kwargs):
            urls.append(url)
            if url.endswith('/2027/february-2027'):
                return SAMPLE.replace('2026-11-05','2027-02-04').replace('2026 Q4','2027 Q4').replace('2027 Q4</th><th>2028','2028 Q4</th><th>2028')
            raise HTTPError(url,404,'Not Found',{},None)
        result=cpi_projections.get_cpi_projection(fake,today=dt.date(2027,2,10))
        self.assertEqual(result['asOf'],'2027-02-04')
        self.assertTrue(urls[0].endswith('/2027/february-2027'))

    def test_2027_march_reuses_newest_official_report(self):
        def fake(url,**kwargs):
            if url.endswith('/2027/february-2027'):
                return SAMPLE.replace('2026-11-05','2027-02-04').replace('2026 Q4','2027 Q4')
            raise HTTPError(url,404,'Not Found',{},None)
        result=cpi_projections.get_cpi_projection(fake,today=dt.date(2027,3,12))
        self.assertEqual(result['asOf'],'2027-02-04')

    def test_stale_or_invalid_data_are_rejected_not_made_up(self):
        def only_last_year(url, **kwargs):
            if '/2026/november-2026' in url:return SAMPLE
            raise HTTPError(url,404,'Not Found',{},None)
        with self.assertRaisesRegex(ValueError,'No validated recent'):
            cpi_projections.get_cpi_projection(only_last_year,today=dt.date(2027,9,1))

if __name__=='__main__':unittest.main()

class CPIReportedPeakTests(unittest.TestCase):
    def test_midyear_peak_comes_from_visible_narrative_not_q4(self):
        narrative = ('<p>CPI inflation increased to 3.5% in September. '
                     'It is now expected to rise to around 5% by the middle of next year.</p>')
        doc = SAMPLE.replace('<h1>Monetary Policy Report - November 2026</h1>',
                             '<h1>Monetary Policy Report - November 2026</h1>' + narrative)
        projection = cpi_projections.parse_cpi_report(doc, 'https://www.bankofengland.co.uk/example')
        self.assertEqual(projection['peakGuidance']['rate'], 5.0)
        self.assertEqual(projection['peakGuidance']['period'], 'mid-2027')
        self.assertEqual(projection['series'][1]['rate'], 4.0)
