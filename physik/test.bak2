from django.test import TestCase
from .models import Aufgabe, AufgabeOption
from .bewertung import bewerte_aufgabe


class MiniSmokeTest(TestCase):

    def setUp(self):
        self.a = Aufgabe.objects.create(
            lfd_nr="SMOKE1",
            themea_id=1,
            kapitel_id=1,
            schwierigkeit=1,
            typ="2",
            frage="Test",
            antwort="dunkle"
        )
        AufgabeOption.objects.create(
            aufgabe=self.a, position=1, text="helle"
        )

    def test_1_integer_equal_ok(self):
        # typ=2 → exakt (nach Normalisierung)
        r = bewerte_aufgabe(self.a, text_antwort="dunkle")
        self.assertTrue(r["richtig"])

    def test_2_integer_equal_fail(self):
        # darf NICHT enthalten sein
        r = bewerte_aufgabe(self.a, text_antwort="dunkle helle")
        self.assertFalse(r["richtig"])

    def test_3_parser_contain_ok(self):
        self.a.typ = "1o2"
        self.a.save()
        r = bewerte_aufgabe(self.a, text_antwort="dunkle helle")
        self.assertTrue(r["richtig"])

    def test_4_parser_nested(self):
        self.a.typ = "1o(2u3)"
        self.a.save()
        AufgabeOption.objects.create(
            aufgabe=self.a, position=2, text="graue"
        )
        r = bewerte_aufgabe(self.a, text_antwort="helle graue")
        self.assertTrue(r["richtig"])
