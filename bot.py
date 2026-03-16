import json
import os
import random
import re
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError

load_dotenv()

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

RATINGS_FILE = DATA_DIR / "ratings.json"
VACATIONS_FILE = DATA_DIR / "vacations.json"
ATTENDANCE_FILE = DATA_DIR / "attendance.json"
STATS_FILE = DATA_DIR / "stats.json"
ECONOMY_FILE = DATA_DIR / "economy.json"

LOG_CHANNEL_NAME = os.getenv("LOG_CHANNEL_NAME", "bot-logs")
STAFF_MANAGER_ROLE = os.getenv("STAFF_MANAGER_ROLE", "Staff Manager")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))
TOKEN = os.getenv("DISCORD_TOKEN", "")

RANK_TIERS: Dict[str, List[str]] = {
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

CATEGORY_ROLES = list(RANK_TIERS.keys())
ALL_STAFF_RANKS = [rank for ranks in RANK_TIERS.values() for rank in ranks]
ALL_ADMIN_RELATED_ROLES = ALL_STAFF_RANKS + CATEGORY_ROLES
VACATION_ROLE = "Vacation"

BASE_LEVEL_MESSAGES = 100
LEVEL_GROWTH_FACTOR = 1.15
LEVEL_ROLES = [f"Level {n}" for n in range(10, 80, 10)]
LEGEND_LEVEL_ROLE = "Great Member"
MESSAGE_COOLDOWN_SECONDS = 15


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
stats_data = load_json(STATS_FILE, {"admin_actions": 0, "say_count": 0, "messages": 0})
economy_data = load_json(ECONOMY_FILE, {})

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


def user_row(user_id: int) -> Dict:
    row = economy_data.setdefault(
        str(user_id),
        {
            "coins": 0,
            "level": 0,
            "xp": 0,
            "messages": 0,
            "last_message_ts": 0,
        },
    )
    return row


def xp_required_for_next_level(current_level: int) -> int:
    # Level 0 -> 1 يحتاج 100 رسالة، وكل مستوى بعده أصعب 15%
    return max(1, int(round(BASE_LEVEL_MESSAGES * (LEVEL_GROWTH_FACTOR ** current_level))))


def find_rank_position(member: discord.Member) -> Optional[Tuple[str, int]]:
    role_names = {r.name for r in member.roles}
    for tier_name, ranks in RANK_TIERS.items():
        for idx, rank in enumerate(ranks):
            if rank in role_names:
                return tier_name, idx
    return None


def tier_of_rank(rank_name: str) -> Optional[str]:
    for tier_name, ranks in RANK_TIERS.items():
        if rank_name in ranks:
            return tier_name
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


async def ensure_category_role(member: discord.Member, tier_name: str):
    category_role = await get_role(member.guild, tier_name)
    if category_role and category_role not in member.roles:
        await member.add_roles(category_role, reason="Auto category role")


async def move_to_rank(member: discord.Member, target_rank: str):
    guild = member.guild

    # لا نحذف رتب الفئات مع الترقية/التنزيل
    rank_roles_to_remove = [r for r in member.roles if r.name in ALL_STAFF_RANKS]
    if rank_roles_to_remove:
        await member.remove_roles(*rank_roles_to_remove, reason="Staff rank change")

    role = await get_role(guild, target_rank)
    if role:
        await member.add_roles(role, reason="Staff rank change")

    tier_name = tier_of_rank(target_rank)
    if tier_name:
        await ensure_category_role(member, tier_name)


async def remove_admin_roles(member: discord.Member):
    roles_to_remove = [r for r in member.roles if r.name in ALL_ADMIN_RELATED_ROLES]
    if roles_to_remove:
        await member.remove_roles(*roles_to_remove, reason="Admin roles removal")


async def apply_level_role(member: discord.Member, level: int):
    role_names_to_manage = set(LEVEL_ROLES + [LEGEND_LEVEL_ROLE])
    old_roles = [r for r in member.roles if r.name in role_names_to_manage]
    if old_roles:
        await member.remove_roles(*old_roles, reason="Level role update")

    target_role_name: Optional[str] = None
    if level >= 80:
        target_role_name = LEGEND_LEVEL_ROLE
    elif level >= 10:
        bracket = min((level // 10) * 10, 70)
        if bracket >= 10:
            target_role_name = f"Level {bracket}"

    if target_role_name:
        role = await get_role(member.guild, target_role_name)
        if role and role not in member.roles:
            await member.add_roles(role, reason="Level reward role")


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync(guild=discord.Object(id=GUILD_ID)) if GUILD_ID else await bot.tree.sync()
        print(f"Synced {len(synced)} application commands")
    except Exception as exc:
        print(f"Slash sync failed: {exc}")

    if not vacation_watcher.is_running():
        vacation_watcher.start()


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or message.guild is None:
        return

    row = user_row(message.author.id)
    now_ts = int(datetime.now(timezone.utc).timestamp())

    # مكافحة السبام: مكافأة تفاعل كل 15 ثانية كحد أدنى
    if now_ts - int(row.get("last_message_ts", 0)) >= MESSAGE_COOLDOWN_SECONDS:
        gained_coins = random.randint(1, 5)
        row["coins"] += gained_coins
        row["messages"] += 1
        row["xp"] += 1  # كل رسالة مؤهلة = 1 XP
        row["last_message_ts"] = now_ts
        stats_data["messages"] = stats_data.get("messages", 0) + 1

        leveled_up = False
        while row["xp"] >= xp_required_for_next_level(row["level"]):
            needed = xp_required_for_next_level(row["level"])
            row["xp"] -= needed
            row["level"] += 1
            leveled_up = True

        save_json(ECONOMY_FILE, economy_data)
        save_json(STATS_FILE, stats_data)

        if leveled_up:
            await apply_level_role(message.author, row["level"])
            nxt = xp_required_for_next_level(row["level"])
            await message.channel.send(
                f"🎉 {message.author.mention} وصلت لفل **{row['level']}**!"
                f" | ALR Coins: **{row['coins']}**\n"
                f"المطلوب للمستوى القادم: **{nxt}** رسالة."
            )

    await bot.process_commands(message)


@commands.check(staff_manager_check)
@bot.command(name="توظيف")
async def hire(ctx: commands.Context, member: discord.Member):
    await move_to_rank(member, "Trial Staff")
    await ensure_category_role(member, "STAFF")
    stats_data["admin_actions"] = stats_data.get("admin_actions", 0) + 1
    save_json(STATS_FILE, stats_data)
    await ctx.send(f"✅ تم توظيف {member.mention} برتبة Trial Staff")
    await log_action(ctx.guild, f"توظيف: {ctx.author.mention} -> {member.mention}")


@commands.check(staff_manager_check)
@bot.command(name="ترقية")
async def promote(ctx: commands.Context, member: discord.Member, steps: int = 1):
    if steps < 1:
        return await ctx.send("❌ عدد الرتب للترقية يجب أن يكون 1 أو أكثر.")

    pos = find_rank_position(member)
    if not pos:
        return await ctx.send("❌ العضو ليس ضمن الرتب الإدارية.")

    tier, idx = pos
    current_rank = RANK_TIERS[tier][idx]
    current_global_idx = ALL_STAFF_RANKS.index(current_rank)
    target_idx = min(current_global_idx + steps, len(ALL_STAFF_RANKS) - 1)

    if target_idx == current_global_idx:
        return await ctx.send("⚠️ العضو في أعلى رتبة بالفعل.")

    next_rank = ALL_STAFF_RANKS[target_idx]
    await move_to_rank(member, next_rank)

    await ctx.send(f"✅ تمت ترقية {member.mention} إلى **{next_rank}** ( +{target_idx - current_global_idx} )")
    await log_action(ctx.guild, f"ترقية: {ctx.author.mention} -> {member.mention} ({next_rank}, +{target_idx - current_global_idx})")


@commands.check(staff_manager_check)
@bot.command(name="تنزيل")
async def demote(ctx: commands.Context, member: discord.Member, steps: int = 1):
    if steps < 1:
        return await ctx.send("❌ عدد الرتب للتنزيل يجب أن يكون 1 أو أكثر.")

    pos = find_rank_position(member)
    if not pos:
        return await ctx.send("❌ العضو ليس ضمن الرتب الإدارية.")

    tier, idx = pos
    current_rank = RANK_TIERS[tier][idx]
    current_global_idx = ALL_STAFF_RANKS.index(current_rank)
    target_idx = max(current_global_idx - steps, 0)

    if target_idx == current_global_idx:
        return await ctx.send("⚠️ العضو في أقل رتبة بالفعل.")

    prev_rank = ALL_STAFF_RANKS[target_idx]
    await move_to_rank(member, prev_rank)
    await ctx.send(f"✅ تم تنزيل {member.mention} إلى **{prev_rank}** ( -{current_global_idx - target_idx} )")
    await log_action(ctx.guild, f"تنزيل: {ctx.author.mention} -> {member.mention} ({prev_rank}, -{current_global_idx - target_idx})")


@commands.check(staff_manager_check)
@bot.command(name="ترقية-فئة")
async def promote_in_tier(ctx: commands.Context, member: discord.Member, steps: int = 1):
    if steps < 1:
        return await ctx.send("❌ عدد الرتب للترقية داخل الفئة يجب أن يكون 1 أو أكثر.")

    pos = find_rank_position(member)
    if not pos:
        return await ctx.send("❌ العضو ليس ضمن الرتب الإدارية.")

    tier, idx = pos
    ranks = RANK_TIERS[tier]
    target_idx = min(idx + steps, len(ranks) - 1)

    if target_idx == idx:
        return await ctx.send("⚠️ وصل لنهاية الفئة الحالية.")

    next_rank = ranks[target_idx]
    await move_to_rank(member, next_rank)
    await ctx.send(f"✅ تمت الترقية داخل الفئة إلى **{next_rank}** ( +{target_idx - idx} )")
    await log_action(ctx.guild, f"ترقية-فئة: {ctx.author.mention} -> {member.mention} ({next_rank}, +{target_idx - idx})")


@commands.check(staff_manager_check)
@bot.command(name="فصل")
async def fire(ctx: commands.Context, member: discord.Member):
    await remove_admin_roles(member)
    await ctx.send(f"✅ تم فصل {member.mention} من الإدارة")
    await log_action(ctx.guild, f"فصل: {ctx.author.mention} -> {member.mention}")


@commands.check(staff_manager_check)
@bot.command(name="اجازة")
async def vacation(ctx: commands.Context, member: discord.Member, hours: int):
    if hours < 1:
        return await ctx.send("❌ مدة الإجازة يجب أن تكون ساعة أو أكثر.")

    old_roles = [r.name for r in member.roles if r.name in ALL_ADMIN_RELATED_ROLES]
    await remove_admin_roles(member)

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

    changed = False
    for guild in bot.guilds:
        for user_id, row in list(vacations_data.items()):
            if row.get("end", 0) > now:
                continue

            member = guild.get_member(int(user_id))
            if not member:
                continue

            vacation_role = await get_role(guild, VACATION_ROLE)
            if vacation_role and vacation_role in member.roles:
                await member.remove_roles(vacation_role, reason="Vacation end")

            restore_names = row.get("old_roles", [])
            roles_to_restore = [await get_role(guild, name) for name in restore_names]
            roles_to_restore = [r for r in roles_to_restore if r is not None]
            if roles_to_restore:
                await member.add_roles(*roles_to_restore, reason="Vacation end restore")

            vacations_data.pop(user_id, None)
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
    if guild is None:
        return await interaction.response.send_message("❌ الأمر داخل السيرفر فقط.", ephemeral=True)

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
    embed.add_field(name="رسائل التفاعل", value=str(stats_data.get("messages", 0)), inline=False)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="profile", description="عرض مستوى وعملة ALR", guild=discord.Object(id=GUILD_ID) if GUILD_ID else None)
@app_commands.describe(member="اختياري: عضو آخر")
async def profile(interaction: discord.Interaction, member: Optional[discord.Member] = None):
    target = member or interaction.user
    row = user_row(target.id)
    needed = xp_required_for_next_level(row["level"])

    embed = discord.Embed(title=f"🏆 ملف {target.display_name}", color=discord.Color.purple())
    embed.add_field(name="ALR Coins", value=str(row["coins"]), inline=True)
    embed.add_field(name="Level", value=str(row["level"]), inline=True)
    embed.add_field(name="XP", value=f"{row['xp']} / {needed}", inline=True)
    embed.add_field(name="Qualified Messages", value=str(row["messages"]), inline=False)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="top_alr", description="أفضل 10 في ALR Coins", guild=discord.Object(id=GUILD_ID) if GUILD_ID else None)
async def top_alr(interaction: discord.Interaction):
    guild = interaction.guild
    if guild is None:
        return await interaction.response.send_message("❌ الأمر داخل السيرفر فقط.", ephemeral=True)

    rows = []
    for user_id, row in economy_data.items():
        member = guild.get_member(int(user_id))
        if member:
            rows.append((member, row.get("coins", 0), row.get("level", 0)))

    rows.sort(key=lambda x: (x[1], x[2]), reverse=True)
    top = rows[:10]

    if not top:
        return await interaction.response.send_message("لا يوجد بيانات بعد.")

    lines = [f"**{idx}.** {member.mention} — 💰 {coins} ALR | Lv.{lvl}" for idx, (member, coins, lvl) in enumerate(top, start=1)]
    embed = discord.Embed(title="💎 Top ALR Coins", description="\n".join(lines), color=discord.Color.gold())
    await interaction.response.send_message(embed=embed)


def parse_member_query(raw: str) -> str:
    match = re.search(r"<@!?(\d+)>", raw)
    if match:
        return match.group(1)
    return raw.strip()


async def resolve_member(guild: discord.Guild, query: str) -> Optional[discord.Member]:
    query = parse_member_query(query)

    if query.isdigit():
        member = guild.get_member(int(query))
        if member:
            return member

    lowered = query.lower()
    for member in guild.members:
        if member.name.lower() == lowered or member.display_name.lower() == lowered:
            return member

    return None


async def avatar_to_image(asset: discord.Asset) -> Image.Image:
    data = await asset.replace(size=256, format="png").read()
    try:
        return Image.open(BytesIO(data)).convert("RGBA")
    except UnidentifiedImageError:
        img = Image.new("RGBA", (256, 256), (70, 70, 70, 255))
        draw = ImageDraw.Draw(img)
        draw.text((90, 118), "N/A", fill=(255, 255, 255, 255), font=ImageFont.load_default())
        return img


@bot.tree.command(name="love", description="حساب نسبة الحب", guild=discord.Object(id=GUILD_ID) if GUILD_ID else None)
@app_commands.describe(person1="منشن / يوزر / ID للشخص الأول", person2="منشن / يوزر / ID للشخص الثاني")
async def love(interaction: discord.Interaction, person1: str, person2: str):
    guild = interaction.guild
    if guild is None:
        return await interaction.response.send_message("❌ الأمر داخل السيرفر فقط.", ephemeral=True)

    first = await resolve_member(guild, person1)
    second = await resolve_member(guild, person2)

    if not first or not second:
        return await interaction.response.send_message(
            "❌ ما قدرت أحدد الشخصين. استخدم منشن أو ID أو اسم واضح داخل السيرفر.",
            ephemeral=True,
        )

    percent = random.randint(1, 100)

    img = Image.new("RGB", (520, 640), (28, 28, 38))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()

    a1 = (await avatar_to_image(first.display_avatar)).resize((220, 220))
    a2 = (await avatar_to_image(second.display_avatar)).resize((220, 220))

    img.paste(a1.convert("RGB"), (150, 30))
    img.paste(a2.convert("RGB"), (150, 380))

    draw.text((220, 300), "❤️", fill=(255, 70, 90), font=font)
    draw.text((188, 332), f"Love: {percent}%", fill=(255, 255, 255), font=font)
    draw.text((30, 600), f"{first.display_name} + {second.display_name}", fill=(220, 220, 220), font=font)

    out = DATA_DIR / f"love_{first.id}_{second.id}.png"
    img.save(out)

    await interaction.response.send_message(file=discord.File(out))


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
