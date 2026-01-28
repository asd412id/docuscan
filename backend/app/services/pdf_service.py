from reportlab.lib.pagesizes import A4, letter, legal
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PyPDF2 import PdfMerger
from PIL import Image
import io
import os
from typing import List, Optional, Tuple, Dict
import tempfile


# Custom page sizes not in reportlab
# Folio/F4: 8.5 x 13 inches (215.9 x 330.2 mm)
FOLIO = (8.5 * inch, 13 * inch)
# Legal: 8.5 x 14 inches (already in reportlab, but defining for clarity)
LEGAL = legal


class PDFService:
    """
    PDF generation service for creating multi-page PDFs from scanned documents.
    """

    PAGE_SIZES = {
        "a4": A4,  # 210 x 297 mm (8.27 x 11.69 in)
        "letter": letter,  # 8.5 x 11 in (215.9 x 279.4 mm)
        "legal": LEGAL,  # 8.5 x 14 in (215.9 x 355.6 mm)
        "folio": FOLIO,  # 8.5 x 13 in (215.9 x 330.2 mm) - F4
        "f4": FOLIO,  # Alias for folio
    }

    def __init__(self):
        self.default_page_size = A4
        self.margin = 0.5 * inch

    def create_pdf_from_images(
        self,
        image_paths: List[str],
        output_path: str,
        page_size: str = "auto",
        quality: int = 90,
    ) -> str:
        """
        Create a PDF from multiple image files.

        Args:
            image_paths: List of paths to image files
            output_path: Output PDF file path
            page_size: Page size ('auto', 'a4' or 'letter'). 'auto' = match image size
            quality: JPEG quality for compression (1-100)

        Returns:
            Path to created PDF
        """
        if page_size.lower() == "auto":
            return self._create_pdf_auto_size(image_paths, output_path, quality)
        else:
            return self._create_pdf_fixed_size(
                image_paths, output_path, page_size, quality
            )

    def _create_pdf_auto_size(
        self,
        image_paths: List[str],
        output_path: str,
        quality: int = 90,
    ) -> str:
        """
        Create PDF where each page size matches its image exactly (no margins).
        """
        # For auto-size, we need to create each page with different dimensions
        # ReportLab canvas doesn't support changing page size, so we create temp PDFs and merge

        temp_pdfs = []

        for img_path in image_paths:
            if not os.path.exists(img_path):
                continue

            with Image.open(img_path) as img:
                img_width, img_height = img.size

                # Page size = image size in points (72 points = 1 inch)
                # Assume 150 DPI for scanned documents
                dpi = 150
                page_width = img_width * 72 / dpi
                page_height = img_height * 72 / dpi

                # Create temp PDF for this page - use delete=False and close immediately
                temp_fd, temp_pdf_path = tempfile.mkstemp(suffix=".pdf")
                os.close(temp_fd)  # Close the file descriptor immediately
                temp_pdfs.append(temp_pdf_path)

                c = canvas.Canvas(temp_pdf_path, pagesize=(page_width, page_height))

                # Optimize image
                optimized_path = self._optimize_image_for_pdf(img_path, quality)

                # Draw image to fill entire page (no margins)
                c.drawImage(
                    optimized_path,
                    0,  # x = 0
                    0,  # y = 0
                    width=page_width,
                    height=page_height,
                    preserveAspectRatio=True,
                )

                # Clean up temp image file
                if optimized_path != img_path:
                    os.remove(optimized_path)

                c.showPage()
                c.save()

        # Merge all temp PDFs into final output
        if len(temp_pdfs) == 1:
            # Just copy single PDF (shutil.copy is safer than move on Windows)
            import shutil

            shutil.copy2(temp_pdfs[0], output_path)
            os.remove(temp_pdfs[0])
        elif len(temp_pdfs) > 1:
            self.merge_pdfs(temp_pdfs, output_path)
            # Clean up temp PDFs
            for temp_pdf in temp_pdfs:
                if os.path.exists(temp_pdf):
                    os.remove(temp_pdf)

        return output_path

    def _create_pdf_fixed_size(
        self,
        image_paths: List[str],
        output_path: str,
        page_size: str = "a4",
        quality: int = 90,
    ) -> str:
        """
        Create PDF with fixed page size (original behavior).
        """
        page_dims = self.PAGE_SIZES.get(page_size.lower(), self.default_page_size)

        c = canvas.Canvas(output_path, pagesize=page_dims)
        page_width, page_height = page_dims

        usable_width = page_width - (2 * self.margin)
        usable_height = page_height - (2 * self.margin)

        for img_path in image_paths:
            if not os.path.exists(img_path):
                continue

            # Open image and get dimensions
            with Image.open(img_path) as img:
                img_width, img_height = img.size

                # Calculate scaling to fit page
                width_ratio = usable_width / img_width
                height_ratio = usable_height / img_height
                scale = min(width_ratio, height_ratio)

                scaled_width = img_width * scale
                scaled_height = img_height * scale

                # Center image on page
                x = self.margin + (usable_width - scaled_width) / 2
                y = self.margin + (usable_height - scaled_height) / 2

                # Optimize image for PDF
                optimized_path = self._optimize_image_for_pdf(img_path, quality)

                # Draw image
                c.drawImage(
                    optimized_path,
                    x,
                    y,
                    width=scaled_width,
                    height=scaled_height,
                    preserveAspectRatio=True,
                )

                # Clean up temp file
                if optimized_path != img_path:
                    os.remove(optimized_path)

            c.showPage()

        c.save()
        return output_path

    def _optimize_image_for_pdf(self, image_path: str, quality: int) -> str:
        """
        Optimize image for PDF embedding.
        """
        with Image.open(image_path) as img:
            # Convert to RGB if necessary
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            # Create temporary file - use mkstemp to avoid Windows file locking issues
            temp_fd, temp_path = tempfile.mkstemp(suffix=".jpg")
            os.close(temp_fd)  # Close the file descriptor immediately
            img.save(temp_path, "JPEG", quality=quality, optimize=True)

            return temp_path

    def merge_pdfs(self, pdf_paths: List[str], output_path: str) -> str:
        """
        Merge multiple PDFs into one.
        """
        merger = PdfMerger()

        for pdf_path in pdf_paths:
            if os.path.exists(pdf_path):
                merger.append(pdf_path)

        merger.write(output_path)
        merger.close()

        return output_path

    def image_to_pdf_bytes(
        self, image_data: bytes, page_size: str = "a4", quality: int = 90
    ) -> bytes:
        """
        Convert image bytes to PDF bytes.
        """
        page_dims = self.PAGE_SIZES.get(page_size.lower(), self.default_page_size)

        # Create PDF in memory
        pdf_buffer = io.BytesIO()
        c = canvas.Canvas(pdf_buffer, pagesize=page_dims)
        page_width, page_height = page_dims

        usable_width = page_width - (2 * self.margin)
        usable_height = page_height - (2 * self.margin)

        # Load image from bytes
        img_buffer = io.BytesIO(image_data)
        with Image.open(img_buffer) as img:
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            img_width, img_height = img.size

            # Calculate scaling
            width_ratio = usable_width / img_width
            height_ratio = usable_height / img_height
            scale = min(width_ratio, height_ratio)

            scaled_width = img_width * scale
            scaled_height = img_height * scale

            x = self.margin + (usable_width - scaled_width) / 2
            y = self.margin + (usable_height - scaled_height) / 2

            # Save optimized image to temp file for reportlab
            # Use mkstemp to avoid Windows file locking issues
            temp_fd, temp_img_path = tempfile.mkstemp(suffix=".jpg")
            os.close(temp_fd)  # Close the file descriptor immediately
            img.save(temp_img_path, "JPEG", quality=quality, optimize=True)

            c.drawImage(
                temp_img_path,
                x,
                y,
                width=scaled_width,
                height=scaled_height,
                preserveAspectRatio=True,
            )

            os.remove(temp_img_path)

        c.showPage()
        c.save()

        pdf_buffer.seek(0)
        return pdf_buffer.getvalue()

    def get_pdf_info(self, pdf_path: str) -> dict:
        """
        Get information about a PDF file.
        """
        from PyPDF2 import PdfReader

        reader = PdfReader(pdf_path)

        return {
            "pages": len(reader.pages),
            "metadata": reader.metadata,
        }

    def create_searchable_pdf_from_images(
        self,
        image_paths: List[str],
        output_path: str,
        ocr_data: List[List[Dict]],
        page_size: str = "auto",
        quality: int = 90,
    ) -> str:
        """
        Create a searchable PDF with invisible text layer from images and OCR data.

        Args:
            image_paths: List of paths to image files
            output_path: Output PDF file path
            ocr_data: List of OCR word data for each image (from extract_text_with_boxes)
            page_size: Page size ('auto', 'a4' or 'letter')
            quality: JPEG quality for compression (1-100)

        Returns:
            Path to created PDF
        """
        if page_size.lower() == "auto":
            return self._create_searchable_pdf_auto_size(
                image_paths, output_path, ocr_data, quality
            )
        else:
            return self._create_searchable_pdf_fixed_size(
                image_paths, output_path, ocr_data, page_size, quality
            )

    def _create_searchable_pdf_auto_size(
        self,
        image_paths: List[str],
        output_path: str,
        ocr_data: List[List[Dict]],
        quality: int = 90,
    ) -> str:
        """
        Create searchable PDF where each page size matches its image exactly.
        """
        temp_pdfs = []

        for idx, img_path in enumerate(image_paths):
            if not os.path.exists(img_path):
                continue

            with Image.open(img_path) as img:
                img_width, img_height = img.size

                # Page size = image size in points (72 points = 1 inch)
                dpi = 150
                page_width = img_width * 72 / dpi
                page_height = img_height * 72 / dpi

                # Create temp PDF for this page
                temp_fd, temp_pdf_path = tempfile.mkstemp(suffix=".pdf")
                os.close(temp_fd)
                temp_pdfs.append(temp_pdf_path)

                c = canvas.Canvas(temp_pdf_path, pagesize=(page_width, page_height))

                # Optimize image
                optimized_path = self._optimize_image_for_pdf(img_path, quality)

                # Draw image to fill entire page
                c.drawImage(
                    optimized_path,
                    0,
                    0,
                    width=page_width,
                    height=page_height,
                    preserveAspectRatio=True,
                )

                # Add invisible text layer if OCR data available
                if idx < len(ocr_data) and ocr_data[idx]:
                    self._add_text_layer(
                        c, ocr_data[idx], img_width, img_height, page_width, page_height
                    )

                # Clean up temp image file
                if optimized_path != img_path:
                    os.remove(optimized_path)

                c.showPage()
                c.save()

        # Merge all temp PDFs into final output
        if len(temp_pdfs) == 1:
            import shutil

            shutil.copy2(temp_pdfs[0], output_path)
            os.remove(temp_pdfs[0])
        elif len(temp_pdfs) > 1:
            self.merge_pdfs(temp_pdfs, output_path)
            for temp_pdf in temp_pdfs:
                if os.path.exists(temp_pdf):
                    os.remove(temp_pdf)

        return output_path

    def _create_searchable_pdf_fixed_size(
        self,
        image_paths: List[str],
        output_path: str,
        ocr_data: List[List[Dict]],
        page_size: str = "a4",
        quality: int = 90,
    ) -> str:
        """
        Create searchable PDF with fixed page size.
        """
        page_dims = self.PAGE_SIZES.get(page_size.lower(), self.default_page_size)

        c = canvas.Canvas(output_path, pagesize=page_dims)
        page_width, page_height = page_dims

        usable_width = page_width - (2 * self.margin)
        usable_height = page_height - (2 * self.margin)

        for idx, img_path in enumerate(image_paths):
            if not os.path.exists(img_path):
                continue

            with Image.open(img_path) as img:
                img_width, img_height = img.size

                # Calculate scaling to fit page
                width_ratio = usable_width / img_width
                height_ratio = usable_height / img_height
                scale = min(width_ratio, height_ratio)

                scaled_width = img_width * scale
                scaled_height = img_height * scale

                # Center image on page
                x = self.margin + (usable_width - scaled_width) / 2
                y = self.margin + (usable_height - scaled_height) / 2

                # Optimize image for PDF
                optimized_path = self._optimize_image_for_pdf(img_path, quality)

                # Draw image
                c.drawImage(
                    optimized_path,
                    x,
                    y,
                    width=scaled_width,
                    height=scaled_height,
                    preserveAspectRatio=True,
                )

                # Add invisible text layer if OCR data available
                if idx < len(ocr_data) and ocr_data[idx]:
                    self._add_text_layer(
                        c,
                        ocr_data[idx],
                        img_width,
                        img_height,
                        scaled_width,
                        scaled_height,
                        x_offset=x,
                        y_offset=y,
                    )

                # Clean up temp file
                if optimized_path != img_path:
                    os.remove(optimized_path)

            c.showPage()

        c.save()
        return output_path

    def _add_text_layer(
        self,
        c: canvas.Canvas,
        words: List[Dict],
        img_width: float,
        img_height: float,
        page_width: float,
        page_height: float,
        x_offset: float = 0,
        y_offset: float = 0,
    ):
        """
        Add invisible text layer to PDF page for searchability.

        Args:
            c: ReportLab canvas
            words: List of word dicts with text, x, y, width, height
            img_width: Original image width in pixels
            img_height: Original image height in pixels
            page_width: PDF page width in points (for the image area)
            page_height: PDF page height in points (for the image area)
            x_offset: X offset for centered images
            y_offset: Y offset for centered images
        """
        # Calculate scale factors from image to PDF coordinates
        scale_x = page_width / img_width
        scale_y = page_height / img_height

        # Set text to invisible using PDF text render mode 3 (invisible)
        # This is done via the textobject which supports render mode
        text_obj = c.beginText()
        text_obj.setTextRenderMode(3)  # Mode 3 = invisible

        for word in words:
            text = word["text"]
            if not text:
                continue

            # Convert image coordinates to PDF coordinates
            # PDF origin is bottom-left, image origin is top-left
            pdf_x = x_offset + word["x"] * scale_x
            pdf_y = y_offset + page_height - (word["y"] + word["height"]) * scale_y

            # Estimate font size based on word height
            font_size = max(1, word["height"] * scale_y * 0.8)

            try:
                text_obj.setTextOrigin(pdf_x, pdf_y)
                text_obj.setFont("Helvetica", font_size)
                text_obj.textOut(text + " ")
            except Exception:
                # Skip words that can't be rendered (e.g., encoding issues)
                pass

        c.drawText(text_obj)


# Singleton instance
pdf_service = PDFService()
