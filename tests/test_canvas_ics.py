import unittest
from app.ics import parse_ics, parse_dt, ext_id

SAMPLE = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Instructure//Canvas//EN
BEGIN:VEVENT
DTSTART:20260614T035900Z
DTEND:20260614T035900Z
UID:event-assignment-987654@psu.instructure.com
SUMMARY:Quiz 1 [CMPEN 331, Section 001: Comp Org and Design]
URL:https://psu.instructure.com/courses/1/assignments/987654
END:VEVENT
BEGIN:VEVENT
DTSTART;TZID=America/New_York:20260613T235900
UID:event-assignment-111@psu.instructure.com
SUMMARY:Homework 3 with a very long title that Canvas will fold across two li
 nes in the feed output
END:VEVENT
BEGIN:VEVENT
DTSTART;VALUE=DATE:20260620
UID:event-calendar-event-555@psu.instructure.com
SUMMARY:Holiday
END:VEVENT
END:VCALENDAR"""


class IcsTests(unittest.TestCase):
    def setUp(self):
        self.ev = parse_ics(SAMPLE)

    def test_event_count(self):
        self.assertEqual(len(self.ev), 3)

    def test_utc_datetime(self):
        self.assertEqual(self.ev[0]["dtstart"].hour, 3)
        self.assertEqual(self.ev[0]["dtstart"].minute, 59)

    def test_tzid_converted_to_utc(self):
        # 23:59 America/New_York (EDT, -4) -> 03:59 UTC next day
        dt = self.ev[1]["dtstart"]
        self.assertEqual(dt.tzinfo.key, "UTC")
        self.assertEqual((dt.hour, dt.day), (3, 14))

    def test_line_unfolding(self):
        self.assertIn("two lines", self.ev[1]["summary"])
        self.assertNotIn("\n", self.ev[1]["summary"])

    def test_assignment_ext_id_dedups_with_token_sync(self):
        # must equal the token-sync external_id form so rows merge, not double
        self.assertEqual(ext_id(self.ev[0]), "canvas:987654")
        self.assertEqual(ext_id(self.ev[1]), "canvas:111")

    def test_non_assignment_falls_back(self):
        self.assertTrue(ext_id(self.ev[2]).startswith("canvas-ics:"))

    def test_date_only_value(self):
        self.assertEqual(self.ev[2]["dtstart"].strftime("%Y%m%d"), "20260620")

    def test_webcal_and_bad_values(self):
        self.assertIsNone(parse_dt(""))
        self.assertIsNone(parse_dt("DTSTART:not-a-date"))


if __name__ == "__main__":
    unittest.main()
