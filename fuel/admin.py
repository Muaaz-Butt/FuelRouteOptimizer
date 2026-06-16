from django.contrib import admin

from fuel.models import FuelPrice, GeocodeCache, Truckstop


class FuelPriceInline(admin.TabularInline):
    model = FuelPrice
    extra = 0
    readonly_fields = ("source_row_hash",)


@admin.register(Truckstop)
class TruckstopAdmin(admin.ModelAdmin):
    list_display = (
        "canonical_name",
        "city",
        "state",
        "geocode_status",
        "latitude",
        "longitude",
        "opis_truckstop_id",
    )
    list_filter = ("state", "geocode_status")
    search_fields = ("canonical_name", "city", "address", "opis_truckstop_id")
    inlines = [FuelPriceInline]


@admin.register(FuelPrice)
class FuelPriceAdmin(admin.ModelAdmin):
    list_display = ("truckstop", "retail_price", "rack_id")
    list_filter = ("rack_id",)
    search_fields = ("truckstop__canonical_name", "truckstop__city")


@admin.register(GeocodeCache)
class GeocodeCacheAdmin(admin.ModelAdmin):
    list_display = ("query", "latitude", "longitude", "confidence", "created_at")
    search_fields = ("query",)
    readonly_fields = ("created_at",)
