import { defineCollection } from 'astro:content';
import { glob, file } from 'astro/loaders';
import { z } from 'astro/zod';

// Helper to handle empty strings and null as optional values
const emptyOrNullToUndefined = (val: unknown) => val === '' || val === null ? undefined : val;

const books = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/books' }),
  schema: z.object({
    book: z.object({
      title: z.string(),
      author: z.string(),
      cover_image_url: z.string().optional(),
      goodreads: z.string().optional(),
      isbn13: z.string().optional(),
      isbn9: z.string().optional(),
      owned: z.boolean().optional(),
      pages: z.coerce.number().optional(),
      publication_year: z.coerce.number().optional(),
      series: z.string().optional(),
      series_position: z.coerce.number().optional(),
      tags: z.array(z.string()).optional(),
      date_read: z.array(z.coerce.date()).optional().default([]),
      rating: z.number().min(1).max(5).optional(),
    }),
  })
});

export const collections = { books };
