from django.db import models


class GeocodeStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    OK = "ok", "OK"
    LOW_CONFIDENCE = "low_confidence", "Low Confidence"
    FAILED = "failed", "Failed"


class Truckstop(models.Model):
    opis_truckstop_id = models.PositiveIntegerField(unique=True, db_index=True)
    canonical_name = models.CharField(max_length=255)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100, db_index=True)
    state = models.CharField(max_length=2, db_index=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    geocode_status = models.CharField(
        max_length=20,
        choices=GeocodeStatus.choices,
        default=GeocodeStatus.PENDING,
        db_index=True,
    )
    geocoded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["state", "city"]),
            models.Index(fields=["latitude", "longitude"]),
        ]
        ordering = ["state", "city", "canonical_name"]

    def __str__(self) -> str:
        return f"{self.canonical_name} ({self.city}, {self.state})"

    @property
    def geocode_query(self) -> str:
        return self.geocode_queries[0]

    @property
    def geocode_queries(self) -> list[str]:
        country = "Canada" if self.state in CANADIAN_PROVINCES else "USA"
        return [
            f"{self.address}, {self.city}, {self.state}, {country}",
            f"{self.city}, {self.state}, {country}",
        ]


CANADIAN_PROVINCES = frozenset({"AB", "BC", "MB", "NB", "NS", "ON", "QC", "SK", "YT"})


class FuelPrice(models.Model):
    truckstop = models.ForeignKey(
        Truckstop,
        on_delete=models.CASCADE,
        related_name="prices",
    )
    rack_id = models.PositiveIntegerField(db_index=True)
    retail_price = models.DecimalField(max_digits=10, decimal_places=8)
    source_row_hash = models.CharField(max_length=64, unique=True)

    class Meta:
        indexes = [
            models.Index(fields=["truckstop", "retail_price"]),
            models.Index(fields=["rack_id"]),
        ]
        ordering = ["retail_price"]

    def __str__(self) -> str:
        return f"${self.retail_price} @ {self.truckstop}"


class GeocodeCache(models.Model):
    query = models.CharField(max_length=512, unique=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    confidence = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    raw_response = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "geocode cache entry"
        verbose_name_plural = "geocode cache entries"

    def __str__(self) -> str:
        return self.query
