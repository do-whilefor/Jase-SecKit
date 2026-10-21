"""Offline checks for README navigation and the bundled hero asset."""

from html.parser import HTMLParser
from pathlib import Path
import re
import unittest
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]


class ReadmeHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.stack = []
        self.errors = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.links.extend(attrs[key] for key in ("src", "href") if key in attrs)
        if tag in {"p", "details", "summary"}:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in {"p", "details", "summary"}:
            if not self.stack or self.stack.pop() != tag:
                self.errors.append(tag)


def heading_ids(text):
    headings = re.findall(r"^#{1,6}\s+(.+)$", text, re.M)
    return {re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-") for heading in headings}


class ReadmeTests(unittest.TestCase):
    def setUp(self):
        self.text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.html = ReadmeHTML()
        self.html.feed(self.text)

    def test_local_links_images_and_fragments_resolve(self):
        links = self.html.links + re.findall(r"\]\(([^)]+)\)", self.text)
        for link in links:
            parsed = urlsplit(link)
            if parsed.scheme or parsed.netloc:
                continue
            with self.subTest(link=link):
                target = ROOT / unquote(parsed.path) if parsed.path else ROOT / "README.md"
                self.assertTrue(target.exists(), f"Missing README target: {link}")
                if parsed.fragment and target.suffix == ".md":
                    self.assertIn(unquote(parsed.fragment), heading_ids(target.read_text(encoding="utf-8")))

    def test_html_sections_are_balanced(self):
        self.assertFalse(self.html.errors)
        self.assertFalse(self.html.stack)

    def test_hero_is_accessible_and_self_contained(self):
        hero = ET.parse(ROOT / "assets/readme-hero.svg").getroot()
        ns = {"svg": "http://www.w3.org/2000/svg"}
        self.assertTrue(hero.find("svg:title", ns).text)
        self.assertTrue(hero.find("svg:desc", ns).text)
        for element in hero.iter():
            self.assertNotIn(element.tag.rsplit("}", 1)[-1], {"script", "foreignObject", "image"})
            for key, value in element.attrib.items():
                if key.rsplit("}", 1)[-1] == "href":
                    self.assertTrue(value.startswith("#"), "Hero must not load remote resources")


if __name__ == "__main__":
    unittest.main()
