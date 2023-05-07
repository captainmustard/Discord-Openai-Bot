import os
import discord
from discord import app_commands
from discord.ext import tasks
from discord.utils import get
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
import math
import asyncio
from lxml import etree

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

async def calculate_heat_index(temperature, humidity):
    # Convert Celsius to Fahrenheit
    fahrenheit = temperature

    # Simple formula for heat index
    heat_index_simple = 0.5 * (fahrenheit + 61.0 + ((fahrenheit - 68.0) * 1.2) + (humidity * 0.094))

    # Full regression equation
    heat_index_regression = -42.379 + 2.04901523 * fahrenheit + 10.14333127 * humidity - 0.22475541 * fahrenheit * humidity - 0.00683783 * fahrenheit**2 - 0.05481717 * humidity**2 + 0.00122874 * fahrenheit**2 * humidity + 0.00085282 * fahrenheit * humidity**2 - 0.00000199 * fahrenheit**2 * humidity**2

    # Adjustments
    if 80 <= fahrenheit <= 112 and humidity < 13:
        adjustment = ((13 - humidity) / 4) * math.sqrt((17 - abs(fahrenheit - 95)) / 17)
        heat_index_regression -= adjustment
    elif 80 <= fahrenheit <= 87 and humidity > 85:
        adjustment = ((humidity - 85) / 10) * ((87 - fahrenheit) / 5)
        heat_index_regression += adjustment

    # Use the simple formula if the heat index is below 80°F, otherwise use the full regression equation
    heat_index = heat_index_simple if heat_index_simple < 80 else heat_index_regression

    return round(heat_index)


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
            temperature = forecast['temperature']
            humidity = forecast['relativeHumidity']['value']
            wind_direction = forecast['windDirection']
            wind_speed = forecast['windSpeed']

            if 'heatIndex' in forecast:
                heat_index = forecast['heatIndex']['value']
            else:
                heat_index = await calculate_heat_index(temperature, humidity)

            weather_info[hour] = {'forecast': forecast, 'heat_index': heat_index}

    # Create a string for each hour's forecast
    weather_strings = []
    for hour, info in weather_info.items():
        forecast = info['forecast']
        heat_index = info['heat_index']
        humidity = forecast['relativeHumidity']['value']
        weather_string = f"At {hour}:00: {forecast['shortForecast']}, {forecast['temperature']}°{forecast['temperatureUnit']}, humidity: {humidity}%, wind speed: {forecast['windSpeed']} mph from {forecast['windDirection']}, heat index: {heat_index}°F."
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
            "content": f"summarize the weather forecast for the day in the writing style of boomhauer from king of the hill. Be consise and to the point. Limit your response to 1000 characters. Follow up with suggestions for weather appropriate outdoor activities. Here is the data {weather_data}",
        },
    ]

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=messages,
        max_tokens=2000,
        n=1,
        stop=None,
        temperature=0.5,
    )

    response_text = response['choices'][0]['message']['content'].strip()
    return response_text

async def send_daily_weather():
    for guild in client.guilds:
        general_channel = discord.utils.get(guild.text_channels, name='general')
        if general_channel:
            response_text = await get_gpt4_response_with_weather()
            await general_channel.send(response_text)

last_alert_ids = set()

async def get_weather_alerts():
    global last_alert_ids

    req = requests.get('https://alerts.weather.gov/cap/wwaatmget.php?x=ARZ029&y=0')
    xml = req.content
    ns = {'atom': 'http://www.w3.org/2005/Atom', 'cap': 'urn:oasis:names:tc:emergency:cap:1.1'}
    atom = etree.fromstring(xml)

    alerts = []

    current_alert_ids = set()

    for element in atom.xpath('//atom:entry', namespaces=ns):
        alert_id = element.find("atom:id", namespaces=ns).text
        current_alert_ids.add(alert_id)

        if alert_id in last_alert_ids:
            continue

        title_element = element.find("atom:title", namespaces=ns)
        title = title_element.text if title_element is not None else ''

        summary_element = element.find("atom:summary", namespaces=ns)
        summary = summary_element.text if summary_element is not None else ''

        # Check if the text contains the "no active alerts" message
        if title.find("There are no active watches, warnings or advisories") != -1:
            continue

        published_element = element.find("atom:published", namespaces=ns)
        published = published_element.text if published_element is not None else ''

        effective_element = element.find("cap:effective", namespaces=ns)
        effective = effective_element.text if effective_element is not None else ''

        expires_element = element.find("cap:expires", namespaces=ns)
        expires = expires_element.text if expires_element is not None else ''

        urgency_element = element.find("cap:urgency", namespaces=ns)
        urgency = urgency_element.text if urgency_element is not None else ''

        severity_element = element.find("cap:severity", namespaces=ns)
        severity = severity_element.text if severity_element is not None else ''

        certainty_element = element.find("cap:certainty", namespaces=ns)
        certainty = certainty_element.text if certainty_element is not None else ''

        area_desc_element = element.find("cap:areaDesc", namespaces=ns)
        area_desc = area_desc_element.text if area_desc_element is not None else ''

        if title:
            published_formatted = datetime.strptime(published, "%Y-%m-%dT%H:%M:%S%z").strftime("%b %-d, %I:%M %p %Z")
            alert_text = f"{title} - Issued on {published_formatted}\nAffected Counties: {area_desc}\nSummary: {summary}\nUrgency: {urgency}\nSeverity: {severity}\n"
            alerts.append((title, alert_text))

    last_alert_ids = current_alert_ids
    return alerts




@tasks.loop(minutes=5)  # Adjust the interval as needed
async def check_weather_alerts():
    alerts = await get_weather_alerts()
    print(alerts)

    if not alerts:
        print("no weather alerts")
        return

    for guild in client.guilds:
        general_channel = get(guild.text_channels, name="robo-sexuals-anonymous")

        if general_channel is None:
            for channel in guild.text_channels:
                if channel.permissions_for(guild.me).send_messages:
                    general_channel = channel
                    break

        if general_channel is None:
            continue

        for title, text in alerts:
            await general_channel.send(f"**{title}**\n{text}\n")

@tasks.loop(hours=24)
async def daily_weather_task():
    now = datetime.now()
    next_run = now.replace(hour=7, minute=0, second=0, microsecond=0)
    print("running daily weather alert")
    if now > next_run:
        next_run += timedelta(days=1)

    await discord.utils.sleep_until(next_run)
    await send_daily_weather()

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
    daily_weather_task.start()
    check_weather_alerts.start()

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
