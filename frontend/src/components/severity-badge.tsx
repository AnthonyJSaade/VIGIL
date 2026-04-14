// SeverityBadge — small colored pill used on finding cards and the detail page.
//
// Falls back to the "info" style for any unknown severity value.

const SEVERITY_STYLES: Record<string, string> = {
  error: "bg-red-500/15 text-red-400 border-red-500/30",
  warning: "bg-yellow-500/15 text-yellow-400 border-yellow-500/30",
  info: "bg-blue-500/15 text-blue-400 border-blue-500/30",
};

export default function SeverityBadge({ severity }: { severity: string }) {
  const styles = SEVERITY_STYLES[severity] ?? SEVERITY_STYLES.info;
  return (
    <span
      className={`inline-flex rounded-md border px-2 py-0.5 text-xs font-semibold uppercase ${styles}`}
    >
      {severity}
    </span>
  );
}
