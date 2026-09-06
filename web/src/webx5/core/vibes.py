"""DI wiring for the vibes feature."""

from webx5.crud.vibe import VibeRepository
from webx5.services.vibe import VibeService

vibe_repo = VibeRepository()
vibe_service = VibeService(repo=vibe_repo)
