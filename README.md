# Papla Voice Generator

A web-based voice generation application using the Papla Media API to convert text to speech with AI voices.

## Features

### ✅ Multiple Script Support
- Start with 3 textareas for different voiceover scripts
- Add up to 10 scripts dynamically
- Individual character counters for each script
- Remove scripts as needed (minimum 1 required)

### ✅ API Connection Testing
- Test API key validity before generating voiceovers
- Display available voices when connection is successful
- Detailed error messages for connection issues

### ✅ Session-Based API Key Storage
- API keys are stored securely in sessions
- Keys persist across page refreshes during the session
- No need to re-enter API key repeatedly

### ✅ Individual and Batch Generation
- Generate voiceovers for individual scripts
- Generate all scripts at once with one click
- Each generated audio is displayed with its script preview

### ✅ Download Functionality
- Download individual audio files
- One-click download all audio files in sequence
- Files are named according to script number

### ✅ Download & Manage Outputs
- Download individual audio files per script
- One-click download all generated audio files in sequence

## Installation and Setup

1. **Clone or download the project**
   ```bash
   git clone <repository-url>
   cd Papla-Voice-Generator
   ```

2. **Install dependencies**
   ```bash
   pip3 install Flask Flask-Session requests
   ```

3. **Run the application**
   ```bash
   # Using the startup script
   ./run_app.sh
   
   # Or directly
   python3 papla_voice_web.py
   ```

4. **Access the application**
   Open your browser and navigate to: http://localhost:5003

## Usage

1. **Enter your Papla API key** in the Settings sidebar
2. **Test the connection** to verify API key and load available voices
3. **Select a voice** from the dropdown menu
4. **Enter your scripts** in the textareas provided
5. **Generate voiceovers** individually or all at once
6. **Download** individual files or combine them into one

## File Structure

```
Papla-Voice-Generator/
├── papla_voice_web.py      # Main Flask application
├── templates/
│   ├── index.html          # Main web interface
│   └── to-do.md           # Original task list
├── static/
│   └── styles.css          # Application styling
├── run_app.sh              # Startup script
├── audio_combiner.py       # Optional CLI helper for combining audio files
└── README.md               # This file
```

## Technical Details

- **Backend**: Flask with Flask-Session for session management
- **Frontend**: HTML5, CSS3, and vanilla JavaScript
- **API Integration**: Papla Media Text-to-Speech API
- **Session Storage**: Filesystem-based sessions

## Browser Compatibility

- Chrome/Chromium (recommended)
- Firefox
- Safari
- Edge

Note: Audio combining feature requires Web Audio API support.

## Troubleshooting

### Common Issues

1. **Port already in use**
   - The app runs on port 5003 by default
   - Change the port in `papla_voice_web.py` if needed

2. **API connection fails**
   - Verify your Papla API key is correct
   - Check your internet connection
   - Ensure API key has sufficient permissions

3. **Audio combining doesn't work**
   - Ensure you're using a compatible browser
   - Check that you have generated at least one audio file
   - Try refreshing the page and regenerating audio

4. **Session not persisting**
   - Ensure cookies are enabled in your browser
   - Check if browser is in private/incognito mode

## Development

To extend or modify the application:

1. **Adding new features**: Edit `papla_voice_web.py` for backend changes
2. **Styling updates**: Modify `static/styles.css`
3. **UI changes**: Update `templates/index.html`
4. **JavaScript functionality**: Edit the script section in `index.html`

## License

This project is for educational and personal use. Please respect the Papla Media API terms of service.# PaplaVoiceGenerator
