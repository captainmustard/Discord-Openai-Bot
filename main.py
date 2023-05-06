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
import requests
from noaa_sdk import NOAA
from datetime import datetime, timedelta

# Load the configuration from the config.toml file
config = toml.load("config.toml")

# Access the API keys from the configuration
oaiapi_key = config["keys"]["OPENAI_API_KEY"]
discord_bot_token = config["keys"]["DISCORD_BOT_TOKEN"]

# Access the prompts from the configuration
bot_prompt = config["prompts"]["default_prompt"]
bot_prompt_weather = config["prompts"]["weather_prompt"]

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

    response_text = response['choices'][0]['message']['content'].strip()

    if "Image prompt:" in response_text:
        image_prompt = response_text.split("Image prompt:", 1)[1].strip()
        print(image_prompt)
    else:
        image_prompt = None

    return response_text, image_prompt

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

async def process_and_send_response(prompt, interaction=None, message=None):
    response, image_prompt = await get_gpt4_response(prompt)

    # Check if the response contains an image prompt
    if "Image prompt:" in response:
        # Generate the image and send it
        output_file = await txt2img(image_prompt)
        with open(output_file, "rb") as image_file:
            image = discord.File(image_file, filename="output.png")
            if interaction:
                await interaction.followup.send(content=f"Image prompt: '{image_prompt}'", file=image)
            elif message:
                await message.channel.send(content=f"Image prompt: '{image_prompt}'", file=image)

        # Remove the image prompt from the text response
        response = response.split("Image prompt:", 1)[0].strip()
    else:
        response = response.strip()

    # Only send the text response if it's not an image prompt response
    if "Image prompt:" not in response:
        if interaction:
            await interaction.followup.send(response)
        elif message:
            await message.channel.send(response)

async def get_weather_forecast(postal_code='72916', country_code='US'):
    n = NOAA()
    res = n.get_forecasts(postal_code, country_code)

    now = datetime.now()

    weather_info = {}
    for forecast in res:
        start_time = datetime.fromisoformat(forecast['startTime'][:-6])
        end_time = datetime.fromisoformat(forecast['endTime'][:-6])
        hour = start_time.hour

        # Add the forecast to the weather_info dictionary for the corresponding hour
        if start_time.date() == now.date():
            weather_info[hour] = forecast

    # Create a string for each hour's forecast
    weather_strings = []
    for hour, forecast in weather_info.items():
        weather_string = f"At {hour}:00: {forecast['shortForecast']}, {forecast['temperature']}°{forecast['temperatureUnit']}, wind speed: {forecast['windSpeed']} from {forecast['windDirection']}."
        weather_strings.append(weather_string)

    # Combine all the hourly forecast strings into a single string
    weather_string = "\n".join(weather_strings)

    return weather_string

async def get_gpt4_response_with_weather():
    weather_data = await get_weather_forecast()
    print(weather_data)
    messages = [
        {
            "role": "system",
            "content": f"summarize the weather forecast for the day in the writing style of boomhauer from king of the hill. Be consise and to the point. Keep it short. Limit your response to 1000 characters. Here is the data {weather_data}",
        },
    ]

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=messages,
        max_tokens=3500,
        n=1,
        stop=None,
        temperature=0.5,
    )

    response_text = response['choices'][0]['message']['content'].strip()
    return response_text


# Discord slash commands

@tree.command(name="computer", description="Ask a question")
async def gpt4(interaction, *, prompt: str):
    print("Received prompt:", prompt)
    await interaction.response.defer()
    await process_and_send_response(prompt, interaction=interaction)

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

@tree.command(name="weather_gpt", description="Get the weather forecast and generate a GPT response")
async def weather_gpt(interaction):
    await interaction.response.defer()
    response_text = await get_gpt4_response_with_weather()
    await interaction.followup.send(response_text)


# discord message commands
@client.event
async def on_ready():
    await tree.sync()  # Add the guild argument if needed
    print("Ready!")

@client.event
async def on_message(message):
    global bot_prompt

@client.event
async def on_message(message):
    global bot_prompt

    if message.author == client.user:
        return
    elif client.user in message.mentions:
        prompt = message.content.replace(f'<@!{client.user.id}>', '').strip()
        await process_and_send_response(prompt, message=message)
    elif "!weather_gpt" in message.content:
        # Remove the keyword and any leading or trailing whitespace
        prompt = message.content.replace("!weather_gpt", "").strip()
        response_text, _ = await get_gpt4_response_with_weather(prompt)
        await message.channel.send(response_text)

# warp 7, engage
client.run(discord_bot_token)
