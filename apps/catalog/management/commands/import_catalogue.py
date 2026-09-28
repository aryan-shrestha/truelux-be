from pathlib import Path
from typing import Any
from zipfile import BadZipFile

from django.core.management.base import BaseCommand, CommandError, CommandParser
from openpyxl.utils.exceptions import InvalidFileException

from apps.catalog.workbook.importer import ImportReport, import_catalogue
from apps.catalog.workbook.layout import DATA_SHEETS


class Command(BaseCommand):
    # No DEBUG guard, unlike the seed commands: loading the merchant's own catalogue
    # into production is the purpose of this command.
    help = (
        "Load the catalogue workbook into the database. Validates every sheet first and "
        "writes nothing if anything is wrong. Adds and updates; never deletes."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("file", type=Path, help="The filled-in .xlsx workbook.")
        parser.add_argument(
            "--images", type=Path, help="The folder holding the image and logo files."
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and report what would change, then roll everything back.",
        )
        parser.add_argument(
            "--replace-images",
            action="store_true",
            help="Replace the images of products and the logos of brands that already have "
            "them. Without it, only products and brands with none get the workbook's files.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        path: Path = options["file"]
        images: Path | None = options["images"]
        if not path.is_file():
            raise CommandError(f"{path} does not exist.")
        if images is not None and not images.is_dir():
            raise CommandError(f"The images folder {images} does not exist.")

        try:
            report = import_catalogue(
                path,
                images_dir=images,
                replace_images=options["replace_images"],
                dry_run=options["dry_run"],
            )
        except (BadZipFile, InvalidFileException) as error:
            raise CommandError(f"{path} is not an .xlsx workbook.") from error

        if report.problems:
            for problem in report.problems:
                self.stderr.write(str(problem))
            raise CommandError(
                f"{len(report.problems)} problem(s) found. Nothing was written; "
                "fix the workbook and run the import again."
            )
        self._summarise(report, dry_run=options["dry_run"])

    def _summarise(self, report: ImportReport, *, dry_run: bool) -> None:
        heading = "Dry run: nothing was written." if dry_run else "Imported."
        self.stdout.write(self.style.SUCCESS(heading))
        for sheet in DATA_SHEETS:
            tally = report.tallies[sheet]
            self.stdout.write(
                f"  {sheet.title}: {tally.created} created, {tally.updated} updated, "
                f"{tally.unchanged} unchanged"
            )
            for header in report.absent_columns.get(sheet, []):
                self.stdout.write(f'    column "{header}" not in workbook, left unchanged')
            if tally.not_in_workbook:
                self.stdout.write(
                    f"    {len(tally.not_in_workbook)} not in workbook, left unchanged: "
                    + ", ".join(tally.not_in_workbook)
                )
        if dry_run:
            self.stdout.write(f"  Images: {report.planned_uploads} would be uploaded")
            return
        self.stdout.write(f"  Images: {report.uploaded} uploaded")
        for failure in report.upload_failures:
            self.stderr.write(f"  Upload failed: {failure}")
        if report.upload_failures:
            raise CommandError(
                f"{len(report.upload_failures)} upload(s) failed; the catalogue itself was "
                "saved. Fix the files and run the import again: products that still have no "
                "images will get them."
            )
