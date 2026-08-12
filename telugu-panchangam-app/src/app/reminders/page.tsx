import AncestorReminder from "@/components/AncestorReminder";
import RemindersHeader from "@/components/RemindersHeader";

export default function RemindersPage() {
  return (
    <main className="max-w-2xl mx-auto px-4 py-8">
      <RemindersHeader />
      <AncestorReminder />
    </main>
  );
}
