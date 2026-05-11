from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from diary.models import DailyMedia, MomentMedia
from diary.storage import CloudinaryMediaStorage


class Command(BaseCommand):
    help = "Upload existing local media files to Cloudinary using their current database paths."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be uploaded without sending files to Cloudinary.",
        )

    def handle(self, *args, **options):
        if not settings.USE_CLOUDINARY_MEDIA:
            raise CommandError(
                "USE_CLOUDINARY_MEDIA must be True and CLOUDINARY_URL must be configured."
            )

        storage = CloudinaryMediaStorage()
        dry_run = options["dry_run"]
        uploaded = 0
        missing = 0

        for model in (DailyMedia, MomentMedia):
            for media in model.objects.exclude(file="").iterator():
                name = media.file.name
                local_path = Path(settings.MEDIA_ROOT) / name
                if not local_path.exists():
                    missing += 1
                    self.stdout.write(self.style.WARNING(f"Missing: {name}"))
                    continue

                if dry_run:
                    self.stdout.write(f"Would upload: {name}")
                    continue

                with local_path.open("rb") as handle:
                    storage.save(name, File(handle, name=local_path.name))
                uploaded += 1
                self.stdout.write(self.style.SUCCESS(f"Uploaded: {name}"))

        if dry_run:
            self.stdout.write(self.style.SUCCESS("Dry run complete."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Uploaded {uploaded} file(s)."))
        if missing:
            self.stdout.write(self.style.WARNING(f"Missing {missing} local file(s)."))
