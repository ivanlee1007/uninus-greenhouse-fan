"""Offline regression coverage for HACS download metadata.

Requirements mirror HACS repositories/base.py get_hacs_json and
utils/validate.py INTEGRATION_MANIFEST_JSON_SCHEMA. No HA mocks required.
"""
import json
from pathlib import Path
import unittest
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


class HacsPackagingTest(unittest.TestCase):
    def test_manifest_and_frontend_version_contract(self):
        metadata = json.loads((ROOT / 'custom_components/uninus_greenhouse_fan/manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(metadata['version'], '0.5.6')
        frontend = (ROOT / 'custom_components/uninus_greenhouse_fan/frontend.py').read_text(encoding='utf-8')
        self.assertIn('CARD_VERSION = "0.5.6"', frontend)
        shipped = (ROOT / 'custom_components/uninus_greenhouse_fan/card.js').read_bytes()
        self.assertEqual(shipped, (ROOT / 'www/uninus-greenhouse-fan-card.js').read_bytes())
        self.assertIn(b'UNiNUS Greenhouse Fan 0.5.6', shipped)
        self.assertIn('card.js?v=0.5.6', (ROOT / 'README.md').read_text(encoding='utf-8'))

    def test_download_ref_has_valid_root_hacs_manifest(self):
        path = ROOT / "hacs.json"
        self.assertTrue(path.is_file(), "HACS refuses explicit download refs without root hacs.json")
        metadata = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(metadata["name"], "UNiNUS Greenhouse Fan")
        self.assertIs(metadata.get("content_in_root", False), False)
        self.assertIs(metadata.get("zip_release", False), False)
        self.assertNotIn("filename", metadata)
        self.assertTrue((ROOT / "custom_components/uninus_greenhouse_fan/manifest.json").is_file())

    def test_integration_manifest_has_hacs_required_fields(self):
        metadata = json.loads((ROOT / "custom_components/uninus_greenhouse_fan/manifest.json").read_text(encoding="utf-8"))
        required = {"codeowners", "documentation", "domain", "issue_tracker", "name", "version"}
        self.assertFalse(required - metadata.keys(), f"Missing HACS fields: {sorted(required - metadata.keys())}")
        self.assertEqual(metadata["codeowners"], ["@ivanlee1007"])
        for key in ("documentation", "issue_tracker"):
            url = urlparse(metadata[key])
            self.assertEqual(url.scheme, "https")
            self.assertEqual(url.netloc, "github.com")
        self.assertEqual(metadata["domain"], "uninus_greenhouse_fan")


if __name__ == "__main__":
    unittest.main()
