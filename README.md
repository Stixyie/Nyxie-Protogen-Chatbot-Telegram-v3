# 🤖 Nyxie: Protogen Telegram Chatbot 🌟

## 📖 İçindekiler
- [Giriş](#giriş)
- [Özellikler](#özellikler)
- [Gereksinimler](#gereksinimler)
- [Kurulum](#kurulum)
- [Kullanım](#kullanım)
- [Konfigürasyon](#konfigürasyon)
- [API Entegrasyonları](#api-entegrasyonları)
- [Güvenlik](#güvenlik)
- [Destek](#destek)
- [Lisans](#lisans)

## 🌈 Giriş

**Nyxie**, Stixyie tarafından geliştirilen gelişmiş bir Protogen AI Telegram chatbot'udur. Yapay zeka teknolojisini kullanarak kullanıcılarla etkileşime giren, zamansal ve bağlamsal olarak duyarlı bir asistantır türkçeye odaklı yapılmıştır ama diğer dillerde belli bir seviyede destek sağlar ama asıl amaçı türkçe konusmayı desteklemektir.

### 🤔 Nyxie Nedir?

Nyxie, sadece bir chatbot değil, aynı zamanda:
- 🧠 Gelişmiş yapay zeka teknolojisi ile çalışan bir dijital arkadaş
- 🌍 Çoklu dil desteği olan bir iletişim asistanı
- 🕰️ Zamansal ve mekânsal farkındalığa sahip bir AI

## 🚀 Özellikler

### 1. 💬 Gelişmiş Konuşma Yeteneği
- Dinamik ve bağlamsal yanıtlar
- Kullanıcı tercihlerini öğrenme ve hatırlama
- Çoklu dil desteği (Türkçe ve İngilizce ve diğer diller)
- Türkçe dil desteği sadece video ve resim analizlerinde 

### 2. 🌦️ Hava Durumu Bilgilendirmesi
- Gerçek zamanlı hava durumu sorgulaması
- Şehre özel detaylı hava durumu raporları
- Emoji ile zenginleştirilmiş hava durumu açıklamaları

### 3. 🕒 Zamansal Kişilik Uyarlaması
- Günün saatine göre dinamik kişilik ayarları
- Mevsim ve günün periyoduna göre yanıt uyarlama
- Kullanıcının yerel saat dilimini algılama

### 4. 🖼️ Görüntü ve Video İşleme
- Gönderilen görüntüleri ve videoları analiz etme
- Google Cloud Vision API ile görüntü tanıma
- Multimedya içeriği hakkında açıklama üretme

### 5. 🧠 Kullanıcı Hafızası
- Kullanıcı tercihlerini ve geçmiş etkileşimlerini kaydetme
- Maksimum 1 milyon token'a kadar konuşma geçmişi
- Güvenli ve şifrelenmiş kullanıcı verileri

## 🛠️ Gereksinimler

### Yazılım Gereksinimleri
- Python 3.8+
- pip paket yöneticisi

### Gerekli Kütüphaneler
- python-telegram-bot
- google-generativeai
- python-dotenv
- requests
- geopy
- timezonefinder
- emoji
- langdetect
- Pillow
- httpx
- google-cloud-vision

## 🔧 Kurulum

### 1. Depoyu Klonlama
```bash
git clone https://github.com/stixyie/Nyxie-Protogen-Chatbot-Telegram-v2-main.git
cd Nyxie-Protogen-Chatbot-Telegram-v2-main
```

### 2. Sanal Ortam Oluşturma
```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows
```

### 3. Bağımlılıkları Yükleme
```bash
pip install -r requirements.txt
```

## 🔐 Konfigürasyon

### Gerekli API Anahtarları
`.env` dosyasında aşağıdaki API anahtarlarını yapılandırın:
- `TELEGRAM_BOT_TOKEN`: Telegram Bot Token
- `GEMINI_API_KEY`: Google Gemini API Anahtarı
- `OPENWEATHER_API_KEY`: OpenWeatherMap API Anahtarı
- `GOOGLE_APPLICATION_CREDENTIALS`: Google Cloud Vision için kimlik bilgileri

### Örnek `.env` Dosyası
```
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
GEMINI_API_KEY=your_gemini_api_key
OPENWEATHER_API_KEY=your_openweather_api_key
GOOGLE_APPLICATION_CREDENTIALS=path/to/credentials.json
```

## 🚀 Kullanım

### Bot'u Başlatma
```bash
python bot.py
```

### Telegram'da Kullanım
1. Bot'a `/start` komutu ile başlayın
2. Mesaj, görüntü veya video gönderin
3. Hava durumu, çeviri veya sohbet için bot ile etkileşime geçin

## 🛡️ Güvenlik

- Kullanıcı verileri şifrelenmiş JSON dosyalarında saklanır
- Maksimum token sınırlaması ile bellek yönetimi
- Hassas bilgilerin loglanmaması

## 🤝 Destek

### Sorun Bildirim
- GitHub Issues: [Proje Sayfası](https://github.com/stixyie/Nyxie-Protogen-Chatbot-Telegram-v2-main/issues)

### Katkıda Bulunma
1. Projeyi forklayın
2. Yeni bir branch oluşturun
3. Değişikliklerinizi yapın
4. Pull Request açın

## 📄 Lisans

Bu proje GPL-3.0 Lisansı altında yayınlanmıştır. Detaylar için `LICENSE` dosyasına bakın.

## 🌟 Teşekkür

- **Stixyie**: Proje yaratıcısı ve baş geliştirici
- **Google**: Gemini ve Cloud Vision API'ları
- **Telegram**: Bot altyapısı

---

**Not**: Nyxie, sürekli gelişen bir AI projesidir. Geri bildirimleriniz ve katkılarınız çok değerlidir! 🚀