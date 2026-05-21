import { Link } from "react-router-dom";

export type BreadcrumbItem = {
  label: string;
  /** Omit on the last crumb (current page). */
  to?: string;
};

type AppBreadcrumbsProps = {
  items: BreadcrumbItem[];
  className?: string;
};

/**
 * Consistent in-page trail. Last item is current location (no link).
 */
export function AppBreadcrumbs({ items, className }: AppBreadcrumbsProps) {
  if (items.length === 0) return null;

  return (
    <nav
      aria-label="Breadcrumb"
      className={className ? `app-breadcrumbs ${className}` : "app-breadcrumbs"}
    >
      <ol className="app-breadcrumbs__list">
        {items.map((item, i) => {
          const isLast = i === items.length - 1;
          return (
            <li key={`${item.label}-${i}`} className="app-breadcrumbs__item">
              {i > 0 ? (
                <span className="app-breadcrumbs__sep" aria-hidden>
                  /
                </span>
              ) : null}
              {isLast || !item.to ? (
                <span
                  className="app-breadcrumbs__current"
                  aria-current={isLast ? "page" : undefined}
                >
                  {item.label}
                </span>
              ) : (
                <Link to={item.to} className="app-breadcrumbs__link">
                  {item.label}
                </Link>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
