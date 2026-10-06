import type { Metadata } from 'next';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Heading } from '@/components/ui/Heading';

export const metadata: Metadata = {
  title: 'Navigateurs compatibles — LeBon42',
  description:
    'LeBon42 fonctionne sur Chrome, Firefox et Safari. Découvrez les navigateurs compatibles.',
};

const BROWSERS: { name: string; description: string; tested: string }[] = [
  {
    name: 'Chrome',
    description:
      'Google Chrome et les navigateurs basés sur Chromium (Microsoft Edge, Brave, Opera…).',
    tested: 'Chrome for Testing 153.0.8010.12',
  },
  {
    name: 'Firefox',
    description: 'Mozilla Firefox, sur ordinateur.',
    tested: 'Firefox 155.0',
  },
  {
    name: 'Safari',
    description: 'Safari sur Mac, iPhone et iPad.',
    tested: 'WebKit build 2359 (moteur de Safari)',
  },
];

const TIPS = [
  'Utilisez la dernière version de votre navigateur pour profiter de toutes les fonctionnalités.',
  'Le JavaScript et les cookies doivent être activés pour vous connecter.',
  'Sur un navigateur ancien, certaines pages peuvent ne pas s’afficher correctement.',
  'Safari est vérifié via son moteur WebKit : le rendu est très proche de l’application Safari.',
];

export default function BrowsersPage() {
  return (
    <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-10 space-y-8">
      <header className="space-y-3">
        <Heading level={1}>Navigateurs compatibles</Heading>
        <p className="text-sm text-slate-600 max-w-2xl leading-relaxed">
          LeBon42 fonctionne sur les navigateurs modernes. Nous testons le site sur Chrome, Firefox
          et Safari : les trois sont pleinement compatibles, pour une même expérience sur tous les
          appareils.
        </p>
      </header>

      <section className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {BROWSERS.map((browser) => (
          <Card key={browser.name} className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <Heading level={3}>{browser.name}</Heading>
              <Badge variant="success">Compatible</Badge>
            </div>
            <p className="text-sm text-slate-600 leading-relaxed">{browser.description}</p>
            <p className="text-xs text-slate-500">
              <span className="font-medium text-slate-600">Version testée :</span>{' '}
              {browser.tested}
            </p>
          </Card>
        ))}
      </section>

      <section className="space-y-4">
        <Heading level={2}>Bon à savoir</Heading>
        <Card>
          <ul className="list-disc space-y-2 pl-5 text-sm text-slate-600 leading-relaxed">
            {TIPS.map((tip) => (
              <li key={tip}>{tip}</li>
            ))}
          </ul>
        </Card>
      </section>
    </main>
  );
}
