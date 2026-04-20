#!/usr/bin/env python3
"""
Create a new book entry from ISBN13.

This script:
1. Queries book metadata using ISBN13
2. Creates markdown file in src/content/books/author/book.md
3. Downloads and saves cover image to public/img/author/book.jpg
"""

import os
import re
import sys
import urllib.request
import urllib.error
import json
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
from urllib.parse import quote


class BookAdder:
    def __init__(self, base_dir: str = "."):
        self.base_dir = Path(base_dir)
        self.books_dir = self.base_dir / "src" / "content" / "books"
        self.img_dir = self.base_dir / "public" / "img"
        
        self.books_dir.mkdir(parents=True, exist_ok=True)
        self.img_dir.mkdir(parents=True, exist_ok=True)

    def fetch_book_data(self, isbn13: str) -> Optional[Dict[str, Any]]:
        """
        Fetch book data from Open Library API.
        Returns dict with title, author, pages, publication_year, cover_id, etc.
        """
        isbn13 = isbn13.replace("-", "").strip()
        
        # Try Open Library ISBN API first
        try:
            url = f"https://openlibrary.org/isbn/{isbn13}.json"
            print(f"Querying: {url}")
            
            req = urllib.request.Request(url, headers={'User-Agent': 'BookAdder/1.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
                
                # Extract relevant data
                book_data = {
                    'title': data.get('title', '').strip(),
                    'isbn13': isbn13,
                    'pages': data.get('number_of_pages'),
                    'publication_year': data.get('publish_date', '')[:4] if data.get('publish_date') else None,
                    'publishers': data.get('publishers', []),
                    'cover_id': data.get('covers', [None])[0] if data.get('covers') else None,
                }
                
                # Extract author - try to get the actual name
                authors = data.get('authors', [])
                if authors:
                    author_key = authors[0].get('key')
                    if author_key:
                        # Try to fetch author details
                        author_name = self._fetch_author_name(author_key)
                        if author_name:
                            book_data['author'] = author_name
                        else:
                            # Fallback to key-based name
                            book_data['author'] = authors[0].get('name', 'Unknown Author')
                    else:
                        book_data['author'] = authors[0].get('name', 'Unknown Author')
                else:
                    book_data['author'] = 'Unknown Author'
                
                return book_data if book_data.get('title') and book_data.get('author') else None
        
        except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, Exception) as e:
            print(f"Error fetching from Open Library: {e}")
            return None

    def _fetch_author_name(self, author_key: str) -> Optional[str]:
        """
        Fetch author name from author key.
        """
        try:
            # author_key is like "/authors/OL27349A"
            if author_key.startswith('/'):
                author_key = author_key[1:]
            
            url = f"https://openlibrary.org/{author_key}.json"
            req = urllib.request.Request(url, headers={'User-Agent': 'BookAdder/1.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode('utf-8'))
                return data.get('name')
        except Exception:
            return None

    def get_cover_url(self, cover_id: Optional[int]) -> Optional[str]:
        """Get cover image URL from Open Library."""
        if not cover_id:
            return None
        return f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"

    def slugify(self, text: str) -> str:
        """Convert text to slug format (lowercase with hyphens)."""
        # Convert to lowercase
        text = text.lower().strip()
        # Replace common special characters
        text = re.sub(r"[&']", '', text)
        # Replace other non-alphanumeric with hyphen
        text = re.sub(r'[^\w\s-]', '', text)
        # Replace whitespace with hyphen
        text = re.sub(r'[-\s]+', '-', text)
        # Strip leading/trailing hyphens
        text = text.strip('-')
        return text

    def download_image(self, url: str, save_path: Path) -> bool:
        """Download image from URL to file."""
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'BookAdder/1.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                with open(save_path, 'wb') as f:
                    f.write(response.read())
            print(f"✓ Cover image saved: {save_path.relative_to(self.base_dir)}")
            return True
        except Exception as e:
            print(f"✗ Failed to download cover: {e}")
            return False

    def create_markdown(self, book_data: Dict[str, Any], author_slug: str, book_slug: str) -> str:
        """Create markdown content with YAML frontmatter."""
        author = book_data.get('author', 'Unknown Author')
        title = book_data.get('title', 'Unknown Title')
        isbn13 = book_data.get('isbn13', '')
        pages = book_data.get('pages')
        pub_year = book_data.get('publication_year')
        
        # Get today's date in YYYY-MM-DD format
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Build frontmatter
        fm_lines = [
            "book:",
            f"  author: {author}",
            f"  isbn13: '{isbn13}'",
            "  owned: false",
        ]
        
        if pages:
            fm_lines.append(f"  pages: {pages}")
        
        if pub_year:
            try:
                fm_lines.append(f"  publication_year: {int(pub_year)}")
            except (ValueError, TypeError):
                pass
        
        fm_lines.extend([
            f"  date_read:",
            f"    - {today}",
            "  rating:",
            "  tags: []",
            f"  title: '{title}'",
        ])
        
        frontmatter = '\n'.join(fm_lines) + '\n'
        
        content = f"---\n{frontmatter}---\n"
        
        return content

    def add_book(self, isbn13: str, author: Optional[str] = None, dry_run: bool = False) -> bool:
        """Add a new book from ISBN13."""
        print(f"\nLooking up ISBN: {isbn13}")
        
        # Fetch book data
        book_data = self.fetch_book_data(isbn13)
        if not book_data:
            print("✗ Could not find book data for this ISBN")
            return False
        
        # Use provided author if given, otherwise use fetched author
        if author:
            book_data['author'] = author
        
        if book_data['author'] == 'Unknown Author':
            print(f"⚠ Book found: {book_data['title']}, but author could not be determined")
            print("  Tip: Use --author to specify the author")
            return False
        
        print(f"✓ Found: {book_data['title']} by {book_data['author']}")
        
        # Create slugs
        author_slug = self.slugify(book_data['author'])
        book_slug = self.slugify(book_data['title'])
        
        print(f"  Author slug: {author_slug}")
        print(f"  Book slug: {book_slug}")
        
        # Create directories
        author_dir = self.books_dir / author_slug
        img_author_dir = self.img_dir / author_slug
        
        author_dir.mkdir(parents=True, exist_ok=True)
        img_author_dir.mkdir(parents=True, exist_ok=True)
        
        # Create markdown file
        md_path = author_dir / f"{book_slug}.md"
        if md_path.exists():
            print(f"✗ File already exists: {md_path.relative_to(self.base_dir)}")
            return False
        
        markdown_content = self.create_markdown(book_data, author_slug, book_slug)
        
        if dry_run:
            print(f"\n[DRY RUN] Would create: {md_path.relative_to(self.base_dir)}")
            print(f"\nFrontmatter:\n{markdown_content}")
        else:
            with open(md_path, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
            print(f"✓ Created: {md_path.relative_to(self.base_dir)}")
        
        # Download cover image
        cover_url = self.get_cover_url(book_data.get('cover_id'))
        if cover_url:
            img_path = img_author_dir / f"{book_slug}.jpg"
            if dry_run:
                print(f"[DRY RUN] Would download cover from: {cover_url}")
            else:
                self.download_image(cover_url, img_path)
        else:
            print("⚠ No cover image available for this book")
        
        return True


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Add a new book to the collection using ISBN13"
    )
    parser.add_argument(
        "isbn",
        help="ISBN13 (with or without hyphens)"
    )
    parser.add_argument(
        "--author",
        help="Author name (if not found automatically)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be created without making changes"
    )
    parser.add_argument(
        "--base-dir",
        default=".",
        help="Base directory of the project"
    )
    
    args = parser.parse_args()
    
    adder = BookAdder(base_dir=args.base_dir)
    success = adder.add_book(args.isbn, author=args.author, dry_run=args.dry_run)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
