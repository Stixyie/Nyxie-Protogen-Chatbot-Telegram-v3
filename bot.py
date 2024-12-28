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
    # Comprehensive logging for debugging
    logger.info("Entering handle_message function")
    
    try:
        # Validate update object
        if not update:
            logger.error("Update object is None")
            return
        
        # Validate message
        if not update.message:
            logger.error("Message is None in update object")
            return
        
        # Log message details for debugging
        logger.info(f"Message received: {update.message}")
        logger.info(f"Message text: {update.message.text}")
        logger.info(f"Message type: {type(update.message)}")
        
        user_id = str(update.effective_user.id)
        logger.info(f"User ID: {user_id}")
        
        # Get user's current language settings from memory
        user_settings = user_memory.get_user_settings(user_id)
        user_lang = user_settings.get('language', 'tr')  # Default to Turkish if not set
        logger.info(f"User language: {user_lang}")
        
        # Check for media types
        if update.message.photo:
            logger.info("Photo detected, calling handle_image")
            await handle_image(update, context)
            return
        
        if update.message.video:
            logger.info("Video detected, calling handle_video")
            await handle_video(update, context)
            return
        
        # Process text messages
        if update.message.text:
            # Normalize and strip the message text
            message_text = update.message.text.strip()
            logger.info(f"Processed message text: {message_text}")
            
            # Language detection and settings
            detected_lang = detect_language_intent(message_text)
            if detected_lang:
                user_memory.update_user_settings(user_id, {'language': detected_lang})
                logger.info(f"Language updated to: {detected_lang}")
            
            # Check for settings changes
            settings_change = detect_settings_from_message(message_text)
            if settings_change:
                user_memory.update_user_settings(user_id, settings_change)
                logger.info(f"User settings updated: {settings_change}")
            
            # Detect location mentions
            location = None  # Removed detect_location_from_message function call
            if location:
                logger.info(f"Location detected: {location}")
                # Removed get_weather_data and get_weather_description function calls
                # await update.message.reply_text(weather_description)
                return
            
            # Prepare context for AI response
            try:
                # Retrieve relevant conversation context
                context_messages = user_memory.get_relevant_context(user_id)
                
                # Prepare personality context
                personality_context = get_time_aware_personality(
                    datetime.now(), 
                    user_lang,
                    user_settings.get('timezone', 'Europe/Istanbul')
                )
                
                # Construct AI prompt
                ai_prompt = f"""DİKKAT: BU YANITI TAMAMEN TÜRKÇE VERECEKSIN!
SADECE TÜRKÇE KULLAN! KESİNLİKLE BAŞKA DİL KULLANMA!

{personality_context}

Görevin: Kullanıcının mesajını Türkçe olarak zeki ve samimi bir şekilde yanıtla.
Rol: Sen Nyxie'sin ve kullanıcıyla Türkçe sohbet ediyorsun.

Yönergeler:
1. SADECE TÜRKÇE KULLAN
2. Doğal ve samimi bir dil kullan
3. Kültürel bağlama uygun ol
4. Kısa ve öz cevaplar ver

Kullanıcının mesajı: {message_text}"""
                
                # Generate AI response
                model = genai.GenerativeModel('gemini-2.0-flash-exp')
                response = model.generate_content(ai_prompt)
                
                # Extract response text
                response_text = response.text if hasattr(response, 'text') else response.candidates[0].content.parts[0].text
                
                # Add emojis
                response_text = add_random_emojis(response_text)
                
                # Save interaction to memory
                user_memory.add_message(user_id, "user", message_text)
                user_memory.add_message(user_id, "assistant", response_text)
                
                # Send response
                await split_and_send_message(update, response_text)
            
            except Exception as ai_error:
                logger.error(f"AI response generation error: {ai_error}", exc_info=True)
                error_message = "Üzgünüm, yanıt oluştururken bir sorun yaşadım. Lütfen tekrar deneyin. 🙏"
                await update.message.reply_text(error_message)
        
        else:
            logger.warning("Unhandled message type received")
            await update.message.reply_text("Bu mesaj türünü şu anda işleyemiyorum. 🤔")
    
    except Exception as e:
        logger.error(f"Mesaj işleme hatası: {e}", exc_info=True)
        error_message = "Üzgünüm, mesajını işlerken bir sorun oluştu. Lütfen tekrar dener misin? 🙏"
        await update.message.reply_text(error_message)

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    try:
        # Enhanced logging for debugging
        logger.info(f"Starting image processing for user {user_id}")
        
        # Validate message and photo
        if not update.message:
            logger.warning("No message found in update")
            await update.message.reply_text("⚠️ Görsel bulunamadı. Lütfen tekrar deneyin.")
            return
        
        # Get user's current language settings from memory
        user_settings = user_memory.get_user_settings(user_id)
        user_lang = user_settings.get('language', 'tr')  # Default to Turkish if not set
        logger.info(f"User language: {user_lang}")
        
        # Check if photo exists
        if not update.message.photo:
            logger.warning("No photo found in the message")
            await update.message.reply_text("⚠️ Görsel bulunamadı. Lütfen tekrar deneyin.")
            return
        
        # Get the largest available photo
        try:
            photo = max(update.message.photo, key=lambda x: x.file_size)
        except Exception as photo_error:
            logger.error(f"Error selecting photo: {photo_error}")
            await update.message.reply_text("⚠️ Görsel seçiminde hata oluştu. Lütfen tekrar deneyin.")
            return
        
        # Download photo
        try:
            photo_file = await context.bot.get_file(photo.file_id)
            photo_bytes = bytes(await photo_file.download_as_bytearray())
        except Exception as download_error:
            logger.error(f"Photo download error: {download_error}")
            await update.message.reply_text("⚠️ Görsel indirilemedi. Lütfen tekrar deneyin.")
            return
        
        logger.info(f"Photo bytes downloaded: {len(photo_bytes)} bytes")
        
        # Comprehensive caption handling with extensive logging
        caption = update.message.caption
        logger.info(f"Original caption: {caption}")
        
        default_prompt = get_analysis_prompt('image', None, user_lang)
        logger.info(f"Default prompt: {default_prompt}")
        
        # Ensure caption is not None
        if caption is None:
            caption = default_prompt or "Bu resmi detaylı bir şekilde analiz et ve açıkla."
        
        # Ensure caption is a string and stripped
        caption = str(caption).strip()
        logger.info(f"Final processed caption: {caption}")
        
        # Create a context-aware prompt that includes language preference
        personality_context = get_time_aware_personality(
            datetime.now(), 
            user_lang,
            user_settings.get('timezone', 'Europe/Istanbul')
        )
        
        if not personality_context:
            personality_context = "Sen Nyxie'sin ve resimleri analiz ediyorsun."  # Fallback personality
        
        # Force Turkish analysis for all users
        analysis_prompt = f"""DİKKAT: BU ANALİZİ TAMAMEN TÜRKÇE YAPACAKSIN!
SADECE TÜRKÇE KULLAN! KESİNLİKLE BAŞKA DİL KULLANMA!

{personality_context}

Görevin: Bu resmi Türkçe olarak analiz et ve açıkla.
Rol: Sen Nyxie'sin ve bu resmi Türkçe açıklıyorsun.

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
        
        try:
            # Prepare the message with both text and image
            model = genai.GenerativeModel('gemini-2.0-flash-exp')
            response = model.generate_content([
                analysis_prompt, 
                {"mime_type": "image/jpeg", "data": photo_bytes}
            ])
            
            response_text = response.text if hasattr(response, 'text') else response.candidates[0].content.parts[0].text
            
            # Add culturally appropriate emojis
            response_text = add_random_emojis(response_text)
            
            # Save the interaction
            user_memory.add_message(user_id, "user", f"[Image] {caption}")
            user_memory.add_message(user_id, "assistant", response_text)
            
            # Uzun mesajları böl ve gönder
            await split_and_send_message(update, response_text)
        
        except Exception as processing_error:
            logger.error(f"Görsel işleme hatası: {processing_error}", exc_info=True)
            error_message = "Üzgünüm, bu görseli işlerken bir sorun oluştu. Lütfen tekrar dener misin? 🙏"
            await update.message.reply_text(error_message)
    
    except Exception as critical_error:
        logger.error(f"Kritik görsel işleme hatası: {critical_error}", exc_info=True)
        await update.message.reply_text("Üzgünüm, görseli işlerken kritik bir hata oluştu. Lütfen tekrar deneyin.")

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    try:
        # Enhanced logging for debugging
        logger.info(f"Starting video processing for user {user_id}")
        
        # Validate message and video
        if not update.message:
            logger.warning("No message found in update")
            await update.message.reply_text("⚠️ Video bulunamadı. Lütfen tekrar deneyin.")
            return
        
        # Get user's current language settings from memory
        user_settings = user_memory.get_user_settings(user_id)
        user_lang = user_settings.get('language', 'tr')  # Default to Turkish if not set
        logger.info(f"User language: {user_lang}")
        
        # Check if video exists
        if not update.message.video:
            logger.warning("No video found in the message")
            await update.message.reply_text("⚠️ Video bulunamadı. Lütfen tekrar deneyin.")
            return
        
        # Get the video file
        video = update.message.video
        if not video:
            logger.warning("No video found in the message")
            await update.message.reply_text("⚠️ Video bulunamadı. Lütfen tekrar deneyin.")
            return
            
        video_file = await context.bot.get_file(video.file_id)
        video_bytes = bytes(await video_file.download_as_bytearray())
        logger.info(f"Video bytes downloaded: {len(video_bytes)} bytes")
        
        # Comprehensive caption handling with extensive logging
        caption = update.message.caption
        logger.info(f"Original caption: {caption}")
        
        default_prompt = get_analysis_prompt('video', None, user_lang)
        logger.info(f"Default prompt: {default_prompt}")
        
        # Ensure caption is not None
        if caption is None:
            caption = default_prompt or "Bu videoyu detaylı bir şekilde analiz et ve açıkla."
        
        # Ensure caption is a string and stripped
        caption = str(caption).strip()
        logger.info(f"Final processed caption: {caption}")
        
        # Create a context-aware prompt that includes language preference
        personality_context = get_time_aware_personality(
            datetime.now(), 
            user_lang,
            user_settings.get('timezone', 'Europe/Istanbul')
        )
        
        if not personality_context:
            personality_context = "Sen Nyxie'sin ve videoları analiz ediyorsun."  # Fallback personality
        
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
        
        except Exception as processing_error:
            logger.error(f"Video processing error: {processing_error}", exc_info=True)
            
            if "Token limit exceeded" in str(processing_error):
                logger.warning(f"Token limit exceeded for user {user_id}, removing oldest messages")
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
                        await update.message.reply_text(response_text)
                    else:
                        await update.message.reply_text("⚠️ Üzgünüm, videonuzu işlerken hafıza sınırına ulaştım. Lütfen tekrar deneyin.")
                except Exception as retry_error:
                    logger.error(f"Retry error: {retry_error}", exc_info=True)
                    await update.message.reply_text("⚠️ Üzgünüm, videonuzu işlerken bir hata oluştu. Lütfen tekrar deneyin.")
            else:
                # Generic error handling
                await update.message.reply_text("⚠️ Üzgünüm, videonuzu işlerken bir hata oluştu. Lütfen tekrar deneyin.")
    
    except Exception as e:
        logger.error(f"Kritik video işleme hatası: {e}", exc_info=True)
        await update.message.reply_text("⚠️ Üzgünüm, videonuzu işlerken kritik bir hata oluştu. Lütfen tekrar deneyin.")

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
