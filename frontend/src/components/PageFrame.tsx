import type { ReactNode } from "react";

export function PageFrame({
  children,
  className = "",
  wide = false,
}: {
  children: ReactNode;
  className?: string;
  wide?: boolean;
}) {
  return (
    <div className={`page-frame${wide ? " page-frame--wide" : ""}${className ? ` ${className}` : ""}`}>
      {children}
    </div>
  );
}

export function PageHeader({
  title,
  description,
  meta,
  actions,
}: {
  title: string;
  description?: string;
  meta?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div className="page-header__main">
        <h1 className="page-header__title">{title}</h1>
        {description && <p className="page-header__desc">{description}</p>}
        {meta && <div className="page-header__meta">{meta}</div>}
      </div>
      {actions && <div className="page-header__actions">{actions}</div>}
    </header>
  );
}

export function Panel({
  children,
  className = "",
  title,
  subtitle,
  id,
}: {
  children: ReactNode;
  className?: string;
  title?: string;
  subtitle?: string;
  id?: string;
}) {
  return (
    <section id={id} className={`panel${className ? ` ${className}` : ""}`}>
      {(title || subtitle) && (
        <header className="panel__header">
          {title && <h2 className="panel__title">{title}</h2>}
          {subtitle && <p className="panel__subtitle">{subtitle}</p>}
        </header>
      )}
      <div className="panel__body">{children}</div>
    </section>
  );
}
