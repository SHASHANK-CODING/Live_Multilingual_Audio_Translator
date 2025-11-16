# 🎤 Speech-to-Text & Translation with Azure + Google Translate + gTTS

This project allows you to **upload an audio file**, convert it to text using **Azure Cognitive Services Speech-to-Text**, **translate** that text into any selected language using **Google Translate**, and finally **convert the translated text back into speech** using **Google Text-to-Speech (gTTS)** — all directly inside **Google Colab**.

---

## 🚀 Features

✅ Upload or record any audio file (MP3, WAV, M4A, etc.)  
✅ Automatic conversion to 16 kHz mono WAV (for better STT accuracy)  
✅ Speech-to-text processing via **Azure Cognitive Services**  
✅ Translation into 30+ languages using **Google Translate API**  
✅ Voice synthesis using **gTTS (Google Text-to-Speech)**  
✅ Interactive Colab UI with dropdown & button widgets  

---

## 🧠 Tech Stack

| Component | Technology Used |
|------------|------------------|
| Speech Recognition | Azure Cognitive Services Speech SDK |
| Translation | Google Translate (`googletrans` library) |
| Speech Synthesis | Google Text-to-Speech (`gTTS`) |
| Audio Conversion | Pydub + FFmpeg |
| Interface | Google Colab Widgets (`ipywidgets`) |

---

## ⚙️ Setup Instructions

### 1️⃣ Open Google Colab
Go to [Google Colab](https://colab.research.google.com) and create a new notebook.

### 2️⃣ Copy the Code
Paste the complete Colab code (from `speech_to_translate_colab.py` or your notebook) into **one cell**.

### 3️⃣ Install Dependencies
These packages are automatically installed by the script:
```bash
!apt-get -y install ffmpeg
!pip install azure-cognitiveservices-speech googletrans==4.0.0-rc1 gTTS pydub ipywidgets
```

### 4️⃣ Add Your Azure Speech Key
When prompted, enter your **Azure Cognitive Services Speech API key** and region.

> ⚠️ **Do not hardcode your key** — always input it interactively for safety.

### 5️⃣ Run the Notebook
- Upload your audio file when prompted.  
- Wait for Azure to recognize and print the text.  
- Select the target language from the dropdown.  
- Click **🔊 Translate & Speak** to listen to the translated audio.

---

## 🌐 Supported Languages

Supports over **30 languages**, including:

| Language | Code | Language | Code |
|-----------|------|-----------|------|
| English | en | Hindi | hi |
| French | fr | Spanish | es |
| Tamil | ta | Telugu | te |
| Malayalam | ml | Arabic | ar |
| Chinese (Simplified) | zh-cn | Japanese | ja |
| Korean | ko | German | de |
| Russian | ru | Bengali | bn |
| Punjabi | pa | Urdu | ur |
| Italian | it | Portuguese | pt |

…and many more!

---

## 📁 File Workflow

| Step | Input | Output |
|------|--------|--------|
| 1️⃣ Upload | `.mp3`, `.wav`, `.m4a`, etc. | Original audio |
| 2️⃣ Convert | Pydub + FFmpeg | 16 kHz mono `.wav` |
| 3️⃣ STT | Azure Speech SDK | Transcribed text |
| 4️⃣ Translate | Google Translate | Translated text |
| 5️⃣ TTS | Google gTTS | `translated_audio.mp3` |

---

## 🧩 Example Usage

```text
🎵 Upload your audio file...
✅ Audio converted to 16 kHz mono WAV
🗣️ Recognized Text: "Hello, how are you?"
✅ Translated Text (hi): "नमस्ते आप कैसे हैं"
🎧 Audio synthesis complete!
```

---

## 🛠️ Troubleshooting

| Issue | Cause | Fix |
|--------|--------|-----|
| `Speech recognition canceled: Connection failure` | Wrong Azure region or key | Verify your Azure key and region |
| `Translation failed` | Google quota or unstable internet | Retry or use smaller text |
| `gTTS synthesis failed` | Language code mismatch | Check supported TTS language codes |
| Widgets not visible | Colab widget manager disabled | Add `from google.colab import output; output.enable_custom_widget_manager()` |

---

## 🔒 Security Notes

- Never commit your **Azure key** to GitHub.  
- Use environment variables or input prompts.  
- Free-tier Azure usage includes limited STT minutes.

---

## 📜 License

This project is open-source under the **MIT License**.  
You are free to modify and distribute it with attribution.

---
