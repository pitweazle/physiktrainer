from django.test import TestCase
from physik.bewertung import bewerte_aufgabe
from .bewertung import bewerte_aufgabe
from .models import Aufgabe, AufgabeOption

class ETypTests(TestCase):

    def setUp(self):
        # ---- Aufgabe W042 nachbauen ----
        self.a = Aufgabe.objects.create(
            lfd_nr="W042",
            themea_id=5,                      # Dummy-Thema
            kapitel_id=1,                   # Dummy-Kapitel
            schwierigkeit=1,
            typ="2o3e4o6",
            frage="... Flächen nehmen mehr Strahlung auf als ... Flächen.",
            antwort="Dunkle … helle"
        )

        # Optionen (Spalten 2–6)
        AufgabeOption.objects.create(aufgabe=self.a, position=1, text="dunkle")
        AufgabeOption.objects.create(aufgabe=self.a, position=2, text="schwarze")
        AufgabeOption.objects.create(aufgabe=self.a, position=3, text="helle")
        AufgabeOption.objects.create(aufgabe=self.a, position=4, text="weiße")
        AufgabeOption.objects.create(aufgabe=self.a, position=5, text="weisse")


    def test_e_typ_richtig(self):
        erg = bewerte_aufgabe(
            self.a,
            text_antwort="dunkle; helle"
        )
        self.assertTrue(erg["richtig"])


    def test_e_typ_falsch_getrennt(self):
        erg = bewerte_aufgabe(
            self.a,
            text_antwort="dunkle helle"
        )
        self.assertFalse(erg["richtig"])

    def test_e_typ_fuzzy(self):
        erg = bewerte_aufgabe(
            self.a,
            text_antwort="dunkle; helleee"
        )
        # erwartet: tolerant richtig
        self.assertTrue(erg["richtig"])
        self.assertIn("Schreibweise", erg["hinweis"])
