import os
import json
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, send_file, jsonify

app = Flask(__name__)


def parse_json(raw: str) -> dict:
    import re
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
RATINGS_FILE = DATA_DIR / "ratings.json"

# ─── Toggle this to False and set ANTHROPIC_API_KEY env var when ready ───────
MOCK_MODE = False


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
    return render_template("index.html", plan=None)


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

    return render_template("index.html", plan=plan, evaluation=None, mock=MOCK_MODE)


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


@app.route("/plan")
def business_plan():
    return render_template("plan.html")


@app.route("/progress")
def progress():
    return render_template("progress.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("REPLIT_DEPLOYMENT") is None
    app.run(host="0.0.0.0", port=port, debug=debug)
