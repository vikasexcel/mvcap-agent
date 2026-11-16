"""Creates the LiveKit side of the phone line: inbound trunk, outbound trunk, dispatch rule.

    uv run python scripts/setup_telephony.py            # show what would be created
    uv run python scripts/setup_telephony.py --apply    # create it

Reads from .env.local: LIVEKIT_URL/KEY/SECRET, MVCAP_PHONE_NUMBER (the Telnyx number, E.164),
TELNYX_SIP_USER and TELNYX_SIP_PASSWORD (the credentials set on the Telnyx connection).
Prints the outbound trunk id: set it as LIVEKIT_SIP_OUTBOUND_TRUNK on the agent.
"""

import asyncio
import os
import sys

from dotenv import load_dotenv
from google.protobuf.duration_pb2 import Duration
from livekit import api
from livekit.protocol import room, sip

AGENT_NAME = "mvcap-agent"
# Must exceed the transfer ringing timeout (30 s) so a ringing transfer isn't cut off.
MEDIA_TIMEOUT_SECONDS = 60


def build(number: str, user: str, password: str):
    media = sip.SIPMediaConfig(media_timeout=Duration(seconds=MEDIA_TIMEOUT_SECONDS))
    inbound = sip.SIPInboundTrunkInfo(
        name="MVCAP inbound (Telnyx)", numbers=[number], media=media
    )
    outbound = sip.SIPOutboundTrunkInfo(
        name="MVCAP outbound (Telnyx)",
        address="sip.telnyx.com",
        transport=sip.SIPTransport.SIP_TRANSPORT_TCP,
        numbers=[number],
        auth_username=user,
        auth_password=password,
        # Telnyx needs the username in the first INVITE (LiveKit Telnyx quickstart, step 4).
        headers_to_attributes={"X-Telnyx-Username": user},
        media=media,
    )
    return inbound, outbound


async def main(apply: bool) -> None:
    load_dotenv(".env.local")
    number = os.environ["MVCAP_PHONE_NUMBER"]
    user = os.environ["TELNYX_SIP_USER"]
    password = os.environ["TELNYX_SIP_PASSWORD"]
    inbound, outbound = build(number, user, password)
    print(f"inbound trunk : {inbound.name} for {number}")
    print(f"outbound trunk: {outbound.name} via {outbound.address} (TCP)")
    print(f"dispatch rule : each call -> its own room, agent '{AGENT_NAME}'")
    if not apply:
        print("\nDry run. Add --apply to create these.")
        return
    lk = api.LiveKitAPI()
    try:
        inb = await lk.sip.create_inbound_trunk(
            api.CreateSIPInboundTrunkRequest(trunk=inbound)
        )
        out = await lk.sip.create_outbound_trunk(
            api.CreateSIPOutboundTrunkRequest(trunk=outbound)
        )
        rule = await lk.sip.create_dispatch_rule(
            api.CreateSIPDispatchRuleRequest(
                name="MVCAP calls to the agent",
                trunk_ids=[inb.sip_trunk_id],
                rule=api.SIPDispatchRule(
                    dispatch_rule_individual=api.SIPDispatchRuleIndividual(
                        room_prefix="call-"
                    )
                ),
                room_config=room.RoomConfiguration(
                    agents=[api.RoomAgentDispatch(agent_name=AGENT_NAME)]
                ),
            )
        )
    finally:
        await lk.aclose()
    print(f"\ninbound trunk id : {inb.sip_trunk_id}")
    print(f"outbound trunk id: {out.sip_trunk_id}  <- LIVEKIT_SIP_OUTBOUND_TRUNK")
    print(f"dispatch rule id : {rule.sip_dispatch_rule_id}")


if __name__ == "__main__":
    asyncio.run(main("--apply" in sys.argv))
