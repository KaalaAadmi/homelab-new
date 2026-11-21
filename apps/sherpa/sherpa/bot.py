"""The Discord side: slash commands, pick-a-result menus, the Request button, and the
"it's ready" posts."""
from __future__ import annotations

import logging
from typing import Any

import discord
from discord import app_commands
from discord.ext import tasks

from .config import Settings
from .models import Kind, RequestError, Requester, Result
from .service import Sherpa, human_size

log = logging.getLogger(__name__)
COLOURS = {Kind.MOVIE: 0xE5A00D, Kind.SERIES: 0x3B82F6, Kind.ANIME: 0xEC4899, Kind.MUSIC: 0x22C55E,
           Kind.BOOK: 0x8B5CF6, Kind.COMIC: 0xEF4444, Kind.MANGA: 0xF97316}
STATUS_ICON = {"requested": "🕓", "downloading": "⬇️", "available": "✅", "failed": "⚠️", "deleted": "🗑️"}


def verb(kind: str, fmt: str | None = None) -> str:
    if kind in ("movie", "series", "anime"):
        return "watch"
    if kind == "music" or fmt == "audiobook":
        return "listen to"
    return "read"


def clip(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


class SherpaBot(discord.Client):
    def __init__(self, settings: Settings, sherpa: Sherpa):
        super().__init__(intents=discord.Intents.default())   # no message-content access needed
        self.s, self.sherpa = settings, sherpa
        self.tree = app_commands.CommandTree(self)
        self.tree.on_error = self.on_app_command_error
        register_commands(self)

    async def setup_hook(self) -> None:
        guild = discord.Object(id=self.s.guild_id)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        self.sync_loop.change_interval(minutes=max(1, self.s.sync_minutes))
        self.sync_loop.start()

    async def close(self) -> None:
        self.sync_loop.cancel()
        await super().close()

    # ------------------------------------------------------------------ who may do what
    def is_admin(self, user: discord.abc.User) -> bool:
        if user.id == self.s.owner_discord_id:
            return True
        return isinstance(user, discord.Member) and any(r.id == self.s.admin_role_id for r in user.roles)

    def is_household(self, user: discord.abc.User) -> bool:
        if self.is_admin(user):
            return True
        return isinstance(user, discord.Member) and any(r.id == self.s.household_role_id for r in user.roles)

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        original = getattr(error, "original", error)
        if isinstance(original, RequestError):
            msg = str(original)
        elif isinstance(error, app_commands.CheckFailure):
            msg = "That command isn't for you, sorry. Ask Arnav for the Household role."
        else:
            log.exception("command failed", exc_info=original)
            msg = "Something went wrong. It's been logged."
        await reply(interaction, msg)

    # ------------------------------------------------------------------ "it's ready" posts
    @tasks.loop(minutes=15)
    async def sync_loop(self) -> None:
        try:
            newly = await self.sherpa.sync()
        except Exception:
            log.exception("sync failed")
            return
        channel = self.get_channel(self.s.announce_channel_id) if self.s.announce_channel_id else None
        for row in newly:
            if channel is not None:
                await channel.send(embed=ready_embed(row), content=f"<@{row['requested_by']}>"
                                   if row.get("requested_by") else None,
                                   allowed_mentions=discord.AllowedMentions(users=True))
            await self.sherpa.mark_announced(row["id"])

    @sync_loop.before_loop
    async def _wait(self) -> None:
        await self.wait_until_ready()


async def reply(interaction: discord.Interaction, content: str | None = None, **kw: Any) -> None:
    kw.setdefault("ephemeral", True)
    if interaction.response.is_done():
        await interaction.followup.send(content, **kw)
    else:
        await interaction.response.send_message(content, **kw)


def result_embed(r: Result, fmt: str | None = None) -> discord.Embed:
    title = r.display + (" · audiobook" if fmt == "audiobook" else "")
    e = discord.Embed(title=clip(title, 256), description=clip(r.overview or "No description.", 1000),
                      colour=COLOURS[r.kind])
    if r.subtitle:
        e.set_author(name=clip(r.subtitle, 256))
    if r.image:
        e.set_thumbnail(url=r.image)
    e.set_footer(text=f"{r.kind.label}" + (" · already here or requested" if r.in_library else ""))
    return e


def ready_embed(row: dict[str, Any]) -> discord.Embed:
    details = row.get("details") or {}
    kind = Kind(row["kind"])
    title = f"{row['title']} ({row['year']})" if row.get("year") else row["title"]
    e = discord.Embed(title=clip(title, 256), colour=COLOURS[kind],
                      description=f"Ready to {verb(row['kind'], details.get('format'))}. "
                                  f"Requested by {row['requested_by_name']}.")
    if details.get("image"):
        e.set_thumbnail(url=details["image"])
    e.set_footer(text=kind.label + (f" · {human_size(row['size_bytes'])}" if row.get("size_bytes") else ""))
    return e


class ResultsView(discord.ui.View):
    """Pick one result from a menu, then press Request. Only the person who searched can use it."""

    def __init__(self, bot: SherpaBot, kind: Kind, results: list[Result], owner_id: int, fmt: str = "ebook"):
        super().__init__(timeout=300)
        self.bot, self.kind, self.results, self.owner_id, self.fmt = bot, kind, results, owner_id, fmt
        self.chosen: Result | None = None
        self.select = discord.ui.Select(placeholder=f"Pick a {kind.label.lower()}…", options=[
            discord.SelectOption(label=clip(r.display, 100), value=str(i),
                                 description=clip(" · ".join(x for x in (
                                     r.subtitle, "already here" if r.in_library else "") if x), 100) or None)
            for i, r in enumerate(results)])
        self.select.callback = self.on_select
        self.add_item(self.select)
        self.request_button = discord.ui.Button(label="Request", style=discord.ButtonStyle.success, disabled=True)
        self.request_button.callback = self.on_request
        self.add_item(self.request_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await reply(interaction, "Run the command yourself to request something.")
            return False
        return True

    async def on_select(self, interaction: discord.Interaction) -> None:
        self.chosen = self.results[int(self.select.values[0])]
        self.request_button.disabled = self.chosen.in_library
        self.request_button.label = "Already here or requested" if self.chosen.in_library else "Request"
        await interaction.response.edit_message(embed=result_embed(self.chosen, self.fmt if self.kind is Kind.BOOK
                                                                   else None), view=self)

    async def on_request(self, interaction: discord.Interaction) -> None:
        if not self.chosen:
            return
        await interaction.response.defer()
        who = Requester(discord_id=interaction.user.id, name=interaction.user.display_name)
        try:
            row = await self.bot.sherpa.request(self.kind, self.chosen, who, self.fmt)
        except RequestError as e:
            await interaction.followup.send(str(e), ephemeral=True)
            return
        self.stop()
        for item in self.children:
            item.disabled = True
        self.request_button.label = "Requested"
        await interaction.edit_original_response(view=self)
        what = self.chosen.display + (" (audiobook)" if self.kind is Kind.BOOK and self.fmt == "audiobook" else "")
        note = " It was already on the list." if row.get("already_tracked") else ""
        await interaction.followup.send(
            f"**{interaction.user.display_name}** requested **{what}** ({self.kind.label.lower()}). "
            f"I'll post in the ready channel when it's there.{note}",
            ephemeral=False, allowed_mentions=discord.AllowedMentions.none())


def register_commands(bot: SherpaBot) -> None:
    tree = bot.tree

    def household():
        return app_commands.check(lambda i: bot.is_household(i.user))

    def admin():
        return app_commands.check(lambda i: bot.is_admin(i.user))

    async def search_and_show(interaction: discord.Interaction, kind: Kind, query: str, fmt: str = "ebook"):
        await interaction.response.defer(ephemeral=True, thinking=True)
        results = await bot.sherpa.search(kind, query)
        if not results:
            await reply(interaction, f"Nothing found for “{clip(query, 80)}”. Try a different spelling?")
            return
        view = ResultsView(bot, kind, results, interaction.user.id, fmt)
        view.chosen = results[0]
        view.request_button.disabled = results[0].in_library
        if results[0].in_library:
            view.request_button.label = "Already here or requested"
        await reply(interaction, f"{len(results)} result(s). Pick one, then press Request.",
                    embed=result_embed(results[0], fmt if kind is Kind.BOOK else None), view=view)

    def media_command(kind: Kind, name: str, description: str):
        @tree.command(name=name, description=description)
        @app_commands.describe(query="What to search for")
        @household()
        async def _cmd(interaction: discord.Interaction, query: str):
            await search_and_show(interaction, kind, query)
        return _cmd

    media_command(Kind.MOVIE, "movie", "Search for a film and request it")
    media_command(Kind.SERIES, "series", "Search for a TV series and request it")
    media_command(Kind.ANIME, "anime", "Search for an anime series or film and request it")
    media_command(Kind.MUSIC, "music", "Search for an album or single and request it")
    media_command(Kind.COMIC, "comic", "Search for a comic series and request it")
    media_command(Kind.MANGA, "manga", "Search for a manga and request it")

    @tree.command(name="book", description="Search for a book and request it")
    @app_commands.describe(query="Title or author", format="Ebook or audiobook")
    @app_commands.choices(format=[app_commands.Choice(name="Ebook", value="ebook"),
                                  app_commands.Choice(name="Audiobook", value="audiobook")])
    @household()
    async def book(interaction: discord.Interaction, query: str, format: app_commands.Choice[str] | None = None):
        await search_and_show(interaction, Kind.BOOK, query, format.value if format else "ebook")

    @tree.command(name="downloads", description="What's downloading right now")
    @household()
    async def downloads(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        items = await bot.sherpa.downloads()
        if not items:
            await reply(interaction, "Nothing downloading right now.")
            return
        lines = [f"`{q['progress']:>3}%` **{clip(q['title'], 70)}** · {q['app']}"
                 + (f" · {q['eta']} left" if q.get("eta") else "") for q in items[:20]]
        more = f"\n…and {len(items) - 20} more" if len(items) > 20 else ""
        await reply(interaction, "\n".join(lines) + more)

    @tree.command(name="mine", description="What you've requested")
    @household()
    async def mine(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        rows = await bot.sherpa.mine(interaction.user.id)
        if not rows:
            await reply(interaction, "You haven't requested anything yet.")
            return
        lines = [f"{STATUS_ICON.get(r['status'], '•')} **{clip(r['title'], 60)}** · {Kind(r['kind']).label}"
                 + (f" · {human_size(r['size_bytes'])}" if r["size_bytes"] else "") for r in rows]
        total = sum(r["size_bytes"] for r in rows)
        await reply(interaction, "\n".join(lines) + f"\n\nTotal on disk: **{human_size(total)}**")

    @tree.command(name="space", description="Disk space, who's using it, and what could go first")
    @admin()
    async def space(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        sp = await bot.sherpa.space()
        pct = round(100 * sp.used / sp.total) if sp.total else 0
        e = discord.Embed(title="Media disk", colour=0xEF4444 if pct >= 90 else 0x22C55E,
                          description=f"**{human_size(sp.free)}** free of {human_size(sp.total)} ({pct}% used)")
        people = "\n".join(f"**{p['requested_by_name']}**: {human_size(p['bytes'])} in {p['items']} item(s)"
                           for p in sp.people[:10]) or "Nothing tracked yet."
        e.add_field(name="By person", value=clip(people, 1024), inline=False)
        cands = "\n".join(f"{human_size(c['size_bytes'])} · **{clip(c['title'], 50)}** "
                          f"({Kind(c['kind']).label}, {c['requested_by_name']}"
                          f"{', yours' if c['is_owner'] else ''})" for c in sp.candidates[:12]) or "None."
        e.add_field(name="Delete first (other people's, oldest first)", value=clip(cands, 1024), inline=False)
        e.set_footer(text="Sherpa never deletes anything. Remove items in Radarr, Sonarr, Lidarr, Chaptarr, "
                          "Mylar3 or Suwayomi and Sherpa will notice on its next check.")
        await reply(interaction, embed=e)

    async def seerr_user_autocomplete(interaction: discord.Interaction, current: str):
        try:
            users = await bot.sherpa.seerr.users()
        except RequestError:
            return []
        out = []
        for u in users:
            name = u.get("displayName") or u.get("username") or u.get("email") or str(u["id"])
            if current.lower() in name.lower():
                out.append(app_commands.Choice(name=clip(f"{name} (#{u['id']})", 100), value=int(u["id"])))
        return out[:25]

    @tree.command(name="link", description="Tie a Discord member to their Seerr account (admin)")
    @app_commands.describe(member="The Discord member", seerr_user="Their Seerr account")
    @app_commands.autocomplete(seerr_user=seerr_user_autocomplete)
    @admin()
    async def link(interaction: discord.Interaction, member: discord.Member, seerr_user: int):
        await bot.sherpa.db.link_seerr(member.id, member.display_name, seerr_user)
        await reply(interaction, f"Linked **{member.display_name}** to Seerr user #{seerr_user}. Their film and "
                                 f"series requests will show under their own name in Seerr too.")
