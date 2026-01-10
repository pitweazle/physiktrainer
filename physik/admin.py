from django.contrib import admin
from .models import ThemenBereich, Kapitel, Aufgabe, AufgabeOption


@admin.register(ThemenBereich)
class ThemenBereichAdmin(admin.ModelAdmin):
    list_display = ("ordnung", "thema", "farbe", "eingeblendet")
    list_filter = ("eingeblendet",)
    search_fields = ("thema",)
    ordering = ("ordnung",)


@admin.register(Kapitel)
class KapitelAdmin(admin.ModelAdmin):
    list_display = ("thema", "zeile", "kapitel")
    list_filter = ("thema",)
    search_fields = ("kapitel", "thema__thema")
    ordering = ("thema__ordnung", "zeile")


class AufgabeOptionInline(admin.TabularInline):
    model = AufgabeOption
    extra = 3
    fields = ("position", "text")
    ordering = ("position",)


@admin.register(Aufgabe)
class AufgabeAdmin(admin.ModelAdmin):
    inlines = [AufgabeOptionInline]
    list_display = ("frage", "lfd_nr", "thema", "kapitel", "schwierigkeit")
    #list_editable = ("lfd_nr",)
    list_filter = ("thema", "kapitel", "schwierigkeit")
    search_fields = ("frage", "antwort", "typ", "anmerkung", "erklaerung", "hilfe")
    ordering = ("thema__ordnung", "kapitel__zeile", "id")
    date_hierarchy = "erstellt"

    exclude = ("von",)
    readonly_fields = ("erstellt",)

    fieldsets = (
        (None, {"fields": ("thema", "kapitel", "schwierigkeit", "typ")}),

        ("Frage", {"fields": ("frage",)}),

        ("Einheit (optional)", {
            "fields": ("einheit",),
            "classes": ("collapse",),
            "description": "Optional – wird hinter dem Eingabefeld angezeigt (z.B. cm, kg, °C).",
        }),

        ("Antwort", {"fields": ("antwort",)}),

        ("Zusatzinformationen", {
            "fields": ("anmerkung", "erklaerung", "hilfe"),
            "classes": ("collapse",),
        }),
    )

    def save_model(self, request, obj, form, change):
        if not obj.pk:
            obj.von = request.user
        super().save_model(request, obj, form, change)
