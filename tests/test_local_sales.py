"""Synthetic regression fixtures, not published house-price observations."""
import datetime as dt
import io
import unittest

from update import local_sales


def sale(uid, year, price, postcode='CM12 0AA', ptype='S', month=4):
    """The exact 16-column HM Land Registry yearly CSV position order."""
    return [uid, str(price), f'{year}-{month:02d}-15 00:00', postcode,
            ptype, 'N', 'F', '10', '', 'TEST STREET', '', 'BILLERICAY',
            'BASILDON', 'ESSEX', 'A', 'A']


def records(year):
    return [dict(id=f'{year}-{n}', date=f'{year}-04-15',
                 price=(500000 if year == 2025 else 550000),
                 type='S', sector='CM12 0') for n in range(20)]


class OfficialLocalSalesTests(unittest.TestCase):
    def test_ppd_parser_excludes_flats_other_areas_nonstandard_and_bad_prices(self):
        rows = [sale('1', 2026, 500000), sale('2', 2026, 490000, ptype='D'),
                sale('3', 2026, 450000, ptype='T'),
                sale('4', 2026, 450000, postcode='CM13 1AA'),
                sale('5', 2026, 480000, ptype='F'),
                sale('6', 2026, 80000000),
                sale('7', 2025, 510000)]
        abnormal = sale('8', 2026, 500000)
        abnormal[14] = 'B'
        rows.append(abnormal)
        found = local_sales.parse_ppd_rows(rows, 2026)
        self.assertEqual({r['id'] for r in found}, {'1', '2', '3'})
        self.assertEqual({r['type'] for r in found}, {'S', 'D', 'T'})

    def test_download_parser_uses_official_no_header_csv(self):
        raw = ','.join(f'"{x}"' for x in sale('a', 2026, 525000)).encode()

        def fake_open(req, timeout):
            return io.BytesIO(raw)

        result = local_sales.fetch_year(2026, opener=fake_open)
        self.assertEqual(result[0]['price'], 525000)
        self.assertEqual(result[0]['sector'], 'CM12 0')

    def test_2027_retains_2025_comparison_without_spreadsheet(self):
        today = dt.date(2027, 1, 15)
        self.assertEqual(local_sales.required_years(today), (2025, 2026))
        calls = []

        def offline_fetch(year):
            calls.append(year)
            return records(year)

        first = local_sales.update_local_sales({}, today=today, fetcher=offline_fetch)
        self.assertEqual(calls, [2025, 2026])
        self.assertEqual(first['summary']['scope'], 'CM12 0 postcode sector')
        self.assertAlmostEqual(first['summary']['annualChange'], 10)
        self.assertEqual(first['summary']['count'], 20)
        self.assertIn('2025', first['dataset']['byYear'])
        self.assertNotIn('2027', first['dataset']['byYear'])

        calls.clear()
        second = local_sales.update_local_sales(first['dataset'], today=dt.date(2027, 1, 20), fetcher=offline_fetch)
        self.assertEqual(calls, [])
        self.assertAlmostEqual(second['summary']['annualChange'], 10)

    def test_2027_later_fetches_current_2027_automatically(self):
        self.assertEqual(local_sales.required_years(dt.date(2027, 11, 11)), (2026, 2027))

    def test_no_sales_does_not_make_up_market_trend(self):
        with self.assertRaisesRegex(ValueError, 'Not enough'):
            local_sales.summarise([], dt.date(2026, 11, 11))

    def test_broader_cm12_fallback_is_explicit(self):
        mixed = []
        for y, base in [(2025, 500000), (2026, 510000)]:
            for i in range(24):
                mixed.append({'id': f'{y}-{i}', 'date': f'{y}-04-15',
                              'price': base, 'type': 'S', 'sector': 'CM12 9'})
        result = local_sales.summarise(mixed, dt.date(2026, 11, 11))
        self.assertEqual(result['scope'], 'CM12 postcode district')
        self.assertEqual(result['count'], 24)


if __name__ == '__main__':
    unittest.main()
