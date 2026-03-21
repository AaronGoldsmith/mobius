"""Cross-family judge panel for evaluating agent outputs."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import string

from mobius.config import MobiusConfig
from mobius.models import CandidateRanking, JudgeVerdict
from mobius.providers.base import ProviderResult
from mobius.runner import run_judge

logger = logging.getLogger(__name__)

JUDGE_SYSTEM_PROMPT = """You are an expert judge evaluating competing solutions to a task.
You will receive a task description and multiple candidate solutions labeled with letters (A, B, C, etc.).

Evaluate each candidate on three criteria, scoring 0-10 for each:
- **Correctness**: Does it solve the task accurately? Are there bugs or errors?
- **Quality**: Is it well-structured, readable, and following best practices?
- **Completeness**: Does it fully address all aspects of the task?

You MUST respond with valid JSON in exactly this format:
{
    "rankings": [
        {"candidate": "A", "correctness": 8, "quality": 7, "completeness": 9, "total": 24},
        {"candidate": "B", "correctness": 6, "quality": 8, "completeness": 7, "total": 21}
    ],
    "winner": "A",
    "reasoning": "Brief explanation of why the winner is best and key differences between candidates."
}

Be fair and objective. Judge the output quality, not the style. Evaluate based on the task requirements.
Do NOT output anything other than the JSON object."""


def _build_judge_prompt(
    task: str,
    outputs: dict[str, str],
    label_map: dict[str, str],
) -> str:
    """Build the prompt for a judge, with outputs labeled and shuffled."""
    lines = [f"## Task\n{task}\n\n## Candidate Solutions\n"]
    for agent_id, label in label_map.items():
        output = outputs[agent_id]
        lines.append(f"### Candidate {label}\n```\n{output}\n```\n")
    return "\n".join(lines)


def _parse_verdict(raw: str, label_to_agent: dict[str, str]) -> JudgeVerdict | None:
    """Parse judge output into a structured verdict."""
    # Try to extract JSON from the response
    try:
        # Handle markdown code blocks
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in the text
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(raw[start:end])
            except json.JSONDecodeError:
                logger.error("Could not parse judge output as JSON")
                return None
        else:
            return None

    try:
        # Parse rankings into CandidateRanking objects
        rankings = []
        for r in data.get("rankings", []):
            rankings.append(CandidateRanking(
                candidate=str(r.get("candidate", "")),
                correctness=float(r.get("correctness", 0)),
                quality=float(r.get("quality", 0)),
                completeness=float(r.get("completeness", 0)),
                total=float(r.get("total", 0)),
            ))

        # Map labels back to agent IDs in scores
        scores = {}
        for ranking in rankings:
            agent_id = label_to_agent.get(ranking.candidate, "")
            if agent_id:
                scores[agent_id] = ranking.total

        winner_label = str(data.get("winner", ""))

        return JudgeVerdict(
            rankings=rankings,
            winner=winner_label,
            reasoning=data.get("reasoning", ""),
            scores=scores,
        )
    except Exception as e:
        logger.error("Error structuring judge verdict: %s", e)
        return None


class JudgePanel:
    """Cross-family judge panel with consensus voting."""

    def __init__(self, config: MobiusConfig):
        self.config = config

    async def evaluate(
        self,
        task: str,
        outputs: dict[str, str],
    ) -> tuple[JudgeVerdict | None, list[str]]:
        """Run the cross-family judge panel.

        Returns (consensus_verdict, judge_models_used).
        Each judge gets independently shuffled candidate order.
        """
        if not outputs:
            logger.warning("No outputs to judge")
            return None, []

        agent_ids = list(outputs.keys())
        labels = list(string.ascii_uppercase[: len(agent_ids)])

        verdicts: list[tuple[JudgeVerdict, str]] = []  # (verdict, model)

        # Prepare per-judge data (independent shuffle per judge)
        judge_tasks = []
        judge_meta = []  # (provider, model, label_to_agent)

        for judge_config in self.config.judge_models:
            provider = judge_config["provider"]
            model = judge_config["model"]

            # Independent shuffle per judge
            shuffled_ids = list(agent_ids)
            random.shuffle(shuffled_ids)
            label_map = dict(zip(shuffled_ids, labels))
            label_to_agent = {v: k for k, v in label_map.items()}

            prompt = _build_judge_prompt(task, outputs, label_map)

            judge_tasks.append(run_judge(
                prompt=prompt,
                system_prompt=JUDGE_SYSTEM_PROMPT,
                provider_name=provider,
                model=model,
            ))
            judge_meta.append((provider, model, label_to_agent))

        # Run all judges in parallel
        results = await asyncio.gather(*judge_tasks, return_exceptions=True)

        judge_models_used = []

        for result, (provider, model, label_to_agent) in zip(results, judge_meta):
            if isinstance(result, Exception):
                logger.warning("Judge %s/%s raised: %s", provider, model, result)
                continue

            if not result.success:
                logger.warning("Judge %s/%s failed: %s", provider, model, result.error)
                continue

            verdict = _parse_verdict(result.output, label_to_agent)
            if verdict:
                verdicts.append((verdict, f"{provider}/{model}"))
                judge_models_used.append(f"{provider}/{model}")
                logger.info(
                    "Judge %s/%s picked winner: %s (mapped to agent)",
                    provider,
                    model,
                    verdict.winner,
                )

        if not verdicts:
            logger.error("All judges failed")
            return None, judge_models_used

        # Consensus: majority vote on winner
        return self._find_consensus(verdicts, agent_ids), judge_models_used

    def _find_consensus(
        self,
        verdicts: list[tuple[JudgeVerdict, str]],
        agent_ids: list[str],
    ) -> JudgeVerdict:
        """Find consensus among judges via majority vote or score aggregation."""
        # Count votes for each winner (by agent ID, not label)
        winner_votes: dict[str, int] = {}
        all_scores: dict[str, list[float]] = {aid: [] for aid in agent_ids}
        reasonings: list[str] = []

        for verdict, model in verdicts:
            # Map the winner label back to find the agent ID from scores
            for agent_id, score in verdict.scores.items():
                if agent_id:
                    all_scores[agent_id].append(score)

            # Find the winning agent ID (highest score in this verdict)
            if verdict.scores:
                winner_id = max(verdict.scores, key=lambda k: verdict.scores.get(k, 0))
                if winner_id:
                    winner_votes[winner_id] = winner_votes.get(winner_id, 0) + 1

            reasonings.append(f"[{model}] {verdict.reasoning}")

        # Majority vote
        if winner_votes:
            consensus_winner = max(winner_votes, key=lambda k: winner_votes[k])
        else:
            # Fallback: highest average score
            avg_scores = {
                aid: (sum(scores) / len(scores) if scores else 0)
                for aid, scores in all_scores.items()
            }
            consensus_winner = max(avg_scores, key=lambda k: avg_scores[k])

        # Aggregate scores (average across judges)
        final_scores = {
            aid: round(sum(scores) / len(scores), 2) if scores else 0.0
            for aid, scores in all_scores.items()
        }

        return JudgeVerdict(
            rankings=[],  # Not meaningful for consensus
            winner=consensus_winner,  # This is now an agent_id
            reasoning="\n\n".join(reasonings),
            scores=final_scores,
        )
