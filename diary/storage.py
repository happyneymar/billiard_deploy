from pathlib import PurePosixPath

from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible


CLOUDINARY_LARGE_UPLOAD_THRESHOLD = 100 * 1024 * 1024
VIDEO_EXTENSIONS = {"mp4", "webm", "mov", "avi"}


@deconstructible
class CloudinaryMediaStorage(Storage):
    """Django storage backend for user-uploaded images and videos on Cloudinary."""

    def _normalize_name(self, name: str) -> str:
        return PurePosixPath(str(name).replace("\\", "/")).as_posix().lstrip("/")

    def _split_name(self, name: str) -> tuple[str, str]:
        normalized = self._normalize_name(name)
        path = PurePosixPath(normalized)
        suffix = path.suffix.lower()
        if suffix:
            public_id = normalized[: -len(suffix)]
        else:
            public_id = normalized
        return public_id, suffix.lstrip(".")

    def _resource_type(self, name: str) -> str:
        ext = PurePosixPath(name).suffix.lower().lstrip(".")
        if ext in VIDEO_EXTENSIONS:
            return "video"
        return "image"

    def _save(self, name, content):
        import cloudinary
        import cloudinary.uploader

        normalized = self._normalize_name(name)
        public_id, _ = self._split_name(normalized)
        cloudinary.config(secure=True)

        if hasattr(content, "seek"):
            content.seek(0)

        upload_source = content
        if getattr(content, "size", 0) > CLOUDINARY_LARGE_UPLOAD_THRESHOLD and hasattr(
            content, "temporary_file_path"
        ):
            upload_source = content.temporary_file_path()

        upload = (
            cloudinary.uploader.upload_large
            if getattr(content, "size", 0) > CLOUDINARY_LARGE_UPLOAD_THRESHOLD
            else cloudinary.uploader.upload
        )
        upload(
            upload_source,
            resource_type="auto",
            public_id=public_id,
            overwrite=True,
            unique_filename=False,
            use_filename=False,
        )
        return normalized

    def delete(self, name):
        import cloudinary
        import cloudinary.uploader

        public_id, _ = self._split_name(name)
        cloudinary.config(secure=True)
        cloudinary.uploader.destroy(
            public_id,
            resource_type=self._resource_type(name),
            invalidate=True,
        )

    def exists(self, name):
        return False

    def url(self, name):
        import cloudinary
        from cloudinary.utils import cloudinary_url

        public_id, file_format = self._split_name(name)
        options = {
            "resource_type": self._resource_type(name),
            "secure": True,
        }
        if file_format:
            options["format"] = file_format

        cloudinary.config(secure=True)
        url, _ = cloudinary_url(public_id, **options)
        return url
