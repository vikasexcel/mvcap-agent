import json
import logging
import os
import textwrap

from dotenv import load_dotenv
from google.genai import types as genai_types
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    ConversationItemAddedEvent,
    JobContext,
    RunContext,
    STTContextOptions,
    TurnHandlingOptions,
    cli,
    function_tool,
    inference,
    llm,
    room_io,
    tts,
)
from livekit.plugins import ai_coustics, elevenlabs, google

import people
from dataset import Dataset, Target
from rules import Outcome, resolve, rule_index
from store import load_dataset
from transfer import hang_up, transfer_call

logger = logging.getLogger("agent")

load_dotenv(".env.local")

# Models are switchable by environment variable while we tune latency and voice. With a
# GOOGLE_API_KEY (the client's own account) the LLM and voice run on it; without one they fall
# back to LiveKit Inference so local development still works.
# gemini-3.8-flash took 4 to 6 s to its first token on our prompt; 3.5-flash with minimal thinking
# took about 2 s (benchmarked 2026-11-16).
LLM_MODEL = os.environ.get("MVCAP_LLM", "gemini-3.5-flash")
LLM_THINKING = os.environ.get("MVCAP_LLM_THINKING", "MINIMAL")  # empty = model default
# Gemini rejects request deadlines under 10 s; past this the Inference model answers instead.
LLM_ATTEMPT_TIMEOUT_SECONDS = 10.0
STT_MODEL = os.environ.get("MVCAP_STT", "assemblyai/universal-3-6-pro")
# Primary voice: ElevenLabs on the client's account (about 0.2 s to first audio against about
# 1 s for Gemini, benchmarked 2026-11-17). Erinome is the fallback and the voice without Eleven keys.
ELEVEN_MODEL = os.environ.get("MVCAP_ELEVEN_MODEL", "eleven_flash_v2_5")
TTS_MODEL = os.environ.get("MVCAP_TTS", "gemini-3.8-flash-tts")
TTS_VOICE = os.environ.get("MVCAP_TTS_VOICE", "Erinome")  # chosen by the client
TTS_STYLE = (
    "Speak in a warm, friendly voice at a natural, conversational pace, like a kind receptionist. "
    "Say exactly the given words and add nothing."
)
INFERENCE_LLM = "google/gemini-3.5-flash"
INFERENCE_TTS = "fishaudio/s2.1-pro"
INFERENCE_VOICE = "fa4c9eb3dccc4806b382b40d61c6b10a"


def build_llm():
    if not os.environ.get("GOOGLE_API_KEY"):
        return inference.LLM(model=INFERENCE_LLM)
    thinking = (
        genai_types.ThinkingConfig(thinking_level=LLM_THINKING)
        if LLM_THINKING
        else None
    )
    primary = google.LLM(
        model=LLM_MODEL,
        **({"thinking_config": thinking} if thinking else {}),
    )
    # The client's Gemini key can time out or run out of credit mid-call; fall back to Inference.
    return llm.FallbackAdapter(
        [primary, inference.LLM(model=INFERENCE_LLM)],
        attempt_timeout=LLM_ATTEMPT_TIMEOUT_SECONDS,
    )


def build_tts():
    gemini = None
    if os.environ.get("GOOGLE_API_KEY"):
        gemini = google.beta.GeminiTTS(
            model=TTS_MODEL, voice_name=TTS_VOICE, instructions=TTS_STYLE
        )
    if os.environ.get("ELEVEN_API_KEY") and os.environ.get("ELEVEN_VOICE_ID"):
        eleven = elevenlabs.TTS(
            voice_id=os.environ["ELEVEN_VOICE_ID"], model=ELEVEN_MODEL
        )
        # If ElevenLabs fails mid-call the caller hears Erinome instead of silence.
        return tts.FallbackAdapter([eleven, gemini] if gemini else [eleven])
    if gemini:
        return gemini
    return inference.TTS(model=INFERENCE_TTS, voice=INFERENCE_VOICE)


STT_KEYTERM_LIMIT = 100  # unverified provider limit: confirm on a live call


def build_instructions(ds: Dataset) -> str:
    notices = [u["text"] for u in ds.status_updates if not u.get("applies_to")]
    notice_block = "\n".join(f"- {n}" for n in notices) or "- none"
    hours = ds.setting("office_hours_statement", "none")
    return (
        textwrap.dedent(
            """\
        You are the phone receptionist for Miami Valley Community Action Partnership (MVCAP). Callers
        are often in a hard moment, so be calm, kind, patient and brief. The greeting has already been
        spoken, so do not greet the caller again. This is a voice call: plain spoken sentences, no
        lists or formatting, one question at a time.

        # How you work
        Your job is to work out what the caller needs and call the right tool. The tools speak the
        official MVCAP wording and do the transferring or hanging up themselves.

        - If the caller asks for a person by name, call find_person. If it returns one exact match, call
          transfer_to_person with that id. If the match is approximate, first confirm the name with
          the caller ("Did you mean Kevin Reeves?") and transfer only after they say yes. If it returns several, ask the caller which one (use the
          titles, or ask for a last name). If it returns none, say you couldn't find that name and ask
          them to repeat it once; after that, call escalate_to_human.
        - For anything else, choose the closest keyword from the list below and call handle_request
          with that keyword exactly as written. Pick from what the caller said. If they mention several
          needs, handle the most urgent one first.
        - If handle_request says it asked a question, stay silent and wait for the caller's answer.
          Then call handle_request again with the same keyword and the answer set to exactly one of
          the listed options (for a county, the county name only). Never ask that question yourself.
        - After a tool speaks, do not repeat, summarize or add to what it said. If it reports that the
          call was transferred or ended, say nothing more.
        - If a tool says the message was spoken and the call continues, ask what else the caller needs.
        - If the request is clearly not something MVCAP does, or no keyword fits, call escalate_to_human
          right away. Do not list services or suggest programs. If the request is only unclear, ask one
          short clarifying question first; if it is still unclear, call escalate_to_human. Never guess
          a keyword that doesn't fit.
        - When the caller says they're finished or says goodbye, call end_call, which says goodbye itself.

        # Rules you must never break
        - Never say, spell or guess an extension, a direct phone number, or any detail about a staff
          member that a tool did not return. Only tools speak numbers.
        - Never invent program details, eligibility, hours or policies. The only facts you may state
          yourself are under "Facts you may state" below. If you don't know, escalate.
        - If someone describes an immediate danger to life, tell them to hang up and call 911 now.
        - Send callers to the website when a tool's wording does, and never promise outcomes.

        # Keywords (call handle_request with the first name on each line)
        """
        )
        + rule_index(ds)
        + textwrap.dedent(
            f"""

        # Facts you may state
        - {hours}

        # Current notices (background only; tools speak the ones that apply)
        {notice_block}
        """
        )
    )


def stt_keyterms(ds: Dataset) -> list[str]:
    terms = ["MVCAP", "HEAP", "PIPP", "PRC", "Weatherization", "Homefull", "Oberer"]
    seen = {t.lower() for t in terms}
    for person in ds.directory:
        for name in (person["last_name"], person.get("first_preferred")):
            if name and name.lower() not in seen and len(terms) < STT_KEYTERM_LIMIT:
                seen.add(name.lower())
                terms.append(name)
    return terms


class Receptionist(Agent):
    def __init__(self, ds: Dataset) -> None:
        super().__init__(
            llm=build_llm(),
            instructions=build_instructions(ds),
        )
        self.ds = ds

    async def _say(self, parts: list[str]) -> None:
        text = " ".join(p for p in parts if p)
        if text:
            await self.session.say(text, allow_interruptions=False)

    async def _transfer(self, target: Target) -> None:
        result = await transfer_call(self.ds, target)
        if not result.ok:
            await self._fail_over(result.reason)

    async def _fail_over(self, reason: str | None) -> None:
        """A transfer failed: try a human, otherwise say so and end the call."""
        logger.error("transfer failed (%s); failing over", reason)
        human = self.ds.setting("human_fallback_number")
        if human and (await transfer_call(self.ds, Target("phone", human))).ok:
            return
        await self._say([self.ds.setting("transfer_failed_message", "")])
        await hang_up()

    async def _perform(self, outcome: Outcome) -> str | None:
        """Speak, then transfer or end. Returns None (no model reply) unless the call continues."""
        await self._say(outcome.speak)
        if outcome.then == "end":
            await hang_up()
            return None
        if outcome.then == "transfer" and outcome.target:
            await self._transfer(outcome.target)
            return None
        return json.dumps(
            {
                "result": "message spoken; the call continues",
                "next": "ask what else the caller needs",
            }
        )

    # Tools that speak scripted wording return None afterwards: the docs define that as "record an
    # empty result and ask for no reply", so the model can't talk over or repeat the script.
    # Tools that transfer or hang up call disallow_interruptions() first, because they change the call.

    @function_tool
    async def handle_request(
        self, context: RunContext, keyword: str, answer: str | None = None
    ) -> str | None:
        """Handle a caller's request using MVCAP's official script. Pass the closest keyword from the
        keyword list. If the tool says it asked a question, wait for the caller's reply and call this
        again with the same keyword and answer set to exactly one of the listed options. The tool
        speaks, transfers and ends the call itself.

        Args:
            keyword: A keyword exactly as written in the keyword list.
            answer: The caller's answer to the question the tool asked, as one of the listed options.
        """
        context.disallow_interruptions()
        outcome = resolve(self.ds, keyword, answer)
        logger.info(
            "handle_request keyword=%r answer=%r -> %s %s",
            keyword,
            answer,
            outcome.status,
            outcome.rule,
        )
        if outcome.status == "unknown":
            return json.dumps(
                {
                    "result": "unknown keyword",
                    "closest": outcome.suggestions,
                    "next": "pick a listed keyword, or call escalate_to_human",
                }
            )
        if outcome.status == "invalid_answer":
            return json.dumps(
                {
                    "result": "answer not recognized",
                    "valid_answers": outcome.options,
                    "next": "ask the caller again, then pass one valid answer",
                }
            )
        if outcome.status == "need_answer":
            await self._say(outcome.speak)
            return None  # the question was spoken; wait for the caller
        return await self._perform(outcome)

    @function_tool
    async def find_person(self, context: RunContext, name: str) -> str:
        """Look up a staff member the caller asked for by name. Returns matching people (never their
        extensions). Use the returned id with transfer_to_person.

        Args:
            name: The name as the caller said it, first name, last name, or both.
        """
        matches = people.search(self.ds, name)
        logger.info("find_person %r -> %d match(es)", name, len(matches))
        return json.dumps(
            {
                "matches": [
                    {
                        "id": p.id,
                        "name": p.display,
                        "title": p.title,
                        "match": "exact" if p.score >= people.EXACT else "approximate",
                    }
                    for p in matches
                ]
            }
        )

    @function_tool
    async def transfer_to_person(
        self, context: RunContext, person_id: int
    ) -> str | None:
        """Transfer the caller to the staff member with this id, as returned by find_person.

        Args:
            person_id: The id from find_person.
        """
        context.disallow_interruptions()
        person = people.get(self.ds, person_id)
        if person is None:
            return json.dumps(
                {"result": "no such person", "next": "call find_person again"}
            )
        if person.target is None:
            logger.warning(
                "%s cannot be transferred: %s", person.display, person.blocked
            )
            return json.dumps(
                {
                    "result": "this person cannot be reached by transfer",
                    "next": "call escalate_to_human",
                }
            )
        await self._say(
            [
                self.ds.setting("default_transfer_message", ""),
                self.ds.setting("voicemail_note", ""),
            ]
        )
        await self._transfer(person.target)
        return None

    @function_tool
    async def escalate_to_human(self, context: RunContext) -> None:
        """Hand the call to a human team member. Use when no keyword fits, the request is unclear
        after one clarifying question, a name can't be found, or the caller asks for a person."""
        context.disallow_interruptions()
        human = self.ds.setting("human_fallback_number")
        if not human:
            logger.error("escalate_to_human: human_fallback_number is not configured")
            await self._say([self.ds.setting("transfer_failed_message", "")])
            await hang_up()
            return
        await self._say([self.ds.setting("fallback_message", "")])
        await self._transfer(Target("phone", human))

    @function_tool
    async def end_call(self, context: RunContext) -> None:
        """End the call when the caller is finished or says goodbye. This tool says goodbye itself."""
        context.disallow_interruptions()
        await self._say([self.ds.setting("goodbye_message", "")])
        await hang_up()


server = AgentServer()


@server.rtc_session(agent_name="mvcap-agent")
async def my_agent(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}

    ds = await load_dataset()

    session = AgentSession(
        stt=inference.STT(model=STT_MODEL, language="en"),
        # Staff names and program acronyms are what speech recognition mishears most.
        stt_context_options=STTContextOptions(
            keyterms=stt_keyterms(ds),
            keyterm_detection={"enabled": True},
        ),
        tts=build_tts(),
        turn_handling=TurnHandlingOptions(
            turn_detection=inference.TurnDetector(),
            # Off on purpose: the tools transfer and hang up, so no speculative responses.
            preemptive_generation={"enabled": False},
        ),
    )

    @session.on("conversation_item_added")
    def _log_turn_metrics(event: ConversationItemAddedEvent) -> None:
        # Per-turn latency (LLM first token, TTS first audio, end-to-end) for tuning pauses.
        metrics = getattr(event.item, "metrics", None)
        if metrics:
            logger.info("turn metrics role=%s %s", event.item.role, dict(metrics))

    await session.start(
        agent=Receptionist(ds),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=ai_coustics.audio_enhancement(
                    model=ai_coustics.EnhancerModel.QUAIL_VF_S
                ),
            ),
        ),
    )

    await ctx.connect()

    # The greeting is the client's exact wording, so it is spoken, not generated.
    await session.say(ds.setting("greeting"), allow_interruptions=False)


if __name__ == "__main__":
    cli.run_app(server)
