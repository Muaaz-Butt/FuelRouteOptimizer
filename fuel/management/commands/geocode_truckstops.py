import logging

from django.core.management.base import BaseCommand, CommandError

from fuel.models import GeocodeCache, GeocodeStatus, Truckstop
from fuel.services.geocoding import geocode_truckstop

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Geocode truck stops using Nominatim (OpenStreetMap) and cache results."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of truck stops to geocode in this run",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=None,
            help="Seconds to wait between geocoding requests (default: settings value)",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-geocode truck stops even if already geocoded successfully",
        )
        parser.add_argument(
            "--status",
            choices=[choice.value for choice in GeocodeStatus],
            default=GeocodeStatus.PENDING,
            help="Only geocode truck stops with this status (default: pending)",
        )
        parser.add_argument(
            "--clear-cache",
            action="store_true",
            help="Delete all geocode cache entries before running",
        )

    def handle(self, *args, **options):
        if options["clear_cache"]:
            deleted_count, _ = GeocodeCache.objects.all().delete()
            self.stdout.write(
                self.style.WARNING(f"Deleted {deleted_count} geocode cache entries.")
            )

        queryset = Truckstop.objects.all().order_by("id")
        if options["force"]:
            if options["status"] != GeocodeStatus.PENDING:
                queryset = queryset.filter(geocode_status=options["status"])
        else:
            queryset = queryset.filter(geocode_status=options["status"])

        if options["limit"] is not None:
            if options["limit"] <= 0:
                raise CommandError("--limit must be a positive integer")
            queryset = queryset[: options["limit"]]

        truckstops = list(queryset)
        if not truckstops:
            self.stdout.write("No truck stops matched the geocoding criteria.")
            return

        counts = {status.value: 0 for status in GeocodeStatus}
        delay = options["delay"]

        for index, truckstop in enumerate(truckstops, start=1):
            if options["force"]:
                for query in truckstop.geocode_queries:
                    GeocodeCache.objects.filter(query=query).delete()

            result = geocode_truckstop(
                truckstop,
                delay=delay,
                use_cache=not options["force"],
            )
            counts[result.status] += 1

            if result.status == GeocodeStatus.OK:
                self.stdout.write(
                    f"[{index}/{len(truckstops)}] {truckstop.opis_truckstop_id}: "
                    f"{result.latitude}, {result.longitude}"
                )
            elif result.status == GeocodeStatus.LOW_CONFIDENCE:
                logger.warning(
                    "Low-confidence geocode for truck stop %s (%s): confidence=%s",
                    truckstop.opis_truckstop_id,
                    truckstop.geocode_query,
                    result.confidence,
                )
                self.stdout.write(
                    self.style.WARNING(
                        f"[{index}/{len(truckstops)}] {truckstop.opis_truckstop_id}: "
                        f"low confidence ({result.confidence})"
                    )
                )
            else:
                logger.warning(
                    "Failed to geocode truck stop %s (%s)",
                    truckstop.opis_truckstop_id,
                    truckstop.geocode_query,
                )
                self.stdout.write(
                    self.style.ERROR(
                        f"[{index}/{len(truckstops)}] {truckstop.opis_truckstop_id}: failed"
                    )
                )

        summary = ", ".join(f"{status}={count}" for status, count in counts.items() if count)
        self.stdout.write(self.style.SUCCESS(f"Geocoding complete: {summary}"))
