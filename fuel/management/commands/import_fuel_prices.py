import csv
import logging
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from fuel.models import FuelPrice, Truckstop
from fuel.validators import REQUIRED_COLUMNS, validate_fuel_price_row

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Import fuel prices from a CSV file into Truckstop and FuelPrice tables."

    def add_arguments(self, parser):
        default_csv = Path(settings.BASE_DIR) / "data" / "fuel_prices.csv"
        parser.add_argument(
            "--file",
            default=str(default_csv),
            help=f"Path to the fuel prices CSV file (default: {default_csv})",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete existing truck stop and price records before importing",
        )

    def handle(self, *args, **options):
        csv_path = Path(options["file"])

        if not csv_path.is_file():
            raise CommandError(f"CSV file not found: {csv_path}")

        if options["clear"]:
            price_count, _ = FuelPrice.objects.all().delete()
            stop_count, _ = Truckstop.objects.all().delete()
            self.stdout.write(
                self.style.WARNING(
                    f"Deleted {stop_count} truck stops and {price_count} fuel prices."
                )
            )

        imported_prices = 0
        skipped_prices = 0
        created_stops = 0
        existing_stops = 0

        with csv_path.open(newline="", encoding="utf-8") as csv_file:
            reader = csv.DictReader(csv_file)

            if reader.fieldnames is None:
                raise CommandError("CSV file is missing a header row.")

            missing_columns = [
                column for column in REQUIRED_COLUMNS if column not in reader.fieldnames
            ]
            if missing_columns:
                raise CommandError(
                    "CSV file is missing required columns: "
                    + ", ".join(missing_columns)
                )

            for line_number, row in enumerate(reader, start=2):
                validated_row, error = validate_fuel_price_row(row)
                if error:
                    skipped_prices += 1
                    logger.warning(
                        "Skipping row %s: %s | data=%s", line_number, error, row
                    )
                    continue

                truckstop, created = Truckstop.objects.get_or_create(
                    opis_truckstop_id=validated_row.opis_truckstop_id,
                    defaults={
                        "canonical_name": validated_row.truckstop_name,
                        "address": validated_row.address,
                        "city": validated_row.city,
                        "state": validated_row.state,
                    },
                )
                if created:
                    created_stops += 1
                else:
                    existing_stops += 1

                _, price_created = FuelPrice.objects.get_or_create(
                    source_row_hash=validated_row.source_row_hash,
                    defaults={
                        "truckstop": truckstop,
                        "rack_id": validated_row.rack_id,
                        "retail_price": validated_row.retail_price,
                    },
                )
                if price_created:
                    imported_prices += 1
                else:
                    skipped_prices += 1
                    logger.info(
                        "Skipping duplicate row %s (hash=%s)",
                        line_number,
                        validated_row.source_row_hash[:12],
                    )

        self.stdout.write(
            self.style.SUCCESS(
                "Import complete: "
                f"{imported_prices} prices imported, "
                f"{skipped_prices} rows skipped, "
                f"{created_stops} truck stops created, "
                f"{existing_stops} existing truck stops reused."
            )
        )
