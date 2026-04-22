import rss from "@astrojs/rss";
import { getCollection } from "astro:content";

function getLatestReadDate(book: Awaited<ReturnType<typeof getCollection<"books">>>[number]) {
  const dates = book.data.book.date_read ?? [];
  if (dates.length > 0) {
    return dates[dates.length - 1];
  }

  if (book.data.book.publication_year) {
    return new Date(book.data.book.publication_year, 0, 1);
  }

  return new Date(0);
}

export async function GET(context: { site: URL | undefined }) {
  const books = await getCollection("books");
  const items = books
    .sort((left, right) => getLatestReadDate(right).getTime() - getLatestReadDate(left).getTime())
    .map((book) => ({
      title: `${book.data.book.title} by ${book.data.book.author}`,
      description: book.body?.trim() || `A new booklog entry for ${book.data.book.title}.`,
      pubDate: getLatestReadDate(book),
      link: `/books/${book.id.replace(".md", "")}`,
    }));

  return rss({
    title: "Chris Hubbs' Booklog",
    description: "Recent additions and reviews from Chris Hubbs' book collection.",
    site: context.site,
    items,
    customData: "<language>en-us</language>",
  });
}