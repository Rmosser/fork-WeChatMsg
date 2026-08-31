import types
import unittest
from pathlib import Path


class MainSpecTests(unittest.TestCase):
    def test_spec_executes_in_pyinstaller_style_namespace(self):
        root = Path(__file__).resolve().parents[1]
        spec_path = root / "main.spec"
        analysis = types.SimpleNamespace(
            pure=[],
            zipped_data=[],
            scripts=[],
            binaries=[],
            zipfiles=[],
            datas=[],
        )

        captured = {}

        def analysis_factory(*args, **kwargs):
            captured.update(kwargs)
            return analysis

        namespace = {
            "SPECPATH": str(root),
            "Analysis": analysis_factory,
            "PYZ": lambda *args, **kwargs: object(),
            "EXE": lambda *args, **kwargs: object(),
            "COLLECT": lambda *args, **kwargs: object(),
        }
        exec(compile(spec_path.read_text(encoding="utf-8"), str(spec_path), "exec"), namespace)
        self.assertEqual(namespace["ROOT"], root)
        destinations = {destination for _, destination in captured["datas"]}
        self.assertIn("pyecharts/datasets", destinations)
        self.assertIn("pyecharts/render/templates", destinations)

    def test_spec_inputs_are_tracked(self):
        root = Path(__file__).resolve().parents[1]
        for relative in (
            "main.py",
            "app/data",
            "app/ImageBox",
            "app/resources",
            "resource/datasets",
            "resource/render/templates",
            "app/data/icon.png",
        ):
            self.assertTrue((root / relative).exists(), relative)


if __name__ == "__main__":
    unittest.main()
