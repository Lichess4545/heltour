import { Badge } from "@/components/ui/badge";

interface Props {
  isCaptain: boolean;
}

export function CaptainBadge({ isCaptain }: Props) {
  if (!isCaptain) return null;
  return (
    <Badge
      variant="outline"
      title="Team captain"
      className="h-4 min-w-4 border-amber-300 bg-amber-100 px-1 font-mono text-[10px] leading-none font-semibold text-amber-900 dark:border-amber-900 dark:bg-amber-950/60 dark:text-amber-200"
    >
      C
    </Badge>
  );
}
