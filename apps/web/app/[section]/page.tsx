import Workbench from "../workbench";
const sections = [
  "connections",
  "sources",
  "runs",
  "reconciliation",
  "journals",
  "intercompany",
  "currency",
  "exceptions",
  "history",
  "reports",
  "policies",
  "administration",
  "jobs",
];
export async function generateStaticParams() {
  return sections.map((section) => ({ section }));
}
export default async function Page({
  params,
}: {
  params: Promise<{ section: string }>;
}) {
  const { section } = await params;
  return <Workbench section={section} />;
}
