import os
import discord
from discord import app_commands
import openai
import json
import requests
import io
import base64
from PIL import Image, PngImagePlugin
import toml

# Load the configuration from the config.toml file
config = toml.load("config.toml")

# Access the API keys from the configuration
oaiapi_key = config["keys"]["OPENAI_API_KEY"]
discord_bot_token = config["keys"]["DISCORD_BOT_TOKEN"]

# Access the prompts from the configuration
bot_prompt = config["prompts"]["default_prompt"]

# Access the txt2img configuration from the configuration
stable_diffusion_url = config["txt2img"]["stable_diffusion"]
negative_prompt = config["txt2img"]["negative_prompt"]

# Set up the OpenAI API client
openai.api_key = oaiapi_key
print(f"API Key: {openai.api_key}")

# Discord permissions
intents = discord.Intents.default()
intents.message_content = True
intents.typing = False
intents.presences = False
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

async def get_gpt4_response(prompt):
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": bot_prompt},
            {"role": "user", "content": prompt},
        ],
        max_tokens=3500,
        n=1,
        stop=None,
        temperature=0.5,
    )
    return response['choices'][0]['message']['content'].strip()

# Stable Diffusion setup
async def txt2img(prompt: str):
    url = stable_diffusion_url
    payload = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "steps": 25
    }

    response = requests.post(url=f'{url}/sdapi/v1/txt2img', json=payload)
    r = response.json()

    for i in r['images']:
        image = Image.open(io.BytesIO(base64.b64decode(i.split(",", 1)[0])))

        png_payload = {
            "image": "data:image/png;base64," + i
        }
        response2 = requests.post(url=f'{url}/sdapi/v1/png-info', json=png_payload)

        pnginfo = PngImagePlugin.PngInfo()
        pnginfo.add_text("parameters", response2.json().get("info"))
        image.save('output.png', pnginfo=pnginfo)

    return 'output.png'

# Discord slash commands
@tree.command(name="computer", description="Ask a question")
async def gpt4(interaction, *, prompt: str):
    print("Received prompt:", prompt)
    await interaction.response.defer()
    response = await get_gpt4_response(prompt)
    print("Received response:", response)
    await interaction.followup.send(response)

@tree.command(name="currentprompt", description="Print current prompt")
async def current_prompt(interaction):
    await interaction.response.send_message(f"Current bot prompt: ```{bot_prompt}```")

@tree.command(name="setprompt", description="Change the bot prompt")
async def set_prompt(interaction, *, new_prompt: str):
    global bot_prompt
    bot_prompt = new_prompt.strip()
    await interaction.response.send_message("Bot prompt changed.")

@tree.command(name="txt2img", description="Generate an image based on a given text")
async def generate_image(interaction: discord.Interaction, *, prompt: str):
    user_mention = interaction.user.mention
    await interaction.response.defer()
    output_file = await txt2img(prompt)
    with open(output_file, "rb") as image_file:
        image = discord.File(image_file, filename="output.png")
        await interaction.followup.send(content=f"{user_mention}, prompt: '{prompt}':", file=image)

# discord message commands
@client.event
async def on_ready():
    await tree.sync()  # Add the guild argument if needed
    print("Ready!")

@client.event
async def on_message(message):
    global bot_prompt

    if message.author == client.user:
        return
    elif client.user in message.mentions:
        prompt = message.content.replace(f'<@!{client.user.id}>', '').strip()
        response = await get_gpt4_response(prompt)
        await message.channel.send(response)

# warp 7, engage
client.run(discord_bot_token)
