"""Moves the caller to a phone number or extension, or ends the call.

The `transfer_mode` setting picks how:
- bridge: the agent dials out into the caller's room, sends the extension as keypad tones once
  it answers, then leaves so the two phone legs stay bridged (two legs stay open for the call).
- blind: a SIP REFER hands the caller to the destination and LiveKit drops out. A REFER can't
  send tones after answer, so an extension rides in the address as post-dial digits (`;postd=`),
  which the provider may ignore. Test it on a live call.
- hybrid: blind for phone numbers, bridge for extensions.
"""

import asyncio
import logging
import os
from dataclasses import dataclass

from google.protobuf.duration_pb2 import Duration
from livekit import api, rtc
from livekit.agents import get_job_context

from dataset import Dataset, Target

logger = logging.getLogger("transfer")

RINGING_TIMEOUT_SECONDS = 30
TONES_GRACE_SECONDS = 4  # extra time for the tones to finish after the pause
HALF_SECOND_PAUSES_PER_SECOND = 2  # each "w" in a DTMF string pauses 0.5 s


@dataclass
class TransferResult:
    ok: bool
    dry_run: bool = False
    reason: str | None = None


def dial_plan(ds: Dataset, target: Target) -> tuple[str, str | None] | None:
    """(number to call, tones to send once it answers), or None if it can't be dialed yet."""
    override = ds.setting("transfer_override_number")
    if target.kind == "phone":
        return override or target.value, None
    number = override or ds.setting("pbx_main_number")
    if not number:
        return None
    pause = float(ds.setting("pbx_dtmf_pause_seconds", 3))
    pauses = round(pause * HALF_SECOND_PAUSES_PER_SECOND)
    return number, "w" * pauses + target.value


def transfer_mode(ds: Dataset, target: Target) -> str:
    """The way this target is transferred: "bridge" or "blind"."""
    mode = ds.setting("transfer_mode", "bridge")
    if mode == "hybrid":
        return "blind" if target.kind == "phone" else "bridge"
    return "blind" if mode == "blind" else "bridge"


def refer_uri(ds: Dataset, target: Target) -> str | None:
    """The REFER address: the number, plus the extension as post-dial digits after a pause."""
    plan = dial_plan(ds, target)
    if plan is None:
        return None
    number, _ = plan
    if target.kind == "phone":
        return f"tel:{number}"
    pause = round(float(ds.setting("pbx_dtmf_pause_seconds", 3)))
    return (
        f"tel:{number};postd={'p' * pause}{target.value}"  # "p" is a one-second pause
    )


def _sip_participant() -> rtc.RemoteParticipant | None:
    ctx = get_job_context()
    for participant in ctx.room.remote_participants.values():
        if participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP:
            return participant
    return None


async def _wait_for_tones(identity: str, seconds: float) -> None:
    """Stay in the room until the dialed leg has finished sending the extension."""
    ctx = get_job_context()
    deadline = asyncio.get_running_loop().time() + seconds
    while asyncio.get_running_loop().time() < deadline:
        leg = ctx.room.remote_participants.get(identity)
        if leg is None or leg.attributes.get("sip.callStatus") != "automation":
            return
        await asyncio.sleep(0.25)


async def _refer(
    ds: Dataset, target: Target, caller: rtc.RemoteParticipant
) -> TransferResult:
    uri = refer_uri(ds, target)
    if uri is None:
        logger.error("cannot transfer to %s: pbx_main_number is not configured", target)
        return TransferResult(False, reason="main_number_not_configured")
    ctx = get_job_context()
    try:
        await ctx.api.sip.transfer_sip_participant(
            api.TransferSIPParticipantRequest(
                participant_identity=caller.identity,
                room_name=ctx.room.name,
                transfer_to=uri,
                play_dialtone=False,
                ringing_timeout=Duration(seconds=RINGING_TIMEOUT_SECONDS),
            )
        )
    except api.SipCallError as error:
        logger.error(
            "blind transfer to %s rejected: reason=%s sip=%s %s",
            uri,
            error.sip_transfer_reason,
            error.sip_status_code,
            error.sip_status,
        )
        return TransferResult(
            False, reason=str(error.sip_transfer_reason or error.sip_status_code)
        )
    except Exception as error:
        logger.exception("blind transfer to %s failed", uri)
        return TransferResult(False, reason=type(error).__name__)
    logger.info("blind transfer: handed the caller to %s", uri)
    return TransferResult(True)


async def _bridge(
    ds: Dataset, target: Target, caller: rtc.RemoteParticipant
) -> TransferResult:
    plan = dial_plan(ds, target)
    if plan is None:
        logger.error("cannot transfer to %s: pbx_main_number is not configured", target)
        return TransferResult(False, reason="main_number_not_configured")
    trunk = os.environ.get("LIVEKIT_SIP_OUTBOUND_TRUNK")
    if not trunk:
        logger.error(
            "cannot transfer to %s: LIVEKIT_SIP_OUTBOUND_TRUNK is not set", target
        )
        return TransferResult(False, reason="outbound_trunk_not_configured")

    number, tones = plan
    ctx = get_job_context()
    identity = f"transfer-{caller.identity}"
    try:
        await ctx.api.sip.create_sip_participant(
            api.CreateSIPParticipantRequest(
                sip_trunk_id=trunk,
                sip_call_to=number,
                room_name=ctx.room.name,
                participant_identity=identity,
                participant_name="Transfer",
                dtmf=tones or "",
                play_ringtone=True,
                wait_until_answered=True,
                ringing_timeout=Duration(seconds=RINGING_TIMEOUT_SECONDS),
            )
        )
    except api.TwirpError as error:
        logger.error("transfer to %s failed: %s %s", target, error.code, error.message)
        return TransferResult(False, reason=str(error.code))
    except Exception as error:
        logger.exception("transfer to %s failed", target)
        return TransferResult(False, reason=type(error).__name__)

    if tones:
        pause = tones.count("w") / HALF_SECOND_PAUSES_PER_SECOND
        await _wait_for_tones(identity, pause + TONES_GRACE_SECONDS)
    logger.info("bridge transfer: transferred the caller to %s (%s)", target, number)
    # The agent leaves; the caller and the dialed leg stay connected in the room.
    ctx.shutdown(reason="transferred")
    return TransferResult(True)


async def transfer_call(ds: Dataset, target: Target) -> TransferResult:
    caller = _sip_participant()
    if caller is None:
        # Console, Agent Console and tests have no phone leg to move.
        logger.warning(
            "[dry run] would transfer the caller to %s (%s)",
            target,
            transfer_mode(ds, target),
        )
        return TransferResult(True, dry_run=True)
    if transfer_mode(ds, target) == "blind":
        return await _refer(ds, target, caller)
    return await _bridge(ds, target, caller)


async def hang_up() -> None:
    ctx = get_job_context()
    if ctx is None or _sip_participant() is None:
        logger.warning("[dry run] would end the call")
        return
    await ctx.delete_room()
