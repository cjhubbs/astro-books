#!/usr/bin/env python3
"""
Migrate reviews from reviews/ folder to src/content/books/ with schema sanitization.
"""

import os
import re
import shutil
from pathlib import Path
from typing import Tuple


class ReviewMigrator:
    def __init__(self, base_dir: str = "."):
        self.base_dir = Path(base_dir)
        self.reviews_dir = self.base_dir / "reviews"
        self.books_dir = self.base_dir / "src" / "content" / "books"
        self.img_dir = self.base_dir / "public" / "img"
        
        self.books_dir.mkdir(parents=True, exist_ok=True)
        self.img_dir.mkdir(parents=True, exist_ok=True)
        
        self.migrated_count = 0
        self.skipped_count = 0
        self.errors = []

    def extract_frontmatter_and_body(self, content: str) -> Tuple[str, str]:
        """Extract YAML frontmatter and markdown body."""
        match = re.match(r'^---\n(.*?)\n---\n(.*)', content, re.DOTALL)
        if not match:
            raise ValueError("File does not contain valid frontmatter")
        return match.group(1), match.group(2)

    def sanitize_frontmatter(self, fm_text: str) -> str:
        """
        Sanitize frontmatter from old schema to new schema.
        """
        lines = fm_text.split('\n')
        
        # First pass: find sections to skip/extract
        skip_indices = set()
        date_read_lines = []
        rating_line = ""
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # Skip spine_color lines
            if 'spine_color:' in line:
                skip_indices.add(i)
                i += 1
                continue
            
            # Skip plan section entirely
            if line.strip() == 'plan:':
                skip_indices.add(i)
                i += 1
                # Skip all indented lines after plan:
                while i < len(lines) and lines[i].startswith('  '):
                    skip_indices.add(i)
                    i += 1
                continue
            
            # Extract and skip review section
            if line.strip() == 'review:':
                skip_indices.add(i)
                i += 1
                # Process review section
                while i < len(lines) and lines[i].startswith('  '):
                    review_line = lines[i]
                    skip_indices.add(i)
                    
                    if 'date_read:' in review_line:
                        date_read_lines.append(review_line)
                        i += 1
                        # Collect all date items (lines starting with "  - ")
                        while i < len(lines) and (lines[i].startswith('  - ') or lines[i].startswith('    - ')):
                            date_read_lines.append(lines[i])
                            skip_indices.add(i)
                            i += 1
                        i -= 1  # Back up one since loop will increment
                    elif 'rating:' in review_line:
                        rating_line = review_line
                    
                    i += 1
                continue
            
            i += 1
        
        # Second pass: build result with transformations
        result = []
        for i, line in enumerate(lines):
            if i in skip_indices:
                continue
            
            # Convert owned values
            if 'owned:' in line:
                val = line.split(':', 1)[1].strip()
                if val == '' or val.lower() in ("''", '""'):
                    line = re.sub(r'owned:.*', 'owned: false', line)
                elif val.lower() in ('true', "'true'", '"true"'):
                    line = re.sub(r'owned:.*', 'owned: true', line)
                elif val.lower() in ('false', "'false'", '"false"'):
                    line = re.sub(r'owned:.*', 'owned: false', line)
            
            # Convert pages from quoted to unquoted
            if 'pages:' in line:
                line = re.sub(r"pages:\s*['\"]?(\d+)['\"]?", r'pages: \1', line)
            
            # Convert publication_year from quoted to unquoted
            if 'publication_year:' in line:
                line = re.sub(r"publication_year:\s*['\"]?(\d+)['\"]?", r'publication_year: \1', line)
            
            # Skip empty series
            if 'series:' in line and 'series_position' not in line:
                val = line.split(':', 1)[1].strip()
                if val in ("''", '""'):
                    continue
            
            # Skip empty series_position
            if 'series_position:' in line:
                val = line.split(':', 1)[1].strip()
                if val in ("''", '""'):
                    continue
                line = re.sub(r"series_position:\s*['\"]?(\d+)['\"]?", r'series_position: \1', line)
            
            # Convert tags to array
            if 'tags:' in line:
                val = line.split(':', 1)[1].strip()
                if val in ("''", '""', ''):
                    line = re.sub(r'tags:.*', 'tags: []', line)
            
            result.append(line)
        
        # Build final output
        output = '\n'.join(result).rstrip()
        
        # Add date_read and rating
        if date_read_lines:
            output += '\n' + '\n'.join(date_read_lines)
        if rating_line:
            output += '\n' + rating_line
        
        return output + '\n'

    def migrate_file(self, review_file: Path, author_dir: str, book_dir_name: str) -> bool:
        """Migrate a single review file."""
        try:
            with open(review_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            frontmatter_text, markdown_content = self.extract_frontmatter_and_body(content)
            sanitized_frontmatter = self.sanitize_frontmatter(frontmatter_text)
            
            new_filename = f"{book_dir_name}.md"
            author_books_dir = self.books_dir / author_dir
            author_books_dir.mkdir(parents=True, exist_ok=True)
            
            new_file_path = author_books_dir / new_filename
            new_content = f"---\n{sanitized_frontmatter}---\n{markdown_content}"
            
            with open(new_file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            # Handle cover image
            review_dir = review_file.parent
            cover_src = review_dir / "cover.jpg"
            
            if cover_src.exists():
                author_img_dir = self.img_dir / author_dir
                author_img_dir.mkdir(parents=True, exist_ok=True)
                cover_dst = author_img_dir / f"{book_dir_name}.jpg"
                shutil.copy2(cover_src, cover_dst)
                print(f"  ✓ Cover: {cover_dst.relative_to(self.base_dir)}")
            
            print(f"✓ {new_file_path.relative_to(self.base_dir)}")
            self.migrated_count += 1
            return True
            
        except Exception as e:
            error_msg = f"✗ {review_file.relative_to(self.base_dir)}: {str(e)}"
            print(error_msg)
            self.errors.append(error_msg)
            self.skipped_count += 1
            return False

    def migrate_all(self, dry_run: bool = False) -> None:
        """Migrate all review files."""
        if not self.reviews_dir.exists():
            print(f"Error: Reviews directory not found")
            return
        
        print(f"Starting migration...")
        if dry_run:
            print("[DRY RUN MODE]\n")
        
        review_files = sorted(self.reviews_dir.glob("*/*/index.md"))
        
        if not review_files:
            print("No review files found!")
            return
        
        print(f"Found {len(review_files)} review files\n")
        
        for i, review_file in enumerate(review_files, 1):
            parts = review_file.parts
            author_dir = parts[-3]
            book_dir = parts[-2]
            
            if not dry_run:
                self.migrate_file(review_file, author_dir, book_dir)
            
            if i % 100 == 0:
                print(f"  ... processed {i} files")
        
        print("\n" + "="*70)
        print(f"✓ Successfully migrated: {self.migrated_count}")
        print(f"✗ Skipped/Failed: {self.skipped_count}")
        
        if self.errors:
            print("\nFirst 10 errors:")
            for error in self.errors[:10]:
                print(f"  {error}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Migrate reviews to books collection")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--base-dir", default=".")
    
    args = parser.parse_args()
    
    migrator = ReviewMigrator(base_dir=args.base_dir)
    migrator.migrate_all(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
