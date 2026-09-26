from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.catalog.workbook.export import build_workbook, catalogue_rows, template_rows


class Command(BaseCommand):
    help = (
        "Write the catalogue workbook: every brand, category, shade, size, skin type, "
        "product and variant in the database, or with --template the blank workbook."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("out", type=Path, help="The .xlsx file to write.")
        parser.add_argument(
            "--template",
            action="store_true",
            help="Write the blank workbook: example rows and the standard skin types only.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        out: Path = options["out"]
        rows = template_rows() if options["template"] else catalogue_rows()
        out.parent.mkdir(parents=True, exist_ok=True)
        build_workbook(rows).save(out)
        self.stdout.write(self.style.SUCCESS(f"Wrote {out}"))
