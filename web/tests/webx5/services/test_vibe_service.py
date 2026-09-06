"""Unit tests for VibeService — T035."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from webx5.crud.vibe import VibeRepository
from webx5.services.vibe import VibeService


def _make_vibe(name: str = "Здоровье", llm_context: str = "Фрукты, Овощи"):
    v = MagicMock()
    v.id = uuid.uuid4()
    v.name = name
    v.description = "desc"
    v.llm_context = llm_context
    return v


class TestVibeServiceCreate:
    def test_create_success(self):
        repo = MagicMock(spec=VibeRepository)
        svc = VibeService(repo=repo)
        session = MagicMock()
        vibe = _make_vibe()
        repo.create.return_value = vibe

        result = svc.create(session, name="Здоровье", description="desc", llm_context="ctx")

        repo.create.assert_called_once()
        session.commit.assert_called_once()
        assert result is vibe

    def test_create_duplicate_name_raises_409(self):
        repo = MagicMock(spec=VibeRepository)
        svc = VibeService(repo=repo)
        session = MagicMock()
        repo.create.side_effect = IntegrityError("dup", params=None, orig=Exception())

        with pytest.raises(HTTPException) as exc_info:
            svc.create(session, name="Здоровье", description="desc", llm_context="ctx")

        assert exc_info.value.status_code == 409
        session.rollback.assert_called_once()


class TestVibeServiceGetAll:
    def test_get_all_returns_list(self):
        repo = MagicMock(spec=VibeRepository)
        svc = VibeService(repo=repo)
        session = MagicMock()
        vibes = [_make_vibe("A"), _make_vibe("B")]
        repo.get_all.return_value = vibes

        result = svc.get_all(session)

        assert result == vibes
        repo.get_all.assert_called_once_with(session)


class TestVibeServiceDelete:
    def test_delete_existing_vibe(self):
        repo = MagicMock(spec=VibeRepository)
        svc = VibeService(repo=repo)
        session = MagicMock()
        vibe = _make_vibe()
        repo.get_by_id.return_value = vibe

        svc.delete(session, vibe.id)

        repo.delete.assert_called_once_with(session, vibe)
        session.commit.assert_called_once()

    def test_delete_missing_vibe_raises_404(self):
        repo = MagicMock(spec=VibeRepository)
        svc = VibeService(repo=repo)
        session = MagicMock()
        repo.get_by_id.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            svc.delete(session, uuid.uuid4())

        assert exc_info.value.status_code == 404
