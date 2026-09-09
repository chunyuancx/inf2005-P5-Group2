"""Integration tests against src.controllers.ApplicationController and
src.verification.VerificationEngine — the group's real code, unmodified.

Run:  python -m pytest tests -v
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.controllers import ApplicationController  # noqa: E402
from src.models import Media, MediaType, Verdict  # noqa: E402
from tests.fakes import (  # noqa: E402
    FakeCrypto,
    FakePayloadService,
    FakeSteganography,
    NaiveStartLocation,
    SelfCheckingStartLocation,
)


def controller(location=None, crypto=None) -> ApplicationController:
    stego = FakeSteganography()
    return ApplicationController(
        image=stego,
        audio=stego,
        crypto=crypto or FakeCrypto(),
        payload=FakePayloadService(),
        location=location or SelfCheckingStartLocation(),
    )


def write_cover(tmp_path, name="cover.png", size=5000, seed=1234) -> str:
    import random
    rng = random.Random(seed)
    p = tmp_path / name
    p.write_bytes(bytes(rng.randrange(256) for _ in range(size)))
    return str(p)


# -------------------------------------------------------------- happy path

def test_authentic_round_trip(tmp_path):
    ctl = controller()
    src = write_cover(tmp_path)
    stego = ctl.protect(src, lsb=1)
    out = str(tmp_path / "stego.png")
    ctl.save(stego, out)

    res = ctl.verify(out, lsb=1)
    assert res.verdict is Verdict.AUTHENTIC, res.message


@pytest.mark.parametrize("lsb", [1, 2, 3, 4, 5, 6, 7, 8])
def test_all_lsb_depths(tmp_path, lsb):
    ctl = controller()
    src = write_cover(tmp_path, name=f"c{lsb}.png")
    stego = ctl.protect(src, lsb=lsb)
    out = str(tmp_path / f"s{lsb}.png")
    ctl.save(stego, out)
    res = ctl.verify(out, lsb=lsb)
    assert res.verdict is Verdict.AUTHENTIC, res.message


# -------------------------------------------------------------- negative cases

def test_tampered_media_detected(tmp_path):
    ctl = controller()
    src = write_cover(tmp_path, size=5000)
    stego = ctl.protect(src, lsb=1)
    out = str(tmp_path / "stego.png")
    ctl.save(stego, out)

    data = bytearray(open(out, "rb").read())
    for i in range(4000, 4100):        # clear of the embedded run
        data[i] ^= 0b1000_0000
    open(out, "wb").write(bytes(data))

    res = ctl.verify(out, lsb=1)
    assert res.verdict is Verdict.TAMPERED, res.message


def test_signature_invalid_with_wrong_verify_key(tmp_path):
    ctl = controller(crypto=FakeCrypto(sign_key="alice", verify_key="alice"))
    src = write_cover(tmp_path)
    stego = ctl.protect(src, lsb=1)
    out = str(tmp_path / "stego.png")
    ctl.save(stego, out)

    wrong = controller(crypto=FakeCrypto(sign_key="mallory", verify_key="mallory"))
    res = wrong.verify(out, lsb=1)
    assert res.verdict is Verdict.SIGNATURE_INVALID, res.message


def test_payload_missing_on_unprotected_file(tmp_path):
    ctl = controller()
    plain = write_cover(tmp_path, name="plain.png")
    res = ctl.verify(plain, lsb=1)
    assert res.verdict is Verdict.PAYLOAD_MISSING, res.message


def test_cannot_verify_on_unsupported_format(tmp_path):
    ctl = controller()
    odd = tmp_path / "cover.mp3"
    odd.write_bytes(b"\x00" * 1000)
    res = ctl.verify(str(odd), lsb=1)
    assert res.verdict is Verdict.CANNOT_VERIFY, res.message


def test_capacity_rejected_before_writing(tmp_path):
    ctl = controller()
    src = write_cover(tmp_path, name="tiny.png", size=20)
    with pytest.raises(Exception):
        ctl.protect(src, lsb=1)


# --------------------------------------- the finding: WrongStartLocation

def test_selfchecking_locator_raises_wrong_start_location(tmp_path):
    """With a self-checking Member-4 design, a wrong key produces
    WRONG_START_LOCATION, distinct from PAYLOAD_MISSING."""
    ctl = controller(location=SelfCheckingStartLocation(key="right-key"))
    src = write_cover(tmp_path)
    stego = ctl.protect(src, lsb=1)
    out = str(tmp_path / "stego.png")
    ctl.save(stego, out)

    wrong_locator = SelfCheckingStartLocation(key="wrong-key")
    ctl_wrong = controller(location=wrong_locator)
    media = ctl_wrong.load(out)
    # simulate: the marker actually stored belongs to "right-key"
    object.__setattr__(media, "_test_stored_marker",
                        SelfCheckingStartLocation(key="right-key")._marker(media))
    res = ctl_wrong.engine.verify(media, 1, ctl_wrong.service_for(media))
    assert res.verdict is Verdict.WRONG_START_LOCATION, res.message


def test_naive_locator_cannot_reach_wrong_start_location(tmp_path):
    """DEMONSTRATES THE RISK: if Member 4's recover() has no self-check
    (just re-derives the same deterministic offset, same as generate()),
    a wrong key can NEVER produce WRONG_START_LOCATION. It always lands on
    PAYLOAD_MISSING or CANNOT_VERIFY instead, because recover() itself never
    raises. This test passing is the problem, not a success.
    """
    ctl = controller(location=NaiveStartLocation(key="right-key"))
    src = write_cover(tmp_path)
    stego = ctl.protect(src, lsb=1)
    out = str(tmp_path / "stego.png")
    ctl.save(stego, out)

    ctl_wrong = controller(location=NaiveStartLocation(key="wrong-key"))
    res = ctl_wrong.verify(out, lsb=1)
    # This is the failure mode: never WRONG_START_LOCATION with a naive locator.
    assert res.verdict is not Verdict.WRONG_START_LOCATION
    assert res.verdict in {Verdict.PAYLOAD_MISSING, Verdict.CANNOT_VERIFY}
