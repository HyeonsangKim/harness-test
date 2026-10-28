import unittest

from calc import average, parse_amount, total_by_team


class CalcTest(unittest.TestCase):
    def test_parse_amount(self):
        self.assertEqual(parse_amount("1,234원"), 1234)
        self.assertEqual(parse_amount("₩5,000"), 5000)
        self.assertEqual(parse_amount(" 300 "), 300)

    def test_average(self):
        self.assertEqual(average([1, 2]), 1.5)
        self.assertEqual(average([]), 0)

    def test_total_by_team(self):
        rows = [("영업", "1,000원"), ("개발", "500원"), ("영업", "2,000원")]
        self.assertEqual(total_by_team(rows), {"영업": 3000, "개발": 500})


if __name__ == "__main__":
    unittest.main()
