---
name: mobius-judge
description: Act as an Opus judge for Mobius competition outputs. Use when the user says "judge this", "mobius judge", or when the mobius-run skill needs judging without API costs.
user-invocable: true
argument-hint: [match-id or 'latest']
allowed-tools: Bash, Read, Glob, Grep, Write
---

# Mobius Judge (Local Opus)

You ARE the judge. You are Claude Opus running locally via the user's Pro subscription — this costs $0 in API calls. Use your full intelligence to evaluate competing agent outputs.

## What to do

1. Load the match data:
```bash
cd /c/Users/aargo/Development/mobius && python -c "
from mobius.config import get_config
from mobius.db import init_db, row_to_dict
import json

config = get_config()
conn, _ = init_db(config)
row = conn.execute('SELECT * FROM matches ORDER BY created_at DESC LIMIT 1').fetchone()
if row:
    d = row_to_dict(dict(row))
    print('TASK:', d['task_description'])
    print('---OUTPUTS---')
    outputs = d.get('outputs', {})
    if isinstance(outputs, str):
        outputs = json.loads(outputs)
    for agent_id, output in outputs.items():
        print(f'\\nAGENT {agent_id[:8]}:')
        print(output[:2000])
else:
    print('No matches found')
"
```

2. **Read all the outputs carefully.** You are judging on:
   - **Correctness** (0-10): Does it solve the task accurately?
   - **Quality** (0-10): Is it well-structured, readable, best practices?
   - **Completeness** (0-10): Does it fully address all aspects?

3. **Provide your verdict.** Be fair, objective, and detailed in your reasoning.

4. **Write the verdict back to the database:**
```bash
cd /c/Users/aargo/Development/mobius && python -c "
from mobius.config import get_config
from mobius.db import init_db
import json

config = get_config()
conn, _ = init_db(config)

# Get latest match
row = conn.execute('SELECT id, competitor_ids FROM matches ORDER BY created_at DESC LIMIT 1').fetchone()
match_id = row['id']

# Update with your verdict
conn.execute('''
    UPDATE matches SET
        winner_id = ?,
        scores = ?,
        judge_reasoning = ?,
        judge_models = ?,
        voided = 0
    WHERE id = ?
''', (
    'WINNER_AGENT_ID',
    json.dumps({'agent1_id': SCORE1, 'agent2_id': SCORE2}),
    'YOUR DETAILED REASONING HERE',
    json.dumps(['local-opus-judge']),
    match_id,
))
conn.commit()
print('Verdict recorded')
"
```

5. Then trigger Elo updates:
```bash
cd /c/Users/aargo/Development/mobius && python -c "
from mobius.config import get_config
from mobius.db import init_db, row_to_dict
from mobius.registry import Registry
from mobius.tournament import Tournament
from mobius.models import MatchRecord
import json

config = get_config()
conn, _ = init_db(config)
registry = Registry(conn, config)
tournament = Tournament(conn, config, registry)

row = conn.execute('SELECT * FROM matches ORDER BY created_at DESC LIMIT 1').fetchone()
match = MatchRecord(**row_to_dict(dict(row)))
# Elo updates happen via tournament.record_match but since it's already recorded,
# manually update ratings
print('Match:', match.id[:8])
print('Winner:', match.winner_id[:8] if match.winner_id else 'none')
print('Done - run mobius leaderboard to see updated rankings')
"
```

## Key Insight

You (Opus) are free on the Pro subscription. The API judges (Gemini, GPT-4o) cost money. For development and testing, use THIS skill as the judge. For production/automated runs, the API judges handle it.

This hybrid approach means:
- Interactive use: Opus judges for free via this skill
- Automated loops: API judges (cross-family) for unbiased results
- Best of both worlds
