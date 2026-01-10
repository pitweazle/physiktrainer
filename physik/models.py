from django.contrib.auth.models import User
from django.conf import settings
from django.db import models

class ThemenBereich(models.Model):
    ordnung = models.PositiveSmallIntegerField(unique=True)
    thema = models.CharField(max_length=30)
    farbe = models.CharField(max_length=40,)
    eingeblendet = models.BooleanField(default = True)

    class Meta:
        ordering = ["ordnung"]
        verbose_name = "Themenbereich"
        verbose_name_plural = "Themenbereiche"

    def __str__(self):
        return f"{self.ordnung} – {self.thema}"

class Kapitel(models.Model):
    thema = models.ForeignKey(
        ThemenBereich,
        on_delete=models.CASCADE,
        related_name="kapitel",
    )

    # Sortierung innerhalb eines Themenbereichs (1..n, ohne Obergrenze)
    zeile = models.PositiveSmallIntegerField()
    kapitel = models.CharField(max_length=100)
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["thema", "zeile"],
                name="uniq_kapitel_pro_thema_zeile",
            )
        ]
        ordering = ["thema__ordnung", "zeile"]
        verbose_name = "Kapitel"
        verbose_name_plural = "Kapitel"

    def __str__(self):
        return f"{self.thema.thema} – {self.zeile}: {self.kapitel}"

class Aufgabe(models.Model):
    lfd_nr = models.CharField("lfd_Nr", max_length=10, unique=True)
    thema = models.ForeignKey("ThemenBereich", on_delete=models.CASCADE, related_name="aufgaben")
    kapitel = models.ForeignKey("Kapitel", on_delete=models.CASCADE, related_name="aufgaben")

    EINFACH = 1
    MITTEL = 2
    PROFI = 3
    SCHWIERIGKEIT_CHOICES = [
        (EINFACH, "Einfach"),
        (MITTEL, "Mittel"),
        (PROFI, "Profi"),
    ]
    schwierigkeit = models.PositiveSmallIntegerField(choices=SCHWIERIGKEIT_CHOICES, default=EINFACH)

    # Typ wieder frei editierbar (ohne FK)
    typ = models.CharField("Typ", max_length=20, blank=True)

    frage = models.CharField("Frage", max_length=255, blank=True)
    einheit = models.CharField(
        "Einheit",
        max_length=15,
        blank=True,
        help_text="Optional – wird hinter dem Eingabefeld angezeigt (z.B. cm, kg, °C).",
    )

    antwort = models.CharField("Antwort", max_length=255, blank=True, help_text="Hier steht die offizielle Antwort.")

    anmerkung = models.CharField("Anmerkung", max_length=255, blank=True, help_text="Optional, nur wenn gewünscht.")
    erklaerung = models.TextField("Erklärung",blank=True,
        help_text="Optional. Wird angezeigt, wenn auf »Lösung« geklickt wird oder eine falsche Eingabe gemacht wurde.",
    )
    hilfe = models.CharField("Hilfe", max_length=255, blank=True, help_text="Optional, nur wenn gewünscht.")

    erstellt = models.DateTimeField("Erstellt", auto_now_add=True)

    von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="erstellte_aufgaben",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "Aufgabe"
        verbose_name_plural = "Aufgaben"

    def __str__(self):
        return f"{self.thema} / {self.kapitel} – {self.frage[:50]}"

class AufgabeOption(models.Model):
    aufgabe = models.ForeignKey(Aufgabe, on_delete=models.CASCADE, related_name="optionen")
    position = models.PositiveSmallIntegerField("Position")
    text = models.CharField("Text", max_length=255)

    class Meta:
        verbose_name = "Option"
        verbose_name_plural = "Optionen"
        unique_together = [("aufgabe", "position")]
        ordering = ["position"]

    def __str__(self):
        return f"{self.aufgabe_id}:{self.position} {self.text}"
