import mysql.connector
import threading
import discord
import socket
import json
import time

from datetime import datetime
from discord.commands import Option

# really fucky way to import from a parent directory
import os, sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from reader import full_webhook_push, unk_webhook_push, card_get_user, stay_length_of_user, add_time_log

bot = discord.Bot()
config = json.load(open("../config.json"))

database = mysql.connector.connect(
    host=config["database"]["host"],
    port=config["database"]["port"],
    user=config["database"]["username"],
    password=config["database"]["password"],
    database=config["database"]["database"]
)
database.autocommit = True

def get_shitty_cursor(*args, **kwargs):
    if not database.is_connected():
        database.reconnect()
    return database.cursor(*args, **kwargs)

def generate_members_embed(members):
    if len(members) == 0:
        return discord.Embed(
            title="Shack Status", 
            description=f"There are no members in the shack right now!",
            color=0xaab40e
        )
    
    s = "s" if len(members) > 1 else ""
    areis = "are" if len(members) > 1 else "is"
    embed = discord.Embed(
        title="Shack Status", 
        description=f"There {areis} {len(members)} member{s} in the shack right now!",
        color=0x1ab00f
    )
    
    for i in range(0, len(members), 2):
        chunk = members[i:i+2]
        for member in chunk:
            last_login = member["last_timestamp"].strftime("%s")
            if member["privacy_enabled"]:
                embed.add_field(name=f"[Name Redacted]", value=f"Logged in <t:{last_login}:R>", inline=True)
            else:
                embed.add_field(name=f"{member['first_name']} {member['last_name'][:1]}.", value=f"{member['position_in_club'].title()}\nLogged in <t:{last_login}:R>", inline=True)
        embed.add_field(name="\u200b", value="\u200b")
    return embed

def get_members(include_unk=False):
    cursor = get_shitty_cursor(dictionary=True)
    cursor.execute("""SELECT
    cards.id AS card_id_orig,
    members.*,
    (SELECT logs.timestamp 
     FROM logs 
     WHERE logs.card_id = members.card_id 
     ORDER BY logs.timestamp DESC 
     LIMIT 1) AS last_timestamp
FROM 
    cards
LEFT JOIN 
    members ON members.card_id = cards.id
WHERE 
    cards.inside_shack = 1""")
    members = []
    for member in cursor.fetchall():
        if not include_unk:
            if member["id"] is None:
                continue
        members.append(member)
    cursor.close()
    return members

def card_get_user(card_id, database):
    cursor = get_shitty_cursor()
    cursor.execute("SELECT id, first_name, last_name, callsign, position_in_club, discord_user_id FROM `members` WHERE `card_id` = %s", (card_id,))
    result = cursor.fetchone()
    cursor.close()
    if result is None:
        return None
    return {
        "id": result[0],
        "first_name": result[1],
        "last_name": result[2],
        "callsign": result[3],
        "position_in_club": result[4],
        "discord_user_id": result[5]
    }

def get_card_id_from_discord(discord_id, database):
    cursor = get_shitty_cursor()
    cursor.execute("SELECT card_id FROM `members` WHERE `discord_user_id` = %s", (discord_id,))
    result = cursor.fetchone()
    cursor.close()
    if result is None:
        return None
    return result[0]

def toggle_inside_shack(card_id, database):
    cursor = get_shitty_cursor()
    cursor.execute("SELECT `inside_shack`,`card_data` FROM `cards` WHERE `id` = %s", (card_id,))
    result = cursor.fetchone()
    
    if result is None:
        cursor.close()
        return False, None
    if result[0] == 0:
        cursor.close()
        return False, result[1]
    
    cursor.execute("UPDATE `cards` SET `inside_shack` = 0 WHERE `id` = %s", (card_id,))
    cursor.close()
    database.commit()
    return True, result[1]

def get_members_from_db(ctx: discord.AutocompleteContext):
    if config["discord"]["admin_role"] is None:
        return ["unauth"]
    if ctx.interaction.user.get_role(config["discord"]["admin_role"]) is None:
        return ["unauth"]
    
    cursor = get_shitty_cursor()
    cursor.execute("""SELECT cards.id AS card_id, members.first_name, members.last_name FROM cards LEFT JOIN members ON members.card_id = cards.id WHERE cards.inside_shack = 1""")
    members = cursor.fetchall()
    cursor.close()
    
    member_list = []
    guest_list = []

    guests_present = False
    for member in members:
        m_name =f"{member[1]} {member[2]} ({member[0]})"
        if member[1] is None or member[2] is None:
            m_name = f"Guest User ({member[0]})"
            guest_list.append(m_name)
            guests_present = True
            continue
        member_list.append(m_name)
    
    member_list.extend(guest_list)
    if guests_present:
        member_list.append("All Guests")
    return member_list

def _unlock_door(delay_time=3):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect(("127.0.0.1", 46099))
        s.send(b"\x01\x01")
        time.sleep(delay_time)
        s.send(b"\x01\x00\x0a")
        s.close()

def unlock_door(delay_time=3):
    threading.Thread(target=_unlock_door, args=(delay_time,), daemon=True).start()

def get_ranked_list_users_by_time(database):
    cursor = get_shitty_cursor(dictionary=True)
    # This is a really fucked up query, but it works lol
    cursor.execute("SELECT SUM(stay_length) AS total_time, members.first_name, members.last_name, members.discord_user_id, members.privacy_enabled FROM card_time_logs LEFT JOIN members ON members.card_id=card_time_logs.card_id WHERE members.id IS NOT NULL GROUP BY card_time_logs.card_id ORDER BY total_time DESC")
    result = cursor.fetchall()
    cursor.close()
    return result

# https://stackoverflow.com/a/24542445
def display_time(seconds, granularity=2):
    result = []
    intervals = (
        ('weeks', 604800),  # 60 * 60 * 24 * 7
        ('days', 86400),    # 60 * 60 * 24
        ('hours', 3600),    # 60 * 60
        ('minutes', 60),
        ('seconds', 1),
    )

    for name, count in intervals:
        value = seconds // count
        if value:
            seconds -= value * count
            if value == 1:
                name = name.rstrip('s')
            result.append("{} {}".format(value, name))
    return ', '.join(result[:granularity])

def get_emoji_from_rank(rank_num):
    ranks = ["🥇", "🥈", "🥉"]
    if rank_num >= 3:
        return "🏅"
    return ranks[rank_num]

@bot.slash_command()
async def open_door(ctx):
    if config["discord"]["admin_role"] is None:
        await ctx.respond("No admin role is set in the config, cannot open the door.")
        return
    if ctx.author.get_role(config["discord"]["admin_role"]) is None:
        await ctx.respond("You do not have permission to open the door.")
        return
    
    unlock_door(10)
    await ctx.respond("The door has been opened.")

@bot.slash_command()
async def shack_members(ctx):
    members = get_members()
    embed = generate_members_embed(members)
    await ctx.respond(embed=embed)

@bot.slash_command()
async def tag_out(ctx: discord.ApplicationContext, card_id: Option(str, "The card ID to tag out of the shack.", required=False, autocomplete=get_members_from_db)): # type: ignore
    if card_id is None:
        card_id = get_card_id_from_discord(ctx.author.id, database)
    else:
        if card_id == "All Guests":
            members = get_members(True)
            for member in members:
                card_id = member["card_id_orig"]
                if member['id'] == None:
                    status, card_data = toggle_inside_shack(card_id, database)
                    if status:
                        on_time, stay_length = stay_length_of_user(card_id, database)
                        add_time_log(card_id, stay_length, on_time, database)
                        user = card_get_user(card_id, database)
                        unk_webhook_push(card_data, card_id, False, config, stay_length)
            await ctx.respond("You have successfully tagged out all guests.")
            return
        
        try:
            card_id = int(card_id.split("(")[1].split(")")[0])
        except:
            await ctx.respond("Invalid card ID.")
            return
        
        if config["discord"]["admin_role"] is None:
            await ctx.respond("No admin role is set in the config, cannot tag out another user.")
            return
        if ctx.author.get_role(config["discord"]["admin_role"]) is None:
            await ctx.respond("You do not have permission to tag out another user.")
            return
        
    status, card_data = toggle_inside_shack(card_id, database)

    if status:
        on_time, stay_length = stay_length_of_user(card_id, database)
        add_time_log(card_id, stay_length, on_time, database)
        user = card_get_user(card_id, database)
        if user is not None:
            full_webhook_push(user["first_name"] + " " + user["last_name"], user["callsign"], user["position_in_club"], card_data, user["discord_user_id"], False, config, stay_length)
        else:
            unk_webhook_push(card_data, card_id, False, config, stay_length)
        await ctx.respond("You have successfully tagged out of the shack.")
    else:
        await ctx.respond("You are not currently tagged in.")
    
@bot.slash_command()
async def leaderboard(ctx: discord.ApplicationContext):
    leaderboard = get_ranked_list_users_by_time(database)
    embed = discord.Embed(title="", color=0x47d530)
    embed.set_author(name="Shack Time Leaderboard", icon_url="https://em-content.zobj.net/source/twitter/53/trophy_1f3c6.png")

    embed_description = ""
    for i, user in enumerate(leaderboard):
        # Format for name: John D. (@Tag)
        # If privacy is enabled, name is [Name Redacted], but keep the @Tag, unless there is no discord user id
        name = user["first_name"] + " " + user["last_name"][:1] + ". "

        if user["privacy_enabled"] == 1:
            name = "[Name Redacted] "
        if user["discord_user_id"] is not None:
            name += f"(<@{user['discord_user_id']}>)"
        
        formatted_time = display_time(user["total_time"])
        emoji = get_emoji_from_rank(i)
        embed_description += f"{emoji} {name} - {formatted_time}\n"
        if i == 2:
            embed_description += "\n"
            
    embed.description = embed_description
    await ctx.respond(embed=embed)
        
        

bot.run(config["discord"]["discord_token"])
