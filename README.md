# Mom's Cookbook Studio

Turn family recipe voice notes into a professional cookbook.

## Features

- Upload audio voice notes (.mp3, .m4a, .mp4, .wav, .ogg)
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
sudo apt-get install -y libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libffi-dev libcairo2
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
python3 app.py
```

The app starts on **http://localhost:5000**.

When it starts, the terminal also prints a **phone URL** like `http://192.168.x.x:5000`. Use that on your phone if both devices are on the same Wi-Fi.

## Use from your phone

You do **not** run this app on the phone itself. Run it on your Mac or laptop, then open it in your phone's browser.

### One-time setup on your computer

1. Pull the latest code:
   ```bash
   git pull origin main
   ```
2. Install dependencies if you have not already:
   ```bash
   pip install -r requirements.txt
   ```
3. Create or update `.env`:
   ```bash
   cp .env.example .env
   ```
   Set at least:
   - `OPENAI_API_KEY`
   - `ANTHROPIC_API_KEY`
   - `ANTHROPIC_RECIPE_MODEL=claude-sonnet-4-5-20250929`
4. Start the app:
   ```bash
   python3 app.py
   ```

### On your phone

1. Connect your phone to the **same Wi-Fi** as your computer.
2. Look at the terminal where the app is running and copy the line that says:
   `On your phone (same Wi-Fi): http://192.168.x.x:5000`
3. Open that URL in **Safari** (iPhone) or **Chrome** (Android).
4. Register or log in.
5. Create a project, then upload a voice memo:
   - iPhone: choose **Browse** or **Voice Memos** when selecting a file
   - Android: choose your voice recorder or Files app

### Important notes

- Keep your computer awake and leave `python3 app.py` running while you use the app from your phone.
- If the phone cannot connect, check that both devices are on the same Wi-Fi and that your firewall allows incoming connections on port `5000`.
- After `git pull`, restart the app so your phone gets the latest fixes.

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
