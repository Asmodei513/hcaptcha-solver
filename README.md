# hCaptcha Solver for Steam Login

A comprehensive hCaptcha solver with multiple solving strategies, designed specifically for Steam login automation.

## Features

- **Audio Challenge Solver**: Uses speech-to-text to solve audio challenges
  - Google Speech Recognition (free API)
  - OpenAI Whisper (local model)
  - Vosk (offline recognition)
  - Automatic retry with multiple backends

- **Image Challenge Solver**: Classifies and selects correct images
  - HuggingFace Inference API
  - Imagga API
  - Local ResNet50 model
  - Extensive category mapping for hCaptcha objects

- **Third-Party API Integration**: Reliable fallback methods
  - 2Captcha API support
  - AntiCaptcha API support
  - Automatic polling and token injection

- **Steam-Specific Features**:
  - Complete login flow handling
  - Steam Guard 2FA support
  - Session persistence
  - Cookie management

- **Browser Automation**:
  - Playwright-based (Chromium, Firefox, WebKit)
  - Realistic browser fingerprinting
  - Anti-detection measures
  - Human-like interaction delays

## Installation

```bash
# Clone or navigate to the solver directory
cd /root/hcaptcha_solver

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium

# Optional: Install additional STT backends
pip install openai-whisper  # For Whisper
pip install vosk  # For Vosk offline
```

## Configuration

### Environment Variables

```bash
# Steam credentials
export STEAM_USERNAME="your_username"
export STEAM_PASSWORD="your_password"

# Third-party CAPTCHA APIs (optional)
export TWOCAPTCHA_API_KEY="your_2captcha_key"
export ANTICAPTCHA_API_KEY="your_anticaptcha_key"

# Image classification APIs (optional)
export HUGGINGFACE_API_KEY="your_huggingface_key"
export IMAGGA_API_KEY="your_imagga_key"
export IMAGGA_API_SECRET="your_imagga_secret"

# Proxy (optional)
export HCAPTCHA_PROXY_SERVER="http://proxy:port"
export HCAPTCHA_PROXY_USERNAME="proxy_user"
export HCAPTCHA_PROXY_PASSWORD="proxy_pass"

# Debug mode
export HCAPTCHA_DEBUG="true"
```

### Programmatic Configuration

```python
from config import SolverConfig, SolverMethod, BrowserConfig, ProxyConfig

config = SolverConfig(
    primary_method=SolverMethod.AUDIO,
    fallback_methods=[SolverMethod.IMAGE, SolverMethod.API_2CAPTCHA],
    browser=BrowserConfig(
        headless=False,
        browser_type="chromium",
        user_agent="Mozilla/5.0 ...",
    ),
    proxy=ProxyConfig(
        enabled=True,
        server="http://proxy:port",
    ),
    max_retries=5,
    debug=True,
)
```

## Usage

### Quick Start

```python
import asyncio
from solver import solve_hcaptcha

async def main():
    success = await solve_hcaptcha(
        url="https://store.steampowered.com/login/"
    )
    print(f"Captcha solved: {success}")

asyncio.run(main())
```

### Steam Login

```python
import asyncio
from steam_login import steam_login_with_captcha

async def main():
    result = await steam_login_with_captcha(
        username="your_username",
        password="your_password",
        steam_guard_code="12345",  # Optional
    )
    
    print(f"Login status: {result.status}")
    print(f"Message: {result.message}")
    
    if result.success:
        print(f"Cookies: {result.cookies}")

asyncio.run(main())
```

### Custom Solver

```python
import asyncio
from config import SolverConfig
from solver import HCaptchaSolver

async def main():
    config = SolverConfig()
    solver = HCaptchaSolver(config)
    
    try:
        success = await solver.solve_with_retry(
            url="https://example.com/captcha-page"
        )
        print(f"Solved: {success}")
    finally:
        await solver.cleanup()

asyncio.run(main())
```

### Audio Solver Only

```python
import asyncio
from audio_solver import AudioSolver

async def main():
    solver = AudioSolver()
    
    # Assuming you have a page object
    success = await solver.solve(page)
    print(f"Audio challenge solved: {success}")

asyncio.run(main())
```

### Image Solver Only

```python
import asyncio
from image_solver import ImageSolver

async def main():
    solver = ImageSolver()
    
    # Assuming you have a page object
    success = await solver.solve(page)
    print(f"Image challenge solved: {success}")

asyncio.run(main())
```

## File Structure

```
hcaptcha_solver/
├── config.py           # Configuration classes and defaults
├── solver.py           # Main solver with fallback logic
├── audio_solver.py     # Audio challenge solver (STT)
├── image_solver.py     # Image challenge solver (classification)
├── steam_login.py      # Steam-specific login integration
├── test_solver.py      # Test script
├── requirements.txt    # Python dependencies
└── README.md           # This file
```

## How It Works

### Audio Challenge Flow

1. Detect hCaptcha on page
2. Switch to audio challenge mode
3. Intercept or extract audio URL
4. Download audio file
5. Transcribe using STT backend(s):
   - Google Speech Recognition (free, requires internet)
   - Whisper (local, requires GPU for speed)
   - Vosk (offline, lightweight)
6. Type transcribed text into input
7. Submit and verify solution
8. Retry with different backend if failed

### Image Challenge Flow

1. Detect hCaptcha on page
2. Extract challenge text (e.g., "Select all images with a seal")
3. Download all challenge images
4. Classify each image using classifier(s):
   - HuggingFace API (accurate, requires API key)
   - Imagga API (good accuracy, requires API key)
   - Local ResNet50 (free, less accurate for hCaptcha)
5. Match classifications against challenge using category mappings
6. Click matching images
7. Submit and verify solution
8. Retry if failed

### Third-Party API Flow

1. Extract hCaptcha sitekey from page
2. Submit captcha to API (2Captcha/AntiCaptcha)
3. Poll for solution (human solvers)
4. Inject token into page
5. Submit form

## Browser Fingerprinting

The solver implements realistic browser fingerprinting to avoid detection:

- **User Agent**: Matches real Chrome/Firefox signatures
- **WebGL**: Spoofs vendor and renderer strings
- **Navigator**: Overrides platform, languages, hardware info
- **Plugins**: Simulates real plugin list
- **Automation Hides**: Removes webdriver indicators
- **Chrome Runtime**: Injects chrome object

## Proxy Support

Supports HTTP proxies with authentication:

```python
from config import SolverConfig, ProxyConfig

config = SolverConfig(
    proxy=ProxyConfig(
        enabled=True,
        server="http://proxy.example.com:8080",
        username="user",
        password="pass",
    )
)
```

## Troubleshooting

### Common Issues

1. **Playwright not installed**
   ```bash
   playwright install chromium
   ```

2. **Speech recognition fails**
   - Check internet connection (for Google API)
   - Install whisper: `pip install openai-whisper`
   - Try different STT backend

3. **Image classification inaccurate**
   - Set HUGGINGFACE_API_KEY for better accuracy
   - Lower confidence_threshold in config

4. **Captcha not detected**
   - Check if site uses hCaptcha (not reCAPTCHA)
   - Increase timeout in config
   - Enable debug mode for logs

5. **Steam login fails**
   - Verify credentials are correct
   - Check for Steam Guard requirements
   - Ensure proxy is working

### Debug Mode

```python
config = SolverConfig(debug=True)
```

This enables:
- Verbose logging
- Screenshot capture
- Network request logging
- Detailed error messages

## Performance Tips

1. **Use headless mode** for faster execution
2. **Enable proxy rotation** to avoid rate limits
3. **Cache sessions** to avoid re-login
4. **Use local Whisper** for faster audio solving
5. **Set appropriate timeouts** based on network speed

## Limitations

- Audio solving accuracy depends on audio quality and STT backend
- Image solving accuracy varies by category
- Third-party APIs have costs and latency
- Steam may block automated access
- Rate limits may apply

## Legal Notice

This tool is for educational purposes only. Using automation to access Steam may violate their Terms of Service. Use responsibly and at your own risk.

## License

MIT License - Use at your own risk

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## Support

For issues or questions:
- Check the troubleshooting section
- Review logs in debug mode
- Open an issue with details
