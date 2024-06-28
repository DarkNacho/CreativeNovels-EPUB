import html
import requests
import re
from bs4 import BeautifulSoup
from urllib.parse import unquote
from ebooklib import epub
from collections import defaultdict


class Novel:
    def __init__(self, url: str):

        self.get_novel(url)

    def get_novel(self, novel_url):
        response = requests.get(novel_url)
        soup = BeautifulSoup(response.text, "html.parser")
        id_node = soup.find("div", id="chapter_list_novel_page")
        self.novel_id = id_node["class"][0]

        # Extract book cover image URL
        image_element = soup.find("img", class_="book_cover")
        self.cover_image_url = (
            image_element["src"] if image_element else "Image not found"
        )

        # Extract title
        title_element = soup.find("title")
        self.title = (
            title_element.text.split("-")[0] if title_element else "Title not found"
        )

    def get_chapters(self):
        response = requests.post(
            "https://creativenovels.com/wp-admin/admin-ajax.php",
            data={"action": "crn_chapter_list", "view_id": self.novel_id},
        )

        # Parse Chapter List
        chapter_matches = re.findall(
            r"(https.*?)\.data\.(.*?)\.data\.(.*?)\.data\.(available|locked)\.end_data\.",
            response.text,
        )
        for chapter_match in chapter_matches:
            chapter_title = unquote(chapter_match[1])
            yield Chapter(chapter_match[0], chapter_title)


class Chapter:
    def __init__(self, link, title):
        self.link = link
        self.title = title
        self.slug = ""
        self.content = ""

    def fill_content_and_parse(self):
        response = requests.get(self.link)
        links = response.headers.get("Link")
        l = re.search(r"<(.*?)>", links.split(",")[1]).group(1)

        # ask for real content to api..
        response = requests.get(l)
        chapter_json = response.json()
        self.title = html.unescape(chapter_json["title"]["rendered"]).strip()
        self.slug = chapter_json["slug"]
        self.content = chapter_json["content"]["rendered"]

        # Parse HTML content to text
        soup = BeautifulSoup(self.content, "html.parser")
        self.content = soup.get_text()

        return self.content


# Prompt for Novel URL
novel_url = input("Enter the URL of the novel from CreativeNovels: ")

# Validate URL
if "creativenovels.com" not in novel_url:
    print("The URL must be from creativenovels.com")
    exit()

novel = Novel(novel_url)

if not novel.title:
    print("Could not retrieve the novel's title. Please check the URL and try again.")
    exit()

print(novel.title)

# Create a new EPUB book
book = epub.EpubBook()
book.set_title(novel.title)
book.set_cover(novel.cover_image_url, requests.get(novel.cover_image_url).content)

chapters = novel.get_chapters()

volumes = defaultdict(list)
for i, chapter in enumerate(chapters):
    chapter.fill_content_and_parse()

    match = re.match(r"volume (\d+) chapter (\d+): (.+)", chapter.title, re.IGNORECASE)
    if match:
        volume_number, chapter_number, title = match.groups()
        volume_number, chapter_number = map(int, [volume_number, chapter_number])
        title_html = f"<h1>Chapter {chapter_number}: {title}</h1>"
        title = f"Chapter {chapter_number}: {title}"
        print(volume_number, chapter_number, title)
    else:
        volume_number = -1
        title = chapter.title
        title_html = f"<h1>{title}</h1>"
        print(volume_number, title)

    epub_chapter = epub.EpubHtml(title=title, file_name=f"chap_{i}.xhtml", lang="en")

    epub_chapter.content = (
        f"<html><head></head><body>{title_html}{chapter.content}</body></html>"
    )
    book.add_item(epub_chapter)
    volumes[volume_number].append(epub_chapter)

# Add default NCX and Nav files
book.add_item(epub.EpubNcx())
book.add_item(epub.EpubNav())

# Define the book's table of contents
book.toc = [
    (
        (epub.Section("Extra"), chapters)
        if volume_number == -1
        else (epub.Section(f"Volume {volume_number}"), chapters)
    )
    for volume_number, chapters in sorted(volumes.items())
]

# Define the EPUB's spine
book.spine = ["nav"] + [
    chapter for chapters in volumes.values() for chapter in chapters
]

# Write the EPUB to a file
invalid_chars = r'[<>:"/\\|?*]'
filename = re.sub(invalid_chars, "", novel.title + ".epub").replace(" ", "_")
epub.write_epub(filename, book)
