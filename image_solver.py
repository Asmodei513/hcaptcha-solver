"""
Image Challenge Solver for hCaptcha.
Downloads challenge images and classifies them using APIs or local models.
"""

import asyncio
import logging
import os
import re
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Any

import requests

from config import ImageSolverConfig


logger = logging.getLogger(__name__)


class ImageClassifier(ABC):
    """Abstract base class for image classifiers."""
    
    @abstractmethod
    def classify(self, image_path: str) -> Dict[str, float]:
        """Classify image and return label -> confidence mapping."""
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """Get classifier name."""
        pass


class LocalModelClassifier(ImageClassifier):
    """Local model-based image classifier using a pre-trained model."""
    
    def __init__(self):
        self.model = None
        self.labels = None
    
    def _load_model(self):
        """Load a pre-trained image classification model."""
        if self.model is not None:
            return True
        
        try:
            import torch
            import torchvision.transforms as transforms
            from torchvision import models
            
            # Load pre-trained ResNet model
            self.model = models.resnet50(pretrained=True)
            self.model.eval()
            
            # Standard ImageNet transforms
            self.transform = transforms.Compose([
                transforms.Resize(256),
                transforms.CenterCrop(224),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.485, 0.456, 0.406],
                    std=[0.229, 0.224, 0.225]
                ),
            ])
            
            # Load ImageNet labels
            labels_url = "https://raw.githubusercontent.com/anishathalye/imagenet-simple-labels/master/imagenet-simple-labels.json"
            response = requests.get(labels_url, timeout=10)
            self.labels = response.json()
            
            logger.info("Loaded local image classification model")
            return True
        
        except ImportError:
            logger.error("torch/torchvision not installed")
            return False
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            return False
    
    def classify(self, image_path: str) -> Dict[str, float]:
        """Classify image using local model."""
        if not self._load_model():
            return {}
        
        try:
            from PIL import Image
            import torch
            
            # Load and preprocess image
            image = Image.open(image_path).convert('RGB')
            input_tensor = self.transform(image).unsqueeze(0)
            
            # Run inference
            with torch.no_grad():
                output = self.model(input_tensor)
            
            # Get probabilities
            probabilities = torch.nn.functional.softmax(output[0], dim=0)
            
            # Get top predictions
            top_prob, top_idx = torch.topk(probabilities, 10)
            
            results = {}
            for prob, idx in zip(top_prob, top_idx):
                if self.labels and idx < len(self.labels):
                    label = self.labels[idx]
                    results[label] = prob.item()
            
            return results
        
        except Exception as e:
            logger.error(f"Classification failed: {e}")
            return {}
    
    def get_name(self) -> str:
        return "local_resnet50"


class HuggingFaceClassifier(ImageClassifier):
    """HuggingFace Inference API classifier."""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "google/vit-base-patch16-224"):
        self.api_key = api_key or os.getenv("HUGGINGFACE_API_KEY", "")
        self.model = model
        self.api_url = f"https://api-inference.huggingface.co/models/{model}"
    
    def classify(self, image_path: str) -> Dict[str, float]:
        """Classify image using HuggingFace API."""
        if not self.api_key:
            logger.warning("HuggingFace API key not set")
            return {}
        
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            
            with open(image_path, 'rb') as f:
                response = requests.post(
                    self.api_url,
                    headers=headers,
                    data=f,
                    timeout=30
                )
            
            if response.status_code != 200:
                logger.error(f"HuggingFace API error: {response.status_code}")
                return {}
            
            results = response.json()
            
            # Parse results
            classifications = {}
            if isinstance(results, list):
                for item in results:
                    if isinstance(item, dict) and 'label' in item and 'score' in item:
                        classifications[item['label']] = item['score']
            
            return classifications
        
        except Exception as e:
            logger.error(f"HuggingFace API error: {e}")
            return {}
    
    def get_name(self) -> str:
        return f"huggingface_{self.model}"


class ImaggaClassifier(ImageClassifier):
    """Imagga image classification API."""
    
    def __init__(self, api_key: str = "", api_secret: str = ""):
        self.api_key = api_key or os.getenv("IMAGGA_API_KEY", "")
        self.api_secret = api_secret or os.getenv("IMAGGA_API_SECRET", "")
    
    def classify(self, image_path: str) -> Dict[str, float]:
        """Classify image using Imagga API."""
        if not self.api_key or not self.api_secret:
            logger.warning("Imagga credentials not set")
            return {}
        
        try:
            response = requests.post(
                'https://api.imagga.com/v2/tags',
                auth=(self.api_key, self.api_secret),
                files={'image': open(image_path, 'rb')},
                timeout=30
            )
            
            if response.status_code != 200:
                logger.error(f"Imagga API error: {response.status_code}")
                return {}
            
            data = response.json()
            tags = data.get('result', {}).get('tags', [])
            
            results = {}
            for tag in tags:
                name = tag.get('tag', {}).get('en', '')
                confidence = tag.get('confidence', 0) / 100.0
                if name:
                    results[name] = confidence
            
            return results
        
        except Exception as e:
            logger.error(f"Imagga API error: {e}")
            return {}
    
    def get_name(self) -> str:
        return "imagga"


class ImageSolver:
    """
    Image challenge solver for hCaptcha.
    Downloads challenge images and classifies them to select correct tiles.
    """
    
    # Common hCaptcha challenge categories and their ImageNet-style mappings
    CATEGORY_MAPPINGS = {
        "seal": ["seal", "sea lion", "otter", "walrus"],
        "lion": ["lion", "cougar", "cheetah", "leopard", "tiger", "cat"],
        "bear": ["bear", "polar bear", "brown bear", "grizzly"],
        "elephant": ["elephant", "mammoth"],
        "dolphin": ["dolphin", "whale", "porpoise"],
        "airplane": ["airplane", "plane", "aircraft", "jet"],
        "bicycle": ["bicycle", "bike", "tricycle"],
        "boat": ["boat", "ship", "sailboat", "canoe", "kayak"],
        "bus": ["bus", "trolleybus", "minibus"],
        "car": ["car", "automobile", "taxi", "cab"],
        "motorcycle": ["motorcycle", "motorbike", "scooter"],
        "train": ["train", "locomotive", "railway"],
        "truck": ["truck", "pickup", "lorry"],
        "traffic light": ["traffic light", "traffic signal"],
        "fire hydrant": ["fire hydrant", "hydrant"],
        "stop sign": ["stop sign", "sign"],
        "parking meter": ["parking meter", "meter"],
        "bench": ["bench", "seat"],
        "bird": ["bird", "eagle", "hawk", "sparrow", "robin", "parrot"],
        "cat": ["cat", "kitten", "tabby", "persian"],
        "dog": ["dog", "puppy", "retriever", "terrier", "spaniel", "hound"],
        "horse": ["horse", "stallion", "mare", "pony"],
        "sheep": ["sheep", "lamb", "ram", "goat"],
        "cow": ["cow", "bull", "cattle", "ox"],
        "bottle": ["bottle", "wine bottle", "beer bottle"],
        "chair": ["chair", "stool", "armchair", "rocking chair"],
        "couch": ["couch", "sofa", "settee"],
        "potted plant": ["potted plant", "plant", "flower pot"],
        "bed": ["bed", "mattress"],
        "dining table": ["dining table", "table", "desk"],
        "toilet": ["toilet", "lavatory"],
        "tv": ["tv", "television", "monitor", "screen"],
        "laptop": ["laptop", "notebook", "computer"],
        "mouse": ["mouse", "computer mouse"],
        "keyboard": ["keyboard", "computer keyboard"],
        "cell phone": ["cell phone", "mobile phone", "smartphone", "telephone"],
        "microwave": ["microwave", "microwave oven"],
        "oven": ["oven", "stove", "range"],
        "toaster": ["toaster"],
        "sink": ["sink"],
        "refrigerator": ["refrigerator", "fridge"],
        "book": ["book", "notebook", "journal"],
        "clock": ["clock", "watch", "timepiece"],
        "vase": ["vase", "urn", "pot"],
        "scissors": ["scissors", "shears"],
        "teddy bear": ["teddy bear", "stuffed animal", "plush"],
        "hair dryer": ["hair dryer", "blow dryer"],
        "toothbrush": ["toothbrush"],
    }
    
    def __init__(self, config: Optional[ImageSolverConfig] = None):
        self.config = config or ImageSolverConfig()
        self.classifiers: List[ImageClassifier] = []
        self._init_classifiers()
    
    def _init_classifiers(self):
        """Initialize image classifiers."""
        # Try HuggingFace first (most reliable)
        hf_key = os.getenv("HUGGINGFACE_API_KEY", "")
        if hf_key:
            self.classifiers.append(HuggingFaceClassifier(api_key=hf_key))
        
        # Try Imagga
        imagga_key = os.getenv("IMAGGA_API_KEY", "")
        if imagga_key:
            self.classifiers.append(ImaggaClassifier())
        
        # Always add local model as fallback
        self.classifiers.append(LocalModelClassifier())
    
    async def download_image(self, page, image_url: str) -> Optional[str]:
        """Download an image from URL."""
        try:
            os.makedirs(self.config.download_dir, exist_ok=True)
            
            filename = f"captcha_img_{uuid.uuid4().hex[:8]}.jpg"
            filepath = os.path.join(self.config.download_dir, filename)
            
            response = requests.get(image_url, timeout=30)
            response.raise_for_status()
            
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            logger.debug(f"Downloaded image: {filepath}")
            return filepath
        
        except Exception as e:
            logger.error(f"Failed to download image: {e}")
            return None
    
    async def get_challenge_info(self, page) -> Tuple[str, List[str]]:
        """
        Get challenge prompt and image URLs from hCaptcha.
        Returns (challenge_text, list_of_image_urls)
        """
        try:
            hcaptcha_frame = page.frame_locator('iframe[src*="hcaptcha"]')
            
            # Get challenge text (e.g., "Select all images with a seal")
            challenge_text = ""
            for selector in ['.prompt-text', '.challenge-header', 'h2', '.text']:
                try:
                    element = hcaptcha_frame.locator(selector)
                    text = await element.text_content(timeout=3000)
                    if text:
                        challenge_text = text.strip()
                        break
                except:
                    continue
            
            # Get image URLs
            image_urls = []
            images = hcaptcha_frame.locator('.task-image img, .challenge-image img, img[src*="hcaptcha"]')
            count = await images.count()
            
            for i in range(count):
                try:
                    src = await images.nth(i).get_attribute('src')
                    if src:
                        image_urls.append(src)
                except:
                    continue
            
            return challenge_text, image_urls
        
        except Exception as e:
            logger.error(f"Failed to get challenge info: {e}")
            return "", []
    
    def classify_image(self, image_path: str) -> Dict[str, float]:
        """Classify an image using available classifiers."""
        for classifier in self.classifiers:
            try:
                results = classifier.classify(image_path)
                if results:
                    logger.debug(f"{classifier.get_name()} results: {results}")
                    return results
            except Exception as e:
                logger.warning(f"Classifier {classifier.get_name()} failed: {e}")
        
        return {}
    
    def should_select(self, challenge_text: str, classifications: Dict[str, float]) -> bool:
        """
        Determine if an image should be selected based on challenge text and classifications.
        """
        challenge_lower = challenge_text.lower()
        
        # Extract the target object from challenge text
        # Common patterns: "Select all images with a X", "Please click on the X"
        target = None
        patterns = [
            r'select all images with (?:a |an |the )?(.+?)(?:\.|$)',
            r'please click on (?:the |all )?(.+?)(?:\.|$)',
            r'click on (?:the |all )?(.+?)(?:\.|$)',
            r'select (?:the |all )?(.+?)(?:\.|$)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, challenge_lower)
            if match:
                target = match.group(1).strip()
                break
        
        if not target:
            target = challenge_lower
        
        # Get category mappings for the target
        related_terms = [target]
        for category, synonyms in self.CATEGORY_MAPPINGS.items():
            if target in category or category in target:
                related_terms.extend(synonyms)
                break
            for synonym in synonyms:
                if target in synonym or synonym in target:
                    related_terms.extend(synonyms)
                    break
        
        # Check if any classification matches
        for label, confidence in classifications.items():
            label_lower = label.lower()
            
            for term in related_terms:
                if term in label_lower or label_lower in term:
                    if confidence >= self.config.confidence_threshold:
                        return True
            
            # Also check for partial matches
            for term in related_terms:
                term_words = term.split()
                label_words = label_lower.split()
                
                common_words = set(term_words) & set(label_words)
                if common_words and confidence >= self.config.confidence_threshold:
                    return True
        
        return False
    
    async def click_images(self, page, indices: List[int]):
        """Click on specific image tiles in the hCaptcha grid."""
        try:
            hcaptcha_frame = page.frame_locator('iframe[src*="hcaptcha"]')
            
            # Get all task image containers
            task_images = hcaptcha_frame.locator('.task-image, .challenge-image')
            count = await task_images.count()
            
            for idx in indices:
                if 0 <= idx < count:
                    # Add human-like delay
                    await asyncio.sleep(0.3 + (idx * 0.1))
                    
                    await task_images.nth(idx).click()
                    logger.debug(f"Clicked image at index {idx}")
            
            # Click verify/submit button
            await asyncio.sleep(1)
            submit = hcaptcha_frame.locator('.button-submit, #refresh, [data-callback]')
            await submit.click()
            
        except Exception as e:
            logger.error(f"Failed to click images: {e}")
            raise
    
    async def solve(self, page) -> bool:
        """
        Main solve method for image challenges.
        Returns True if captcha was solved successfully.
        """
        for attempt in range(self.config.max_retries):
            try:
                logger.info(f"Image solve attempt {attempt + 1}/{self.config.max_retries}")
                
                # Get challenge info
                challenge_text, image_urls = await self.get_challenge_info(page)
                
                if not challenge_text:
                    logger.error("Could not get challenge text")
                    continue
                
                if not image_urls:
                    logger.error("Could not get image URLs")
                    continue
                
                logger.info(f"Challenge: {challenge_text}")
                logger.info(f"Found {len(image_urls)} images")
                
                # Download and classify images
                select_indices = []
                
                for i, url in enumerate(image_urls):
                    image_path = await self.download_image(page, url)
                    if not image_path:
                        continue
                    
                    classifications = self.classify_image(image_path)
                    if self.should_select(challenge_text, classifications):
                        select_indices.append(i)
                        logger.info(f"Image {i}: MATCH - {classifications}")
                    else:
                        logger.debug(f"Image {i}: no match - {classifications}")
                
                if not select_indices:
                    logger.warning("No images matched the challenge")
                    # Try selecting none and refreshing
                    continue
                
                logger.info(f"Selecting images at indices: {select_indices}")
                
                # Click selected images
                await self.click_images(page, select_indices)
                
                # Wait for verification
                await asyncio.sleep(2)
                
                # Check if solved
                if await self._check_solved(page):
                    logger.info("Image challenge solved successfully!")
                    return True
                
                logger.warning("Image solution did not work, retrying...")
            
            except Exception as e:
                logger.error(f"Image solve attempt {attempt + 1} failed: {e}")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay)
        
        return False
    
    async def _check_solved(self, page) -> bool:
        """Check if the captcha was solved successfully."""
        try:
            hcaptcha_frame = page.frame_locator('iframe[src*="hcaptcha"]')
            
            # Look for success indicators
            success_selectors = [
                '.checkmark',
                '[data-success]',
                '.success',
            ]
            
            for selector in success_selectors:
                try:
                    element = hcaptcha_frame.locator(selector)
                    if await element.is_visible(timeout=1000):
                        return True
                except:
                    continue
            
            # Check if captcha disappeared
            try:
                captcha = page.locator('#captchagame, .h-captcha')
                if not await captcha.is_visible(timeout=1000):
                    return True
            except:
                pass
            
            return False
        
        except Exception:
            return False


async def create_image_solver(config: Optional[ImageSolverConfig] = None) -> ImageSolver:
    """Factory function to create an ImageSolver instance."""
    return ImageSolver(config)
