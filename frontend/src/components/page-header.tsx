export function PageHeader({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-4 border-b border-subtle bg-surface px-4 py-6 sm:flex-row sm:items-center sm:justify-between sm:px-6 lg:px-8">
      <div>
        <p className="mb-1 text-[10px] font-bold uppercase tracking-[0.16em] text-primary">
          Administração
        </p>
        <h1 className="text-xl font-bold tracking-tight text-fg">{title}</h1>
        <p className="mt-1 text-xs text-muted">{description}</p>
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}
