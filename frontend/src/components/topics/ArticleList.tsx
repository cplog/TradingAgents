import type { TopicArticle } from "../../api";

type Props = {
  articles: TopicArticle[];
};

export function ArticleList({ articles }: Props) {
  if (!articles.length) {
    return <p className="topics-empty">No articles in the latest run.</p>;
  }
  return (
    <ul className="topics-article-list">
      {articles.map((art) => (
        <li key={art.url} className="topics-article-list__item">
          <a href={art.url} target="_blank" rel="noopener noreferrer">
            {art.title}
          </a>
          {art.snippet ? <p className="topics-article-list__snippet">{art.snippet}</p> : null}
          {art.source ? (
            <span className="topics-article-list__source">{art.source}</span>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
