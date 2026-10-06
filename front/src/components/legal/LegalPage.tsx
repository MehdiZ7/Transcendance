import React from "react";
import { Card } from "@/components/ui/Card";
import { Heading } from "@/components/ui/Heading";

export interface LegalSection {
  title: string;
  body: React.ReactNode;
}

export interface LegalPageProps {
  title: string;
  updatedAt: string;
  sections: LegalSection[];
}

export function LegalPage({ title, updatedAt, sections }: LegalPageProps) {
  return (
    <main className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8">
      <header className="space-y-2">
        <Heading level={1}>{title}</Heading>
        <p className="text-xs text-slate-500">Dernière mise à jour : {updatedAt}</p>
      </header>

      <Card className="space-y-6">
        {sections.map((section) => (
          <section key={section.title} className="space-y-2">
            <h2 className="text-lg font-bold text-slate-800">{section.title}</h2>
            <div className="text-sm text-slate-600 leading-relaxed space-y-2">
              {section.body}
            </div>
          </section>
        ))}
      </Card>
    </main>
  );
}
