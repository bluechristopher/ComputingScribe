import unittest
import io
import tempfile
from pathlib import Path
from PIL import Image

from src.agent.image_generator import ExamImageGenerator, ImageGenerationResult
from src.agent.session_manager import SessionManager, ExamSession
from src.agent.orchestrator import EduScribeOrchestrator

class TestExamImageGenerator(unittest.TestCase):
    def setUp(self):
        self.generator = ExamImageGenerator(model_name="gemini-3.1-flash-image")

    def test_image_generation_result_structure(self):
        res = ImageGenerationResult(
            image_bytes=b"dummy_bytes",
            mime_type="image/png",
            prompt="Draw a binary search tree",
            commentary="Generated diagram",
            iteration_count=1,
            model_used="gemini-3.1-flash-image",
            success=True
        )
        self.assertTrue(res.success)
        self.assertEqual(res.model_used, "gemini-3.1-flash-image")
        self.assertEqual(res.iteration_count, 1)
        self.assertEqual(res.mime_type, "image/png")

    def test_diagram_generation_fallback(self):
        res = self.generator.generate_image(
            prompt="Draw a binary search tree with root 50 and children 25, 75",
            aspect_ratio="1:1",
            style_preset="data_structure"
        )
        self.assertTrue(res.success)
        self.assertIsNotNone(res.image_bytes)
        self.assertGreater(len(res.image_bytes), 100)
        
        # Verify valid PNG image using Pillow
        img = Image.open(io.BytesIO(res.image_bytes))
        self.assertEqual(img.format, "PNG")
        self.assertGreaterEqual(img.width, 100)
        self.assertGreaterEqual(img.height, 100)

    def test_conversational_image_refinement(self):
        # Step 1: Initial diagram
        res1 = self.generator.generate_image(
            prompt="Circular queue with elements Val_0, Val_1, Val_2, Val_3",
            style_preset="data_structure"
        )
        self.assertTrue(res1.success)
        self.assertEqual(res1.iteration_count, 1)

        # Step 2: Refine diagram iteratively
        res2 = self.generator.refine_image(
            instruction="Add a new element Val_4 and update REAR pointer to index 4",
            previous_image_bytes=res1.image_bytes,
            previous_prompt=res1.prompt,
            iteration_count=2
        )
        self.assertTrue(res2.success)
        self.assertEqual(res2.iteration_count, 2)
        self.assertIn("Val_4", res2.prompt)

        # Verify image remains valid PNG
        img = Image.open(io.BytesIO(res2.image_bytes))
        self.assertEqual(img.format, "PNG")

    def test_generic_scenario_style(self):
        res = self.generator.generate_image(
            prompt="A realistic photo of an automated transit gate with smart card reader",
            style_preset="generic"
        )
        self.assertTrue(res.success)
        self.assertIsNotNone(res.image_bytes)
        img = Image.open(io.BytesIO(res.image_bytes))
        self.assertEqual(img.format, "PNG")

    def test_session_manager_save_image_asset(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sm = SessionManager()
            dummy_session = ExamSession(
                session_id="test_img_session_001",
                title="Image Test Session",
                paper_type="practical",
                syllabus_code="9569",
                paper_number="02",
                latex_source=r"\documentclass{article}\begin{document}\end{document}",
                mark_scheme_source=""
            )
            # Create a simple test PNG
            test_img = Image.new("RGB", (200, 200), color="#ffffff")
            buf = io.BytesIO()
            test_img.save(buf, format="PNG")
            img_bytes = buf.getvalue()

            asset = sm.save_image_asset(dummy_session, "test_diagram.png", img_bytes, "image/png")
            self.assertIn("path", asset)
            self.assertTrue(asset["path"].startswith("assets/"))
            self.assertEqual(asset["original_name"], "test_diagram.png")
            self.assertEqual(len(dummy_session.image_assets), 1)

if __name__ == "__main__":
    unittest.main()
