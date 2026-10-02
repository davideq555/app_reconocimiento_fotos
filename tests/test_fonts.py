import os
import subprocess
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import font
from unittest.mock import patch

from photo_recognition import fonts


class ParseFontDescriptionTests(unittest.TestCase):
    def test_family_and_size(self):
        self.assertEqual(fonts._parse_font_description("'Cantarell 11'"), ('Cantarell', 11))

    def test_family_only(self):
        self.assertEqual(fonts._parse_font_description('Noto Sans'), ('Noto Sans', None))

    def test_decimal_size(self):
        self.assertEqual(fonts._parse_font_description('Ubuntu Sans 10.5'), ('Ubuntu Sans', 10))

    def test_empty(self):
        self.assertEqual(fonts._parse_font_description(''), ('', None))


class MatchFamilyTests(unittest.TestCase):
    families = ('fixed', 'jetbrainsmono nf', 'Noto Sans')

    def test_exact(self):
        self.assertEqual(fonts._match_family('Noto Sans', self.families), 'Noto Sans')

    def test_normalizes_spaced_nerd_font(self):
        self.assertEqual(fonts._match_family('JetBrains Mono', self.families), 'jetbrainsmono nf')

    def test_empty_candidate_matches_nothing(self):
        self.assertIsNone(fonts._match_family('', self.families))
        self.assertIsNone(fonts._match_family(None, self.families))

    def test_missing(self):
        self.assertIsNone(fonts._match_family('Comic Sans MS', self.families))


class DetectionSourceTests(unittest.TestCase):
    def test_gsettings_missing_binary(self):
        with patch.object(fonts.subprocess, 'run', side_effect=FileNotFoundError):
            self.assertEqual(fonts._gsettings_font('font-name'), (None, None))

    def test_gsettings_error_status(self):
        failed = subprocess.CompletedProcess((), 1, stdout='', stderr='')
        with patch.object(fonts.subprocess, 'run', return_value=failed):
            self.assertEqual(fonts._gsettings_font('font-name'), (None, None))

    def test_gsettings_output(self):
        ok = subprocess.CompletedProcess((), 0, stdout="'Cantarell 11'\n", stderr='')
        with patch.object(fonts.subprocess, 'run', return_value=ok):
            self.assertEqual(fonts._gsettings_font('font-name'), ('Cantarell', 11))

    def test_kde_font(self):
        with tempfile.TemporaryDirectory() as home:
            config_dir = Path(home) / '.config'
            config_dir.mkdir()
            (config_dir / 'kdeglobals').write_text('[General]\nfont=Fira Sans,10,-1,5,50,0,0,0,0,0\n')
            with patch.dict(os.environ, {'HOME': home}):
                self.assertEqual(fonts._kde_ui_font(), ('Fira Sans', 10))

    def test_kde_missing_file(self):
        with tempfile.TemporaryDirectory() as home:
            with patch.dict(os.environ, {'HOME': home}):
                self.assertEqual(fonts._kde_ui_font(), (None, None))


class SystemFontTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
            cls.root.withdraw()
        except tk.TclError as error:
            raise unittest.SkipTest(f'Display unavailable: {error}')

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def test_detected_ui_family_is_renderable(self):
        ui_family, mono_family, _ = fonts.detect_system_fonts()
        families = font.families()
        self.assertIn(ui_family, families)
        self.assertIn(mono_family, families)

    def test_never_selects_bitmap_fixed_when_scalable_exists(self):
        ui_family, _, _ = fonts.detect_system_fonts()
        if any(family != 'fixed' for family in font.families()):
            self.assertNotEqual(ui_family, 'fixed')

    def test_apply_configures_named_fonts(self):
        ui_family, mono_family, _ = fonts.apply_system_fonts()
        self.assertEqual(font.nametofont('TkDefaultFont').actual('family'), ui_family)
        self.assertEqual(font.nametofont('TkFixedFont').actual('family'), mono_family)


if __name__ == '__main__':
    unittest.main()
