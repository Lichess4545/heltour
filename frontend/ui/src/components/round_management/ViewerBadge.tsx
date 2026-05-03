import type { components } from "@litour/api-client";
import { ShieldCheck, User, UserX } from "lucide-react";

import { Badge } from "@/components/ui/badge";

type Viewer = components["schemas"]["ViewerDTO"];

interface Props {
  viewer: Viewer;
}

// Small visibility aid for the header — tells the viewer at a glance
// whether the API saw their Django session and what staff surfaces are
// available. Anonymous viewers see a quiet "anonymous" pill; logged-in
// non-staff see "signed in"; users with `change_pairing` see "staff".
export function ViewerBadge({ viewer }: Props) {
  if (!viewer.is_authenticated) {
    return (
      <Badge variant="outline" className="gap-1" title="No Django session">
        <UserX className="size-3" />
        <span className="hidden sm:inline">anonymous</span>
      </Badge>
    );
  }
  if (viewer.can_edit_pairings) {
    return (
      <Badge variant="default" className="gap-1" title="change_pairing permission resolved">
        <ShieldCheck className="size-3" />
        <span className="hidden sm:inline">staff</span>
      </Badge>
    );
  }
  return (
    <Badge variant="secondary" className="gap-1" title="Signed in (no change_pairing perm)">
      <User className="size-3" />
      <span className="hidden sm:inline">signed in</span>
    </Badge>
  );
}
