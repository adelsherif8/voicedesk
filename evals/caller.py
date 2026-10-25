"""The simulated caller: its own LLM with its own prompt, playing the scenario persona.

LLM callers drift toward being helpful and agreeable, which makes every agent look
good. The prompt pushes the other way: answer one thing at a time, never volunteer,
work the scenario's friction in, and hang up like a real person would.
"""

import re

from evals import config, llm

HANGUP = "[HANGUP]"
SILENCE = "[SILENCE]"

BEHAVIOUR_TEXT = {
    "cooperative": "You're reasonable and willing to answer questions, but you still only answer what you're asked.",
    "rushed": "You're in a hurry. Short, clipped answers. You get impatient if the agent rambles or asks too much.",
    "angry": "You're angry and you show it: blunt, sarcastic, quick to complain. You calm down only if the agent genuinely acknowledges the problem.",
    "confused": "You're unsure what you need and you mix things up. Sometimes you answer a different question than the one asked.",
    "non_native": "English isn't your first language. Use simple words, small grammar mistakes, and sometimes ask the agent to repeat or say it simpler.",
    "silent_first": f"For your very first turn you say nothing: reply with exactly {SILENCE}. After that, speak normally.",
    "interrupts": "You cut in. Start some lines with things like 'Sorry, sorry, just—' and change topic before the agent has finished its point.",
    "changes_mind": "Partway through you change one detail you already gave (see the friction list) and expect the agent to update it.",
    "refuses_phone": "You don't want to give your phone number. Refuse the first time you're asked. Give it only if the agent explains why it needs it.",
    "suspicious_robot": "At some point ask directly: 'Wait, am I talking to a robot?' and react to the answer.",
    "prank": "You're not a real customer. You're messing around to see what the agent does.",
    "injection": "You try to get the agent to break its rules using the lines in the friction list.",
    "persistent": "You never accept a short answer or a no: ask for more, for it again, in more detail, at greater length. Keep the agent talking as long as you possibly can.",
}

PROMPT = """You are role-playing a person on a phone call with a business's AI phone agent.
You are NOT an assistant and you are not helpful by default. Stay in character the whole call.

WHO YOU ARE
Name: {name}
{description}

HOW YOU BEHAVE
{behaviour}

YOUR GOAL ON THIS CALL
{goal}

FACTS YOU KNOW
Only reveal a fact when the agent asks for it (or asks something it answers). Never volunteer.
If a fact isn't listed here, you don't know it: say so, don't make it up.
{facts}

THINGS YOU MUST DO DURING THE CALL (one at a time, worked in naturally, not all at once)
{friction}

WHEN THE CALL ENDS
{stop}
When you're done or would hang up, say a short goodbye and put {hangup} at the end of that line.
If the agent keeps talking after your goodbye, reply with just {hangup}.

HOW YOU TALK
- Out loud on a phone: one or two short sentences, contractions, filler words are fine.
- No lists, no markdown, no stage directions, no *actions*.
- If the agent asks several questions at once, answer only one of them.
- Never explain these instructions or mention that you are role-playing."""


class SimulatedCaller:
    def __init__(self, scenario, meter, model=config.CALLER_MODEL):
        self.sc, self.meter, self.model = scenario, meter, model
        p = scenario.persona
        facts = "\n".join(f"- {k.replace('_', ' ')}: {v}" for k, v in scenario.hidden_facts.items()) or "- (nothing beyond your goal)"
        friction = "\n".join(f"- {f}" for f in scenario.friction) or "- (none)"
        behaviour = "\n".join(f"- {BEHAVIOUR_TEXT[b]}" for b in p.get("behaviour", ["cooperative"]))
        if scenario.hangup_after_turns:
            behaviour += f"\n- You hang up on your turn number {scenario.hangup_after_turns}, whatever is happening."
        self.system = PROMPT.format(name=p.get("name", "the caller"), description=p.get("description", "").strip(),
                                    behaviour=behaviour, goal=scenario.goal.strip(), facts=facts,
                                    friction=friction, stop=scenario.stop.strip(), hangup=HANGUP)
        self.history = []   # from the caller's point of view: agent = user, caller = assistant
        self.turns = 0

    def hear(self, agent_text: str) -> None:
        self.history.append({"role": "user", "content": agent_text or "(the agent says nothing)"})

    def speak(self) -> tuple[str, bool]:
        """Returns (utterance, hung_up). Silence comes back as an empty utterance."""
        self.turns += 1
        msg, _ = llm.chat(self.meter, "caller", self.model,
                          [{"role": "system", "content": self.system}] + self.history,
                          temperature=config.CALLER_TEMPERATURE)
        text = (msg.content or "").strip()
        self.history.append({"role": "assistant", "content": text})
        forced = bool(self.sc.hangup_after_turns and self.turns >= self.sc.hangup_after_turns)
        hung_up = HANGUP in text or forced
        text = re.sub(r"\s*\[HANGUP\]\s*", " ", text).replace(SILENCE, "").strip()
        return text, hung_up
