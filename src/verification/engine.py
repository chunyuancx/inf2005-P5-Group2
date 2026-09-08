import hmac
import logging

from src.exceptions import IntegrationError, PayloadMissing, WrongStartLocation
from src.interfaces import CryptoService, PayloadService, StartLocationService, SteganographyService
from src.models import Media, Verdict, VerificationResult

logger = logging.getLogger(__name__)


class VerificationEngine:
    def __init__(self, crypto: CryptoService, payload: PayloadService,
                 location: StartLocationService):
        self.crypto, self.payload, self.location = crypto, payload, location

    def verify(self, media: Media, lsb: int,
               steganography: SteganographyService) -> VerificationResult:
        statuses = {stage: "Not run" for stage in ("location", "payload", "signature", "hash")}
        stage = "location"
        try:
            start = self.location.recover(media, lsb)
            statuses[stage] = "Recovered"
            stage = "payload"
            encoded = steganography.extract(media, lsb, start)
            if not encoded:
                raise PayloadMissing("No payload was found.")
            payload = self.payload.unpack(encoded)
            statuses[stage] = "Parsed"
            stage = "signature"
            if not self.crypto.verify_signature(payload.signed_data, payload.signature):
                statuses[stage] = "Invalid"
                return VerificationResult(Verdict.SIGNATURE_INVALID, "Payload signature is invalid.", statuses)
            statuses[stage] = "Valid"
            stage = "hash"
            if not hmac.compare_digest(self.crypto.hash_media(media, lsb), payload.digest):
                statuses[stage] = "Mismatch"
                return VerificationResult(Verdict.TAMPERED, "Canonical media digest does not match.", statuses)
            statuses[stage] = "Match"
            return VerificationResult(Verdict.AUTHENTIC, "Signature and canonical media digest verified.", statuses)
        except WrongStartLocation as exc:
            statuses[stage] = "Failed"
            return VerificationResult(Verdict.WRONG_START_LOCATION, str(exc), statuses)
        except PayloadMissing as exc:
            statuses[stage] = "Missing"
            return VerificationResult(Verdict.PAYLOAD_MISSING, str(exc), statuses)
        except IntegrationError as exc:
            statuses[stage] = "Unavailable"
            return VerificationResult(Verdict.CANNOT_VERIFY, str(exc), statuses)
        except Exception:
            logger.exception("Verification failed at %s", stage)
            statuses[stage] = "Failed"
            return VerificationResult(Verdict.CANNOT_VERIFY, "Verification failed; consult application logs.", statuses)
