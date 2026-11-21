from types import SimpleNamespace

import discord

from sherpa.bot import SherpaBot, ready_embed, verb
from sherpa.config import Settings


def test_commands_and_roles():
    s = Settings(owner_discord_id=1, admin_role_id=10, household_role_id=20)
    bot = SherpaBot(s, sherpa=None)
    names = {c.name for c in bot.tree.get_commands()}
    assert names == {"movie", "series", "anime", "music", "book", "comic", "manga", "downloads", "mine", "space",
                     "link"}
    assert not bot.intents.message_content      # Sherpa doesn't read messages

    class FakeMember(discord.Member):
        def __init__(self, uid, *roles):
            self._uid, self._roles_ = uid, [SimpleNamespace(id=r) for r in roles]
        id = property(lambda self: self._uid)
        roles = property(lambda self: self._roles_)

    assert bot.is_admin(FakeMember(5, 10)) and bot.is_household(FakeMember(5, 10))
    assert not bot.is_admin(FakeMember(6, 20)) and bot.is_household(FakeMember(6, 20))
    assert not bot.is_household(FakeMember(7, 99))
    owner = SimpleNamespace(id=1, roles=[])
    assert bot.is_admin(owner) and bot.is_household(owner)


def test_ready_embed_and_verbs():
    e = ready_embed({"kind": "book", "title": "Dune", "year": 1965, "requested_by_name": "Sam", "size_bytes": 2048,
                     "details": {"format": "audiobook"}})
    assert "listen to" in e.description and "Sam" in e.description and e.footer.text == "Book · 2 KB"
    assert verb("anime") == "watch" and verb("manga") == "read" and verb("music") == "listen to"
