import logging
from asyncio import sleep
import datetime
import discord
import re
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from discord.ext import commands
#from sql.polls import SqlClass
from discord_bot.sqlHandler import (select, execute)

log = logging.getLogger(__name__)


class AnonPoll(commands.Cog):
    def __init__(self, client):
        self.client = client

        self.pollsigns = ["🇦", "🇧", "🇨", "🇩", "🇪", "🇫", "🇬", "🇭", "🇮", "🇯", "🇰", "🇱", "🇲", "🇳", "🇴",
                          "🇵", "🇶", "🇷", "🇸", "🇹", "🇺", "🇻", "🇼", "🇽", "🇾", "🇿"]
        self.reg = re.compile(r'({.+})\ *(\[[^\n\r\[\]]+\] *)+')

        # starts up the schedular and all the tasks for all commands on timer
        self.sched = AsyncIOScheduler()
        client.loop.create_task(self._async_init())
        self.sched.start()

    async def _async_init(self) -> None:
        """Queues up all in progress polls
        :return:
        """
        await self.client.wait_until_ready()
        polls = select("SELECT time, message_id, channel_id, guild_id FROM polls")
        now = datetime.datetime.now()

        for poll in polls:
            if not poll[0]:
                pass  # no end time, does nothign
            else:
                time = datetime.datetime.strptime(poll[0], '%Y-%m-%d %H:%M:%S.%f')
                if time > now:
                    self.sched.add_job(self._end_poll, "date", run_date=time,
                                       id=str(poll[1]) + str(poll[2]) + str(poll[3]),
                                       args=(poll[1], poll[2], poll[3])
                                       )
                else:
                    await self._end_poll(poll[1], poll[2], poll[3])

    def _delete_poll(self, message_id: int, channel_id: int, guild_id: int) -> None:
        """Deletes the poll
        :param message_id:
        :param channel_id:
        :param guild_id:
        :return:
        """
        poll = select("""SELECT time, message_id, channel_id, guild_id FROM polls
        WHERE message_id=%s AND channel_id=%s AND guild_id=%s""", message_id, channel_id, guild_id )
        if poll:
            log.debug('Deleting poll')
            execute("DELETE FROM polls WHERE message_id=%s AND channel_id=%s AND guild_id=%s", message_id, channel_id, guild_id)
            if poll[0][0]:
                self.sched.remove_job(str(poll[0][1]) + str(poll[0][2]) + str(poll[0][3]))

    async def _end_poll(self, message_id: int, channel_id: int, guild_id: int) -> None:
        """End function for when timed polls finish. counts up votes and sends into channel
        :param message_id: message id of the poll
        :param channel_id: channel id of the poll
        :param guild_id: guild id of the poll
        :return:
        """
        embed = self._count_poll(message_id, channel_id, guild_id)
        channel = self.client.get_channel(channel_id)

        await channel.send(embed=embed)
        execute("DELETE FROM polls WHERE message_id=%s AND channel_id=%s AND guild_id=%s", message_id, channel_id, guild_id)

    def _count_poll(self, message_id: int, channel_id: int, guild_id: int) -> object:
        """Counts up the votes for a poll and returns the embed
        :param message_id: message id of the poll
        :param channel_id: channel id of the poll
        :param guild_id: guild of the poll
        :return: discord.Embed
        """
        poll_info = select("""SELECT polls.name, options.name, options.emote_id, polls.message_id, polls.channel_id, polls.guild_id
        FROM polls, options
        WHERE polls.message_id=%s AND polls.channel_id=%s AND polls.guild_id=%s
        AND polls.message_id = options.message_id
        AND polls.channel_id = options.channel_id
        AND polls.guild_id = options.guild_id""", message_id, channel_id, guild_id)

        votes = {}
        for poll in poll_info:
            votes[poll[2]] = [0, poll[1]]

        user_votes = select("SELECT votes.emote_id FROM votes WHERE votes.message_id=%s AND votes.channel_id=%s AND votes.guild_id=%s", message_id, channel_id, guild_id)

        for vote in user_votes:
            votes[vote[0]][0] += 1

        description = ''
        for emote, value in votes.items():
            description += f'{emote} {value[1]}: {value[0]}\n'

        embed = discord.Embed(title=poll_info[0][0], color=discord.Color.gold(), description=description)
        return embed

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload) -> None:
        """Toggles user vote
        :param payload: info about the user who voted
        :return:
        """
        if payload.member == self.client.user:
            return

        # Get Polls
        if select("""SELECT polls.name, options.name, options.emote_id, polls.message_id, polls.channel_id, polls.guild_id
        FROM polls, options
        WHERE polls.message_id=%s AND polls.channel_id=%s AND polls.guild_id=%s
        AND polls.message_id = options.message_id
        AND polls.channel_id = options.channel_id
        AND polls.guild_id = options.guild_id""", payload.message_id, payload.channel_id, payload.guild_id):
            # Check votes
            if select("SELECT message_id FROM votes WHERE votes.discord_id=%s AND votes.emote_id=%s AND votes.message_id=%s AND votes.channel_id=%s AND votes.guild_id=%s", payload.user_id, payload.emoji.name, payload.message_id, payload.channel_id, payload.guild_id):
                # Remove votes
                execute("DELETE FROM votes WHERE discord_id=%s AND emote_id=%s AND message_id=%s AND channel_id=%s AND guild_id=%s", payload.user_id, payload.emoji.name, payload.message_id, payload.channel_id, payload.guild_id)
            else:
                # Add vote
                execute("INSERT INTO votes (`discord_id`, `emote_id`, `message_id`, `channel_id`, `guild_id`) VALUES (%s,%s,%s,%s,%s)",payload.user_id, payload.emoji.name, payload.message_id, payload.channel_id, payload.guild_id)

            # deletes reaction if it found the poll
            channel = self.client.get_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)
            await message.remove_reaction(payload.emoji, payload.member)

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload) -> None:
        """Checks whether a user deleted one of gregories messages
        then checks whether it was one of the polls and deletes it
        :param payload:
        :return:
        """
        if payload.cached_message is not None:
            if payload.cached_message.author == self.client.user:
                self._delete_poll(payload.message_id, payload.channel_id, payload.guild_id)

    @commands.command(aliases=['poll2'])
    async def anonpoll(self, ctx, *, args) -> None:
        """Creates anonymous poll with optional timed ending. With a limit of 20 options
        :param ctx:
        :param args: 1d2h3m4s {title}[arg][arg]
        :return: Creates a poll with timed output
        """
        log.debug('matching regex poll')
        time = None
        # checks message against regex to see if it matches
        if not self.reg.match(args):
            # check if it has time at start of command
            # splits arguments and datetime
            index = args.find(' ')
            time = args[:index]
            args = args[index:].lstrip()

            # converts to datetime
            time_dict = {}
            check = False
            for time_letter in ['d', 'h', 'm', 's']:
                found = time.find(time_letter)
                if found != -1:
                    check = True
                    split_arg = time.split(time_letter)
                    time_dict[time_letter] = float(split_arg[0])
                    time = split_arg[1]
                else:
                    time_dict[time_letter] = 0

            if not check:
                raise discord.errors.DiscordException
            else:
                time = datetime.datetime.now() + datetime.timedelta(days=time_dict['d'], hours=time_dict['h'], minutes=time_dict['m'],
                                                                    seconds=time_dict['s'])

            # checks if the args are formatted correctly
            if not self.reg.match(args):
                raise discord.errors.DiscordException

        # have args and possible datetime
        # formatting of arguments in message
        args = args.split('[')
        name = args.pop(0)[1:]
        name = name[:name.find('}')]
        args = [arg[:arg.find(']')] for arg in args]  # thanks ritz for this line

        # filtering out
        if len(args) > 20:
            await ctx.send(f"bad {ctx.author.name}! thats too much polling >:(")
            return
        elif len(args) == 0:
            await ctx.send(f"bad {ctx.author.name}! thats too little polling >:(")
            return
        elif name == '' or '' in args:
            await ctx.send(f"bad {ctx.author.name}! thats too simplistic polling >:(")
            return

        # creating embed for poll
        # main body
        description = ''
        for count in range(len(args)):
            description += f'{self.pollsigns[count]} {args[count]}\n\n'

        footer = 'endpoll <id> (true for dms)'

        embed = discord.Embed(title=name, color=discord.Color.gold(), description=description)
        embed.set_footer(text=footer)
        msg = await ctx.send(embed=embed)
        # adds a message id to the end of the poll
        footer += f'\nid: {msg.id}'
        embed.set_footer(text=footer)
        await msg.edit(embed=embed)

        # SQL Setup
        log.debug('Uploading poll data to database')
        # self.sql.add_poll(msg.id, msg.channel.id, msg.author.guild.id, name, time)
        execute(
            """INSERT INTO polls (`message_id`, `channel_id`, `guild_id`, `name`, `time`) 
            VALUES (%s,%s,%s,%s,%s)""",
            msg.id, msg.channel.id, msg.author.guild.id, name, time
        )
        # self.sql.add_options(msg.id, msg.channel.id, msg.author.guild.id, self.pollsigns, args)
        for n, arg in enumerate(args):
            execute(
                """INSERT INTO options 
                (`message_id`, `channel_id`, `guild_id`, `emote_id`, `name`) 
                VALUES (%s,%s,%s,%s,%s)""",
                msg.id, msg.channel.id, msg.author.guild.id, self.pollsigns[n], arg
            )
        
        # Background task
        if time:
            self.sched.add_job(self._end_poll, "date", run_date=time,
                               id=str(msg.id) + str(msg.channel.id) + str(msg.author.guild.id),
                               args=(msg.id, msg.channel.id, msg.author.guild.id)
                               )

        # adding reactions
        log.debug('Adding reactions')
        for count in range(len(args)):
            await msg.add_reaction(self.pollsigns[count])

    @anonpoll.error
    async def pollanon_error(self, ctx, error) -> None:
        """Error output for poll
        :param ctx:
        :param error: The type of error
        :return:
        """
        if isinstance(error, commands.errors.MissingRequiredArgument) or isinstance(error, discord.errors.DiscordException):
            await ctx.send('`ERROR Missing Required Argument: make sure it is .anonpoll <time 1d2h3m4s> {title} [args]`')
        else:
            log.info(error)

    @commands.command(aliases=['checkvote'])
    async def checkvotes(self, ctx) -> None:
        """Checks what polls you have voted on in this server
        :param ctx:
        :return: embed of votes sent to user's dms
        """
        await ctx.message.delete()

        # votes = self.sql.check_votes(ctx.author.id, ctx.author.guild.id)
        votes = select("""
        SELECT polls.message_id, polls.channel_id, polls.guild_id, options.emote_id, options.name, polls.name
        FROM votes, options, polls
        WHERE votes.discord_id = %s AND votes.guild_id = %s
        AND votes.emote_id = options.emote_id
        AND votes.message_id = options.message_id AND options.message_id = polls.message_id
        AND votes.channel_id = options.channel_id AND options.channel_id = polls.channel_id
        AND votes.guild_id = options.guild_id AND options.guild_id = polls.guild_id
        """, ctx.author.id, ctx.author.guild.id)
        # [(809138215331168317, 809080848057106432, 798298345177088022, '🇦', 'arg1', 'name of poll'), ...
        # count unique occurrences of (message_id, channel_id, guild_id) in (votes[0],votes[1],votes[2])
        polls = [(vote[0], vote[1], vote[2]) for vote in votes]  # removes unnessary code from list
        polls = list(dict.fromkeys(polls))  # removes item if it appears in the list poll
        # [(811247486101487646, 798309035945754694, 798298345177088022), ...

        if len(polls) == 0:
            # sends output if user hasnt voted on anything
            msg = await ctx.send('You havent voted on any active polls')
            await sleep(10)
            await msg.delete()
        else:
            # generates the embed
            embed = discord.Embed(title="You have voted", colour=discord.Color.gold())
            for poll in polls:
                # generates the field
                title = ''
                description = ''
                for vote in votes:
                    if (vote[0], vote[1], vote[2]) == poll:  # goes though each poll once by one
                        # TODO: Rewrite code to automatically do this using list ordering rather than this
                        title = vote[-1]
                        description += f"\n{vote[3]} {vote[4]}\n"

                embed.add_field(name=title, value=description[:-1], inline=True)
            try:
                await ctx.author.send(embed=embed)
            except discord.errors.Forbidden:
                # if user has dms disabled
                msg = await ctx.send('I cant send you a DM! please check your discord settings')
                await sleep(10)
                await msg.delete()

    @commands.command(aliases=['stoppoll', 'stopoll', 'deletepoll', 'yeetpoll', "polln't"])
    async def endpoll(self, ctx, message_id: int, dm: bool) -> None:
        """Ends the poll and outputs the result
        :param ctx:
        :param message_id: the message id of the poll
        :param dm: Whether the bot should send the results to dms
        :return:
        """
        embed = self._count_poll(message_id, ctx.channel.id, ctx.author.guild.id)
        if not dm:
            await ctx.send(embed=embed)
            execute("DELETE FROM polls WHERE message_id=%s AND channel_id=%s AND guild_id=%s", message_id, ctx.channel.id, ctx.author.guild.id)
        else:
            try:
                await ctx.author.send(embed=embed)
                execute("DELETE FROM polls WHERE message_id=%s AND channel_id=%s AND guild_id=%s", message_id, ctx.channel.id, ctx.author.guild.id)
            except discord.errors.Forbidden:
                # if user has dms disabled
                msg = await ctx.send('I cant send you a DM! please check your discord settings')
                await sleep(10)
                await msg.delete()

    @endpoll.error
    async def endpoll_error(self, ctx, error):
        """Error handling for the end poll function
        :param ctx:
        :param error:
        :return:
        """
        if isinstance(error, commands.errors.MissingRequiredArgument) or isinstance(error,
                                                                                    discord.errors.DiscordException):
            await ctx.send(
                '`ERROR Missing Required Argument: make sure it is .endpoll <message id> <send to dms True/False>`')
        else:
            log.info(error)
