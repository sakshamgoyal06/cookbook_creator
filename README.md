# Mom's Cookbook Studio

Turn family recipe voice notes into a professional cookbook.

## Features

- Upload audio voice notes (.mp3, .m4a, .wav, .ogg, .opus)
- AI-powered transcription via OpenAI
- Automatic recipe structuring into cookbook format
- Review, edit, and approve recipes
- Generate beautifully designed PDF cookbook pages
- Recipe dashboard with status tracking

## Setup

### 1. System Dependencies

WeasyPrint requires native libraries:

```bash
# Ubuntu / Debian
sudo apt-get install -y libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libffi-dev libcairo2 ffmpeg
```

### 2. Python Dependencies

```bash
pip install -r requirements.txt
```

### 3. Environment Variables

Copy `.env.example` to `.env` and fill in your OpenAI API key:

```bash
cp .env.example .env
# Edit .env and set OPENAI_API_KEY
```

### 4. Run the App

```bash
python app.py
```

The app starts at **http://localhost:5000**.

## Usage

1. **Upload** a recipe voice note from the home page
2. The system transcribes the audio and structures it into a cookbook recipe
3. **Review** the recipe — unclear items are highlighted for your attention
4. **Edit** any fields that need adjustment
5. **Approve** the recipe when it looks good
6. **Generate PDF** to create a beautiful cookbook page

## Tech Stack

- **Backend:** Python + Flask
- **Database:** SQLite
- **AI:** OpenAI API (transcription + recipe formatting)
- **PDF:** WeasyPrint (HTML/CSS to PDF)
- **Config:** python-dotenv

## Future Plans

- WhatsApp / Twilio integration for voice note submission
- Multi-cookbook compilation
- Food photo integration
- User authentication
