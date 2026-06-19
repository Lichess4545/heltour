import { Badge } from "@/components/ui/badge";

interface Props {
  gender: string | null;
}

const TITLES: Record<string, string> = {
  male: "Male",
  female: "Female",
  "non-binary": "Non-binary",
  "not-represented": "My gender is not represented",
  "prefer-not-disclose": "Prefer not to disclose",
};

// Tone classes layered on top of shadcn Badge variant="outline". Kept in
// component-local CSS rather than the global theme because gender colors
// are domain-specific (chess league display preference), not a brand role.
const TONE: Record<string, string> = {
  male: "bg-sky-100 text-sky-900 border-sky-200 dark:bg-sky-950/60 dark:text-sky-200 dark:border-sky-900",
  female:
    "bg-pink-100 text-pink-900 border-pink-200 dark:bg-pink-950/60 dark:text-pink-200 dark:border-pink-900",
  "non-binary":
    "bg-violet-100 text-violet-900 border-violet-200 dark:bg-violet-950/60 dark:text-violet-200 dark:border-violet-900",
};

// Single-letter gender pill matching the legacy `gender_badge` template tag.
// Renders nothing when the player has no gender set, so callers can drop it
// into any layout unconditionally.
export function GenderBadge({ gender }: Props) {
  if (!gender) return null;
  const letter = gender.charAt(0).toUpperCase();
  const title = TITLES[gender] ?? gender;
  const tone = TONE[gender];
  return (
    <Badge
      variant="outline"
      title={title}
      className={`h-4 min-w-4 px-1 font-mono text-[10px] leading-none font-semibold ${tone ?? ""}`}
    >
      {letter}
    </Badge>
  );
}
