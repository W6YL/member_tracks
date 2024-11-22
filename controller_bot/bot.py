import mysql.connector
import discord
import json

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

def get_members():
    cursor = database.cursor(dictionary=True)
    cursor.execute("""SELECT
    cards.id AS card_id,
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
        if member["id"] is None:
            continue
        members.append(member)
    cursor.close()
    return members

def card_get_user(card_id, database):
    cursor = database.cursor()
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
    cursor = database.cursor()
    cursor.execute("SELECT card_id FROM `members` WHERE `discord_user_id` = %s", (discord_id,))
    result = cursor.fetchone()
    cursor.close()
    if result is None:
        return None
    return result[0]

def toggle_inside_shack(card_id, database):
    cursor = database.cursor()
    cursor.execute("SELECT `inside_shack`,`card_data` FROM `cards` WHERE `id` = %s", (card_id,))
    result = cursor.fetchone()
    if result is None:
        return False, None
    if result[0] == 0:
        return False, result[1]
    
    cursor.execute("UPDATE `cards` SET `inside_shack` = 0 WHERE `id` = %s", (card_id,))
    cursor.close()
    database.commit()
    return True, result[1]

@bot.slash_command()
async def shack_members(ctx):
    members = get_members()
    embed = generate_members_embed(members)
    await ctx.respond(embed=embed)

# TODO: this
@bot.slash_command()
async def tag_out(ctx, card_id: Option(int, "The card ID to tag out of the shack.", required=False)):
    if card_id is None:
        card_id = get_card_id_from_discord(ctx.author.id, database)
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
    

bot.run(config["discord"]["discord_token"])
