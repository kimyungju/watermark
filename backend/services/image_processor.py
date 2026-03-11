import os

import cv2
import numpy as np

# LaMa model loaded lazily
_lama_session = None


def _get_lama_session():
    global _lama_session
    if _lama_session is None:
        import onnxruntime as ort

        model_path = os.environ.get(
            "LAMA_MODEL_PATH",
            os.path.join(os.path.dirname(__file__), "..", "models", "lama.onnx"),
        )
        if os.path.exists(model_path):
            _lama_session = ort.InferenceSession(
                model_path, providers=["CPUExecutionProvider"]
            )
    return _lama_session


class ImageProcessor:
    def detect_watermark(self, img: np.ndarray) -> np.ndarray | None:
        """Detect watermark regions. Returns a binary mask or None if no watermark found."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape

        # Method 1: Detect semi-transparent overlaid text/logos
        # Look for high-frequency low-contrast patterns
        blurred = cv2.GaussianBlur(gray, (21, 21), 0)
        diff = cv2.absdiff(gray, blurred)

        # Threshold to find subtle watermark patterns
        _, thresh = cv2.threshold(diff, 8, 255, cv2.THRESH_BINARY)

        # Method 2: Edge detection for sharper watermarks
        edges = cv2.Canny(gray, 30, 100)
        dilated_edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)

        # Combine both methods
        combined = cv2.bitwise_or(thresh, dilated_edges)

        # Morphological operations to clean up the mask
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        mask = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel, iterations=3)
        mask = cv2.dilate(mask, kernel, iterations=2)

        # Check if enough watermark pixels detected (at least 0.5% of image)
        watermark_ratio = np.count_nonzero(mask) / (h * w)
        if watermark_ratio < 0.005:
            return None

        return mask

    def inpaint(self, img: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """Remove watermark using inpainting."""
        session = _get_lama_session()

        if session is not None:
            return self._lama_inpaint(session, img, mask)

        # Fallback to OpenCV inpainting if LaMa model not available
        return cv2.inpaint(img, mask, inpaintRadius=5, flags=cv2.INPAINT_TELEA)

    def _lama_inpaint(self, session, img: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """Run LaMa ONNX model for inpainting."""
        h, w = img.shape[:2]

        # Resize to model input size (typically 512x512)
        img_resized = cv2.resize(img, (512, 512))
        mask_resized = cv2.resize(mask, (512, 512))

        # Normalize
        img_input = img_resized.astype(np.float32) / 255.0
        img_input = np.transpose(img_input, (2, 0, 1))  # HWC -> CHW
        img_input = np.expand_dims(img_input, 0)  # Add batch dim

        mask_input = (mask_resized > 127).astype(np.float32)
        mask_input = np.expand_dims(np.expand_dims(mask_input, 0), 0)  # 1x1xHxW

        outputs = session.run(None, {"image": img_input, "mask": mask_input})
        result = outputs[0][0]  # Remove batch dim

        # Convert back: CHW -> HWC, denormalize
        result = np.transpose(result, (1, 2, 0))
        result = np.clip(result * 255, 0, 255).astype(np.uint8)

        # Resize back to original dimensions
        return cv2.resize(result, (w, h))

    def process(self, input_path: str, output_dir: str) -> dict:
        """Process a single image. Returns dict with output_path and watermark_detected."""
        img = cv2.imread(input_path)
        if img is None:
            raise ValueError(f"Cannot read image: {input_path}")

        ext = os.path.splitext(input_path)[1].lower()
        output_path = os.path.join(output_dir, f"output{ext}")

        mask = self.detect_watermark(img)
        if mask is None:
            # No watermark detected — copy original
            cv2.imwrite(output_path, img)
            return {"output_path": output_path, "watermark_detected": False}

        result = self.inpaint(img, mask)
        cv2.imwrite(output_path, result)
        return {"output_path": output_path, "watermark_detected": True}
