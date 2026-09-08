from pathlib import Path

from src.exceptions import IntegrationError, UnsupportedFileType
from src.interfaces import (AudioSteganographyService, CryptoService,
                            ImageSteganographyService, PayloadService, StartLocationService)
from src.models import Media, MediaType, Verdict, VerificationResult
from src.verification import VerificationEngine


class ApplicationController:
    def __init__(self, image: ImageSteganographyService, audio: AudioSteganographyService,
                 crypto: CryptoService, payload: PayloadService, location: StartLocationService):
        self.image, self.audio = image, audio
        self.crypto, self.payload, self.location = crypto, payload, location
        self.engine = VerificationEngine(crypto, payload, location)

    @staticmethod
    def validate_lsb(lsb: int) -> None:
        if type(lsb) is not int or not 1 <= lsb <= 8:
            raise IntegrationError("LSB must be an integer from 1 to 8.")

    @staticmethod
    def load(path: str) -> Media:
        file = Path(path)
        suffix = file.suffix.lower()
        if suffix in {".png", ".bmp"}:
            kind = MediaType.IMAGE
        elif suffix == ".wav":
            kind = MediaType.AUDIO
        else:
            raise UnsupportedFileType("Supported skeleton formats: PNG, BMP and PCM WAV.")
        try:
            return Media(file.read_bytes(), suffix, kind)
        except OSError as exc:
            raise IntegrationError("Cannot read the selected file.") from exc

    def service_for(self, media: Media):
        if media.kind == MediaType.IMAGE:
            return self.image
        if media.kind == MediaType.AUDIO:
            return self.audio
        raise UnsupportedFileType("Unsupported media type.")

    def protect(self, path: str, lsb: int) -> Media:
        self.validate_lsb(lsb)
        media = self.load(path)
        service = self.service_for(media)
        try:
            start = self.location.generate(media, lsb)
            digest = self.crypto.hash_media(media, lsb)
            content = self.payload.create(media, digest)
            encoded = self.payload.pack(content, self.crypto.sign(content))
            if len(encoded) > service.capacity(media, lsb, start):
                raise IntegrationError("Payload exceeds the available media capacity.")
            return Media(service.embed(media, encoded, lsb, start), media.suffix, media.kind)
        except IntegrationError:
            raise
        except Exception as exc:
            raise IntegrationError("Protection failed; check the configured service adapters.") from exc

    def verify(self, path: str, lsb: int) -> VerificationResult:
        try:
            self.validate_lsb(lsb)
            media = self.load(path)
            return self.engine.verify(media, lsb, self.service_for(media))
        except IntegrationError as exc:
            return VerificationResult(Verdict.CANNOT_VERIFY, str(exc))

    @staticmethod
    def save(media: Media, path: str) -> None:
        if Path(path).suffix.lower() != media.suffix:
            raise IntegrationError("Save with the original format extension.")
        try:
            # Exclusive creation prevents accidental destruction of the source.
            with Path(path).open("xb") as output:
                output.write(media.data)
        except FileExistsError as exc:
            raise IntegrationError("Destination exists. Choose a new file name.") from exc
        except OSError as exc:
            raise IntegrationError("Cannot save the stego file.") from exc
