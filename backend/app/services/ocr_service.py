import os
import pytesseract
from PIL import Image
import cv2
import numpy as np
from typing import Tuple, Optional, List, Dict

from app.config import get_settings


settings = get_settings()
pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd

# Set TESSDATA_PREFIX for Tesseract to find language data files
if settings.tesseract_cmd and settings.tesseract_cmd != "tesseract":
    tesseract_dir = os.path.dirname(settings.tesseract_cmd)
    tessdata_dir = os.path.join(tesseract_dir, "tessdata")
    if os.path.exists(tessdata_dir):
        os.environ["TESSDATA_PREFIX"] = tesseract_dir  # Tesseract expects parent dir


class OCRService:
    """
    OCR service using Tesseract for text extraction from documents.
    """

    SUPPORTED_LANGUAGES = {
        "eng": "English",
        "ind": "Indonesian",
        "chi_sim": "Chinese (Simplified)",
        "chi_tra": "Chinese (Traditional)",
        "jpn": "Japanese",
        "kor": "Korean",
        "ara": "Arabic",
        "tha": "Thai",
        "vie": "Vietnamese",
    }

    def __init__(self):
        self.default_lang = "eng+ind"
        self.config = "--oem 3 --psm 3"  # LSTM + auto page segmentation

    def extract_text(self, image: np.ndarray, lang: str = None) -> Tuple[str, float]:
        """
        Extract text from image using Tesseract OCR.

        Returns:
            Tuple of (extracted_text, confidence_score)
        """
        lang = lang or self.default_lang

        # Preprocess image for better OCR
        processed = self._preprocess_for_ocr(image)

        # Convert to PIL Image
        pil_image = Image.fromarray(processed)

        # Get OCR data with confidence
        data = pytesseract.image_to_data(
            pil_image,
            lang=lang,
            config=self.config,
            output_type=pytesseract.Output.DICT,
        )

        # Extract text and calculate average confidence
        text_parts = []
        confidences = []

        for i, conf in enumerate(data["conf"]):
            if int(conf) > 0:  # Valid confidence
                text = data["text"][i].strip()
                if text:
                    text_parts.append(text)
                    confidences.append(int(conf))

        full_text = " ".join(text_parts)
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0

        return full_text, avg_confidence / 100.0

    def extract_text_simple(self, image: np.ndarray, lang: str = None) -> str:
        """
        Simple text extraction without confidence scores.
        """
        lang = lang or self.default_lang
        processed = self._preprocess_for_ocr(image)
        pil_image = Image.fromarray(processed)

        return pytesseract.image_to_string(pil_image, lang=lang, config=self.config)

    def detect_language(self, image: np.ndarray) -> str:
        """
        Detect the language of text in the image.
        """
        processed = self._preprocess_for_ocr(image)
        pil_image = Image.fromarray(processed)

        try:
            osd = pytesseract.image_to_osd(pil_image)
            for line in osd.split("\n"):
                if "Script:" in line:
                    script = line.split(":")[1].strip()
                    return self._script_to_lang(script)
        except Exception:
            pass

        return "eng"

    def _script_to_lang(self, script: str) -> str:
        """
        Convert script name to language code.
        """
        script_map = {
            "Latin": "eng",
            "Han": "chi_sim",
            "Japanese": "jpn",
            "Korean": "kor",
            "Arabic": "ara",
            "Thai": "tha",
        }
        return script_map.get(script, "eng")

    def _preprocess_for_ocr(self, image: np.ndarray) -> np.ndarray:
        """
        Preprocess image for better OCR results.
        """
        # Convert to grayscale if needed
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()

        # Resize if too small
        height, width = gray.shape
        if max(height, width) < 1000:
            scale = 1000 / max(height, width)
            gray = cv2.resize(
                gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC
            )

        # Denoise
        gray = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)

        # Adaptive threshold
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )

        # Morphological operations to clean up
        kernel = np.ones((1, 1), np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

        return binary

    def get_available_languages(self) -> list:
        """
        Get list of available Tesseract languages.
        """
        try:
            langs = pytesseract.get_languages()
            return [l for l in langs if l in self.SUPPORTED_LANGUAGES]
        except Exception:
            return ["eng"]

    def extract_text_with_boxes(
        self, image: np.ndarray, lang: str = None
    ) -> List[Dict]:
        """
        Extract text with bounding box information for searchable PDF.

        Returns:
            List of dicts with keys: text, x, y, width, height, conf
            Coordinates are in image pixels from top-left.
        """
        lang = lang or self.default_lang

        # Preprocess image for better OCR
        processed = self._preprocess_for_ocr(image)

        # Get scale factor if image was resized during preprocessing
        orig_h, orig_w = image.shape[:2]
        proc_h, proc_w = processed.shape[:2]
        scale_x = orig_w / proc_w
        scale_y = orig_h / proc_h

        # Convert to PIL Image
        pil_image = Image.fromarray(processed)

        # Get OCR data with bounding boxes
        data = pytesseract.image_to_data(
            pil_image,
            lang=lang,
            config=self.config,
            output_type=pytesseract.Output.DICT,
        )

        words = []
        n_boxes = len(data["text"])

        for i in range(n_boxes):
            conf = int(data["conf"][i])
            text = data["text"][i].strip()

            if conf > 0 and text:
                words.append(
                    {
                        "text": text,
                        "x": int(data["left"][i] * scale_x),
                        "y": int(data["top"][i] * scale_y),
                        "width": int(data["width"][i] * scale_x),
                        "height": int(data["height"][i] * scale_y),
                        "conf": conf,
                    }
                )

        return words


# Singleton instance
ocr_service = OCRService()
