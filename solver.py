"""
Main hCaptcha Solver.
Orchestrates multiple solving strategies with fallback logic.
"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from config import SolverConfig, SolverMethod
from audio_solver import AudioSolver
from image_solver import ImageSolver


logger = logging.getLogger(__name__)


class CaptchaSolvingError(Exception):
    """Custom exception for captcha solving failures."""
    pass


class HCaptchaSolver:
    """
    Main hCaptcha solver that orchestrates multiple solving strategies.
    
    Supports:
    - Audio challenge solving via speech recognition
    - Image challenge solving via image classification
    - Third-party API fallbacks (2Captcha, AntiCaptcha)
    """
    
    def __init__(self, config: Optional[SolverConfig] = None):
        self.config = config or SolverConfig()
        self.audio_solver = AudioSolver(self.config.audio)
        self.image_solver = ImageSolver(self.config.image)
        
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._playwright = None
        
        self._setup_logging()
    
    def _setup_logging(self):
        """Configure logging based on config."""
        log_level = logging.DEBUG if self.config.debug else logging.INFO
        
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        
        # File handler
        if self.config.log_file:
            file_handler = logging.FileHandler(self.config.log_file)
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        
        logger.addHandler(console_handler)
        logger.setLevel(log_level)
    
    async def initialize(self):
        """Initialize browser with realistic fingerprint."""
        logger.info("Initializing browser...")
        
        self._playwright = await async_playwright().start()
        
        # Select browser type
        browser_launcher = {
            "chromium": self._playwright.chromium,
            "firefox": self._playwright.firefox,
            "webkit": self._playwright.webkit,
        }.get(self.config.browser.browser_type, self._playwright.chromium)
        
        # Launch options
        launch_options = {
            "headless": self.config.browser.headless,
            "slow_mo": self.config.browser.slow_mo,
        }
        
        # Add proxy if configured
        proxy = self.config.proxy.get_proxy_dict()
        if proxy:
            launch_options["proxy"] = proxy
            logger.info(f"Using proxy: {proxy['server']}")
        
        # Launch browser
        self.browser = await browser_launcher.launch(**launch_options)
        
        # Create context with fingerprint
        context_options = {
            "user_agent": self.config.browser.user_agent,
            "viewport": {
                "width": self.config.browser.viewport_width,
                "height": self.config.browser.viewport_height,
            },
            "locale": self.config.browser.locale,
            "timezone_id": self.config.browser.timezone_id,
            "permissions": ["geolocation"],
            "geolocation": {"latitude": 40.7128, "longitude": -74.0060},
            "color_scheme": "light",
            "device_scale_factor": 1,
            "is_mobile": False,
            "has_touch": False,
        }
        
        self.context = await self.browser.new_context(**context_options)
        
        # Inject fingerprint overrides
        await self._inject_fingerprints()
        
        # Create page
        self.page = await self.context.new_page()
        
        # Set default timeout
        self.page.set_default_timeout(self.config.browser.timeout)
        
        logger.info("Browser initialized successfully")
    
    async def _inject_fingerprints(self):
        """Inject realistic browser fingerprint overrides."""
        fingerprint_js = """
        () => {
            // Override navigator properties
            Object.defineProperty(navigator, 'platform', {
                get: () => '""" + self.config.browser.platform + """'
            });
            Object.defineProperty(navigator, 'vendor', {
                get: () => '""" + self.config.browser.vendor + """'
            });
            Object.defineProperty(navigator, 'hardwareConcurrency', {
                get: () => 8
            });
            Object.defineProperty(navigator, 'deviceMemory', {
                get: () => 8
            });
            Object.defineProperty(navigator, 'maxTouchPoints', {
                get: () => 0
            });
            
            // Override WebGL
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) {
                    return '""" + self.config.browser.webgl_vendor + """';
                }
                if (parameter === 37446) {
                    return '""" + self.config.browser.webgl_renderer + """';
                }
                return getParameter.call(this, parameter);
            };
            
            // Override permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
            
            // Hide automation indicators
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            // Override chrome runtime
            window.chrome = {
                runtime: {},
                loadTimes: function() {},
                csi: function() {},
                app: {}
            };
            
            // Override plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [
                    { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
                    { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
                    { name: 'Native Client', filename: 'internal-nacl-plugin' }
                ]
            });
            
            // Override languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
        }
        """
        
        await self.context.add_init_script(fingerprint_js)
    
    async def navigate_to_steam_login(self):
        """Navigate to Steam login page."""
        logger.info(f"Navigating to Steam login: {self.config.steam.login_url}")
        await self.page.goto(self.config.steam.login_url, wait_until='networkidle')
        await asyncio.sleep(2)
    
    async def detect_captcha(self) -> bool:
        """Detect if hCaptcha is present on the page."""
        try:
            # Check for hCaptcha iframe
            hcaptcha = self.page.locator('iframe[src*="hcaptcha"], .h-captcha, #hcaptcha')
            is_visible = await hcaptcha.is_visible(timeout=5000)
            
            if is_visible:
                logger.info("hCaptcha detected on page")
                return True
            
            return False
        
        except Exception:
            return False
    
    async def get_captcha_type(self) -> str:
        """Detect the type of captcha challenge (audio/image)."""
        try:
            hcaptcha_frame = self.page.frame_locator('iframe[src*="hcaptcha"]')
            
            # Check if audio challenge is active
            audio_elements = hcaptcha_frame.locator('#audio-button, .audio-button, [data-audio]')
            if await audio_elements.is_visible(timeout=2000):
                return "audio"
            
            # Check if image challenge is active
            image_elements = hcaptcha_frame.locator('.task-image, .challenge-image')
            if await image_elements.is_visible(timeout=2000):
                return "image"
            
            return "unknown"
        
        except Exception:
            return "unknown"
    
    async def switch_to_audio(self):
        """Switch hCaptcha to audio challenge mode."""
        try:
            hcaptcha_frame = self.page.frame_locator('iframe[src*="hcaptcha"]')
            
            # Find and click audio button
            audio_button = hcaptcha_frame.locator(
                '#audio-button, .audio-button, [data-audio], '
                'button[aria-label*="audio"], button[aria-label*="Audio"]'
            )
            
            await audio_button.click(timeout=5000)
            await asyncio.sleep(1)
            
            logger.info("Switched to audio challenge mode")
        
        except Exception as e:
            logger.error(f"Failed to switch to audio: {e}")
            raise
    
    async def solve_captcha(self) -> bool:
        """
        Solve the hCaptcha using configured methods with fallback.
        Returns True if captcha was solved successfully.
        """
        methods = [self.config.primary_method] + self.config.fallback_methods
        
        for method in methods:
            try:
                logger.info(f"Attempting to solve with method: {method.value}")
                
                success = await self._solve_with_method(method)
                
                if success:
                    logger.info(f"Captcha solved with method: {method.value}")
                    return True
                
                logger.warning(f"Method {method.value} failed, trying next...")
            
            except Exception as e:
                logger.error(f"Method {method.value} raised exception: {e}")
                continue
        
        logger.error("All solving methods failed")
        return False
    
    async def _solve_with_method(self, method: SolverMethod) -> bool:
        """Solve captcha with a specific method."""
        if method == SolverMethod.AUDIO:
            return await self._solve_audio()
        
        elif method == SolverMethod.IMAGE:
            return await self._solve_image()
        
        elif method == SolverMethod.API_2CAPTCHA:
            return await self._solve_2captcha()
        
        elif method == SolverMethod.API_ANTICAPTCHA:
            return await self._solve_anticaptcha()
        
        else:
            logger.error(f"Unknown solving method: {method}")
            return False
    
    async def _solve_audio(self) -> bool:
        """Solve using audio challenge method."""
        try:
            # Switch to audio mode if not already
            captcha_type = await self.get_captcha_type()
            if captcha_type != "audio":
                await self.switch_to_audio()
            
            return await self.audio_solver.solve(self.page)
        
        except Exception as e:
            logger.error(f"Audio solving failed: {e}")
            return False
    
    async def _solve_image(self) -> bool:
        """Solve using image challenge method."""
        try:
            return await self.image_solver.solve(self.page)
        
        except Exception as e:
            logger.error(f"Image solving failed: {e}")
            return False
    
    async def _solve_2captcha(self) -> bool:
        """Solve using 2Captcha API."""
        api_key = self.config.captcha_api.twocaptcha_api_key
        if not api_key:
            logger.warning("2Captcha API key not configured")
            return False
        
        try:
            import requests
            
            # Get sitekey from page
            sitekey = await self._get_sitekey()
            if not sitekey:
                logger.error("Could not find hCaptcha sitekey")
                return False
            
            page_url = self.page.url
            
            # Submit captcha
            submit_url = "http://2captcha.com/in.php"
            submit_data = {
                "key": api_key,
                "method": "hcaptcha",
                "sitekey": sitekey,
                "pageurl": page_url,
                "json": 1,
            }
            
            # Add proxy if configured
            if self.config.proxy.enabled and self.config.proxy.server:
                submit_data["proxy"] = self.config.proxy.server
                submit_data["proxytype"] = "HTTP"
            
            response = requests.post(submit_url, data=submit_data, timeout=30)
            result = response.json()
            
            if result.get("status") != 1:
                logger.error(f"2Captcha submit failed: {result}")
                return False
            
            task_id = result["request"]
            logger.info(f"2Captcha task submitted: {task_id}")
            
            # Poll for result
            result_url = "http://2captcha.com/res.php"
            timeout = self.config.captcha_api.twocaptcha_timeout
            interval = self.config.captcha_api.twocaptcha_polling_interval
            
            elapsed = 0
            while elapsed < timeout:
                await asyncio.sleep(interval)
                elapsed += interval
                
                response = requests.get(
                    result_url,
                    params={"key": api_key, "action": "get", "id": task_id, "json": 1},
                    timeout=30
                )
                result = response.json()
                
                if result.get("status") == 1:
                    token = result["request"]
                    await self._inject_captcha_token(token)
                    return True
                
                if result.get("request") != "CAPCHA_NOT_READY":
                    logger.error(f"2Captcha error: {result}")
                    return False
            
            logger.error("2Captcha timeout")
            return False
        
        except Exception as e:
            logger.error(f"2Captcha solving failed: {e}")
            return False
    
    async def _solve_anticaptcha(self) -> bool:
        """Solve using AntiCaptcha API."""
        api_key = self.config.captcha_api.anticaptcha_api_key
        if not api_key:
            logger.warning("AntiCaptcha API key not configured")
            return False
        
        try:
            import requests
            
            # Get sitekey
            sitekey = await self._get_sitekey()
            if not sitekey:
                logger.error("Could not find hCaptcha sitekey")
                return False
            
            page_url = self.page.url
            
            # Create task
            create_url = "https://api.anti-captcha.com/createTask"
            task_data = {
                "clientKey": api_key,
                "task": {
                    "type": "HCaptchaTaskProxyless",
                    "websiteURL": page_url,
                    "websiteKey": sitekey,
                }
            }
            
            # Add proxy if configured
            if self.config.proxy.enabled and self.config.proxy.server:
                task_data["task"]["type"] = "HCaptchaTask"
                task_data["task"]["proxyType"] = "http"
                task_data["task"]["proxyAddress"] = self.config.proxy.server.split("://")[-1].split(":")[0]
                if self.config.proxy.username:
                    task_data["task"]["proxyLogin"] = self.config.proxy.username
                if self.config.proxy.password:
                    task_data["task"]["proxyPassword"] = self.config.proxy.password
            
            response = requests.post(create_url, json=task_data, timeout=30)
            result = response.json()
            
            if result.get("errorId") != 0:
                logger.error(f"AntiCaptcha create task failed: {result}")
                return False
            
            task_id = result["taskId"]
            logger.info(f"AntiCaptcha task created: {task_id}")
            
            # Poll for result
            result_url = "https://api.anti-captcha.com/getTaskResult"
            timeout = self.config.captcha_api.anticaptcha_timeout
            interval = self.config.captcha_api.anticaptcha_polling_interval
            
            elapsed = 0
            while elapsed < timeout:
                await asyncio.sleep(interval)
                elapsed += interval
                
                response = requests.post(
                    result_url,
                    json={"clientKey": api_key, "taskId": task_id},
                    timeout=30
                )
                result = response.json()
                
                if result.get("status") == "ready":
                    token = result["solution"]["gRecaptchaResponse"]
                    await self._inject_captcha_token(token)
                    return True
                
                if result.get("errorId") != 0:
                    logger.error(f"AntiCaptcha error: {result}")
                    return False
            
            logger.error("AntiCaptcha timeout")
            return False
        
        except Exception as e:
            logger.error(f"AntiCaptcha solving failed: {e}")
            return False
    
    async def _get_sitekey(self) -> Optional[str]:
        """Extract hCaptcha sitekey from the page."""
        try:
            # Try multiple methods to find sitekey
            
            # Method 1: Check data-sitekey attribute
            sitekey = await self.page.evaluate("""
                () => {
                    const el = document.querySelector('[data-sitekey]');
                    if (el) return el.getAttribute('data-sitekey');
                    
                    // Check h-captcha div
                    const hcaptcha = document.querySelector('.h-captcha');
                    if (hcaptcha) return hcaptcha.getAttribute('data-sitekey');
                    
                    // Check iframe src
                    const iframe = document.querySelector('iframe[src*="hcaptcha"]');
                    if (iframe) {
                        const url = new URL(iframe.src);
                        return url.searchParams.get('sitekey');
                    }
                    
                    return null;
                }
            """)
            
            if sitekey:
                return sitekey
            
            # Method 2: Check page source
            content = await self.page.content()
            import re
            match = re.search(r'data-sitekey=["\']([^"\']+)["\']', content)
            if match:
                return match.group(1)
            
            # Method 3: Check window.hcaptcha
            sitekey = await self.page.evaluate("""
                () => {
                    if (window.hcaptcha) {
                        return window.hcaptcha.getResponse();
                    }
                    return null;
                }
            """)
            
            return sitekey
        
        except Exception as e:
            logger.error(f"Failed to get sitekey: {e}")
            return None
    
    async def _inject_captcha_token(self, token: str):
        """Inject solved captcha token into the page."""
        try:
            await self.page.evaluate(f"""
                () => {{
                    // Set hCaptcha response
                    const textarea = document.querySelector('[name="h-captcha-response"]');
                    if (textarea) textarea.value = '{token}';
                    
                    const gTextarea = document.querySelector('[name="g-recaptcha-response"]');
                    if (gTextarea) gTextarea.value = '{token}';
                    
                    // Try calling callback
                    if (window.hcaptcha) {{
                        // Not directly possible, but try
                    }}
                    
                    // Set in all forms
                    document.querySelectorAll('form').forEach(form => {{
                        let input = form.querySelector('[name="h-captcha-response"]');
                        if (!input) {{
                            input = document.createElement('input');
                            input.type = 'hidden';
                            input.name = 'h-captcha-response';
                            form.appendChild(input);
                        }}
                        input.value = '{token}';
                    }});
                }}
            """)
            
            logger.info("Injected captcha token into page")
        
        except Exception as e:
            logger.error(f"Failed to inject token: {e}")
            raise
    
    async def wait_for_captcha_resolution(self, timeout: int = 60) -> bool:
        """Wait for captcha to be resolved (success or new challenge)."""
        start = datetime.now()
        
        while (datetime.now() - start).seconds < timeout:
            # Check if captcha is gone (solved)
            try:
                captcha = self.page.locator('#captchagame, .h-captcha, iframe[src*="hcaptcha"]')
                if not await captcha.is_visible(timeout=2000):
                    logger.info("Captcha resolved - no longer visible")
                    return True
            except:
                return True
            
            # Check for error messages
            try:
                error = self.page.locator('.error-message, .captcha-error, [data-error]')
                if await error.is_visible(timeout=1000):
                    error_text = await error.text_content()
                    logger.warning(f"Captcha error: {error_text}")
                    return False
            except:
                pass
            
            await asyncio.sleep(1)
        
        logger.warning("Captcha resolution timeout")
        return False
    
    async def cleanup(self):
        """Clean up browser resources."""
        try:
            if self.page:
                await self.page.close()
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self._playwright:
                await self._playwright.stop()
            
            logger.info("Browser cleanup completed")
        
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
    
    async def solve_with_retry(self, url: Optional[str] = None) -> bool:
        """
        High-level method to solve captcha with full retry logic.
        
        Args:
            url: URL to navigate to (optional, defaults to Steam login)
        
        Returns:
            True if captcha was solved successfully
        """
        try:
            # Validate config
            warnings = self.config.validate()
            for warning in warnings:
                logger.warning(warning)
            
            # Initialize browser
            await self.initialize()
            
            # Navigate to page
            if url:
                await self.page.goto(url, wait_until='networkidle')
            else:
                await self.navigate_to_steam_login()
            
            # Check for captcha
            if not await self.detect_captcha():
                logger.info("No captcha detected")
                return True
            
            # Solve captcha
            for attempt in range(self.config.max_retries):
                logger.info(f"Solve attempt {attempt + 1}/{self.config.max_retries}")
                
                success = await self.solve_captcha()
                
                if success:
                    # Verify solution
                    if await self.wait_for_captcha_resolution():
                        return True
                    logger.warning("Solution did not resolve captcha")
                
                if attempt < self.config.max_retries - 1:
                    logger.info(f"Retrying in {self.config.retry_delay}s...")
                    await asyncio.sleep(self.config.retry_delay)
            
            return False
        
        except Exception as e:
            logger.error(f"Solver failed with exception: {e}")
            return False
        
        finally:
            await self.cleanup()


async def create_solver(config: Optional[SolverConfig] = None) -> HCaptchaSolver:
    """Factory function to create an HCaptchaSolver instance."""
    return HCaptchaSolver(config)


# Convenience function for quick solving
async def solve_hcaptcha(
    url: str,
    config: Optional[SolverConfig] = None,
) -> bool:
    """
    Convenience function to solve hCaptcha on a given URL.
    
    Args:
        url: URL with hCaptcha
        config: Optional solver configuration
    
    Returns:
        True if captcha was solved
    """
    solver = HCaptchaSolver(config)
    return await solver.solve_with_retry(url)
