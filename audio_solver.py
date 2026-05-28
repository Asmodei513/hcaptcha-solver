"""
Audio Challenge Solver for hCaptcha.
Downloads audio challenges and solves them using speech-to-text backends.
"""

import asyncio
import logging
import os
import re
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, List, Tuple

import requests
import speech_recognition as sr
from pydub import AudioSegment

from config import AudioSolverConfig


logger = logging.getLogger(__name__)


class STTBackend(ABC):
    """Abstract base class for speech-to-text backends."""
    
    @abstractmethod
    def transcribe(self, audio_path: str) -> Optional[str]:
        """Transcribe audio file to text."""
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """Get backend name."""
        pass


class GoogleFreeSTT(STTBackend):
    """Google free Speech Recognition API backend."""
    
    def __init__(self, language: str = "en-US"):
        self.language = language
        self.recognizer = sr.Recognizer()
        # Tune for captcha audio (usually short phrases)
        self.recognizer.energy_threshold = 300
        self.recognizer.dynamic_energy_threshold = True
    
    def transcribe(self, audio_path: str) -> Optional[str]:
        """Transcribe using Google's free API."""
        try:
            # Convert to WAV if needed
            wav_path = self._ensure_wav(audio_path)
            
            with sr.AudioFile(wav_path) as source:
                # Adjust for ambient noise
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio_data = self.recognizer.record(source)
            
            # Try Google free API
            text = self.recognizer.recognize_google(
                audio_data,
                language=self.language,
                show_all=False
            )
            
            logger.info(f"Google STT result: {text}")
            return self._clean_text(text)
        
        except sr.UnknownValueError:
            logger.warning("Google STT could not understand audio")
            return None
        except sr.RequestError as e:
            logger.error(f"Google STT request failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Google STT error: {e}")
            return None
    
    def _ensure_wav(self, audio_path: str) -> str:
        """Convert audio to WAV format if needed."""
        if audio_path.lower().endswith('.wav'):
            return audio_path
        
        try:
            audio = AudioSegment.from_file(audio_path)
            wav_path = audio_path.rsplit('.', 1)[0] + '.wav'
            audio.export(wav_path, format='wav')
            return wav_path
        except Exception as e:
            logger.error(f"Audio conversion failed: {e}")
            return audio_path
    
    def _clean_text(self, text: str) -> str:
        """Clean recognized text for captcha use."""
        if not text:
            return ""
        # Remove extra whitespace, convert to lowercase
        cleaned = text.strip().lower()
        # Remove common artifacts
        cleaned = re.sub(r'[^\w\s]', '', cleaned)
        return cleaned
    
    def get_name(self) -> str:
        return "google_free"


class WhisperLocalSTT(STTBackend):
    """Local Whisper model backend."""
    
    def __init__(self, model_size: str = "base", language: str = "en"):
        self.model_size = model_size
        self.language = language
        self.model = None
    
    def _load_model(self):
        """Lazy load Whisper model."""
        if self.model is None:
            try:
                import whisper
                self.model = whisper.load_model(self.model_size)
                logger.info(f"Loaded Whisper model: {self.model_size}")
            except ImportError:
                logger.error("whisper package not installed. Install with: pip install openai-whisper")
                return False
            except Exception as e:
                logger.error(f"Failed to load Whisper model: {e}")
                return False
        return True
    
    def transcribe(self, audio_path: str) -> Optional[str]:
        """Transcribe using local Whisper model."""
        if not self._load_model():
            return None
        
        try:
            result = self.model.transcribe(
                audio_path,
                language=self.language,
                fp16=False,  # Use FP32 for CPU
                without_timestamps=True
            )
            
            text = result.get("text", "").strip()
            logger.info(f"Whisper STT result: {text}")
            
            # Clean text
            cleaned = re.sub(r'[^\w\s]', '', text.lower().strip())
            return cleaned if cleaned else None
        
        except Exception as e:
            logger.error(f"Whisper transcription failed: {e}")
            return None
    
    def get_name(self) -> str:
        return f"whisper_{self.model_size}"


class VoskLocalSTT(STTBackend):
    """Vosk offline speech recognition backend."""
    
    def __init__(self, model_path: Optional[str] = None, sample_rate: int = 16000):
        self.model_path = model_path
        self.sample_rate = sample_rate
        self.model = None
        self.rec = None
    
    def _load_model(self):
        """Lazy load Vosk model."""
        if self.model is None:
            try:
                from vosk import Model, KaldiRecognizer
                import wave
                
                if self.model_path:
                    self.model = Model(self.model_path)
                else:
                    # Try to use default model
                    self.model = Model(lang="en-us")
                logger.info("Loaded Vosk model")
                return True
            except ImportError:
                logger.error("vosk package not installed")
                return False
            except Exception as e:
                logger.error(f"Failed to load Vosk model: {e}")
                return False
        return True
    
    def transcribe(self, audio_path: str) -> Optional[str]:
        """Transcribe using Vosk."""
        if not self._load_model():
            return None
        
        try:
            import wave
            from vosk import KaldiRecognizer
            
            # Ensure WAV format
            if not audio_path.lower().endswith('.wav'):
                audio = AudioSegment.from_file(audio_path)
                audio_path_wav = audio_path.rsplit('.', 1)[0] + '.wav'
                audio.export(audio_path_wav, format='wav')
                audio_path = audio_path_wav
            
            wf = wave.open(audio_path, "rb")
            rec = KaldiRecognizer(self.model, wf.getframerate())
            rec.SetWords(False)
            
            results = []
            while True:
                data = wf.readframes(4000)
                if len(data) == 0:
                    break
                if rec.AcceptWaveform(data):
                    result = rec.Result()
                    results.append(result)
            
            # Get final result
            final = rec.FinalResult()
            results.append(final)
            
            # Parse results
            import json
            text_parts = []
            for r in results:
                try:
                    d = json.loads(r)
                    if "text" in d:
                        text_parts.append(d["text"])
                except:
                    pass
            
            text = " ".join(text_parts).strip()
            logger.info(f"Vosk STT result: {text}")
            
            cleaned = re.sub(r'[^\w\s]', '', text.lower().strip())
            return cleaned if cleaned else None
        
        except Exception as e:
            logger.error(f"Vosk transcription failed: {e}")
            return None
    
    def get_name(self) -> str:
        return "vosk_local"


class AudioSolver:
    """
    Audio challenge solver for hCaptcha.
    Downloads audio challenges and solves them using multiple STT backends.
    """
    
    def __init__(self, config: Optional[AudioSolverConfig] = None):
        self.config = config or AudioSolverConfig()
        self.backends: List[STTBackend] = []
        self._init_backends()
    
    def _init_backends(self):
        """Initialize STT backends based on configuration."""
        for backend_name in self.config.stt_backends:
            if backend_name == "google_free":
                self.backends.append(GoogleFreeSTT(
                    language=self.config.google_language
                ))
            elif backend_name == "whisper_local":
                self.backends.append(WhisperLocalSTT(
                    model_size=self.config.whisper_model,
                    language=self.config.whisper_language
                ))
            elif backend_name == "vosk_local":
                self.backends.append(VoskLocalSTT())
            else:
                logger.warning(f"Unknown STT backend: {backend_name}")
        
        if not self.backends:
            logger.warning("No STT backends available, falling back to Google Free")
            self.backends.append(GoogleFreeSTT())
    
    async def download_audio(self, page, audio_url: str) -> Optional[str]:
        """Download audio challenge from hCaptcha."""
        try:
            os.makedirs(self.config.download_dir, exist_ok=True)
            
            # Generate unique filename
            import uuid
            filename = f"captcha_{uuid.uuid4().hex[:8]}.mp3"
            filepath = os.path.join(self.config.download_dir, filename)
            
            # Download using requests (more reliable than page download)
            response = requests.get(audio_url, timeout=30)
            response.raise_for_status()
            
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            # Check duration
            audio = AudioSegment.from_file(filepath)
            duration_seconds = len(audio) / 1000.0
            
            if duration_seconds > self.config.max_duration:
                logger.warning(f"Audio too long: {duration_seconds}s > {self.config.max_duration}s")
                return None
            
            logger.info(f"Downloaded audio: {filepath} ({duration_seconds:.1f}s)")
            return filepath
        
        except Exception as e:
            logger.error(f"Failed to download audio: {e}")
            return None
    
    async def get_audio_url(self, page) -> Optional[str]:
        """Extract audio challenge URL from hCaptcha iframe."""
        try:
            # Wait for hCaptcha iframe
            hcaptcha_frame = page.frame_locator('iframe[src*="hcaptcha"]')
            
            # Click audio challenge button
            audio_button = hcaptcha_frame.locator('#audio-button, [data-audio]')
            await audio_button.click()
            await asyncio.sleep(1)
            
            # Find audio source
            audio_source = hcaptcha_frame.locator('audio source, audio[src]')
            
            # Try multiple selectors
            for selector in ['audio source', 'audio', '#audio-source', '.audio-src']:
                try:
                    element = hcaptcha_frame.locator(selector)
                    src = await element.get_attribute('src')
                    if src:
                        return src
                except:
                    continue
            
            # Try to intercept network request for audio
            return None
        
        except Exception as e:
            logger.error(f"Failed to get audio URL: {e}")
            return None
    
    async def intercept_audio_url(self, page) -> Optional[str]:
        """Intercept audio URL from network requests."""
        audio_url = None
        
        async def handle_response(response):
            nonlocal audio_url
            url = response.url
            if 'audio' in url and ('hcaptcha' in url or 'captcha' in url):
                if url.endswith('.mp3') or url.endswith('.wav') or 'audio' in url:
                    audio_url = url
        
        page.on('response', handle_response)
        
        # Trigger audio challenge
        try:
            hcaptcha_frame = page.frame_locator('iframe[src*="hcaptcha"]')
            audio_button = hcaptcha_frame.locator('#audio-button, [data-audio], .audio-button')
            await audio_button.click(timeout=5000)
        except:
            pass
        
        await asyncio.sleep(3)
        page.remove_listener('response', handle_response)
        
        return audio_url
    
    async def solve_audio_challenge(self, audio_path: str) -> Optional[str]:
        """Solve audio challenge using available STT backends."""
        for backend in self.backends:
            for attempt in range(self.config.max_retries):
                try:
                    logger.info(
                        f"Attempting transcription with {backend.get_name()} "
                        f"(attempt {attempt + 1}/{self.config.max_retries})"
                    )
                    
                    # Run transcription in thread pool to avoid blocking
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(
                        None, backend.transcribe, audio_path
                    )
                    
                    if result:
                        logger.info(
                            f"Transcription successful with {backend.get_name()}: {result}"
                        )
                        return result
                    
                    logger.warning(
                        f"Transcription failed with {backend.get_name()}, "
                        f"attempt {attempt + 1}"
                    )
                    
                    if attempt < self.config.max_retries - 1:
                        await asyncio.sleep(self.config.retry_delay)
                
                except Exception as e:
                    logger.error(f"Error with {backend.get_name()}: {e}")
                    if attempt < self.config.max_retries - 1:
                        await asyncio.sleep(self.config.retry_delay)
        
        logger.error("All STT backends failed")
        return None
    
    async def type_solution(self, page, solution: str):
        """Type the solution into the hCaptcha input field."""
        try:
            hcaptcha_frame = page.frame_locator('iframe[src*="hcaptcha"]')
            
            # Find and fill the text input
            text_input = hcaptcha_frame.locator('#audio-response, input[type="text"]')
            await text_input.fill(solution)
            
            # Small delay to appear human-like
            await asyncio.sleep(0.5 + (len(solution) * 0.1))
            
            # Submit
            submit_button = hcaptcha_frame.locator(
                '#audio-submit, button[type="submit"], .submit-button'
            )
            await submit_button.click()
            
            logger.info(f"Submitted audio solution: {solution}")
        
        except Exception as e:
            logger.error(f"Failed to type solution: {e}")
            raise
    
    async def solve(self, page) -> bool:
        """
        Main solve method for audio challenges.
        Returns True if captcha was solved successfully.
        """
        for attempt in range(self.config.max_retries):
            try:
                logger.info(f"Audio solve attempt {attempt + 1}/{self.config.max_retries}")
                
                # Try to get audio URL
                audio_url = await self.get_audio_url(page)
                if not audio_url:
                    audio_url = await self.intercept_audio_url(page)
                
                if not audio_url:
                    logger.error("Could not find audio URL")
                    continue
                
                # Download audio
                audio_path = await self.download_audio(page, audio_url)
                if not audio_path:
                    logger.error("Could not download audio")
                    continue
                
                # Solve
                solution = await self.solve_audio_challenge(audio_path)
                if not solution:
                    logger.error("Could not transcribe audio")
                    continue
                
                # Type solution
                await self.type_solution(page, solution)
                
                # Wait for verification
                await asyncio.sleep(2)
                
                # Check if solved
                if await self._check_solved(page):
                    logger.info("Audio challenge solved successfully!")
                    return True
                
                logger.warning("Solution did not work, retrying...")
            
            except Exception as e:
                logger.error(f"Audio solve attempt {attempt + 1} failed: {e}")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay)
        
        return False
    
    async def _check_solved(self, page) -> bool:
        """Check if the captcha was solved successfully."""
        try:
            # Check for success indicators
            hcaptcha_frame = page.frame_locator('iframe[src*="hcaptcha"]')
            
            # Look for checkmark or success state
            success_selectors = [
                '.checkmark',
                '[data-success]',
                '.success',
                '#success',
            ]
            
            for selector in success_selectors:
                try:
                    element = hcaptcha_frame.locator(selector)
                    if await element.is_visible(timeout=1000):
                        return True
                except:
                    continue
            
            # Check if captcha container disappeared
            try:
                captcha = page.locator('#captchagame, .h-captcha')
                if not await captcha.is_visible(timeout=1000):
                    return True
            except:
                pass
            
            return False
        
        except Exception:
            return False


async def create_audio_solver(config: Optional[AudioSolverConfig] = None) -> AudioSolver:
    """Factory function to create an AudioSolver instance."""
    return AudioSolver(config)
