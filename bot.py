import asyncio
import json
import os
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

load_dotenv()

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

RATINGS_FILE = DATA_DIR / "ratings.json"
VACATIONS_FILE = DATA_DIR / "vacations.json"
ATTENDANCE_FILE = DATA_DIR / "attendance.json"
STATS_FILE = DATA_DIR / "stats.json"

LOG_CHANNEL_NAME = os.getenv("LOG_CHANNEL_NAME", "bot-logs")
STAFF_MANAGER_ROLE = os.getenv("STAFF_MANAGER_ROLE", "Staff Manager")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))
TOKEN = os.getenv("DISCORD_TOKEN", "")

RANK_TIERS = {
    "STAFF": [
        "Trial Staff",
        "Trainee",
        "Helper",
        "Visor",
        "Senior",
        "Moderator",
        "Senior Moderator",
        "Head Moderator",
    ],
    "MIDDLE STAFF": ["designer", "Agon", "Advisor", "Developer"],
    "HIGHER MANAGEMENT": ["Co Manager", "Manager", "Co Leader", "Leader"],
    "OWNER": ["RIGHT HAND", "LEFT HAND"],
}

ALL_STAFF_RANKS = [rank for ranks in RANK_TIERS.values() for rank in ranks]
VACATION_ROLE = "Vacation"
BEST_STAFF_ROLE = "Best Staff Of The Month"


def load_json(path: Path, default):
    if not path.exists():
        path.write_text(json.dumps(default, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


ratings_data = load_json(RATINGS_FILE, {})
vacations_data = load_json(VACATIONS_FILE, {})
attendance_data = load_json(ATTENDANCE_FILE, {})
stats_data = load_json(STATS_FILE, {"admin_actions": 0, "say_count": 0})

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


@dataclass
class RankPosition:
    tier_name: str
    index: int


def find_rank_position(member: discord.Member) -> Optional[Tuple[str, int]]:
    role_names = {r.name for r in member.roles}
    for tier_name, ranks in RANK_TIERS.items():
        for idx, rank in enumerate(ranks):
            if rank in role_names:
                return tier_name, idx
    return None


async def get_role(guild: discord.Guild, role_name: str) -> Optional[discord.Role]:
    return discord.utils.get(guild.roles, name=role_name)


async def staff_manager_check(ctx: commands.Context) -> bool:
    return any(role.name == STAFF_MANAGER_ROLE for role in ctx.author.roles)


async def log_action(guild: discord.Guild, message: str):
    channel = discord.utils.get(guild.text_channels, name=LOG_CHANNEL_NAME)
    if channel:
        embed = discord.Embed(title="Staff Log", description=message, color=discord.Color.blurple())
        embed.timestamp = datetime.now(timezone.utc)
        await channel.send(embed=embed)


def avg_rating_for(user_id: int) -> Tuple[float, int, int]:
    row = ratings_data.get(str(user_id), {})
    values = [entry["stars"] for entry in row.values()]
    total = sum(values)
    count = len(values)
    avg = (total / count) if count else 0.0
    return avg, total, count


async def move_to_rank(member: discord.Member, target_rank: str):
    guild = member.guild
    staff_roles = [r for r in member.roles if r.name in ALL_STAFF_RANKS]
    if staff_roles:
        await member.remove_roles(*staff_roles, reason="Staff rank change")
    role = await get_role(guild, target_rank)
    if role:
        await member.add_roles(role, reason="Staff rank change")


async def remove_all_staff_roles(member: discord.Member):
    roles_to_remove = [r for r in member.roles if r.name in ALL_STAFF_RANKS]
    if roles_to_remove:
        await member.remove_roles(*roles_to_remove, reason="Staff removal")


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID)) if GUILD_ID else await bot.tree.sync()
        print(f"Synced {len(synced)} application commands")
    except Exception as exc:
        print(f"Slash sync failed: {exc}")
    vacation_watcher.start()


@commands.check(staff_manager_check)
@bot.command(name="توظيف")
async def hire(ctx: commands.Context, member: discord.Member):
    await move_to_rank(member, "Trial Staff")
    stats_data["admin_actions"] = stats_data.get("admin_actions", 0) + 1
    save_json(STATS_FILE, stats_data)
    await ctx.send(f"✅ تم توظيف {member.mention} برتبة Trial Staff")
    await log_action(ctx.guild, f"توظيف: {ctx.author.mention} -> {member.mention}")


@commands.check(staff_manager_check)
@bot.command(name="ترقية")
async def promote(ctx: commands.Context, member: discord.Member):
    pos = find_rank_position(member)
    if not pos:
        return await ctx.send("❌ العضو ليس ضمن الرتب الإدارية.")

    tier, idx = pos
    all_ranks = ALL_STAFF_RANKS
    current_rank = RANK_TIERS[tier][idx]
    global_idx = all_ranks.index(current_rank)
    if global_idx + 1 >= len(all_ranks):
        return await ctx.send("⚠️ العضو في أعلى رتبة بالفعل.")

    next_rank = all_ranks[global_idx + 1]
    await move_to_rank(member, next_rank)
    await ctx.send(f"✅ تمت ترقية {member.mention} إلى **{next_rank}**")
    await log_action(ctx.guild, f"ترقية: {ctx.author.mention} -> {member.mention} ({next_rank})")


@commands.check(staff_manager_check)
@bot.command(name="تنزيل")
async def demote(ctx: commands.Context, member: discord.Member):
    pos = find_rank_position(member)
    if not pos:
        return await ctx.send("❌ العضو ليس ضمن الرتب الإدارية.")

    tier, idx = pos
    current_rank = RANK_TIERS[tier][idx]
    global_idx = ALL_STAFF_RANKS.index(current_rank)
    if global_idx == 0:
        return await ctx.send("⚠️ العضو في أقل رتبة بالفعل.")

    prev_rank = ALL_STAFF_RANKS[global_idx - 1]
    await move_to_rank(member, prev_rank)
    await ctx.send(f"✅ تم تنزيل {member.mention} إلى **{prev_rank}**")
    await log_action(ctx.guild, f"تنزيل: {ctx.author.mention} -> {member.mention} ({prev_rank})")


@commands.check(staff_manager_check)
@bot.command(name="ترقية-فئة")
async def promote_in_tier(ctx: commands.Context, member: discord.Member):
    pos = find_rank_position(member)
    if not pos:
        return await ctx.send("❌ العضو ليس ضمن الرتب الإدارية.")

    tier, idx = pos
    ranks = RANK_TIERS[tier]
    if idx + 1 >= len(ranks):
        return await ctx.send("⚠️ وصل لنهاية الفئة الحالية.")

    next_rank = ranks[idx + 1]
    await move_to_rank(member, next_rank)
    await ctx.send(f"✅ تمت الترقية داخل الفئة إلى **{next_rank}**")
    await log_action(ctx.guild, f"ترقية-فئة: {ctx.author.mention} -> {member.mention} ({next_rank})")


@commands.check(staff_manager_check)
@bot.command(name="فصل")
async def fire(ctx: commands.Context, member: discord.Member):
    await remove_all_staff_roles(member)
    await ctx.send(f"✅ تم فصل {member.mention} من الإدارة")
    await log_action(ctx.guild, f"فصل: {ctx.author.mention} -> {member.mention}")


@commands.check(staff_manager_check)
@bot.command(name="اجازة")
async def vacation(ctx: commands.Context, member: discord.Member, hours: int):
    old_roles = [r.name for r in member.roles if r.name in ALL_STAFF_RANKS]
    await remove_all_staff_roles(member)

    vacation_role = await get_role(ctx.guild, VACATION_ROLE)
    if vacation_role:
        await member.add_roles(vacation_role, reason="Vacation start")

    end_ts = (datetime.now(timezone.utc) + timedelta(hours=hours)).timestamp()
    vacations_data[str(member.id)] = {
        "end": end_ts,
        "old_roles": old_roles,
    }
    save_json(VACATIONS_FILE, vacations_data)
    await ctx.send(f"🏖️ تم منح {member.mention} إجازة لمدة {hours} ساعة")
    await log_action(ctx.guild, f"إجازة: {ctx.author.mention} -> {member.mention} ({hours}h)")


@tasks.loop(minutes=1)
async def vacation_watcher():
    await bot.wait_until_ready()
    now = datetime.now(timezone.utc).timestamp()

    for guild in bot.guilds:
        changed = False
        for user_id, row in list(vacations_data.items()):
            if row["end"] <= now:
                member = guild.get_member(int(user_id))
                if not member:
                    continue

                vacation_role = await get_role(guild, VACATION_ROLE)
                if vacation_role and vacation_role in member.roles:
                    await member.remove_roles(vacation_role, reason="Vacation end")

                roles_to_restore = [await get_role(guild, name) for name in row.get("old_roles", [])]
                roles_to_restore = [r for r in roles_to_restore if r is not None]
                if roles_to_restore:
                    await member.add_roles(*roles_to_restore, reason="Vacation end restore")

                del vacations_data[user_id]
                changed = True
                await log_action(guild, f"انتهاء الإجازة: {member.mention}")

        if changed:
            save_json(VACATIONS_FILE, vacations_data)


@commands.check(staff_manager_check)
@bot.command(name="تسجيل")
async def check_in(ctx: commands.Context):
    user_id = str(ctx.author.id)
    attendance_data.setdefault(user_id, {"sessions": [], "active_start": None})
    if attendance_data[user_id]["active_start"] is not None:
        return await ctx.send("⚠️ أنت مسجل بالفعل.")

    attendance_data[user_id]["active_start"] = datetime.now(timezone.utc).timestamp()
    save_json(ATTENDANCE_FILE, attendance_data)
    await ctx.send("✅ تم تسجيل الدخول.")
    await log_action(ctx.guild, f"تسجيل دخول: {ctx.author.mention}")


@commands.check(staff_manager_check)
@bot.command(name="خروج")
async def check_out(ctx: commands.Context):
    user_id = str(ctx.author.id)
    attendance_data.setdefault(user_id, {"sessions": [], "active_start": None})
    start = attendance_data[user_id]["active_start"]
    if start is None:
        return await ctx.send("⚠️ أنت غير مسجل حالياً.")

    end = datetime.now(timezone.utc).timestamp()
    duration = int(end - start)
    attendance_data[user_id]["sessions"].append({"start": start, "end": end, "duration": duration})
    attendance_data[user_id]["active_start"] = None
    save_json(ATTENDANCE_FILE, attendance_data)
    await ctx.send(f"✅ تم تسجيل الخروج. مدة الجلسة: {duration // 60} دقيقة")
    await log_action(ctx.guild, f"تسجيل خروج: {ctx.author.mention} ({duration}s)")


@commands.check(staff_manager_check)
@bot.command(name="say")
async def say_embed(ctx: commands.Context, *, message: str):
    emb = discord.Embed(description=message, color=discord.Color.green())
    emb.set_footer(text=f"By {ctx.author}")
    await ctx.send(embed=emb)
    stats_data["say_count"] = stats_data.get("say_count", 0) + 1
    save_json(STATS_FILE, stats_data)
    await log_action(ctx.guild, f"say: {ctx.author.mention}")


class RatingView(discord.ui.View):
    def __init__(self, staff_id: int):
        super().__init__(timeout=120)
        self.staff_id = staff_id

    async def _save_rating(self, interaction: discord.Interaction, stars: int):
        staff_row = ratings_data.setdefault(str(self.staff_id), {})
        voter_id = str(interaction.user.id)
        if voter_id in staff_row:
            return await interaction.response.send_message("❌ لقد قيّمت هذا الإداري مسبقاً.", ephemeral=True)

        staff_row[voter_id] = {
            "stars": stars,
            "reason": "",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        save_json(RATINGS_FILE, ratings_data)
        await interaction.response.send_message(f"✅ تم حفظ تقييمك: {stars} نجوم", ephemeral=True)

    @discord.ui.button(label="⭐", style=discord.ButtonStyle.secondary)
    async def one(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._save_rating(interaction, 1)

    @discord.ui.button(label="⭐⭐", style=discord.ButtonStyle.secondary)
    async def two(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._save_rating(interaction, 2)

    @discord.ui.button(label="⭐⭐⭐", style=discord.ButtonStyle.primary)
    async def three(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._save_rating(interaction, 3)

    @discord.ui.button(label="⭐⭐⭐⭐", style=discord.ButtonStyle.success)
    async def four(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._save_rating(interaction, 4)

    @discord.ui.button(label="⭐⭐⭐⭐⭐", style=discord.ButtonStyle.success)
    async def five(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._save_rating(interaction, 5)


@bot.tree.command(name="rate", description="تقييم إداري", guild=discord.Object(id=GUILD_ID) if GUILD_ID else None)
async def rate(interaction: discord.Interaction, member: discord.Member):
    embed = discord.Embed(
        title="تقييم إداري",
        description=f"اختر عدد النجوم لتقييم {member.mention}",
        color=discord.Color.gold(),
    )
    await interaction.response.send_message(embed=embed, view=RatingView(member.id), ephemeral=True)


@bot.tree.command(name="stats", description="إحصائيات البوت", guild=discord.Object(id=GUILD_ID) if GUILD_ID else None)
async def stats(interaction: discord.Interaction):
    guild = interaction.guild
    staff_count = len([m for m in guild.members if any(r.name in ALL_STAFF_RANKS for r in m.roles)])

    totals = []
    for staff_id in ratings_data.keys():
        avg, total, count = avg_rating_for(int(staff_id))
        totals.append((int(staff_id), avg, total, count))

    totals.sort(key=lambda x: (x[2], x[1]), reverse=True)
    top_user = guild.get_member(totals[0][0]).mention if totals and guild.get_member(totals[0][0]) else "لا يوجد"
    all_stars = sum(t[2] for t in totals)
    all_votes = sum(t[3] for t in totals)
    avg_global = (all_stars / all_votes) if all_votes else 0.0

    embed = discord.Embed(title="📊 Staff Stats", color=discord.Color.blurple())
    embed.add_field(name="عدد الإداريين", value=str(staff_count), inline=False)
    embed.add_field(name="عدد التقييمات", value=str(all_votes), inline=False)
    embed.add_field(name="أفضل إداري", value=top_user, inline=False)
    embed.add_field(name="متوسط التقييم", value=f"{avg_global:.2f}", inline=False)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="love", description="حساب نسبة الحب", guild=discord.Object(id=GUILD_ID) if GUILD_ID else None)
async def love(interaction: discord.Interaction, member: discord.Member):
    percent = random.randint(1, 100)
    avatar1 = interaction.user.display_avatar.replace(size=128)
    avatar2 = member.display_avatar.replace(size=128)

    img = Image.new("RGB", (500, 220), (30, 30, 40))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()

    data1 = await avatar1.read()
    data2 = await avatar2.read()
    # PIL cannot read raw bytes directly on some environments,
    # use asyncio-safe temp paths for compatibility.
    temp1 = DATA_DIR / f"{interaction.user.id}_a1.png"
    temp2 = DATA_DIR / f"{member.id}_a2.png"
    temp1.write_bytes(data1)
    temp2.write_bytes(data2)
    p1 = Image.open(temp1).resize((128, 128))
    p2 = Image.open(temp2).resize((128, 128))

    img.paste(p1, (35, 45))
    img.paste(p2, (335, 45))
    draw.text((224, 95), "❤️", font=font, fill=(255, 70, 90))
    draw.text((185, 180), f"{interaction.user.display_name} ❤️ {member.display_name} = {percent}%", font=font, fill=(255, 255, 255))

    out = DATA_DIR / f"love_{interaction.user.id}_{member.id}.png"
    img.save(out)
    await interaction.response.send_message(file=discord.File(out))

    for tp in [temp1, temp2]:
        if tp.exists():
            tp.unlink()


@bot.event
async def on_command_error(ctx: commands.Context, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send(f"❌ هذا الأمر متاح فقط لمن يملك رتبة {STAFF_MANAGER_ROLE}.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ بيانات ناقصة. تحقق من صيغة الأمر.")
    else:
        await ctx.send("❌ حدث خطأ غير متوقع.")


if __name__ == "__main__":
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN is missing in environment")
    bot.run(TOKEN)
