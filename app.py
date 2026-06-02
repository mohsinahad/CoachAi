import os
import re
import json
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, send_file, jsonify, Response, stream_with_context

app = Flask(__name__)


def parse_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()
    # remove trailing commas before } or ]
    raw = re.sub(r",\s*([}\]])", r"\1", raw)
    return json.loads(raw)

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
RATINGS_FILE  = DATA_DIR / "ratings.json"
EVENTS_FILE   = DATA_DIR / "events.json"
FEEDBACK_FILE = DATA_DIR / "feedback.json"


def log_event(event: str, data: dict = {}) -> None:
    events = json.loads(EVENTS_FILE.read_text()) if EVENTS_FILE.exists() else []
    events.append({"timestamp": datetime.now().isoformat(), "event": event, "data": data})
    EVENTS_FILE.write_text(json.dumps(events, indent=2))

# ─── Toggle this to False and set ANTHROPIC_API_KEY env var when ready ───────
MOCK_MODE = False
LOCAL = os.environ.get("REPLIT_DEPLOYMENT") is None


def get_mock_plan(age_group: str, players: int, duration: int, focus: str, last_week: str) -> dict:
    return {
        "age_group": age_group,
        "players": players,
        "duration": duration,
        "focus": focus,
        "sections": [
            {
                "type": "warmup",
                "title": "Passing Circle",
                "duration": 10,
                "setup": f"Split {players} players into groups of 5–6. Each group forms a circle with one player in the middle.",
                "instructions": [
                    "Outside players pass to the middle player who returns it and pivots to face the next",
                    "Swap the middle player every 90 seconds",
                    "Round 2: middle player must control with one foot, pass with the other",
                    "Round 3: add a verbal call — receiver must shout their name before the ball arrives",
                ],
                "coaching_points": [
                    "Eyes up before receiving — scan early",
                    "Non-kicking foot pointed at the target",
                    "Firm pass along the ground, not floated",
                ],
                "why": "Gets players moving, activates communication, and warms up the passing touch before any pressure is applied.",
            },
            {
                "type": "drill",
                "title": "Pass and Move Gates",
                "duration": 20,
                "setup": "Set up 8 small gates (two cones 1m apart) scattered across a 20x20m area. Players work in pairs.",
                "instructions": [
                    "Each pair has one ball — pass through a gate to score a point",
                    "After passing, both players immediately move to find a new gate",
                    "Challenge: score as many gates as possible in 90 seconds",
                    "Progression: add a first-touch control rule — must control before passing back",
                    f"If last week had issues with {last_week or 'first touch'}: freeze the drill when you see a bad touch and demonstrate the correct technique",
                ],
                "coaching_points": [
                    "Player without the ball moves immediately — no standing still",
                    "Receive the ball on the back foot to create space",
                    "Short sharp pass — not a slow roll",
                ],
                "why": "Forces players to pass AND move simultaneously, building the habit that passing is only half the job.",
            },
            {
                "type": "drill",
                "title": "Rondo — Keep Ball 5v2",
                "duration": 15,
                "setup": "Mark a 10x10m square. 5 players on the outside, 2 defenders in the middle.",
                "instructions": [
                    "Outside players keep possession away from the 2 defenders",
                    "If defenders win the ball, the player who lost it swaps into the middle",
                    "Target: 5 consecutive passes = 1 point for the outside team",
                    "Defenders work in pairs for 90 seconds then rotate",
                    "Progression: limit outside players to 2 touches",
                ],
                "coaching_points": [
                    "Move to create angles — never stand in a straight line",
                    "Support the ball carrier immediately after passing",
                    "Quick decision — know where the next pass goes before the ball arrives",
                ],
                "why": "Rondos are used by every top club in the world. They teach decision-making under pressure in a fun, competitive format.",
            },
            {
                "type": "game",
                "title": f"Small-Sided Game — Combination Goal",
                "duration": duration - 50,
                "setup": f"Two teams of {players // 2}. Standard small-sided pitch with two small goals. Normal rules.",
                "instructions": [
                    "Normal game with one rule change: a goal only counts if it follows a combination of 3+ passes",
                    "Coach counts the passes aloud to build awareness",
                    "Award a bonus point for any goal scored from a one-two (wall pass)",
                    "Stop the game once if you see good passing to celebrate it in front of both teams",
                ],
                "coaching_points": [
                    "Encourage — praise the pass, not just the goal",
                    "Let the game flow, only freeze for a clear teachable moment",
                    "Equal playing time for all — rotate if needed",
                ],
                "why": "Transfers the passing habits from the drills into a real game context where kids are motivated to perform.",
            },
            {
                "type": "cooldown",
                "title": "Cooldown & Team Talk",
                "duration": 5,
                "setup": "Players sit or lie in a circle. Keep it relaxed.",
                "instructions": [
                    "2 minutes of light stretching — quads, hamstrings, shoulders",
                    "Ask the group: what was the best pass of today?",
                    "Name one thing the team improved on compared to last week",
                    "One thing to practise at home before next session",
                ],
                "coaching_points": [
                    "End on a positive — every player should leave feeling good",
                    "Keep it short — kids switch off after 2 minutes of talking",
                ],
                "why": "Brings the session to a calm close and reinforces the learning through group reflection.",
            },
        ],
    }


EVALUATIONS_FILE = DATA_DIR / "evaluations.json"

EVAL_CRITERIA = [
    ("age_appropriate",  "Age Appropriate",   "Are the drills suitable for this age group physically and cognitively?"),
    ("clarity",          "Clarity",           "Can a volunteer parent with zero coaching experience follow these instructions?"),
    ("session_flow",     "Session Flow",      "Does the session build logically from warmup through to cooldown?"),
    ("time_balance",     "Time Balance",      "Are the time allocations sensible and do they add up correctly?"),
    ("engagement",       "Engagement",        "Would kids this age actually enjoy and stay focused through these drills?"),
    ("focus_alignment",  "Focus Alignment",   "Does every section genuinely work toward the stated session focus?"),
    ("coaching_points",  "Coaching Points",   "Are the coaching cues specific, correct, and actionable for a non-expert?"),
    ("feasibility",      "Feasibility",       "Can this realistically be run with the stated number of players and equipment?"),
]


def evaluate_plan(plan: dict) -> dict:
    if MOCK_MODE:
        return {
            "overall_score": 7.4,
            "overall_comment": "Solid mock session with good structure. Real evaluation will run once API is connected.",
            "criteria": [
                {"key": k, "name": n, "score": 7, "reason": "Mock evaluation — connect API for real scores."}
                for k, n, _ in EVAL_CRITERIA
            ],
        }

    import anthropic, json as _json
    client = anthropic.Anthropic(
        api_key=os.environ.get("AI_INTEGRATIONS_ANTHROPIC_API_KEY"),
        base_url=os.environ.get("AI_INTEGRATIONS_ANTHROPIC_BASE_URL"),
    )

    criteria_text = "\n".join(
        f'{i+1}. {key} (1-10): {desc}'
        for i, (key, _, desc) in enumerate(EVAL_CRITERIA)
    )

    prompt = f"""You are a strict youth soccer coaching expert evaluating an AI-generated session plan.
Score each criterion honestly from 1 to 10. A 7 means genuinely good. A 10 means nothing to improve.

Session details: {plan['age_group']}, {plan['players']} players, {plan['duration']} minutes, focus: {plan['focus']}

Criteria to score:
{criteria_text}

Return raw JSON only — no markdown, no explanation outside the JSON:
{{
  "overall_score": <average of all scores as float>,
  "overall_comment": "<one sentence overall assessment>",
  "criteria": [
    {{"key": "<key>", "name": "<name>", "score": <int 1-10>, "reason": "<one sentence>"}}
  ]
}}

Session plan to evaluate:
{json.dumps(plan, indent=2)}"""

    msg = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )

    result = parse_json(msg.content[0].text)

    evaluations = json.loads(EVALUATIONS_FILE.read_text()) if EVALUATIONS_FILE.exists() else []
    evaluations.append({
        "timestamp": datetime.now().isoformat(),
        "age_group": plan["age_group"],
        "focus":     plan["focus"],
        "players":   plan["players"],
        "duration":  plan["duration"],
        **result,
    })
    EVALUATIONS_FILE.write_text(json.dumps(evaluations, indent=2))

    return result


def get_real_plan(age_group: str, players: int, duration: int, focus: str, last_week: str) -> dict:
    import anthropic

    client = anthropic.Anthropic(
        api_key=os.environ.get("AI_INTEGRATIONS_ANTHROPIC_API_KEY"),
        base_url=os.environ.get("AI_INTEGRATIONS_ANTHROPIC_BASE_URL"),
    )

    age_guidance = {
        "U6":  "Players are 4-6 years old. Focus entirely on fun and basic ball familiarity. No tactics, no positions. Keep every activity under 8 minutes. Use games not drills. Coaching points must be about enjoyment and basic ball contact only.",
        "U8":  "Players are 6-8 years old. Simple skill introduction — dribbling, basic passing, kicking. Fun and confidence first. Coaching points should be very basic: watch the ball, use the inside of your foot. No tactical concepts.",
        "U10": "Players are 8-10 years old. Introduce simple techniques with light competition. Basic passing, movement, small-sided play. Coaching points can include body position and basic awareness of teammates. Keep tactics very simple.",
        "U12": "Players are 10-12 years old. CRITICAL: do NOT coach foot planting, basic ball contact, or beginner technique cues — these players already know them. Focus on TACTICAL concepts: through balls, one-twos, third-man runs, pressing triggers, creating and exploiting space, switching play. Drills must have decision-making pressure. Coaching points must be tactical and intermediate-to-advanced.",
        "U14": "Players are 12-14 years old. High tactical complexity. Focus on positional play, pressing systems, transitions, build-up patterns, movement off the ball. Coaching points must be advanced: timing of runs, compactness in defence, playing through lines.",
        "U16": "Players are 14-16 years old. Near-adult tactical understanding. Sessions should mirror structured semi-professional training. Focus on team shape, high-intensity pressing, clinical finishing, game model concepts. Coaching points must be specific and advanced.",
    }

    prompt = f"""You are an expert youth soccer coach with 20 years experience.
Generate a complete training session plan.

Details:
- Age group: {age_group}
- Players: {players}
- Duration: {duration} minutes
- Main focus: {focus}
- Issue from last session: {last_week or "None"}

AGE GROUP GUIDANCE — follow this strictly, it overrides everything else:
{age_guidance.get(age_group, '')}

Structure:
1. Warmup: 10-15% of total time
2. Main Drill 1: 20-25% of total time
3. Main Drill 2: 20-25% of total time
4. Small-sided game: 30-35% of total time
5. Cooldown: 5 minutes

Return raw JSON only — no markdown, no text outside the JSON:
{{
  "age_group": "{age_group}",
  "players": {players},
  "duration": {duration},
  "focus": "{focus}",
  "sections": [
    {{
      "type": "warmup|drill|game|cooldown",
      "title": "section title",
      "duration": minutes_as_integer,
      "setup": "how to set up the space and players",
      "instructions": ["step 1", "step 2", "step 3"],
      "coaching_points": ["point 1", "point 2"],
      "why": "one sentence explaining why this drill helps"
    }}
  ]
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    return parse_json(message.content[0].text)


@app.route("/", methods=["GET"])
def index():
    log_event("page_view", {"path": "/"})
    return render_template("index.html", plan=None, local=LOCAL)


@app.route("/generate", methods=["POST"])
def generate():
    age_group = request.form.get("age_group", "U10")
    players   = int(request.form.get("players", 12))
    duration  = int(request.form.get("duration", 75))
    focus     = request.form.get("focus", "Passing")
    last_week = request.form.get("last_week", "").strip()

    if MOCK_MODE:
        plan = get_mock_plan(age_group, players, duration, focus, last_week)
    else:
        plan = get_real_plan(age_group, players, duration, focus, last_week)

    return render_template("index.html", plan=plan, evaluation=None, mock=MOCK_MODE, local=LOCAL)


DELIMITER = "\n---NEXT---\n"


@app.route("/stream-plan", methods=["POST"])
def stream_plan():
    age_group = request.form.get("age_group", "U10")
    players   = int(request.form.get("players", 12))
    duration  = int(request.form.get("duration", 75))
    focus     = request.form.get("focus", "Passing")
    last_week = request.form.get("last_week", "").strip()

    def generate():
        meta = {"age_group": age_group, "players": players, "duration": duration, "focus": focus}
        log_event("plan_generated", {"age_group": age_group, "focus": focus, "players": players, "duration": duration})
        yield json.dumps(meta) + DELIMITER

        if MOCK_MODE:
            import time
            plan = get_mock_plan(age_group, players, duration, focus, last_week)
            for section in plan["sections"]:
                time.sleep(0.4)
                yield json.dumps(section) + DELIMITER
            return

        import anthropic
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

        age_guidance = {
            "U6": """Players are 4-6 years old.
- Activities must be GAMES not drills: tag, colours, animals, treasure hunts with a ball. No standing in lines.
- Zero tactics, zero positions, zero formations.
- Every child must have a ball or be actively moving at all times.
- Switch activities every 5-6 minutes — attention span is very short.
- Coaching points: maximum 1 per activity, must be physical and joyful ("kick it as hard as you can!", "dribble to the cone and back").
- The session should feel like playtime that happens to use a ball.""",

            "U8": """Players are 6-8 years old.
- Introduce basic skills (dribbling, passing, shooting) through fun competitive games.
- Every child should have a ball or be actively involved — no long queues.
- Light competition works well: first team to score, beat the clock, score in 3 gates.
- Max 10 minutes per activity before moving on.
- Coaching points: maximum 2 per drill, concrete and physical ("use the inside of your foot", "look at the goal before you shoot").
- Keep instructions short — demonstrate, don't lecture.""",

            "U10": """Players are 8-10 years old.
- They know HOW to kick and pass — now teach WHEN, WHERE, and WHY.
- Every passing drill must include MOVEMENT after the pass — never stationary passing lines.
- Use 2v1 and 3v2 situations to introduce decision-making under light pressure.
- Rondos (3v1, 4v2 in a small grid) are excellent for this age.
- Competition keeps engagement: award points, use scoreboards, create mini-tournaments.
- Coaching points must be specific and observable: "receive on your back foot so you can see the field", "pass to your teammate's front foot", "move immediately after passing — don't watch".
- The small-sided game must include a rule that directly rewards the session focus (e.g. for passing: a bonus point for completing 5 consecutive passes before scoring).
- Avoid abstract language — everything must be something they can immediately do.""",

            "U12": """Players are 10-12 years old.
CRITICAL: Do NOT use basic technique cues — they already know how to pass, dribble, and shoot.
- Focus entirely on TACTICAL concepts: through balls, one-twos, third-man runs, pressing triggers, switching the point of attack, creating and exploiting space behind the defensive line.
- Drills must have pressure and decision-making: defenders, time limits, or numerical disadvantages.
- Use 4v2, 5v2, 6v4 rondos and combination play grids with live defenders.
- Coaching points must be tactical and specific: "play the third-man when the first defender commits to the ball", "trigger the press when the pass goes backwards or to the goalkeeper", "switch play when you see the far side is open".
- The game must replicate a realistic match situation — positional overloads, transition moments, or directional play.
- Challenge them: if a drill feels too easy after 5 minutes, add a defender or reduce the space.""",

            "U14": """Players are 12-14 years old.
- High tactical complexity: positional play, structured pressing, attacking and defensive transitions, combination play.
- Drills should replicate match situations: half-press triggers, building out from the back under pressure, third-man and fourth-man combinations.
- Coaching points: specific tactical cues tied to team shape and game model ("the 8 drops into the half-space when the 6 has the ball", "press when the ball goes to the centre-back's weak foot").
- The game must have positional constraints or transition rules that demand tactical discipline.
- Players can handle multi-phase combinations and should be challenged to think ahead.""",

            "U16": """Players are 14-16 years old.
- Professional-level tactical training. Team shape, structured pressing systems, clinical finishing sequences.
- Every drill should have a clear tactical objective linked to the team's game model.
- Coaching points: precise, measurable, and uncompromising ("the striker's pressing trigger is the centre-back's first touch under pressure — go at 80% intensity immediately").
- Sessions should feel demanding and purposeful — like professional training.""",
        }

        system_prompt = """You are an expert youth soccer coach with 20 years of experience coaching recreational and academy players aged 4-16. You specialise in writing session plans that volunteer parent coaches — with zero formal training — can pick up and run confidently on a Saturday morning.

A great session plan has these qualities:
1. FLOW: each section builds on the previous one. Warmup activates the skill, drills isolate and develop it, game applies it under pressure.
2. CLARITY: setup instructions are specific enough that someone who has never run the drill can set it up in 2 minutes. Include area size, cone layout, player grouping.
3. COACHING POINTS: always observable behaviours, never abstract concepts. Bad example: "communicate with teammates". Good example: "call your teammate's name before you want the ball, and point to where you want it".
4. ENGAGEMENT: every drill has a competitive element — score, time challenge, or consequence. Kids disengage from drills with no stakes.
5. FOCUS ALIGNMENT: every single drill and the game must directly develop the session focus. No filler.
6. TIMING: durations must add up exactly to the total session length. Never pad cooldown beyond 5 minutes."""

        prompt = f"""Generate a youth soccer session plan as 5 JSON objects separated by ---NEXT---

SESSION DETAILS:
- Age group: {age_group}
- Players: {players}
- Duration: {duration} minutes total
- Session focus: {focus}
- Issue from last session: {last_week or "None"}

AGE GROUP RULES (follow strictly — these override everything else):
{age_guidance.get(age_group, '')}

OUTPUT FORMAT — output ONLY raw JSON objects, no markdown, no extra text:
{{"type":"warmup","title":"...","duration":<int>,"setup":"...","instructions":["step 1","step 2","step 3","step 4"],"coaching_points":["specific observable cue 1","specific observable cue 2","specific observable cue 3"],"why":"..."}}
---NEXT---
{{"type":"drill","title":"...","duration":<int>,"setup":"...","instructions":["..."],"coaching_points":["..."],"why":"..."}}
---NEXT---
{{"type":"drill","title":"...","duration":<int>,"setup":"...","instructions":["..."],"coaching_points":["..."],"why":"..."}}
---NEXT---
{{"type":"game","title":"...","duration":<int>,"setup":"...","instructions":["..."],"coaching_points":["..."],"why":"..."}}
---NEXT---
{{"type":"cooldown","title":"...","duration":5,"setup":"...","instructions":["..."],"coaching_points":["..."],"why":"..."}}

QUALITY RULES:
- instructions: minimum 4 steps per section, written for someone who has never coached before
- coaching_points: minimum 3 per section, must be specific and observable — not abstract
- setup: must state area size, number of cones/balls, and how players are organised
- durations: warmup 10-15%, each drill 20-25%, game 30-35%, cooldown 5 min — must total exactly {duration} minutes
- game section: must include a specific rule that rewards the {focus} focus"""

        buffer = ""
        with client.messages.stream(
            model="claude-haiku-4-5-20251001",
            max_tokens=4500,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                buffer += text
                while DELIMITER.strip() in buffer:
                    parts = buffer.split(DELIMITER.strip(), 1)
                    chunk = parts[0].strip()
                    if chunk:
                        try:
                            cleaned = re.sub(r",\s*([}\]])", r"\1", chunk)
                            json.loads(cleaned)
                            yield cleaned + DELIMITER
                        except json.JSONDecodeError:
                            pass
                    buffer = parts[1] if len(parts) > 1 else ""

        if buffer.strip():
            try:
                cleaned = re.sub(r",\s*([}\]])", r"\1", buffer.strip())
                json.loads(cleaned)
                yield cleaned + DELIMITER
            except json.JSONDecodeError:
                pass

    return Response(
        stream_with_context(generate()),
        mimetype="text/plain",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@app.route("/evaluate", methods=["POST"])
def evaluate():
    plan = request.get_json()
    result = evaluate_plan(plan)
    return jsonify(result)


@app.route("/rate", methods=["POST"])
def rate():
    data = request.get_json()
    ratings = json.loads(RATINGS_FILE.read_text()) if RATINGS_FILE.exists() else []
    ratings.append({
        "timestamp": datetime.now().isoformat(),
        "rating":      data.get("rating"),
        "what_worked": data.get("what_worked", ""),
        "what_wrong":  data.get("what_wrong", ""),
        "age_group":   data.get("age_group", ""),
        "focus":       data.get("focus", ""),
    })
    RATINGS_FILE.write_text(json.dumps(ratings, indent=2))
    return jsonify({"saved": True, "total": len(ratings)})


@app.route("/ratings")
def ratings():
    data = json.loads(RATINGS_FILE.read_text()) if RATINGS_FILE.exists() else []
    return jsonify(data)


@app.route("/evaluations")
def evaluations():
    data = json.loads(EVALUATIONS_FILE.read_text()) if EVALUATIONS_FILE.exists() else []
    return jsonify(data)


@app.route("/ratings/clear", methods=["POST"])
def clear_ratings():
    RATINGS_FILE.write_text("[]")
    return jsonify({"cleared": True})


@app.route("/track", methods=["POST"])
def track():
    data = request.get_json(silent=True) or {}
    event = data.pop("event", "unknown")
    log_event(event, data)
    return jsonify({"ok": True})


@app.route("/feedback", methods=["POST"])
def feedback():
    data = request.get_json(silent=True) or {}
    entries = json.loads(FEEDBACK_FILE.read_text()) if FEEDBACK_FILE.exists() else []
    entries.append({
        "timestamp": datetime.now().isoformat(),
        "message":   data.get("message", "").strip(),
        "page":      data.get("page", "/"),
    })
    FEEDBACK_FILE.write_text(json.dumps(entries, indent=2))
    return jsonify({"saved": True})


@app.route("/analytics")
def analytics():
    analytics_key = os.environ.get("ANALYTICS_KEY")
    if not LOCAL:
        if not analytics_key or request.args.get("key") != analytics_key:
            return "", 404

    from collections import defaultdict

    events           = json.loads(EVENTS_FILE.read_text())   if EVENTS_FILE.exists()   else []
    feedback_entries = json.loads(FEEDBACK_FILE.read_text()) if FEEDBACK_FILE.exists() else []
    ratings          = json.loads(RATINGS_FILE.read_text())  if RATINGS_FILE.exists()  else []

    page_views      = sum(1 for e in events if e["event"] == "page_view")
    plans_generated = [e for e in events if e["event"] == "plan_generated"]

    age_counts: dict[str, int]   = defaultdict(int)
    focus_counts: dict[str, int] = defaultdict(int)
    for p in plans_generated:
        age_counts[p["data"].get("age_group", "Unknown")] += 1
        focus_counts[p["data"].get("focus", "Unknown")]   += 1

    daily: dict[str, int] = defaultdict(int)
    for e in events:
        daily[e["timestamp"][:10]] += 1

    avg_rating = round(sum(r["rating"] for r in ratings) / len(ratings), 1) if ratings else 0

    return render_template(
        "analytics.html",
        page_views     = page_views,
        plans_count    = len(plans_generated),
        age_counts     = sorted(age_counts.items()),
        focus_counts   = sorted(focus_counts.items()),
        daily          = sorted(daily.items())[-14:],
        ratings        = list(reversed(ratings[-10:])),
        avg_rating     = avg_rating,
        ratings_count  = len(ratings),
        feedback       = list(reversed(feedback_entries[-20:])),
        local          = LOCAL,
    )


@app.route("/plan")
def business_plan():
    return render_template("plan.html")


@app.route("/progress")
def progress():
    return render_template("progress.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    debug = os.environ.get("REPLIT_DEPLOYMENT") is None
    app.run(host="0.0.0.0", port=port, debug=debug)
