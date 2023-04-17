from typing import Optional

import discord, logging, os
from discord.ext.commands import CommandNotFound
from discord.ext import commands
from discord import app_commands, Message, File
from settings import TOKEN, GUILD_ID, BOT_COMMANDS, NEED_LOGS

from datetime import datetime, timezone

from karma_dc.karma import get_action_info, thank_back_check, add_points, get_user_by_user_id, get_role_id
from karma_dc.create_db import Log
from karma_dc.admin import get_log_channel, if_admin_command, admin_comand, cancel_action, export_log, export_users
from karma_dc.admin import leaderboard as lb

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

MY_GUILD = discord.Object(id=GUILD_ID)  # replace with your guild id

engine = create_engine("sqlite:///users.db")
session = sessionmaker(bind=engine)
s = session()

logger = logging.getLogger()

# dd/mm/YY H:M:S
dt_string = "bot_log_public"
log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", dt_string + ".log")

with open(log_file, mode='a+'): pass

logging.basicConfig(level=logging.INFO, 
                    filename = log_file,
                    format = "%(asctime)s - %(module)s - %(levelname)s - %(funcName)s: %(lineno)d - %(message)s",
                    datefmt='%H:%M:%S',
                    force=True,
                )
                
logger.warning("RERUNNING")

# Define a simple View that gives us a confirmation menu
class CancelButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.value = None

    # When the confirm button is pressed, set the inner value to `True` and
    # stop the View from listening to more input.
    # We also send the user an ephemeral message that we're confirming their choice.
    @discord.ui.button(label='Cancel', style=discord.ButtonStyle.red)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message('Cancelled!', ephemeral=True)
        self.value = True
        self.stop()


class MyClient(commands.Bot):
    def __init__(self, *, command_prefix: str, intents: discord.Intents):
        super().__init__(intents=intents, command_prefix=command_prefix)
        # A CommandTree is a special type that holds all the application command
        # state required to make it work. This is a separate class because it
        # allows all the extra state to be opt-in.
        # Whenever you want to work with application commands, your tree is used
        # to store and work with them.
        # Note: When using commands.Bot instead of discord.Client, the bot will
        # maintain its own tree instead.
        # self.tree = app_commands.CommandTree(self)

    # In this basic example, we just synchronize the app commands to one guild.
    # Instead of specifying a guild to every command, we copy over our global commands instead.
    # By doing so, we don't have to wait up to an hour until they are shown to the end-user.
    # async def setup_hook(self):
    #     # This copies the global commands over to your guild.
    #     self.tree.copy_global_to(guild=MY_GUILD)
    #     await self.tree.sync(guild=MY_GUILD)
    
    async def give_karma_role(self: discord.Client, member: discord.Member, role_id: int):
        if role_id == -1:
            return
        guild =  await self.fetch_guild(GUILD_ID)

        if not isinstance(member, discord.Member):
            member = await guild.fetch_member(member.id)

        roles = guild.roles
        for role in roles:
            if role.id == role_id:
                await member.add_roles(role)

    async def send_log_message(self: discord.Client, content: str, message=None):
        if not NEED_LOGS:
            return
        channel = await self.fetch_channel(int(get_log_channel()))
        if message is None:
            return await channel.send(content)
        
        content += "\n{}".format(message.jump_url)
        user_message = message.content

        ch2 = await self.fetch_channel(message.reference.channel_id)
        helper_message = await ch2.fetch_message(message.reference.message_id)
        helper_message = helper_message.content
        
        content += "\nhelper message: {}\nuser message: {}".format(helper_message, user_message)

        view = CancelButton()
        log_msg = await channel.send(content, view=view)

        await view.wait()
        if view.value is None:
            print('Timed out...')
        elif view.value:
            cancel_action(message.id, s=s)
            await log_msg.edit(
                content=log_msg.content + "\nCANCELLED"
            )


intents = discord.Intents.default()
intents.message_content = True
intents.members = True
client = MyClient(command_prefix='!', intents=intents)

@client.event
async def on_command_error(ctx, error):
    if isinstance(error, CommandNotFound):
        return
    raise error

@client.event
async def on_ready():
    print(f'Logged in as {client.user} (ID: {client.user.id})')
    print('------')

@client.event
async def on_message(message: Message):
    if message.author.id == client.user.id:
        return
    await client.process_commands(message)
    # exit function if message is not a reply
    if message.type != discord.MessageType.reply:
        return
    if message.author == client.user:
        return
    
    action_id, action_input, points = get_action_info(message.content)
    
    if points == 0:
        return

    channel_id = message.channel.id
    channel_name = message.channel.name
    message_id = message.id
    parent_message_id = message.reference.message_id

    user_author = message.author
    parent_message = await message.channel.fetch_message(message.reference.message_id)
    helper_author = parent_message.author
    time = datetime.now(tz=timezone.utc)

    # print(type(user_author), type(helper_author))
    if user_author.bot or helper_author.bot:
        return
    if user_author == helper_author:
        return
    
    user_id = user_author.id
    helper_id = helper_author.id
    user_name = user_author.name + "#" + user_author.discriminator
    helper_name = helper_author.name + "#" + helper_author.discriminator

    is_thank_back = thank_back_check(parent_message_id, user_id=user_id, s=s)

    ans = add_points(
        logger=logger,
        msg_id=message_id,
        helper_id=helper_id, helper_name=helper_name,
        user_id=user_id, user_name=user_name,
        channel_id=channel_id,
        channel_name=channel_name,
        points_change=points,
        action_id=action_id, action_input=action_input,
        is_thank_back=is_thank_back,
        time=time,
        s=s
    )
    if ans is None:
        return
    
    ans, changed = ans
    if changed:
        helper_object = get_user_by_user_id(helper_id, s)
        
        await client.give_karma_role(helper_author, get_role_id(helper_object.rolename))

    await client.send_log_message(ans, message)

@client.command()
async def karma(ctx: commands.Context, *args):
    # if ctx.channel.id != BOT_COMMANDS:
    #     return
    user = get_user_by_user_id(ctx.author.id, s)
    if user is None:
        points = 0
    else:
        points = user.points
    await ctx.send("{} You have {} points in your pocket. Keep building 💪".format(ctx.author.mention, points))

@client.command()
async def leaderboard(ctx: commands.Context, *args):
    ans = lb(s=s)
    if len(ans) > 20:
        ans = ans[:20]
    await ctx.send('\n'.join(ans))

@client.command()
async def export(ctx: commands.Context, *args):
    if not if_admin_command(ctx.channel.id, ctx.author.id):
        return
    export_log(s)
    export_users(s)
    users_file = File("data/users.csv")
    log_file = File("data/logs.csv")

    await ctx.send(files=[users_file, log_file])

@client.command()
async def show(ctx: commands.Context, member: Optional[discord.Member], *args):
    if not if_admin_command(ctx.channel.id, ctx.author.id):
        return
    if (len(args) != 0) or (not isinstance(member, discord.Member)):
        return await ctx.send("Something wrong with command")
    uname = member.name + "#" + member.discriminator
    ans = admin_comand("show", user_name=uname, user_id=member.id, num=None, s=s)

    await ctx.send(ans)

@client.command()
async def add(ctx: commands.Context, member: Optional[discord.Member], *args):
    if not if_admin_command(ctx.channel.id, ctx.author.id):
        return
    if (len(args) != 1) or (not isinstance(member, discord.Member)) or (not str(args[0]).isdigit()):
        return await ctx.send("Something wrong with command")

    uname = member.name + "#" + member.discriminator
    ans = admin_comand("add", user_name=uname, user_id=member.id, num=int(args[0]), s=s)
    
    admin_name = ctx.author.name + "#" + ctx.author.discriminator
    rows = [
        f"admin: {admin_name}",
        f"admin id: {ctx.author.id}",
        f"action: add",
        f"user: {uname}",
        f"amount: {args[0]}"
    ]
    log_msg = '\n'.join(rows)

    await client.send_log_message(log_msg)
    await ctx.send(ans)
    
@client.command()
async def sub(ctx: commands.Context, member: Optional[discord.Member], *args):
    if not if_admin_command(ctx.channel.id, ctx.author.id):
        return
    if (len(args) != 1) or (not isinstance(member, discord.Member)) or (not str(args[0]).isdigit()):
        return await ctx.send("Something wrong with command")

    uname = member.name + "#" + member.discriminator
    ans = admin_comand("sub", user_name=uname, user_id=member.id, num=int(args[0]), s=s)
    
    admin_name = ctx.author.name + "#" + ctx.author.discriminator
    rows = [
        f"admin: {admin_name}",
        f"admin id: {ctx.author.id}",
        f"action: sub",
        f"user: {uname}",
        f"amount: {args[0]}"
    ]
    log_msg = '\n'.join(rows)

    await client.send_log_message(log_msg)
    await ctx.send(ans)

@client.command()
async def set(ctx: commands.Context, member: Optional[discord.Member], *args):
    if not if_admin_command(ctx.channel.id, ctx.author.id):
        return
    if (len(args) != 1) or (not isinstance(member, discord.Member)) or (not str(args[0]).isdigit()):
        return await ctx.send("Something wrong with command")

    uname = member.name + "#" + member.discriminator
    ans = admin_comand("set", user_name=uname, user_id=member.id, num=int(args[0]), s=s)
    
    admin_name = ctx.author.name + "#" + ctx.author.discriminator
    rows = [
        f"admin: {admin_name}",
        f"admin id: {ctx.author.id}",
        f"action: set",
        f"user: {uname}",
        f"amount: {args[0]}"
    ]
    log_msg = '\n'.join(rows)

    await client.send_log_message(log_msg)
    await ctx.send(ans)
    
client.run(TOKEN)