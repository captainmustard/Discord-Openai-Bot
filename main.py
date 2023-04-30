import os
import discord
from discord.ext import commands
import openai

# Set up the OpenAI API client
openai.api_key = os.environ["OPENAI_API_KEY"]

intents = discord.Intents.default()
intents.message_content = True
intents.typing = False
intents.presences = False

# Set up the Discord bot
bot = commands.Bot(command_prefix="!", intents=intents)

# Define a helper function for making requests to the GPT-4 API
async def get_gpt4_response(prompt):
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",  # Change this to GPT-4 when it's available
        messages=[
            {"role": "system", "content": "Respond to everything in the writing style of Hunter S. Thompson."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=100,
        n=1,
        stop=None,
        temperature=0.5,
    )
    return response['choices'][0]['message']['content'].strip()

# Define a command that uses GPT-4 to generate a response
@bot.command(name="computer")
async def gpt4(ctx, *, prompt):
    response = await get_gpt4_response(prompt)
    await ctx.send(response)

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if bot.user in message.mentions:
        prompt = message.content.replace(f'<@!{bot.user.id}>', '').strip()
        response = await get_gpt4_response(prompt)
        await message.channel.send(response)
    await bot.process_commands(message)

# Run the bot
bot.run(os.environ["DISCORD_BOT_TOKEN"])
