import hmac
import json
import logging

from src.exceptions import IntegrationError, PayloadMissing, WrongStartLocation
from src.interfaces import CryptoService, PayloadService, StartLocationService, SteganographyService
from src.models import Media, Verdict, VerificationResult

logger = logging.getLogger(__name__)


class VerificationEngine:
    STAGES = ("location", "payload", "signature", "hash")

    def __init__(self, crypto: CryptoService, payload: PayloadService,
                 location: StartLocationService):
        self.crypto, self.payload, self.location = crypto, payload, location
        # Optional observer called with the stage name as each stage begins,
        # so a front end can show live progress. Verification never depends on it.
        self.on_stage = None

    def _begin(self, stage: str) -> str:
        if self.on_stage is not None:
            try:
                self.on_stage(stage)
            except Exception:  # a broken observer must never change a verdict
                logger.exception("Stage observer failed at %s", stage)
        return stage

    def verify(self, media: Media, lsb: int,
               steganography: SteganographyService) -> VerificationResult:
        statuses = {stage: "Not run" for stage in self.STAGES}
        stage = self._begin("location")
        try:
            start = self.location.recover(media, lsb)
            statuses[stage] = "Computed"
            stage = self._begin("payload")
            encoded = steganography.extract(media, lsb, start)
            if not encoded:
                raise PayloadMissing("No payload was found.")
            payload = self.payload.unpack(encoded)
            statuses[stage] = "Parsed"
            stage = self._begin("signature")
            if not self.crypto.verify_signature(payload.signed_data, payload.signature):
                statuses[stage] = "Invalid"
                return VerificationResult(Verdict.SIGNATURE_INVALID, "Payload signature is invalid.", statuses)
            statuses[stage] = "Valid"
            stage = self._begin("hash")
            if not hmac.compare_digest(self.crypto.hash_media(media, lsb), payload.digest):
                statuses[stage] = "Mismatch"
                return VerificationResult(Verdict.TAMPERED, "Canonical media digest does not match.", statuses)
            statuses[stage] = "Match"
            try:
                decoded_payload = json.loads(payload.signed_data).get("metadata", {}).get("payload", "")
            except (ValueError, TypeError, AttributeError):
                decoded_payload = ""
            return VerificationResult(Verdict.AUTHENTIC, "Signature and canonical media digest verified.",
                                      statuses, decoded_payload if isinstance(decoded_payload, str) else "")
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
