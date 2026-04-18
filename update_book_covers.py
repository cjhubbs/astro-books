#!/usr/bin/env python3
"""
Update book cover images for the astro-books project.

This script:
1. Iterates through all book markdown files in src/content/books
2. Checks if the cover image exists in public/img and is >= 500px tall
3. If missing or too small, searches online for a larger cover using ISBN
4. Downloads and saves the image to the appropriate location
"""

import os
import sys
import re
import yaml
import requests
from pathlib import Path
from PIL import Image
from io import BytesIO
import time

# Configuration
BASE_DIR = Path(__file__).parent
BOOKS_DIR = BASE_DIR / "src" / "content" / "books"
IMG_DIR = BASE_DIR / "public" / "img"
MIN_HEIGHT = 400

# Request headers to avoid blocks
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def extract_frontmatter(file_path):
    """Extract YAML frontmatter from a markdown file."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        # Parse frontmatter
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter_text = parts[1]
                frontmatter = yaml.safe_load(frontmatter_text)
                return frontmatter.get("book", {})
    except Exception as e:
        print(f"Error parsing {file_path}: {e}")
    
    return {}


def get_image_height(image_path):
    """Get the height of an image file in pixels. Returns None if file doesn't exist."""
    try:
        if not image_path.exists():
            return None
        img = Image.open(image_path)
        return img.height
    except Exception as e:
        print(f"Error reading image {image_path}: {e}")
        return None


def search_book_cover_google_books(isbn, title, author):
    """Search for a book cover using Google Books API."""
    try:
        # Try with ISBN first
        if isbn:
            url = f"https://www.googleapis.com/books/v1/volumes"
            params = {"q": f"isbn:{isbn}", "maxResults": 1}
            response = SESSION.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("items"):
                    item = data["items"][0]
                    volume_info = item.get("volumeInfo", {})
                    image_links = volume_info.get("imageLinks", {})
                    if "thumbnail" in image_links:
                        # Get the large version
                        large_url = image_links["thumbnail"].replace("&edge=curl", "")
                        return large_url
    except Exception as e:
        print(f"Google Books search failed: {e}")
    
    return None


def normalize_isbn(isbn):
    """Normalize an ISBN to digits plus an optional trailing X."""
    if not isbn:
        return None

    normalized = re.sub(r"[^0-9Xx]", "", str(isbn)).upper()
    return normalized or None


def lookup_openlibrary_olid(isbn):
    """Look up an Open Library edition OLID from an ISBN via the book JSON endpoint."""
    normalized_isbn = normalize_isbn(isbn)
    if not normalized_isbn:
        return None

    lookup_urls = [
        f"https://openlibrary.org/isbn/{normalized_isbn}.json",
        (
            "https://openlibrary.org/api/books"
            f"?bibkeys=ISBN:{normalized_isbn}&format=json&jscmd=data"
        ),
    ]

    for url in lookup_urls:
        try:
            response = SESSION.get(url, timeout=10)
            if response.status_code != 200:
                continue

            data = response.json()

            if isinstance(data, dict):
                key = data.get("key")
                if isinstance(key, str) and key.startswith("/books/"):
                    return key.split("/")[-1]

                item = data.get(f"ISBN:{normalized_isbn}")
                if isinstance(item, dict):
                    identifiers = item.get("identifiers", {})
                    olids = identifiers.get("openlibrary", [])
                    if olids:
                        return olids[0]

                    url_value = item.get("url", "")
                    match = re.search(r"/books/(OL[^/]+M)", url_value)
                    if match:
                        return match.group(1)
        except Exception as e:
            print(f"OpenLibrary OLID lookup failed for ISBN {normalized_isbn}: {e}")

    return None


def search_book_cover_openlibrary(isbn, title, author):
    """Search for a book cover using OpenLibrary OLIDs to avoid ISBN rate limits."""
    try:
        olid = lookup_openlibrary_olid(isbn)
        if not olid:
            return None

        url = f"https://covers.openlibrary.org/b/olid/{olid}-L.jpg?default=false"
        response = SESSION.head(url, timeout=10, allow_redirects=True)

        if response.status_code == 200:
            return url
    except Exception as e:
        print(f"OpenLibrary search failed: {e}")

    return None


def download_image(image_url, file_path):
    """Download an image from a URL and save it to a file."""
    try:
        response = SESSION.get(image_url, timeout=15)
        response.raise_for_status()
        
        # Verify it's a valid image
        img = Image.open(BytesIO(response.content))
        
        # Save the image
        file_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(file_path, "JPEG", quality=95)
        
        return True, img.height
    except Exception as e:
        print(f"Error downloading image from {image_url}: {e}")
        return False, None


def title_to_slug(title):
    """Convert a book title to a slug for use in filenames."""
    # Convert to lowercase and replace spaces with hyphens
    slug = title.lower()
    # Replace spaces and other special chars with hyphens
    slug = re.sub(r"[^\w\-]", "-", slug)
    # Remove multiple consecutive hyphens
    slug = re.sub(r"-+", "-", slug)
    # Remove leading/trailing hyphens
    slug = slug.strip("-")
    return slug


def process_book(book_path, author_slug):
    """Process a single book file and update its cover if needed."""
    book_data = extract_frontmatter(book_path)
    
    if not book_data:
        return None
    
    title = book_data.get("title")
    isbn = book_data.get("isbn13") or book_data.get("isbn10")
    author = book_data.get("author")
    
    if not title:
        print(f"⚠️  No title found in {book_path}")
        return None
    
    # Determine the expected image path
    title_slug = title_to_slug(title)
    image_path = IMG_DIR / author_slug / f"{title_slug}.jpg"
    
    # Check current image
    height = get_image_height(image_path)
    
    if height and height >= MIN_HEIGHT:
        #print(f"✓ {title} ({author_slug}): Image exists and is {height}px tall")
        return {"status": "ok", "height": height}
    
    # Image is missing or too small, search for a better one
    if height:
        print(f"⚠️  {title} ({author_slug}): Image is only {height}px tall, searching for larger...")
    else:
        print(f"🔍 {title} ({author_slug}): Image ({image_path} missing, searching...")
    
    if not isbn:
        print(f"❌ {title}: No ISBN available, cannot search")
        return {"status": "no_isbn"}
    
    # Try multiple sources
    image_url = None
    
    # # Try OpenLibrary first (usually has consistent URLs)
    image_url = search_book_cover_openlibrary(isbn, title, author)
    if not image_url:
        # Fall back to Google Books
        image_url = search_book_cover_google_books(isbn, title, author)
    
    if not image_url:
        print(f"❌ {title}: Could not find cover image online (ISBN: {isbn})")
        return {"status": "not_found"}
    
    # Download the image
    print(f"⬇️  {title}: Downloading from {image_url[:60]}...")
    success, new_height = download_image(image_url, image_path)
    
    if success:
        print(f"✅ {title}: Downloaded image ({new_height}px tall)")
        return {"status": "updated", "height": new_height, "url": image_url}
    else:
        print(f"❌ {title}: Failed to download image")
        return {"status": "download_failed"}


def main():
    """Main entry point."""
    print("🚀 Starting book cover update process...\n")
    
    if not BOOKS_DIR.exists():
        print(f"❌ Books directory not found: {BOOKS_DIR}")
        sys.exit(1)
    
    results = {
        "ok": 0,
        "updated": 0,
        "not_found": 0,
        "no_isbn": 0,
        "download_failed": 0,
        "error": 0,
    }
    
    # Iterate through author directories
    for author_dir in sorted(BOOKS_DIR.iterdir()):
        if not author_dir.is_dir():
            continue
        
        author_slug = author_dir.name
        book_files = list(author_dir.glob("*.md"))
        
        if not book_files:
            continue
        
        print(f"\n📚 {author_slug}/ ({len(book_files)} books)")
        
        for book_path in sorted(book_files):
            result = process_book(book_path, author_slug)
            if result:
                status = result.get("status", "error")
                results[status] = results.get(status, 0) + 1
            else:
                results["error"] += 1
            
            # Add a small delay to be respectful to API servers
            time.sleep(0.5)
    
    # Print summary
    print("\n" + "=" * 50)
    print("📊 Summary:")
    print(f"  ✓ OK (no action needed): {results['ok']}")
    print(f"  ✅ Updated: {results['updated']}")
    print(f"  ❌ Not found: {results['not_found']}")
    print(f"  ⚠️  No ISBN: {results['no_isbn']}")
    print(f"  ❌ Download failed: {results['download_failed']}")
    print(f"  ⚠️  Errors: {results['error']}")
    print("=" * 50)


if __name__ == "__main__":
    main()
