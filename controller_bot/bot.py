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

def get_members(include_unk=False):
    cursor = database.cursor(dictionary=True)
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

def get_members_from_db(ctx: discord.AutocompleteContext):
    if config["discord"]["admin_role"] is None:
        return ["unauth"]
    if ctx.interaction.user.get_role(config["discord"]["admin_role"]) is None:
        return ["unauth"]
    
    cursor = database.cursor()
    cursor.execute("""SELECT cards.id AS card_id, members.first_name, members.last_name FROM cards LEFT JOIN members ON members.card_id = cards.id WHERE cards.inside_shack = 1""")
    members = cursor.fetchall()
    cursor.close()
    
    member_list = []
    guests_present = False
    for member in members:
        m_name =f"{member[1]} {member[2]} ({member[0]})"
        if member[1] is None or member[2] is None:
            m_name = f"Guest User ({member[0]})"
            guests_present = True
        member_list.append(m_name)
    if guests_present:
        member_list.append("All Guests")
    return member_list

@bot.slash_command()
async def shack_members(ctx):
    members = get_members()
    embed = generate_members_embed(members)
    await ctx.respond(embed=embed)

# TODO: this
@bot.slash_command()
async def tag_out(ctx: discord.ApplicationContext, card_id: Option(str, "The card ID to tag out of the shack.", required=False, autocomplete=get_members_from_db)):
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
    

bot.run(config["discord"]["discord_token"])
