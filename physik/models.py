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
    kapitel = models.CharField(max_length=50)
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
