# converter.py
import zipfile
import os
from bs4 import BeautifulSoup
from ebooklib import epub
import base64
import uuid
import logging

# Setup basic logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s: %(message)s')

def extract_cover_image(soup, epub_book):
    """Extracts the cover image from the FB2 XML soup and adds it to the EPUB book."""
    try:
        cover_image_tag = soup.find('binary', {'content-type': ['image/jpeg', 'image/jpg']})
        if cover_image_tag:
            cover_data = cover_image_tag.text.strip()
            cover_image_data = base64.b64decode(cover_data)
            epub_book.set_cover("cover.jpg", cover_image_data, create_page=True)
    except Exception as e:
        logging.warning(f"Failed to decode cover image: {e}")

def process_section_elements(section):
    """Processes the content elements within a section, formatting them appropriately for EPUB."""
    content = ''
    for element in section.find_all(['p', 'a', 'subtitle']):
        if element.name == 'p' and not element.find_parent('title'):
            p_text = process_paragraph(element)
            content += f'<p style="text-indent: 1em;">{p_text}</p>'
        elif element.name == 'a':
            a_href = element.get('l:href', 'href')
            a_text = element.get_text()
            content += f'<a href="{a_href}">{a_text}</a>'
        elif element.name == 'subtitle':
            content += f'<p style="text-indent: 1em;"><subtitle>{element.get_text()}</subtitle></p>'
    return content

def process_paragraph(paragraph):
    """Processes a paragraph, applying styling as necessary."""
    p_text = paragraph.get_text()
    if paragraph.find('emphasis'):
        p_text = f'<i>{p_text}</i>'
    elif paragraph.find('a'):
        p_text = '' 
    return p_text

def extract_metadata(soup):
    """Extracts metadata like title, authors, and annotations from the FB2 XML soup."""
    title_info = soup.find('title-info')
    title = 'Unknown Title'
    language = 'en'
    authors = []
    annotation = None

    if title_info:
        title_tag = title_info.find('book-title')
        title = title_tag.text if title_tag else title

        lang_tag = title_info.find('lang')
        language = lang_tag.text if lang_tag else language

        author_tags = title_info.find_all('author')
        authors = [' '.join(author.find(tag).text for tag in ['first-name', 'middle-name', 'last-name'] if author.find(tag)) for author in author_tags]

        annotation_tag = title_info.find('annotation')
        annotation = annotation_tag if annotation_tag else annotation

    return title, authors, annotation

def add_annotation_to_book(book, annotation_content):
    """Adds the book annotation as the first chapter of the EPUB book."""
    if annotation_content:
        processed_annotation = process_section_elements(annotation_content)
        annotation_content_with_title = f'<h1>Annotation</h1>{processed_annotation}'
        annotation_chapter = epub.EpubHtml(title='Annotation', file_name='annotation.xhtml', content=annotation_content_with_title, lang='en')
        book.add_item(annotation_chapter)
        book.spine.insert(0, annotation_chapter)
        return annotation_chapter

def create_epub_chapters(soup, epub_book):
    """Creates EPUB chapters from the FB2 content."""
    toc = []
    spine = ['nav']
    chapter_count = 0 

    for body in soup.find_all('body'):
        for section in body.find_all('section'):
            chapter_count += 1
            section_title = section.find('title').get_text(strip=True) if section.find('title') else f'Chapter {chapter_count}'
            content = process_section_elements(section)

            chapter_file_name = f'chapter_{chapter_count}.xhtml'
            epub_chapter = epub.EpubHtml(title=section_title, file_name=chapter_file_name, lang='en')
            epub_chapter.content = f'<h1>{section_title}</h1>{content}'
            epub_book.add_item(epub_chapter)
            spine.append(epub_chapter)
            toc.append(epub.Link(chapter_file_name, section_title, f'chapter_{chapter_count}'))

    epub_book.spine = spine
    return toc

def convert_fb2_to_epub(fb2_content, output_path):
    """Processes FB2 file content and converts it to an EPUB book object."""
    soup = BeautifulSoup(fb2_content, 'lxml-xml')
    book_title, authors, annotation_content = extract_metadata(soup)

    book = epub.EpubBook()
    book.set_identifier(str(uuid.uuid4()))
    book.set_title(book_title)
    book.set_language('en')
    for author in authors:
        book.add_author(author)

    extract_cover_image(soup, book)

    chapters_toc = create_epub_chapters(soup, book)
    for link in chapters_toc:
        book.toc.append(link)

    annotation_chapter = add_annotation_to_book(book, annotation_content)
    if annotation_chapter:
        book.toc.insert(0, epub.Link(annotation_chapter.file_name, annotation_chapter.title, 'annotation'))
        book.spine.insert(0, annotation_chapter)

    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    epub.write_epub(output_path, book, {})

def convert_file(fb2_path):
    """Converts a single FB2 file to an EPUB file."""
    try:
        if not os.path.exists(fb2_path):
            raise FileNotFoundError("FB2 file does not exist")

        with open(fb2_path, 'rb') as fb2_file:
            fb2_content = fb2_file.read()

        base_name = os.path.splitext(os.path.basename(fb2_path))[0]
        output_path = f'{base_name}.epub'
        convert_fb2_to_epub(fb2_content, output_path)
        logging.info(f'Created EPUB book: {output_path}')

    except Exception as e:
        logging.error(f"Failed to convert FB2 to EPUB: {e}")

    return output_path

def convert_archive(zip_path):
    """Converts all FB2 files within a ZIP archive to EPUB format."""
    epub_files = []
    try:
        if not os.path.exists(zip_path):
            raise FileNotFoundError("ZIP file does not exist")

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            fb2_files = [f for f in zip_ref.namelist() if f.endswith('.fb2')]
            if not fb2_files:
                raise ValueError("No FB2 files found in the ZIP archive")

            for fb2_file_name in fb2_files:
                fb2_content = zip_ref.read(fb2_file_name)
                base_name = os.path.splitext(fb2_file_name)[0]
                output_path = f'{base_name}.epub'
                convert_fb2_to_epub(fb2_content, output_path)
                logging.info(f'Created EPUB book: {output_path}')
                epub_files.append(output_path)

    except Exception as e:
        logging.error(f"Failed to convert FB2 archive to EPUB: {e}")

    return epub_files

# convert_archive('your_file.fb2.zip')
# convert_archive('Compress.zip')
# convert_file('04_pozhirateli_mirov_4_tom.fb2')