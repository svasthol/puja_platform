import { Header } from "@/components/layout/header";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export function ComingSoonPage({ title, sprint }: { title: string; sprint: string }) {
  return (
    <>
      <Header title={title} description={`Planned for ${sprint} — API endpoints not shipped yet.`} />
      <div className="p-8">
        <Card className="max-w-lg">
          <CardTitle className="flex items-center gap-2">
            Coming soon <Badge tone="warning">{sprint}</Badge>
          </CardTitle>
          <CardDescription>
            The admin shell navigation is wired; backend endpoints for this section land in the next
            Phase 4 sprint. See spec/plans/ADMIN.md.
          </CardDescription>
        </Card>
      </div>
    </>
  );
}
