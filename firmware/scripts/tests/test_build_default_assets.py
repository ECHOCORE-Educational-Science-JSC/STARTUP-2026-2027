import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "build_default_assets", ROOT / "scripts" / "build_default_assets.py"
)
BUILD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD)


class BuildDefaultAssetsTest(unittest.TestCase):
    def test_wisio_assets_include_explicit_pronunciations_and_keep_other_commands(self):
        config = {'wake_word': 'HEY WISIO', 'display': 'Hey Wisio'}
        commands = BUILD.custom_wake_commands(config, ['mn5q8_en'])
        self.assertEqual(commands, BUILD.custom_wake_commands(config, ['mn7_en']))
        self.assertEqual([c['phonemes'] for c in commands],
                         ['hd WmZmb', 'hd WgZmb', 'hd WgSmb', 'hd WmSmb', 'hd VmZmb', 'hd VmSmb',
                          'hd WmSYb', 'hf WmSmb', 'hf WmZmb', 'hd WmSme'])
        self.assertEqual(len({c['command'] for c in commands}), 10)
        for command in commands:
            self.assertEqual(command['text'], 'Hey Wisio')
            self.assertEqual(command['action'], 'wake')
        with tempfile.TemporaryDirectory() as directory:
            BUILD.generate_index_json(directory, 'srmodels.bin', None, None,
                                      multinet_model_info={'commands': commands})
            packed = json.loads((Path(directory) / 'index.json').read_text())
            self.assertEqual(packed['multinet_model']['commands'], commands)
        self.assertEqual(BUILD.custom_wake_commands(config, ['mn6_en']),
                         [{'command': 'HEY WISIO', 'text': 'Hey Wisio', 'action': 'wake'}])
        config['wake_word'] = 'TURN ON THE LIGHT'
        self.assertEqual(len(BUILD.custom_wake_commands(config, ['mn7_en'])), 1)
        self.assertNotIn('phonemes', BUILD.custom_wake_commands(config, ['mn7_en'])[0])

    def test_text_font_metadata_uses_bundle_charset_size_and_bpp(self):
        with tempfile.TemporaryDirectory() as directory:
            assets = Path(directory)
            BUILD.generate_index_json(
                str(assets),
                None,
                "font_noto_sans_common_20_4.bin",
                None,
                font_bundle_id="noto-v1",
            )
            index = json.loads((assets / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(
                index["text_font_meta"],
                {"charset": "common", "size": 20, "bpp": 4, "bundle": "noto-v1"},
            )

    def test_text_font_requires_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                BUILD.generate_index_json(
                    directory, None, "font_noto_sans_common_20_4.bin", None
                )


if __name__ == "__main__":
    unittest.main()
