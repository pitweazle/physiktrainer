from django.test import TestCase
# Importiere direkt über den App-Namen, wie er in INSTALLED_APPS steht
from physik.models import ThemenBereich, Kapitel, Aufgabe, AufgabeOption
from physik.bewertung import bewerte_aufgabe

class SchlagwortLogikTest(TestCase):
    def setUp(self):
        self.thema = ThemenBereich.objects.create(ordnung=1, thema="Wärmelehre", farbe="red", kurz="W")
        self.kapitel = Kapitel.objects.create(thema=self.thema, zeile=1, kapitel="Wärmeausbreitung")

        self.aufgabe = Aufgabe.objects.create(
            lfd_nr="W001",
            thema=self.thema,
            kapitel=self.kapitel,
            typ="3u(4o6)Y" # Die 3 muss "Luft" sein
        )

        # Position 2 (Index 0): Langer Satz
        AufgabeOption.objects.create(aufgabe=self.aufgabe, position=2, text="Die Luft...")
        # Position 3 (Index 1): Luft <--- Das wird von NUM 3 gesucht (3-2=1)
        AufgabeOption.objects.create(aufgabe=self.aufgabe, position=3, text="Luft")
        # Position 4 (Index 2): mehr
        AufgabeOption.objects.create(aufgabe=self.aufgabe, position=4, text="mehr")
        # Position 5 (Index 3): isoliert
        AufgabeOption.objects.create(aufgabe=self.aufgabe, position=5, text="isoliert")
        # Position 6 (Index 4): schlechter Wärmeleiter
        AufgabeOption.objects.create(aufgabe=self.aufgabe, position=6, text="schlechter Wärmeleiter")

    def test_bereich_logik_4o6(self):
        """
        Prüft, ob 'Luft' (3) und 'isoliert' (5) als richtig erkannt werden,
        da 5 im Bereich von 4 bis 6 liegt (4o6).
        """
        antwort_text = "Luft isoliert"
        # Wir übergeben eine leere Session, falls bewerte_aufgabe sie braucht
        ergebnis = bewerte_aufgabe(self.aufgabe, text_antwort=antwort_text, session={})
        
        self.assertTrue(
            ergebnis.get("richtig"), 
            f"Fehler: '{antwort_text}' wurde als falsch gewertet. "
            f"Logik '4o6' sollte die Position 5 (isoliert) einschließen."
        )

    def test_mindestbedingung_luft(self):
        """Prüft, ob es ohne das Pflichtwort 'Luft' (3) korrekterweise falsch ist."""
        antwort_text = "Es isoliert einfach gut."
        ergebnis = bewerte_aufgabe(self.aufgabe, text_antwort=antwort_text, session={})
        self.assertFalse(ergebnis.get("richtig"), "Sollte falsch sein, da 'Luft' fehlt.")