from django.contrib import admin

from django.contrib import admin
from .models import ThemenBereich, Kapitel


@admin.register(ThemenBereich)
class ThemenBereichAdmin(admin.ModelAdmin):
    list_display = ("ordnung", "thema", "farbe")
    ordering = ("ordnung",)


@admin.register(Kapitel)
class KapitelAdmin(admin.ModelAdmin):
    list_display = ("thema", "zeile", "kapitel")
    list_filter = ("thema",)
    ordering = ("thema", "zeile")

