import datetime as dt
import io
import json
import os
import unittest
import zipfile
from unittest.mock import patch
from openpyxl import Workbook

from update import feeds
from update.main import refresh


class ParsingTests(unittest.TestCase):
    def test_boe_daily_and_change_points(self):
        data = b'DATE,IUDBEDR\n01 Nov 2026,3.75\n05 Nov 2026,4\n06 Nov 2026,4\n'
        result = feeds.get_bank_rate(lambda url: data)
        self.assertEqual(result['rate'], 4)
        self.assertEqual(result['asOf'], '2026-11-06')
        self.assertEqual(len(result['history']), 2)

    def test_location_filter_and_property_type(self):
        lat, lng = feeds.STATION
        payload = {'status':'success','data':{'raw_data':[
            {'address':'A', 'price':525000,'bedrooms':3,'lat':lat,'lng':lng,'type':'semi-detached house'},
            {'address':'B', 'price':500000,'bedrooms':4,'lat':lat,'lng':lng,'type':'End of terrace'},
            {'address':'C', 'price':505000,'bedrooms':4,'lat':lat,'lng':lng,'type':'terraced_house'},
            {'address':'D', 'price':580000,'bedrooms':4,'lat':lat+.03,'lng':lng,'type':'detached house'},
            {'address':'E', 'price':610000,'bedrooms':4,'lat':lat,'lng':lng,'type':'detached house'},
            {'address':'F', 'price':570000,'bedrooms':2,'lat':lat,'lng':lng,'type':'detached house'},
        ]}}
        cleaned = feeds.parse_propertydata(payload)
        self.assertEqual(len(cleaned['listings']), 2)
        self.assertEqual({p['type'] for p in cleaned['listings']},{'Semi-detached','End of terrace'})

    def test_hpi_locality_not_national(self):
        payload = b'Date,Region_Name,Area_Code,Average_Price,Monthly_Change,Annual_Change\n2026-08-01,Basildon,E07000066,420500,0.3,1.2\n2026-08-01,United Kingdom,K02000001,273000,0.1,0.6\n'
        hpi = feeds.parse_hpi_csv(payload, 'official')
        self.assertEqual(hpi['averagePrice'], 420500)
        self.assertEqual(hpi['annualChange'], 1.2)
        self.assertEqual(hpi['area'],'Basildon local authority')

    def test_yield_curve_zip_parsing(self):
        out = io.BytesIO()
        def book(sheet):
            wb = Workbook()
            ws = wb.active
            ws.title = sheet
            ws.append(['title'])
            ws.append(['description'])
            ws.append(['years'])
            ws.append(['Date',.08333333,.16666667,.25,.5,1,2])
            ws.append(['units'])
            ws.append([dt.datetime(2026,11,9), 3.6,3.65,3.7,3.75,3.8,4.2])
            buf=io.BytesIO()
            wb.save(buf)
            return buf.getvalue()
        with zipfile.ZipFile(out, 'w') as z:
            z.writestr('OIS daily.xlsx',book('1. fwds, short end'))
            z.writestr('GLC Inflation daily.xlsx',book('4. spot curve'))
        date, curve=feeds.parse_curve_zip(out.getvalue(),'OIS',r'fwds?,?\s*short end$')
        self.assertEqual(date,'2026-11-09')
        self.assertAlmostEqual(curve[3],3.7)
        def loader(url,**kwargs): return out.getvalue()
        curves=feeds.get_market_curves(4,3.95,fetch=loader)
        self.assertEqual([x['months'] for x in curves['ois']['forecast']],[3,6,12])
        self.assertAlmostEqual(curves['ois']['forecast'][0]['rate'],3.75)
        self.assertAlmostEqual(curves['gilts']['rpiBreakeven'],3.8)

    def test_boe_short_end_months_row_precedes_years_row(self):
        # Actual BoE layout: month numbers followed by fractional YEAR values.
        # A parser selecting the first numeric header would turn 1m into 12m.
        buff = io.BytesIO()
        wb = Workbook()
        ws = wb.active
        ws.title = '1. fwds, short end'
        ws.append(['Bank of England'])
        ws.append(['Interest rate forwards'])
        ws.append(['months:', 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])
        ws.append(['years:'] + [m / 12 for m in range(1, 13)])
        ws.append(['units: percent'])
        ws.append([dt.datetime(2026, 11, 10)] + [4.0 + m / 100 for m in range(1, 13)])
        excel = io.BytesIO()
        wb.save(excel)
        with zipfile.ZipFile(buff, 'w') as archive:
            archive.writestr('OIS daily data current month.xlsx', excel.getvalue())
        date, curve = feeds.parse_curve_zip(
            buff.getvalue(), 'OIS', r'fwds?,?\s*short end$',
            required_months=(3, 6, 12))
        self.assertEqual(date, '2026-11-10')
        self.assertAlmostEqual(curve[3], 4.03)
        self.assertAlmostEqual(curve[6], 4.06)
        self.assertAlmostEqual(curve[12], 4.12)

    def test_ois_uses_recent_complete_observation_without_extrapolating(self):
        def make_zip(latest, earlier):
            output = io.BytesIO()
            wb = Workbook()
            ws = wb.active
            ws.title = '1. fwds, short end'
            ws.append(['header'])
            ws.append(['header'])
            ws.append(['header'])
            ws.append(['Date', 1/12, 2/12, 3/12, 4/12, 5/12, 6/12, 7/12, 12/12, 13/12])
            ws.append(['units'])
            ws.append([dt.datetime(2026, 11, 9)] + earlier)
            ws.append([dt.datetime(2026, 11, 10)] + latest)
            content = io.BytesIO()
            wb.save(content)
            with zipfile.ZipFile(output, 'w') as z:
                z.writestr('OIS daily.xlsx', content.getvalue())
            return output.getvalue()

        # Latest row has no data at the required 3m and 6m tenors but has
        # adjacent points to interpolate; the published 12m point is present.
        missing = [3.8, 3.75, None, 3.70, 3.69, None, 3.60, 3.58, 3.55]
        complete = [3.9, 3.85, 3.82, 3.78, 3.76, 3.73, 3.66, 3.65, 3.64]
        date, curve = feeds.parse_curve_zip(make_zip(missing, complete), 'OIS',
                 r'fwds?,?\s*short end$', required_months=(3,6,12))
        self.assertEqual(date, '2026-11-10')
        self.assertAlmostEqual(curve[3], 3.725)
        self.assertAlmostEqual(curve[6], 3.69 + (3.6 - 3.69)/2)
        self.assertAlmostEqual(curve[12], 3.58)

        # No next point means no extrapolation. Fall back to a dated complete
        # observation if within seven days of the latest.
        missing_far = [3.8, 3.75, None, None, None, None, None, None, None]
        date, curve = feeds.parse_curve_zip(make_zip(missing_far, complete), 'OIS',
                 r'fwds?,?\s*short end$', required_months=(3,6,12))
        self.assertEqual(date, '2026-11-09')
        self.assertEqual(curve[12], 3.65)

    def test_refresh_retains_failure_as_warning_not_fabricated(self):
        class Adapters:
            @staticmethod
            def get_bank_rate():
                return {'rate':4.0,'asOf':'2026-11-09','history':[{'date':'2026-11-05','rate':4.0}], 'sourceUrl':'https://official'}
            @staticmethod
            def get_sonia(): raise ValueError('source unavailable')
            @staticmethod
            def get_guidance(): raise ValueError('source unavailable')
            @staticmethod
            def get_hpi(): raise ValueError('source unavailable')
        state={'bankRate':3.75,'listings':[], 'snapshots':[], 'sources':{},'ois':{'forecast':[]},'gilts':{}}
        with patch.dict(os.environ,{'PROPERTYDATA_API_KEY':''}):
            after=refresh(state,now=dt.datetime(2026,11,11,tzinfo=dt.timezone.utc),adapters=Adapters)
        self.assertEqual(after['bankRate'],4)
        self.assertEqual(after['status'],'PARTIAL')
        self.assertEqual(after['ois']['forecast'],[])
        self.assertGreaterEqual(len(after['errors']),3)


if __name__ == '__main__':
    unittest.main()
