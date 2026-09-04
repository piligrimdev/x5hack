from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from webx5.entities.challenge_log import ChallengeGenerationLog


class ChallengeLogRepository:
    def record(
        self,
        session: Session,
        *,
        user_id: uuid.UUID,
        challenge_type: str,
        script_result: dict,
        prompt: str | None = None,
        response: str | None = None,
    ) -> uuid.UUID:
        """Persist one audit row for a single call of `generate_challenge_for_user`.

        `script_result` — the dict returned by `synth.challenges.generate_challenge_for_user`.
        `prompt` / `response` — captured raw LLM I/O (available only for path='personal').
        """
        entry = ChallengeGenerationLog(
            user_id=user_id,
            task_id=None,
            model=script_result.get("model"),
            prompt=prompt,
            response=response,
            path=script_result.get("path", "unknown"),
            reasoning=script_result.get("reasoning"),
            error=script_result.get("error"),
            challenge_type=challenge_type,
        )
        session.add(entry)
        session.flush()
        return entry.id

    def attach_task(self, session: Session, log_id: uuid.UUID, task_id: uuid.UUID) -> None:
        entry = session.get(ChallengeGenerationLog, log_id)
        if entry is not None:
            entry.task_id = task_id
            session.flush()
