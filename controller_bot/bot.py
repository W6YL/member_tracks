import mysql.connector
import discord
import json

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
                embed.add_field(name=f"Name Redacted", value=f"Privacy Enabled\nLogged in <t:{last_login}:R>", inline=True)
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

@bot.slash_command()
async def shack_members(ctx):
    members = get_members()
    embed = generate_members_embed(members)
    await ctx.respond(embed=embed)

bot.run(config["discord"]["discord_token"])
