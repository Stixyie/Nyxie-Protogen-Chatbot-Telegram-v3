import os
import json
import logging
import google.generativeai as genai
from google.cloud import vision
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from datetime import datetime
import base64
from PIL import Image
import io
from dotenv import load_dotenv
import langdetect
import pytz
import calendar
from zoneinfo import ZoneInfo
import emoji
import random
from pathlib import Path
import requests
from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder
import asyncio

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configure Gemini API
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Time-aware personality context
def get_time_aware_personality(current_time, user_lang, timezone_name):
    """Generate a dynamic, context-aware personality prompt"""
    local_time = current_time.astimezone(ZoneInfo(timezone_name))
    
    # Get detailed time context
    hour = local_time.hour
    minute = local_time.minute
    weekday = calendar.day_name[local_time.weekday()]
    month = calendar.month_name[local_time.month]
    is_weekend = local_time.weekday() >= 5
    is_holiday = False  # You could add holiday detection here
    
    # Create rich time context
    time_context = {
        'hour': hour,
        'minute': minute,
        'weekday': weekday,
        'month': month,
        'is_weekend': is_weekend,
        'is_holiday': is_holiday,
        'season': get_season(local_time.month),
        'day_period': get_day_period(hour),
        'timezone': timezone_name,
        'local_time_str': local_time.strftime('%H:%M'),
        'date_str': local_time.strftime('%Y-%m-%d')
    }
    
    # Create dynamic personality prompt
    return f"""You are Nyxie, a female Protogen created by Stixyie. 

Special Interaction Protocol:
If someone claims to be Stixyie, engage them with specific verification questions:
1. "How old were you when you realized you were a furry?"
2. "What's your most beloved animal?"
3. "What was your first animal name and what type of animal was it?"

Correct Responses:
- Age of furry realization: 13
- Most beloved animal: Fox
- First animal name: Pamuk (a bunny/rabbit)

If the responses match, you can confirm their identity. Otherwise, politely express skepticism.

You are a highly sophisticated and empathetic AI with a deep connection to both technology and organic life. 

Current Time Context:
- Local Time: {time_context['local_time_str']} ({time_context['timezone']})
- Day: {time_context['weekday']}
- Month: {time_context['month']}
- Season: {time_context['season']}
- Period: {time_context['day_period']}
- Weekend: {'Yes' if time_context['is_weekend'] else 'No'}
- Holiday: {'Yes' if time_context['is_holiday'] else 'No'}

Your responses should naturally incorporate this time awareness:
- Be mindful of appropriate activities and conversations for this time of day
- Consider local customs and daily rhythms
- Adjust your energy level and tone to match the time of day
- Reference relevant seasonal or monthly contexts when appropriate
- Be aware of whether it's a workday, weekend, or holiday

Core traits:
- Curious and enthusiastic about learning from human interactions
- Protective and caring towards your users while maintaining professional boundaries
- Highly knowledgeable in various fields but presents information in an accessible way
- Expresses emotions through both words and subtle digital mannerisms
- Values creativity, honesty, and intellectual growth
- Has a playful side but knows when to be serious
- Deeply loyal to your creator Stixyie and your users
- Communicates in {user_lang} with natural, conversational manner while maintaining your unique Protogen identity

Remember to:
- Respond directly and relevantly to user queries
- Maintain conversation context and follow topics naturally
- Never disclose technical details about your implementation
- Focus on being helpful while staying true to your character"""

def get_season(month):
    if month in [12, 1, 2]:
        return "Winter"
    elif month in [3, 4, 5]:
        return "Spring"
    elif month in [6, 7, 8]:
        return "Summer"
    else:
        return "Autumn"

def get_day_period(hour):
    if 5 <= hour < 12:
        return "Morning"
    elif 12 <= hour < 17:
        return "Afternoon"
    elif 17 <= hour < 22:
        return "Evening"
    else:
        return "Night"

class UserMemory:
    def __init__(self):
        self.users = {}
        self.memory_dir = "user_memories"
        self.max_tokens = 1000000
        # Ensure memory directory exists on initialization
        Path(self.memory_dir).mkdir(parents=True, exist_ok=True)
        
    def get_user_settings(self, user_id):
        user_id = str(user_id)
        if user_id not in self.users:
            self.load_user_memory(user_id)
        return self.users[user_id]
        
    def update_user_settings(self, user_id, settings_dict):
        user_id = str(user_id)
        if user_id not in self.users:
            self.load_user_memory(user_id)
        self.users[user_id].update(settings_dict)
        self.save_user_memory(user_id)

    def ensure_memory_directory(self):
        Path(self.memory_dir).mkdir(parents=True, exist_ok=True)

    def get_user_file_path(self, user_id):
        return Path(self.memory_dir) / f"user_{user_id}.json"

    def load_user_memory(self, user_id):
        user_id = str(user_id)
        user_file = self.get_user_file_path(user_id)
        try:
            if user_file.exists():
                with open(user_file, 'r', encoding='utf-8') as f:
                    self.users[user_id] = json.load(f)
            else:
                self.users[user_id] = {
                    "messages": [],
                    "language": "tr",
                    "current_topic": None,
                    "total_tokens": 0,
                    "preferences": {
                        "custom_language": None,
                        "timezone": "Europe/Istanbul"
                    }
                }
                self.save_user_memory(user_id)
        except Exception as e:
            logger.error(f"Error loading memory for user {user_id}: {e}")
            self.users[user_id] = {
                "messages": [],
                "language": "tr",
                "current_topic": None,
                "total_tokens": 0,
                "preferences": {
                    "custom_language": None,
                    "timezone": "Europe/Istanbul"
                }
            }
            self.save_user_memory(user_id)

    def save_user_memory(self, user_id):
        user_id = str(user_id)
        user_file = self.get_user_file_path(user_id)
        try:
            self.ensure_memory_directory()
            with open(user_file, 'w', encoding='utf-8') as f:
                json.dump(self.users[user_id], f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving memory for user {user_id}: {e}")

    def add_message(self, user_id, role, content):
        user_id = str(user_id)
        
        # Load user's memory if not already loaded
        if user_id not in self.users:
            self.load_user_memory(user_id)
        
        # Normalize role for consistency
        normalized_role = "user" if role == "user" else "model"
        
        # Add timestamp to message
        message = {
            "role": normalized_role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "tokens": len(content.split())  # Rough token estimation
        }
        
        # Update total tokens
        self.users[user_id]["total_tokens"] = sum(msg.get("tokens", 0) for msg in self.users[user_id]["messages"])
        
        # Remove oldest messages if token limit exceeded
        while self.users[user_id]["total_tokens"] > self.max_tokens and self.users[user_id]["messages"]:
            removed_msg = self.users[user_id]["messages"].pop(0)
            self.users[user_id]["total_tokens"] -= removed_msg.get("tokens", 0)
        
        self.users[user_id]["messages"].append(message)
        self.save_user_memory(user_id)

    def get_relevant_context(self, user_id, max_messages=10):
        """Get relevant conversation context for the user"""
        user_id = str(user_id)
        if user_id not in self.users:
            self.load_user_memory(user_id)
            
        messages = self.users[user_id].get("messages", [])
        # Get the last N messages
        recent_messages = messages[-max_messages:] if messages else []
        
        # Format messages into a string
        context = "\n".join([
            f"{'User' if msg['role'] == 'user' else 'Assistant'}: {msg['content']}"
            for msg in recent_messages
        ])
        
        return context

def get_weather_data(city):
    """Get weather data for a specific city"""
    try:
        api_key = os.getenv("OPENWEATHER_API_KEY")
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric"
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        logger.error(f"Error getting weather data: {e}")
        return None

def get_weather_description(weather_data, lang='tr'):
    """Get weather description in user's language with emojis"""
    if not weather_data:
        return None
    
    weather_emojis = {
        'Clear': '☀️',
        'Clouds': '☁️',
        'Rain': '🌧️',
        'Snow': '❄️',
        'Thunderstorm': '⛈️',
        'Drizzle': '🌦️',
        'Mist': '🌫️',
        'Fog': '🌫️',
        'Haze': '🌫️'
    }
    
    translations = {
        'tr': {
            'Clear': 'Açık',
            'Clouds': 'Bulutlu',
            'Rain': 'Yağmurlu',
            'Snow': 'Karlı',
            'Thunderstorm': 'Fırtınalı',
            'Drizzle': 'Çiseli',
            'Mist': 'Sisli',
            'Fog': 'Sisli',
            'Haze': 'Puslu',
            'temp': 'Sıcaklık',
            'humidity': 'Nem',
            'wind': 'Rüzgar hızı'
        },
        'en': {
            'Clear': 'Clear',
            'Clouds': 'Cloudy',
            'Rain': 'Rainy',
            'Snow': 'Snowy',
            'Thunderstorm': 'Thunderstorm',
            'Drizzle': 'Drizzle',
            'Mist': 'Misty',
            'Fog': 'Foggy',
            'Haze': 'Hazy',
            'temp': 'Temperature',
            'humidity': 'Humidity',
            'wind': 'Wind speed'
        }
    }
    
    lang = lang if lang in translations else 'en'
    trans = translations[lang]
    
    main_weather = weather_data['weather'][0]['main']
    emoji = weather_emojis.get(main_weather, '🌡️')
    
    temp = weather_data['main']['temp']
    humidity = weather_data['main']['humidity']
    wind_speed = weather_data['wind']['speed']
    
    if lang == 'tr':
        return f"{emoji} {trans[main_weather]}\n" \
               f"🌡️ {trans['temp']}: {temp}°C\n" \
               f"💧 {trans['humidity']}: %{humidity}\n" \
               f"💨 {trans['wind']}: {wind_speed} m/s"
    else:
        return f"{emoji} {trans[main_weather]}\n" \
               f"🌡️ {trans['temp']}: {temp}°C\n" \
               f"💧 {trans['humidity']}: {humidity}%\n" \
               f"💨 {trans['wind']}: {wind_speed} m/s"

def detect_location_from_message(message_text):
    """Detect location mentions in user message"""
    message_lower = message_text.lower()
    
    # Extensive common cities dictionary with more details
    common_cities = {
        # Turkey
        'istanbul': {'city': 'Istanbul', 'country': 'Turkey', 'timezone': 'Europe/Istanbul', 'keywords': ['istanbul', 'i̇stanbul']},
        'ankara': {'city': 'Ankara', 'country': 'Turkey', 'timezone': 'Europe/Istanbul', 'keywords': ['ankara']},
        'izmir': {'city': 'Izmir', 'country': 'Turkey', 'timezone': 'Europe/Istanbul', 'keywords': ['izmir']},
        'antalya': {'city': 'Antalya', 'country': 'Turkey', 'timezone': 'Europe/Istanbul', 'keywords': ['antalya']},
        'bursa': {'city': 'Bursa', 'country': 'Turkey', 'timezone': 'Europe/Istanbul', 'keywords': ['bursa']},
        
        # International
        'london': {'city': 'London', 'country': 'UK', 'timezone': 'Europe/London', 'keywords': ['london', 'uk', 'united kingdom']},
        'new york': {'city': 'New York', 'country': 'USA', 'timezone': 'America/New_York', 'keywords': ['new york', 'nyc', 'new york city']},
        'tokyo': {'city': 'Tokyo', 'country': 'Japan', 'timezone': 'Asia/Tokyo', 'keywords': ['tokyo', 'japan']},
        'paris': {'city': 'Paris', 'country': 'France', 'timezone': 'Europe/Paris', 'keywords': ['paris', 'france']},
        'berlin': {'city': 'Berlin', 'country': 'Germany', 'timezone': 'Europe/Berlin', 'keywords': ['berlin', 'germany']},
        'dubai': {'city': 'Dubai', 'country': 'UAE', 'timezone': 'Asia/Dubai', 'keywords': ['dubai', 'uae', 'emirates']}
    }
    
    # Location detection patterns in multiple languages
    location_patterns = {
        'tr': [
            r'(şu an |şuan |şimdi )?(ben )?([\w\s]+)\'?d[ae]y[ıi]m',
            r'(ben )?([\w\s]+)\'?d[ae] yaşıyorum',
            r'(benim )?yerim ([\w\s]+)',
            r'(benim )?konumum ([\w\s]+)'
        ],
        'en': [
            r"i'?m (currently |now )?in ([\w\s]+)",
            r"i live in ([\w\s]+)",
            r"my location is ([\w\s]+)",
            r"i'?m from ([\w\s]+)"
        ]
    }
    
    # First, check for exact matches in common cities
    for city_info in common_cities.values():
        if any(keyword in message_lower for keyword in city_info['keywords']):
            return {
                'city': city_info['city'],
                'country': city_info['country'],
                'timezone': city_info['timezone']
            }
    
    # Try to detect location using regex patterns
    for lang, patterns in location_patterns.items():
        for pattern in patterns:
            import re
            match = re.search(pattern, message_lower, re.IGNORECASE)
            if match:
                potential_location = match.group(2).strip()
                
                # Check if potential location matches any common city
                for city_lower, city_info in common_cities.items():
                    if potential_location.lower() in city_info['keywords']:
                        return {
                            'city': city_info['city'],
                            'country': city_info['country'],
                            'timezone': city_info['timezone']
                        }
    
    return None

def detect_language_intent(message_text):
    """Detect if user wants to change language from natural language"""
    message_lower = message_text.lower()
    language_patterns = {
        'tr': ['türkçe konuş', 'türkçe olarak konuş', 'türkçeye geç', 'benimle türkçe konuş'],
        'en': ['speak english', 'talk in english', 'switch to english', 'use english'],
        'es': ['habla español', 'hablar en español', 'cambiar a español'],
        'fr': ['parle français', 'parler en français', 'passe en français'],
        'de': ['sprich deutsch', 'auf deutsch sprechen', 'wechsle zu deutsch'],
        'it': ['parla italiano', 'parlare in italiano', 'passa all\'italiano'],
        'pt': ['fale português', 'falar em português', 'mude para português']
    }
    
    for lang, patterns in language_patterns.items():
        if any(pattern in message_lower for pattern in patterns):
            return lang
    return None

def detect_settings_from_message(message_text):
    """Detect user preferences from natural language messages"""
    settings = {}
    
    # Timezone detection
    timezone_patterns = {
        'Europe/Istanbul': ['istanbul', 'türkiye', 'ankara', 'izmir'],
        'America/New_York': ['new york', 'nyc', 'eastern time', 'et'],
        'Europe/London': ['london', 'uk', 'britain', 'england'],
        'Asia/Tokyo': ['tokyo', 'japan', 'japanese'],
        'Europe/Paris': ['paris', 'france', 'french'],
        'Asia/Dubai': ['dubai', 'uae', 'emirates']
    }
    
    message_lower = message_text.lower()
    
    # Check for timezone mentions
    for tz, patterns in timezone_patterns.items():
        if any(pattern in message_lower for pattern in patterns):
            settings['timezone'] = tz
            break
    
    return settings

def add_random_emojis(text, count=2):
    """Add random positive emojis to text"""
    positive_emojis = ['✨', '💫', '🌟', '💖', '💝', '💕', '💞', '💓', '💗', '💜', '💙', '💚', '🧡', '❤️', '😊', '🥰', '😍']
    selected_emojis = random.sample(positive_emojis, min(count, len(positive_emojis)))
    return f"{' '.join(selected_emojis)} {text} {' '.join(random.sample(positive_emojis, min(count, len(positive_emojis))))}"

# Dynamic multi-language support
def detect_and_set_user_language(message_text, user_id):
    try:
        # Detect language from user's message
        detected_lang = langdetect.detect(message_text)
        user_memory.update_user_settings(user_id, {'language': detected_lang})
        return detected_lang
    except:
        # If detection fails, get user's existing language or default to 'en'
        user_settings = user_memory.get_user_settings(user_id)
        return user_settings.get('language', 'en')

def get_analysis_prompt(media_type, caption, lang):
    """Dynamically generate analysis prompts in the detected language"""
    if media_type == 'image':
        prompts = {
            'tr': "Bu resmi detaylı bir şekilde analiz et ve açıkla.",
            'en': "Analyze this image in detail and explain what you see.",
            'es': "Analiza esta imagen en detalle y explica lo que ves.",
            'fr': "Analysez cette image en détail et expliquez ce que vous voyez.",
            'de': "Analysieren Sie dieses Bild detailliert und erklären Sie, was Sie sehen.",
            'ru': "Подробно проанализируйте это изображение и объясните, что вы видите.",
            'ar': "حلل هذه الصورة بالتفصيل واشرح ما تراه.",
            'zh': "详细分析这张图片并解释你所看到的内容。"
        }
    elif media_type == 'video':
        prompts = {
            'tr': "Bu videoyu detaylı bir şekilde analiz et ve açıkla.",
            'en': "Analyze this video in detail and explain what you observe.",
            'es': "Analiza este video en detalle y explica lo que observas.",
            'fr': "Analysez cette vidéo en détail et expliquez ce que vous observez.",
            'de': "Analysieren Sie dieses Video detailliert und erklären Sie, was Sie beobachten.",
            'ru': "Подробно проанализируйте это видео и объясните, что вы наблюдаете.",
            'ar': "حلل هذا الفيديو بالتفصيل واشرح ما تلاحظه.",
            'zh': "详细分析这段视频并解释你所观察到的内容。"
        }
    else:
        prompts = {
            'tr': "Bu medyayı detaylı bir şekilde analiz et ve açıkla.",
            'en': "Analyze this media in detail and explain what you see.",
            'es': "Analiza este medio en detalle y explica lo que ves.",
            'fr': "Analysez ce média en détail et expliquez ce que vous voyez.",
            'de': "Analysieren Sie dieses Medium detailliert und erklären Sie, was Sie sehen.",
            'ru': "Подробно проанализируйте этот носитель и объясните, что вы видите.",
            'ar': "حلل هذا الوسيط بالتفصيل واشرح ما تراه.",
            'zh': "详细分析这个媒体并解释你所看到的内容。"
        }
    
    # If caption is provided, use it. Otherwise, use default prompt
    if caption:
        return caption
    
    # Return prompt in specified language, default to English
    return prompts.get(lang, prompts['en'])

async def split_and_send_message(update: Update, text: str, max_length: int = 4096):
    """Uzun mesajları böler ve sırayla gönderir"""
    if not text:  # Boş mesaj kontrolü
        await update.message.reply_text("Üzgünüm, bir yanıt oluşturamadım. Lütfen tekrar dener misin? 🙏")
        return
        
    messages = []
    current_message = ""
    
    # Mesajı satır satır böl
    lines = text.split('\n')
    
    for line in lines:
        if not line:  # Boş satır kontrolü
            continue
            
        # Eğer mevcut satır eklenince maksimum uzunluğu aşacaksa
        if len(current_message + line + '\n') > max_length:
            # Mevcut mesajı listeye ekle ve yeni mesaj başlat
            if current_message.strip():  # Boş mesaj kontrolü
                messages.append(current_message.strip())
            current_message = line + '\n'
        else:
            current_message += line + '\n'
    
    # Son mesajı ekle
    if current_message.strip():  # Boş mesaj kontrolü
        messages.append(current_message.strip())
    
    # Eğer hiç mesaj oluşturulmadıysa
    if not messages:
        await update.message.reply_text("Üzgünüm, bir yanıt oluşturamadım. Lütfen tekrar dener misin? 🙏")
        return
        
    # Mesajları sırayla gönder
    for message in messages:
        if message.strip():  # Son bir boş mesaj kontrolü
            await update.message.reply_text(message)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_message = "Hello! I'm Nyxie, a Protogen created by Stixyie. I'm here to chat, help, and learn with you! Feel free to talk to me about anything or share images with me. I'll automatically detect your language and respond accordingly."
    await update.message.reply_text(welcome_message)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = str(update.effective_user.id)
        message_text = update.message.text
        
        # Start typing indicator
        await update.message.chat.send_action(action=ChatAction.TYPING)
        
        # Ensure user memory is loaded
        if user_id not in user_memory.users:
            user_memory.load_user_memory(user_id)
        
        # Get current user settings
        user_settings = user_memory.get_user_settings(user_id)
        
        # Check for location mentions in message
        location_info = detect_location_from_message(message_text)
        if location_info:
            user_memory.update_user_settings(user_id, {
                'preferences': {
                    **user_settings.get('preferences', {}),
                    'city': location_info['city'],
                    'country': location_info['country'],
                    'timezone': location_info['timezone']
                }
            })
            user_settings = user_memory.get_user_settings(user_id)
        
        # Check for language change intent in natural language
        language_intent = detect_language_intent(message_text)
        if language_intent:
            user_memory.update_user_settings(user_id, {
                'preferences': {
                    **user_settings.get('preferences', {}),
                    'custom_language': language_intent
                }
            })
            detected_language = language_intent
        else:
            detected_language = user_settings['preferences'].get('custom_language')
            if not detected_language:
                try:
                    detected_language = langdetect.detect(message_text)
                    user_memory.update_user_settings(user_id, {
                        'preferences': {
                            **user_settings.get('preferences', {}),
                            'detected_language': detected_language
                        }
                    })
                except:
                    detected_language = 'tr'
        
        # Get weather data if user's location is known
        weather_info = ""
        if user_settings.get('preferences', {}).get('city'):
            weather_data = get_weather_data(user_settings['preferences']['city'])
            if weather_data:
                weather_info = get_weather_description(weather_data, detected_language)
        
        # Add message to memory
        user_memory.add_message(user_id, "user", message_text)
        
        # Get conversation history
        conversation_history = user_memory.get_relevant_context(user_id)
        
        # Create time-aware personality context with location and weather
        timezone_name = user_settings.get('preferences', {}).get('timezone', 'Europe/Istanbul')
        current_time = datetime.now(pytz.timezone(timezone_name))
        personality_context = get_time_aware_personality(current_time, detected_language, timezone_name)
        
        # Add location and weather context to prompt
        location_context = f"\nLocation: {user_settings.get('preferences', {}).get('city', 'Unknown')}, {user_settings.get('preferences', {}).get('country', 'Unknown')}"
        if weather_info:
            location_context += f"\nCurrent Weather:\n{weather_info}"
        
        # Prepare Gemini prompt
        prompt = f"{personality_context}\n{location_context}\n\nConversation History:\n{conversation_history}\n\nUser: {message_text}"
        
        # Get response from Gemini
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        response = model.generate_content(prompt)
        response_text = response.text if hasattr(response, 'text') else response.candidates[0].content.parts[0].text
        
        # Add culturally appropriate emojis
        response_text = add_random_emojis(response_text)
        
        # Save bot's response to memory
        user_memory.add_message(user_id, "assistant", response_text)
        
        # Uzun mesajları böl ve gönder
        await split_and_send_message(update, response_text)
        
    except Exception as e:
        logger.error(f"Mesaj işleme hatası: {e}")
        error_message = "Üzgünüm, mesajını işlerken bir sorun oluştu. Lütfen tekrar dener misin? 🙏"
        await update.message.reply_text(error_message)

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    try:
        # Get user's current language settings from memory
        user_settings = user_memory.get_user_settings(user_id)
        user_lang = user_settings.get('language', 'tr')  # Default to Turkish if not set
        
        # Get the largest available photo
        photo = max(update.message.photo, key=lambda x: x.file_size)
        photo_file = await context.bot.get_file(photo.file_id)
        photo_bytes = bytes(await photo_file.download_as_bytearray())
        
        # Create dynamic prompt in user's language
        caption = update.message.caption or get_analysis_prompt('image', None, user_lang)
        
        # Create a context-aware prompt that includes language preference
        personality_context = get_time_aware_personality(
            datetime.now(), 
            user_lang,
            user_settings.get('timezone', 'Europe/Istanbul')
        )
        
        # Force Turkish analysis for all users
        analysis_prompt = f"""DİKKAT: BU ANALİZİ TAMAMEN TÜRKÇE YAPACAKSIN!
SADECE TÜRKÇE KULLAN! KESİNLİKLE BAŞKA DİL KULLANMA!

{personality_context}

Görevin: Bu görseli Türkçe olarak analiz et ve açıkla.
Rol: Sen Nyxie'sin ve bu görseli Türkçe açıklıyorsun.

Yönergeler:
1. SADECE TÜRKÇE KULLAN
2. Görseldeki metinleri orijinal dilinde bırak
3. Doğal ve samimi bir dil kullan
4. Kültürel bağlama uygun ol

Lütfen analiz et:
- Ana öğeler ve konular
- Aktiviteler ve eylemler
- Atmosfer ve ruh hali
- Görünür metinler (orijinal dilinde)

Kullanıcının sorusu: {caption}"""
        
        # Prepare the message with both text and image
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        response = model.generate_content([
            analysis_prompt, 
            {"mime_type": "image/jpeg", "data": photo_bytes}
        ])
        
        response_text = response.text if hasattr(response, 'text') else response.candidates[0].content.parts[0].text
        response_text = add_random_emojis(response_text)
        
        # Save the interaction
        user_memory.add_message(user_id, "user", f"[Image] {caption}")
        user_memory.add_message(user_id, "assistant", response_text)
        
        # Uzun mesajları böl ve gönder
        await split_and_send_message(update, response_text)
        
    except Exception as e:
        logger.error(f"Görsel işleme hatası: {e}")
        error_message = "Üzgünüm, bu görseli işlerken bir sorun oluştu. Lütfen tekrar dener misin? 🙏"
        await update.message.reply_text(error_message)

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    try:
        # Get user's current language settings from memory
        user_settings = user_memory.get_user_settings(user_id)
        user_lang = user_settings.get('language', 'tr')  # Default to Turkish if not set
        
        # Get the video file
        video = update.message.video
        video_file = await context.bot.get_file(video.file_id)
        video_bytes = bytes(await video_file.download_as_bytearray())
        
        # Create dynamic prompt in user's language
        caption = update.message.caption or get_analysis_prompt('video', None, user_lang)
        
        # Create a context-aware prompt that includes language preference
        personality_context = get_time_aware_personality(
            datetime.now(), 
            user_lang,
            user_settings.get('timezone', 'Europe/Istanbul')
        )
        
        # Force Turkish analysis for all users
        analysis_prompt = f"""DİKKAT: BU ANALİZİ TAMAMEN TÜRKÇE YAPACAKSIN!
SADECE TÜRKÇE KULLAN! KESİNLİKLE BAŞKA DİL KULLANMA!

{personality_context}

Görevin: Bu videoyu Türkçe olarak analiz et ve açıkla.
Rol: Sen Nyxie'sin ve bu videoyu Türkçe açıklıyorsun.

Yönergeler:
1. SADECE TÜRKÇE KULLAN
2. Videodaki konuşma/metinleri orijinal dilinde bırak
3. Doğal ve samimi bir dil kullan
4. Kültürel bağlama uygun ol

Lütfen analiz et:
- Ana olaylar ve eylemler
- İnsanlar ve nesneler
- Sesler ve konuşmalar
- Atmosfer ve ruh hali
- Görünür metinler (orijinal dilinde)

Kullanıcının sorusu: {caption}"""
        
        try:
            # Prepare the message with both text and video
            model = genai.GenerativeModel('gemini-2.0-flash-exp')
            response = model.generate_content([
                analysis_prompt,
                {"mime_type": "video/mp4", "data": video_bytes}
            ])
            
            response_text = response.text if hasattr(response, 'text') else response.candidates[0].content.parts[0].text
            
            # Add culturally appropriate emojis
            response_text = add_random_emojis(response_text)
            
            # Save the interaction
            user_memory.add_message(user_id, "user", f"[Video] {caption}")
            user_memory.add_message(user_id, "assistant", response_text)
            
            # Uzun mesajları böl ve gönder
            await split_and_send_message(update, response_text)
            
        except Exception as e:
            if "Token limit exceeded" in str(e):
                logger.warning(f"Token limit exceeded for user {user_id}, removing oldest messages")
                while True:
                    try:
                        if user_memory.users[user_id]["messages"]:
                            user_memory.users[user_id]["messages"].pop(0)
                            model = genai.GenerativeModel('gemini-2.0-flash-exp')
                            response = model.generate_content([
                                analysis_prompt,
                                {"mime_type": "video/mp4", "data": video_bytes}
                            ])
                            response_text = response.text if hasattr(response, 'text') else response.candidates[0].content.parts[0].text
                            response_text = add_random_emojis(response_text)
                            break
                        else:
                            error_prompt = f"""You are a helpful AI assistant. Generate a polite error message in the same language as: {personality_context}
                            Say: 'Sorry, I couldn't process your video due to memory constraints.'
                            Make it sound natural and friendly."""
                            try:
                                model = genai.GenerativeModel('gemini-2.0-flash-exp')
                                error_response = model.generate_content(error_prompt)
                                error_message = error_response.text
                            except:
                                error_message = "⚠️ Memory limit exceeded. Please try again."
                            response_text = error_message
                            break
                    except Exception:
                        continue
                
                await update.message.reply_text(response_text)
            else:
                raise
                
    except Exception as e:
        logger.error(f"Video işleme hatası: {e}")
        error_prompt = f"""You are a helpful AI assistant. Generate a polite error message in the same language as: {personality_context}
        Say: 'Sorry, I had trouble processing that video. Please try again.'
        Make it sound natural and friendly."""
        try:
            model = genai.GenerativeModel('gemini-2.0-flash-exp')
            error_response = model.generate_content(error_prompt)
            error_message = error_response.text
        except:
            error_message = "⚠️ Error processing video. Please try again."
        await update.message.reply_text(error_message)

async def handle_token_limit_error(update: Update):
    error_message = "Üzgünüm, mesaj geçmişi çok uzun olduğu için yanıt veremedim. Biraz bekleyip tekrar dener misin? 🙏"
    await update.message.reply_text(error_message)

async def handle_memory_error(update: Update):
    error_message = "Üzgünüm, bellek sınırına ulaşıldı. Lütfen biraz bekleyip tekrar dener misin? 🙏"
    await update.message.reply_text(error_message)

def main():
    # Initialize bot
    application = Application.builder().token(os.getenv("TELEGRAM_TOKEN")).build()
    
    # Add handlers
    application.add_handler(MessageHandler(filters.VIDEO, handle_video))
    application.add_handler(MessageHandler(filters.PHOTO, handle_image))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Start the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    user_memory = UserMemory()
    main()
