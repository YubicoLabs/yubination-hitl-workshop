"""Small, dependency-free participant source contract."""
import json
import re
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = "https://github.com/YubicoLabs/yubination-hitl-workshop"
GUIDES = ("DEVELOPER-QUICKSTART.md", "WINDOWS-SOURCE-REHEARSAL.md")


class ParticipantAlignment(unittest.TestCase):
    def test_api_key_first(self):
        dialog = (ROOT / "frontend/src/components/mcp-setup-dialog.ts").read_text()
        self.assertLess(dialog.index("Connect with an API key"),
                        dialog.index("Preloop native onboarding (optional)"))
        self.assertNotIn("Native onboarding (preferred)", dialog)

    def test_local_metadata(self):
        compose = json.loads((ROOT / "compose.json").read_text())
        self.assertEqual(compose["services"]["console"]["build"]["args"]["WORKSHOP_ORIGIN"],
                         "http://localhost:${WORKSHOP_PORT:-8080}")
        docker = (ROOT / "frontend/Dockerfile").read_text()
        self.assertLess(docker.index("ARG WORKSHOP_ORIGIN"), docker.index("RUN npm run build"))
        self.assertIn("ENV WORKSHOP_ORIGIN=${WORKSHOP_ORIGIN}", docker)
        png = (ROOT / "frontend/public/images/yubination-workshop-share.png").read_bytes()
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">II", png[16:24]), (1200, 630))
        seo = (ROOT / "frontend/src/brand-seo.ts").read_text()
        self.assertIn("if (config.workshop)", seo)
        self.assertIn("validate_workshop_origin", seo)
        self.assertIn("return `https://${config.domain}`", seo)

    def test_source_distribution(self):
        config = json.loads((ROOT / "frontend/public/workshop/source.json").read_text())
        self.assertEqual(config, {"source_repository_url": REPO})
        ui = (ROOT / "frontend/src/views/authed/workshop-lab-view.ts").read_text()
        self.assertIn("This local distribution includes source only.", ui)
        self.assertNotIn("Windows testing is pending", ui)
        self.assertNotIn("Windows installation and hardware testing are pending", ui)
        for guide in GUIDES:
            self.assertIn("integrations/previewsign/docs/" + guide, ui)
            self.assertTrue((ROOT / "integrations/previewsign/docs" / guide).is_file())
        self.assertIn("this.participantArtifact", ui)
        self.assertIn("this.windowsArtifact", ui)
        for path in re.findall(r"integrations/previewsign/docs/[A-Z-]+\.md", ui):
            self.assertTrue((ROOT / path).is_file(), path)

    def test_mac_package_instructions_require_artifact(self):
        ui = (ROOT / "frontend/src/views/authed/workshop-lab-view.ts").read_text()
        mac = ui.split('name="mac"', 1)[1].split('</sl-tab-panel>', 1)[0]
        guarded = re.search(
            r"\$\{this\.participantArtifact\s*\? html`\s*<p>\s*"
            r"Only use the commands below(?P<commands>.*?)`\s*: ''\}",
            mac, re.S,
        )
        self.assertIsNotNone(guarded, "Mac package instructions must require an artifact")
        commands = guarded.group("commands")
        for command in ("shasum -a 256", "tar -xzf", "install.py install",
                        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"):
            self.assertIn(command, commands)
        for start, end in (('<div data-platform-folder>', '</div>'),
                           ('<h2>7. Cleanup</h2>', 'data-platform-cleanup="windows"')):
            section = ui.split(start, 1)[1].split(end, 1)[0]
            self.assertRegex(section, r"this\.previewSignPlatform === 'mac'\s*&&\s*this\.participantArtifact")
            self.assertIn("this.previewSignPlatform === 'source' ||", section)
            self.assertIn("this.previewSignPlatform === 'mac'", section)

    def test_local_doc_link_closure(self):
        docs = [ROOT / "README.md", ROOT / "integrations/previewsign/README.md"]
        docs += [ROOT / "integrations/previewsign/docs" / name for name in GUIDES]
        for doc in docs:
            with self.subTest(doc=doc):
                text = doc.read_text()
                for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
                    if re.match(r"[a-z]+:", link) or link.startswith("#"):
                        continue
                    self.assertTrue((doc.parent / link.split("#")[0]).is_file(), link)
                for script in re.findall(r"integrations/previewsign/scripts/[\w.-]+\.py", text):
                    self.assertTrue((ROOT / script).is_file(), script)
        for name in GUIDES:
            text = (ROOT / "integrations/previewsign/docs" / name).read_text()
            self.assertIn(REPO + ".git", text)
            self.assertNotIn("not yet participant-rehearsed", text)


if __name__ == "__main__":
    unittest.main()
