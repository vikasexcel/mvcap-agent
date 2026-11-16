"""Moves the caller to a phone number or extension, or ends the call."""

import logging
from dataclasses import dataclass

from livekit import api, rtc
from livekit.agents import get_job_context

from dataset import Dataset, Target

logger = logging.getLogger("transfer")

RINGING_TIMEOUT_SECONDS = 30


@dataclass
class TransferResult:
    ok: bool
    dry_run: bool = False
    reason: str | None = None


def destination(ds: Dataset, target: Target) -> str | None:
    """The `transfer_to` URI for a target, or None if it can't be dialed yet."""
    if target.kind == "phone":
        return f"tel:{target.value}"
    template = ds.setting("pbx_transfer_template")
    if not template:
        return (
            None  # how extensions are dialed is decided by the Telnyx/PBX transfer test
        )
    return template.format(ext=target.value)


def _sip_participant() -> rtc.RemoteParticipant | None:
    ctx = get_job_context()
    for participant in ctx.room.remote_participants.values():
        if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
            return participant
    return None


async def transfer_call(ds: Dataset, target: Target) -> TransferResult:
    participant = _sip_participant()
    if participant is None:
        # Console, Agent Console and tests have no phone leg to move.
        logger.warning("[dry run] would transfer the caller to %s", target)
        return TransferResult(True, dry_run=True)

    uri = destination(ds, target)
    if uri is None:
        logger.error(
            "cannot transfer to %s: pbx_transfer_template is not configured", target
        )
        return TransferResult(False, reason="extension_dialing_not_configured")

    ctx = get_job_context()
    try:
        await ctx.api.sip.transfer_sip_participant(
            api.TransferSIPParticipantRequest(
                participant_identity=participant.identity,
                room_name=ctx.room.name,
                transfer_to=uri,
                play_dialtone=False,
                ringing_timeout=_ringing_timeout(),
            )
        )
        logger.info("transferred the caller to %s", uri)
        return TransferResult(True)
    except api.SipCallError as error:
        logger.error(
            "transfer to %s rejected: reason=%s sip=%s %s",
            uri,
            error.sip_transfer_reason,
            error.sip_status_code,
            error.sip_status,
        )
        return TransferResult(
            False, reason=str(error.sip_transfer_reason or error.sip_status_code)
        )
    except Exception as error:
        logger.exception("transfer to %s failed", uri)
        return TransferResult(False, reason=type(error).__name__)


def _ringing_timeout():
    from google.protobuf.duration_pb2 import Duration

    return Duration(seconds=RINGING_TIMEOUT_SECONDS)


async def hang_up() -> None:
    ctx = get_job_context()
    if ctx is None or _sip_participant() is None:
        logger.warning("[dry run] would end the call")
        return
    await ctx.delete_room()
